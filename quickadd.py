"""
One-line quick add. Examples:

  uber 18                     expense $18 from Account 1, category guessed
  18 lunch #food              '#' forces a category
  amazon 42 @2                '@2' pays from Account 2
  coffee 5 yesterday          dates: yesterday, today, 11/14
  +2000 salary                income into Account 3
  move 500                    transfer Account 3 -> Account 1
  move 200 1>2                transfer Account 1 -> Account 2
  split pizza 40 20           you paid 40, your share 20
  split pizza 40              your share defaults to half
  split dinner 60 20 they     someone else paid 60, your share 20
  settle 40                   friend paid you back (Account 4 -> Account 1)
  settle out 40               you paid a friend back (Account 1 -> Account 4)
"""

import re
from datetime import timedelta

from ledger import (ACCOUNTS, EXPENSE_CATS, INCOME_ACC, INCOME_CATS, SPEND_ACC,
                    SPLIT_ACC, f, guess_category)

NUM = re.compile(r"^[+-]?\$?\d[\d,]*(\.\d+)?$")
ARROW = re.compile(r"^([1-4])\s*(?:>|->|to)\s*([1-4])$")
MDY = re.compile(r"^(\d{1,2})/(\d{1,2})$")


def _acc(n):
    return ACCOUNTS[int(n) - 1]


def parse(text, rules, today):
    raw = " ".join(str(text or "").split())
    if not raw:
        return {"error": "Type something like: uber 18"}

    low = raw.lower()
    kind = "expense"
    first = low.split()[0]
    if raw.startswith("+") or first in ("income", "earned", "received", "salary", "paycheck"):
        kind = "income"
    elif first in ("move", "transfer", "mv"):
        kind = "transfer"
    elif first == "settle":
        kind = "settle"
    elif first == "split":
        kind = "split"

    out = {"date": today, "account": None, "to_account": "", "category": None,
           "your_share": "", "total": ""}
    numbers, words, accounts = [], [], []
    tokens = raw.split()
    # 'move 200 1>2' style with spaces: join "1 > 2"
    joined = re.sub(r"\b([1-4])\s*(->|>)\s*([1-4])\b", r"\1>\3", raw)
    tokens = joined.split()

    for i, tok in enumerate(tokens):
        t = tok.lower()
        if i == 0 and kind != "expense" and t.lstrip("+") in (
                "income", "earned", "received", "move", "transfer", "mv", "settle", "split"):
            continue
        if t in ("yesterday", "yday"):
            out["date"] = today - timedelta(days=1)
            continue
        if t == "today":
            continue
        m = MDY.match(t)
        if m:
            try:
                d = today.replace(month=int(m.group(1)), day=int(m.group(2)))
                out["date"] = d if d <= today else d.replace(year=today.year - 1)
                continue
            except ValueError:
                pass
        if t.startswith("@") and t[1:] in ("1", "2", "3", "4"):
            out["account"] = _acc(t[1:])
            continue
        if t.startswith("#") and len(t) > 1:
            pool = INCOME_CATS if kind == "income" else EXPENSE_CATS
            hit = next((c for c in pool if c.lower().startswith(t[1:])), None)
            if hit:
                out["category"] = hit
                continue
        m = ARROW.match(t)
        if m and kind == "transfer":
            accounts = [m.group(1), m.group(2)]
            continue
        if NUM.match(t):
            if kind == "transfer" and numbers and t in ("1", "2", "3", "4"):
                accounts.append(t)
                continue
            numbers.append(f(t))
            continue
        words.append(tok)

    note = " ".join(words).strip()
    nlow = note.lower()

    if not numbers:
        return {"error": "Add an amount, e.g. 'uber 18'"}

    if kind == "income":
        amt = abs(numbers[-1])
        cat = out["category"] or guess_category(note, rules, "income")[0]
        return {**out, "kind": "income", "amount": amt, "note": note.capitalize() or cat,
                "category": cat, "account": out["account"] or INCOME_ACC}

    if kind == "transfer":
        src, dst = (accounts + [None, None])[:2]
        return {**out, "kind": "transfer", "amount": abs(numbers[0]), "note": note or "Transfer",
                "category": "", "account": _acc(src) if src else INCOME_ACC,
                "to_account": _acc(dst) if dst else SPEND_ACC}

    if kind == "settle":
        paying = any(w in nlow.split() for w in ("out", "paid", "pay", "sent"))
        acc = out["account"] or SPEND_ACC
        return {**out, "kind": "transfer", "amount": abs(numbers[0]),
                "note": "Splitwise settle-up" + (" (paid)" if paying else " (received)"),
                "category": "", "account": acc if paying else SPLIT_ACC,
                "to_account": SPLIT_ACC if paying else acc}

    if kind == "split":
        they = any(w in nlow.split() for w in ("they", "them", "owe", "friend", "roommate"))
        if they:
            note = " ".join(w for w in words if w.lower() not in ("they", "them", "owe")).strip()
        total = abs(numbers[0])
        share = abs(numbers[1]) if len(numbers) > 1 else round(total / 2, 2)
        cat = out["category"] or guess_category(note, rules)[0]
        return {**out, "kind": "split", "amount": 0.0 if they else total, "your_share": share,
                "total": total, "note": note.capitalize() or "Split", "category": cat,
                "account": out["account"] or SPEND_ACC}

    amt = abs(numbers[-1])
    cat = out["category"] or guess_category(note, rules)[0]
    return {**out, "kind": "expense", "amount": amt, "note": note.capitalize() or cat,
            "category": cat, "account": out["account"] or SPEND_ACC}


def describe(e, labels):
    """Short human summary used in flash messages and Shortcut notifications."""
    amt = f"${f(e['amount']):,.2f}"
    k = e["kind"]
    if k == "expense":
        return f"{amt} {e['note']} → {e['category']} ({labels.get(e['account'], e['account'])})"
    if k == "income":
        return f"+{amt} {e['note']} → {labels.get(e['account'], e['account'])}"
    if k == "transfer":
        return f"{amt} {labels.get(e['account'])} → {labels.get(e['to_account'])}"
    if k == "split":
        share = f"${f(e['your_share']):,.2f}"
        if f(e["amount"]):
            return f"Split {e['note']}: you paid {amt}, your share {share}"
        return f"Split {e['note']}: they paid, your share {share}"
    if k == "adjust":
        return f"Balance check {amt} on {labels.get(e['account'])}"
    return amt
