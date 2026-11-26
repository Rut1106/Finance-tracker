"""
Bank alert emails (Chase, Wells Fargo) -> ledger rows.

Built from Rut's real alert emails:
  Chase   "You received money with Zelle®"   "NAME sent you money ... Amount | $171.18"
  Wells   "You sent money with Zelle"         "You sent $500.00 to RUT PATEL"
plus the usual purchase / deposit alert wording, matched loosely so small
wording changes don't break it. Anything unclear is reported as "unparsed".

parse_bank(sender, subject, body, my_names) returns
  ("skip", None) | ("unparsed", None) | ("ok", {"bank": "chase"|"wells", "kind": ..., ...})

kind:
  purchase  card purchase / debit           -> expense from that bank's account
  deposit   direct deposit / payroll        -> income into that bank's account
  zelle_in  someone sent you money          -> income (or a Splitwise settle-up)
  zelle_out you sent someone money          -> expense (or a Splitwise settle-up)
  self_out  you sent money to yourself      -> transfer between your own accounts
  self_in   you received from yourself      -> skipped (the "sent" side records it)
"""

import re

MONEY = r"\$\s?([\d,]+(?:\.\d{1,2})?)"
SKIP = ("statement", "fico", "credit score", "scheduled", "autopay", "payment is due",
        "payment due", "payment received", "thank you for your payment", "password",
        "sign in", "signed in", "new device", "recipient", "profile", "verify", "security",
        "paperless", "offer", "rewards", "points", "upgrade", "experience", "save you",
        "update", "welcome", "enroll", "limit", "balance", "travel", "card is on its way",
        "has been mailed", "available credit", "refinance", "purchase a car", "mortgage")


def _num(s):
    return float(s.replace(",", ""))


def _clean(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip(" .,|:-#")
    return name[:60].title() if name.isupper() else name[:60]


def _bank_of(sender, text):
    s = (sender or "").lower()
    if "chase" in s:
        return "chase"
    if "wellsfargo" in s or "wells fargo" in s:
        return "wells"
    t = text.lower()
    if "jpmorgan chase" in t or "chase.com" in t:
        return "chase"
    if "wells fargo" in t:
        return "wells"
    return None


def _is_me(name, my_names):
    low = name.lower()
    return any(n and n in low for n in my_names)


def parse_bank(sender, subject, body, my_names=("rut patel",)):
    subject = " ".join(str(subject or "").split())
    body = " ".join(str(body or "").replace("|", " ").split())
    text = f"{subject} . {body}"
    bank = _bank_of(sender, text)
    if not bank:
        return "skip", None
    if sender and "alert" not in sender.lower():
        return "skip", None          # marketing mail (chase@mcmap..., mail1.wellsfargo...)
    low = subject.lower()
    my_names = [n.strip().lower() for n in my_names if n and n.strip()]

    # ---- Zelle received: "NAME sent you money" + "Amount $171.18"
    if "zelle" in low and ("received" in low or "sent you" in body.lower()):
        who = (re.search(r"([A-Z][A-Z .'-]{1,60}?) sent you money", body)
               or re.search(r"([A-Za-z][A-Za-z .'-]{1,60}?) sent you money", body))
        amt = re.search(r"\bamount\b[^$\d]{0,10}" + MONEY, body, re.I) or re.search(MONEY, body)
        if amt:
            name = _clean(re.sub(r"(?i)^(?:zelle\S*\s+)?payment\s+", "", who.group(1))) if who else "someone"
            kind = "self_in" if _is_me(name, my_names) else "zelle_in"
            return "ok", {"bank": bank, "kind": kind, "amount": _num(amt.group(1)),
                          "who": name, "note": f"Zelle from {name}"}
        return "unparsed", None

    # ---- Zelle sent: "You sent $500.00 to RUT PATEL"
    m = re.search(r"you sent " + MONEY + r" to ([A-Za-z][A-Za-z .'-]{1,60}?)(?:\s+(?:date|on|from|with|confirmation|memo)\b|[.|]|$)",
                  text, re.I)
    if m:
        name = _clean(m.group(2))
        kind = "self_out" if _is_me(name, my_names) else "zelle_out"
        return "ok", {"bank": bank, "kind": kind, "amount": _num(m.group(1)),
                      "who": name, "note": f"Zelle to {name}"}

    # ---- Direct deposit / payroll
    if re.search(r"direct deposit|payroll|deposit (?:posted|received|of)", text, re.I):
        amt = re.search(r"deposit[^$]{0,40}" + MONEY, text, re.I) or re.search(MONEY, text)
        if amt:
            src = re.search(r"\bfrom ([A-Z][A-Za-z0-9 &.'-]{2,40}?)(?:\s+(?:on|to|was|has)\b|[.|]|$)", body)
            name = _clean(src.group(1)) if src else "Direct deposit"
            return "ok", {"bank": bank, "kind": "deposit", "amount": _num(amt.group(1)),
                          "who": name, "note": name}
        return "unparsed", None

    if any(w in low for w in SKIP):
        return "skip", None

    # ---- Card purchases (Chase: "Your $12.34 transaction with STARBUCKS";
    #      Wells: "Purchase amount $12.34 ... Merchant detail STARBUCKS" or similar)
    purchase_words = re.search(r"transaction|purchase|charge|card was used|debit card|spent", text, re.I)
    if purchase_words and not any(w in low for w in ("zelle", "transfer")):
        amt = (re.search(r"(?:transaction|purchase|charge)(?: amount)?[^$\d]{0,25}" + MONEY, text, re.I)
               or re.search(MONEY + r"\s+(?:transaction|purchase|charge)", text, re.I)
               or re.search(MONEY, subject) or re.search(MONEY, body))
        mer = (re.search(r"merchant(?: detail| name)?[:\s]+([A-Z0-9][^$]{1,50}?)(?=\s+(?:date|time|card|account|amount|on|if|this)\b|[.|]|$)", text, re.I)
               or re.search(r"\b(?:transaction|purchase|charge) (?:with|at) ([A-Z0-9][^$]{1,50}?)(?=\s+(?:on|was|has|account|date|for)\b|[.|]|$)", text, re.I)
               or re.search(MONEY + r" (?:transaction )?(?:with|at) ([A-Z0-9][^$]{1,50}?)(?=\s+(?:on|was|has|account|date)\b|[.|]|$)", text, re.I))
        if amt:
            merchant = _clean(mer.group(mer.lastindex)) if mer else "Card purchase"
            return "ok", {"bank": bank, "kind": "purchase", "amount": _num(amt.group(1)),
                          "who": merchant, "note": merchant}
        return "unparsed", None

    if any(w in low for w in SKIP):
        return "skip", None
    if re.search(MONEY, text) and re.search(r"zelle|deposit|transaction|purchase|sent|received", low):
        return "unparsed", None
    return "skip", None
