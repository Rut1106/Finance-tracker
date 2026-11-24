"""
Splitwise auto-sync.

Pulls expenses dated on/after your fresh-start date and turns each into a
ledger row, waiting in the Inbox for one-tap confirmation.

Uses the general Splitwise math, so it handles any split:
  paid  = what you paid in cash   -> leaves your spending account
  owed  = your share              -> counts as your spending
  paid - owed                     -> change in Account 4 (Splitwise)

Settle-ups ("payments") become transfers between Account 1 and Account 4.

If a "you paid" split matches an Apple Pay purchase already logged
(same amount, within 3 days), that purchase is upgraded to a split
instead of being counted twice.
"""

import os
import re
from datetime import datetime

import requests

from ledger import SPEND_ACC, SPLIT_ACC, f, parse_date

API = "https://secure.splitwise.com/api/v3.0"

SW_CATEGORY = {
    "groceries": "Groceries", "dining out": "Food", "food and drink": "Food", "liquor": "Food",
    "movies": "Entertainment", "music": "Entertainment", "games": "Entertainment",
    "sports": "Entertainment", "entertainment": "Entertainment",
    "clothing": "Shopping", "electronics": "Shopping", "household supplies": "Shopping",
    "furniture": "Shopping", "gifts": "Shopping",
    "gas/fuel": "Transportation", "parking": "Transportation", "taxi": "Transportation",
    "bus/train": "Transportation", "car": "Transportation",
    "plane": "Travel", "hotel": "Travel",
    "rent": "Rent", "mortgage": "Rent",
    "electricity": "Bills", "heat/gas": "Bills", "tv/phone/internet": "Bills", "water": "Bills",
    "trash": "Bills", "utilities": "Bills", "insurance": "Bills",
    "medical expenses": "Health", "education": "Education",
}


def enabled():
    return bool(os.environ.get("SPLITWISE_TOKEN", "").strip())


def _token():
    """Accept the key even if it was pasted with quotes, spaces or a 'Bearer ' prefix."""
    t = os.environ.get("SPLITWISE_TOKEN", "").strip().strip('"').strip("'").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t


def _get(path, **params):
    r = requests.get(
        f"{API}/{path}",
        headers={"Authorization": f"Bearer {_token()}",
                 "Accept": "application/json",
                 # Splitwise's firewall blocks the default "python-requests" agent
                 "User-Agent": "Mozilla/5.0 (compatible; RutFinance/2.0; personal finance tracker)"},
        params=params, timeout=20)
    if r.status_code == 401:
        raise RuntimeError("Splitwise says the key is wrong (401). Generate a new API key "
                           "and paste only the key into SPLITWISE_TOKEN on Render.")
    if r.status_code == 403:
        body = " ".join(r.text.split())[:90]
        if "cloudflare" in r.text.lower() or "<html" in r.text.lower():
            raise RuntimeError("Splitwise's firewall blocked the server (403). "
                               f"Details: {body}")
        raise RuntimeError(f"Splitwise refused the key (403): {body}")
    r.raise_for_status()
    return r.json()


def fetch(start_date):
    me = _get("get_current_user")["user"]["id"]
    expenses = _get("get_expenses", dated_after=f"{start_date}T00:00:00Z", limit=200)["expenses"]
    return me, expenses


def to_rows(me, expenses, new_id, now_iso):
    rows = []
    for e in expenses:
        if e.get("deleted_at"):
            continue
        mine = next((u for u in e.get("users", []) if u.get("user_id") == me), None)
        if not mine:
            continue
        paid, owed = f(mine.get("paid_share")), f(mine.get("owed_share"))
        if not paid and not owed:
            continue
        try:
            day = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).date().isoformat()
        except Exception:
            day = now_iso[:10]
        base = {"id": new_id(), "created": now_iso, "date": day, "merchant": "",
                "source": "splitwise", "status": "inbox", "ext_id": f"sw{e['id']}",
                "your_share": "", "total": f"{f(e.get('cost')):.2f}", "to_account": ""}
        desc = (e.get("description") or "Splitwise").strip()[:120]
        if e.get("payment"):
            if paid:   # you paid a friend back
                rows.append({**base, "kind": "transfer", "amount": f"{paid:.2f}", "account": SPEND_ACC,
                             "to_account": SPLIT_ACC, "category": "",
                             "note": f"Splitwise settle-up (paid): {desc}"})
            else:      # a friend paid you back
                rows.append({**base, "kind": "transfer", "amount": f"{owed:.2f}", "account": SPLIT_ACC,
                             "to_account": SPEND_ACC, "category": "",
                             "note": f"Splitwise settle-up (received): {desc}"})
            continue
        cat_name = ((e.get("category") or {}).get("name") or "").lower()
        rows.append({**base, "kind": "split", "amount": f"{paid:.2f}",
                     "your_share": f"{owed:.2f}", "account": SPEND_ACC,
                     "category": SW_CATEGORY.get(cat_name, "Other"), "note": desc})
    return rows


def stage(store, rows):
    """Add rows to the Inbox, skipping duplicates. A 'you paid' split that matches an
    Apple Pay purchase (same amount, within 3 days) upgrades that purchase instead.
    Returns (imported, merged)."""
    ledger = store.rows("ledger")
    seen = {r["ext_id"] for r in ledger if r["ext_id"]}
    imported = merged = 0
    fresh = []
    for row in rows:
        if row["ext_id"] in seen:
            continue
        seen.add(row["ext_id"])
        twin = None
        if row["kind"] == "split" and f(row["amount"]) > 0:
            d = parse_date(row["date"])
            for r in ledger:
                rd = parse_date(r["date"])
                if (r["kind"] == "expense" and not r["ext_id"] and rd and d
                        and abs((rd - d).days) <= 3
                        and abs(f(r["amount"]) - f(row["amount"])) < 0.01):
                    twin = r
                    break
        if twin:
            store.update("ledger", dict(twin, kind="split", your_share=row["your_share"],
                                        total=row["total"], ext_id=row["ext_id"],
                                        note=twin["note"] or row["note"]))
            ledger = store.rows("ledger")
            merged += 1
        else:
            fresh.append(row)
            imported += 1
    if fresh:
        store.append("ledger", None, rows=fresh)
    return imported, merged


def sync(store, start_date, new_id, now_iso):
    """API sync (needs Splitwise Pro). Returns (imported, merged). Raises on API errors."""
    me, expenses = fetch(start_date)
    return stage(store, to_rows(me, expenses, new_id, now_iso))


# ------------------------------------------------------------------ email bridge
# Free alternative to the API: Splitwise emails are forwarded to a bot Gmail, and a
# Google Apps Script there posts each one to /api/splitwise-email.

MONEY = r"(?:USD|US\$|\$)\s?([\d,]+(?:\.\d{1,2})?)"
SKIP_WORDS = ("deleted", "updated", "commented", "password", "login", "balance for",
              "added you to", "invited", "privacy", "welcome", "reminder", "action required",
              "restored", "subscription", "receipt")


def _amt(pattern, text):
    m = re.search(pattern, text, re.I)
    return f(m.group(m.lastindex)) if m else None


def parse_email(subject, body):
    """Return ("skip", None) | ("unparsed", None) | ("ok", partial_row)."""
    subject = " ".join(str(subject or "").split())
    text = " ".join(f"{subject} . {body or ''}".split())
    low = subject.lower()

    # Settle-ups: "Rakhi Waykole paid you USD68.65 on Splitwise"
    m = re.search(r"^(.+?) paid you " + MONEY, subject, re.I)
    if m:
        return "ok", {"kind": "transfer", "amount": f(m.group(2)), "account": SPLIT_ACC,
                      "to_account": SPEND_ACC, "category": "",
                      "note": f"{m.group(1).strip()} paid you back"}
    m = re.search(r"^you paid (.+?) " + MONEY, subject, re.I)
    if m:
        return "ok", {"kind": "transfer", "amount": f(m.group(2)), "account": SPEND_ACC,
                      "to_account": SPLIT_ACC, "category": "",
                      "note": f"You paid {m.group(1).strip()} back"}

    if any(w in low for w in SKIP_WORDS):
        return "skip", None

    # New expense: description is usually quoted in the subject
    q = re.search(r"[\"\u201c\u2018']([^\"\u201d\u2019']{1,80})[\"\u201d\u2019']", subject)
    desc = (q.group(1) if q else re.sub(r"(?i)\s*on splitwise$", "", subject))[:100].strip()
    total = _amt(r"\b(?:total|cost)\b[^\d$]{0,12}" + MONEY, text)
    owe = _amt(r"\byou owe\b[^\d$]{0,40}?" + MONEY, text)
    back = _amt(r"\byou (?:get back|are owed|lent)\b[^\d$]{0,40}?" + MONEY, text)
    if owe:                     # someone else paid, your share = what you owe
        return "ok", {"kind": "split", "amount": 0.0, "your_share": owe,
                      "total": total or "", "note": desc or "Splitwise", "account": SPEND_ACC}
    if back and total:          # you paid the total, friends owe you `back`
        return "ok", {"kind": "split", "amount": total, "your_share": round(total - back, 2),
                      "total": total, "note": desc or "Splitwise", "account": SPEND_ACC}
    if "payment" in text.lower() or "you are not involved" in text.lower():
        return "skip", None
    return "unparsed", None
