"""
Money rules for Rut Finance v2 — the same paths as v1:

  Account 3  = income lands here (salary)
  Account 1  = spending account (Apple Pay / card purchases)
  Account 2  = general
  Account 4  = Splitwise ledger (positive = friends owe you)

Every entry is one row in the `ledger` tab. Its effect on accounts:

  expense   account -amount                          spend = amount
  income    account +amount                          income = amount
  transfer  account -amount, to_account +amount      (no spend / income)
  split     account -amount (what YOU paid in cash)  spend = your_share
            Account 4 +(amount - your_share)
            -> "I paid 40, my share 20": A1 -40, A4 +20, spend 20
            -> "They paid, my share 20": amount 0, A4 -20, spend 20
  adjust    account +/-amount (weekly balance check)  negative = untracked spend
"""

import re
from datetime import date, datetime, timedelta

ACCOUNTS = ["Account 1", "Account 2", "Account 3", "Account 4"]
SPEND_ACC, GENERAL_ACC, INCOME_ACC, SPLIT_ACC = ACCOUNTS
ROLES = {SPEND_ACC: "Spending", GENERAL_ACC: "General", INCOME_ACC: "Income", SPLIT_ACC: "Splitwise"}

EXPENSE_CATS = ["Food", "Groceries", "Transportation", "Shopping", "Bills", "Rent",
                "Entertainment", "Health", "Education", "Travel", "Other"]
INCOME_CATS = ["Salary", "Freelance", "Refund", "Gift", "Other"]

# Built-in keyword -> category guesses (learned rules always win over these)
KEYWORDS = {
    "Food": ["starbucks", "chipotle", "mcdonald", "taco", "pizza", "burger", "cafe", "coffee",
             "restaurant", "doordash", "ubereats", "grubhub", "panda", "subway", "chick",
             "wendy", "kfc", "domino", "dunkin", "lunch", "dinner", "breakfast", "snack",
             "boba", "tea", "biryani", "food", "canes", "raising", "whataburger", "popeyes"],
    "Groceries": ["walmart", "kroger", "costco", "aldi", "heb", "h-e-b", "tom thumb",
                  "target", "patel", "india bazaar", "trader joe", "whole foods", "sprouts",
                  "grocery", "groceries", "fiesta", "99 ranch", "sams club", "sam's"],
    "Transportation": ["uber", "lyft", "dart", "shell", "exxon", "chevron", "qt ", "quiktrip",
                       "7-eleven", "gas", "fuel", "parking", "toll", "metro", "bus", "train"],
    "Shopping": ["amazon", "best buy", "apple store", "nike", "h&m", "zara", "ikea",
                 "marshalls", "ross", "tj maxx", "kohl", "macy", "shein", "temu", "ebay"],
    "Bills": ["att", "at&t", "t-mobile", "tmobile", "verizon", "mint mobile", "electric",
              "txu", "reliant", "internet", "spectrum", "xfinity", "insurance", "phone bill"],
    "Rent": ["rent", "apartment", "lease"],
    "Entertainment": ["netflix", "spotify", "hulu", "disney", "youtube", "movie", "cinema",
                      "amc", "cinemark", "steam", "playstation", "xbox", "concert", "bowling"],
    "Health": ["cvs", "walgreens", "pharmacy", "doctor", "clinic", "dental", "gym",
               "planet fitness", "la fitness", "medicine"],
    "Education": ["utd", "tuition", "course", "udemy", "coursera", "book", "textbook", "chegg"],
    "Travel": ["airline", "american air", "southwest", "delta", "united", "spirit", "frontier",
               "hotel", "airbnb", "marriott", "hilton", "expedia", "flight"],
}
INCOME_KEYWORDS = {
    "Salary": ["salary", "payroll", "paycheck", "stipend", "utd pay", "wage", "ta pay", "ra pay"],
    "Refund": ["refund", "return", "cashback", "cash back", "reimburse"],
    "Gift": ["gift", "mom", "dad", "birthday"],
    "Freelance": ["freelance", "client", "invoice", "gig"],
}

STOP = {"the", "at", "in", "on", "for", "and", "from", "to", "a", "an", "of", "with",
        "inc", "llc", "co", "store", "purchase", "payment", "pos", "sq", "tst"}


def f(x):
    """Safe float. Also copes with "USD 5.75", "$1,234.50", "−12" from Shortcuts/emails."""
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x or "").replace(",", "").replace("\u2212", "-").strip()
    try:
        return float(s.replace("$", "") or 0)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group()) if m else 0.0


def parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------- categorizing
def rule_key(text):
    """Turn 'UBER *TRIP 8812' or 'Starbucks Store #123' into a stable key: 'uber', 'starbucks'."""
    words = re.sub(r"[^a-z&' ]+", " ", str(text).lower()).split()
    words = [w for w in words if len(w) >= 3 and w not in STOP]
    return words[0] if words else ""


def guess_category(text, rules, kind="expense"):
    """Return (category, learned?) — learned rules first, then keywords, else Other."""
    low = " " + str(text).lower() + " "
    key = rule_key(text)
    if kind == "expense":
        for r in rules:
            if r["key"] and (r["key"] == key or f" {r['key']} " in low):
                return r["category"], True
        for cat, words in KEYWORDS.items():
            if any(w in low for w in words):
                return cat, False
        return "Other", False
    for cat, words in INCOME_KEYWORDS.items():
        if any(w in low for w in words):
            return cat, False
    return "Other", False


# ---------------------------------------------------------------- effects
def effects(r):
    """(account deltas dict, spend, income, spend_category) for one confirmed row."""
    kind, amt = r["kind"], f(r["amount"])
    acc, to = r["account"], r["to_account"]
    if kind == "expense":
        return {acc: -amt}, amt, 0.0, r["category"]
    if kind == "income":
        return {acc: amt}, 0.0, amt, r["category"]
    if kind == "transfer":
        return {acc: -amt, to: amt}, 0.0, 0.0, None
    if kind == "split":
        share = f(r["your_share"])
        deltas = {SPLIT_ACC: amt - share}
        if amt:
            deltas[acc] = deltas.get(acc, 0) - amt
        return deltas, share, 0.0, r["category"]
    if kind == "adjust":
        return {acc: amt}, max(0.0, -amt), max(0.0, amt), "Untracked"
    return {}, 0.0, 0.0, None


def confirmed(store):
    return [r for r in store.rows("ledger") if r["status"] == "ok"]


def opening_balances(store):
    return {a: f((store.find("accounts", a) or {}).get("opening", 0)) for a in ACCOUNTS}


def labels(store):
    out = {}
    for a in ACCOUNTS:
        row = store.find("accounts", a) or {}
        out[a] = row.get("label") or ROLES[a]
    return out


def balances(store, upto=None):
    bal = opening_balances(store)
    for r in confirmed(store):
        if upto and (parse_date(r["date"]) or date.min) > upto:
            continue
        for a, d in effects(r)[0].items():
            if a:
                bal[a] = bal.get(a, 0) + d
    return bal


def month_rows(store, y, m):
    out = []
    for r in confirmed(store):
        d = parse_date(r["date"])
        if d and d.year == y and d.month == m:
            out.append(r)
    return out


def month_stats(store, y, m):
    spend = income = untracked = 0.0
    by_cat, by_merchant, by_dow, spend_days = {}, {}, [0.0] * 7, set()
    rows = month_rows(store, y, m)
    for r in rows:
        _, s, i, cat = effects(r)
        income += i
        if s:
            spend += s
            by_cat[cat] = by_cat.get(cat, 0) + s
            d = parse_date(r["date"])
            spend_days.add(d)
            if r["kind"] == "adjust":
                untracked += s
            elif r["source"] != "recurring":   # habits only: rent/bills would drown them out
                by_dow[d.weekday()] += s
                name = (r["merchant"] or r["note"] or cat).strip()
                by_merchant[name] = by_merchant.get(name, 0) + s
    return {"spend": spend, "income": income, "untracked": untracked, "by_cat": by_cat,
            "by_merchant": by_merchant, "by_dow": by_dow, "spend_days": spend_days,
            "count": sum(1 for r in rows if r["kind"] in ("expense", "split"))}


def add_months(y, m, k):
    idx = y * 12 + (m - 1) + k
    return idx // 12, idx % 12 + 1


def last_day(y, m):
    ny, nm = add_months(y, m, 1)
    return date(ny, nm, 1) - timedelta(days=1)


def snapshots(store, start, today):
    """Opening -> closing total balance for every month since the fresh start."""
    out = []
    y, m = start.year, start.month
    opening_total = sum(opening_balances(store).values())
    while (y, m) <= (today.year, today.month):
        st = month_stats(store, y, m)
        net = 0.0
        for r in month_rows(store, y, m):
            net += sum(effects(r)[0].values())
        out.append({"label": date(y, m, 1).strftime("%b %Y"), "opening": opening_total,
                    "closing": opening_total + net, "net": net, "income": st["income"],
                    "spend": st["spend"], "current": (y, m) == (today.year, today.month)})
        opening_total += net
        y, m = add_months(y, m, 1)
    return list(reversed(out))


# ---------------------------------------------------------------- safe to spend
def safe_to_spend(store, today, plan=None, save=0.0):
    """How much can be spent per day for the rest of the month and still land on plan.

    plan  = money available to spend this month. If not set: income this month +
            recurring income still to come.
    left  = plan - savings goal - spent before today - recurring bills still to come.
    daily = left / days remaining (today included). today_left = daily - spent today.
    """
    y, m = today.year, today.month
    ym = today.strftime("%Y-%m")
    end = last_day(y, m)
    days_left = (end - today).days + 1

    spent_before = spent_today = n_today = income = 0.0
    rows = [r for r in store.rows("ledger") if r["status"] in ("ok", "inbox")]   # inbox = real, just unsorted
    for r in rows:
        d0 = parse_date(r["date"])
        if not d0 or (d0.year, d0.month) != (y, m):
            continue
        _, s, i, _ = effects(r)
        income += i
        d = parse_date(r["date"])
        if d == today:
            spent_today += s
            if s and r["kind"] != "adjust":
                n_today += 1
        elif d and d < today:
            spent_before += s

    rec_in = rec_out = 0.0
    for r in store.rows("recurring"):
        if r["last_posted"] == ym:
            continue
        if r["kind"] == "income":
            rec_in += f(r["amount"])
        elif r["kind"] == "expense":
            rec_out += f(r["amount"])

    auto = plan is None
    if auto:
        plan = income + rec_in
    left = plan - f(save) - spent_before - rec_out
    daily = left / days_left if days_left else 0.0
    after_today = left - spent_today
    tomorrow = (after_today / (days_left - 1)) if days_left > 1 else None
    return {"plan": plan, "auto": auto, "save": f(save), "left": left, "days_left": days_left,
            "daily": daily, "spent_today": spent_today, "n_today": int(n_today),
            "today_left": daily - spent_today, "after_today": after_today,
            "tomorrow": tomorrow, "bills_ahead": rec_out, "income_ahead": rec_in,
            "has_plan": plan > 0}
