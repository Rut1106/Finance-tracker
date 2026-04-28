from flask import Flask, render_template, request, redirect
from datetime import datetime, date
import io
import os
import json
import base64
import time
import gspread
from google.oauth2.service_account import Credentials
import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure

app = Flask(__name__)

# ---------- Google Sheets setup ----------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_gc_cache = None
_sh_cache = None

def get_gc():
    global _gc_cache
    if _gc_cache is not None:
        return _gc_cache
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    _gc_cache = gspread.authorize(creds)
    return _gc_cache

SHEET_NAME = "Finance Tracker"

def get_sheet(tab):
    global _sh_cache
    if _sh_cache is None:
        _sh_cache = get_gc().open(SHEET_NAME)
    return _sh_cache.worksheet(tab)

# ---------- Cache ----------
_cache = {}
_cache_ttl = 30

def get_cached_data():
    global _sh_cache
    now = time.time()
    if "data" in _cache and now - _cache.get("ts", 0) < _cache_ttl:
        return _cache["data"]

    if _sh_cache is None:
        _sh_cache = get_gc().open(SHEET_NAME)
    sh = _sh_cache

    data = {
        "expenses":   sh.worksheet("expenses").get_all_records(),
        "incomes":    sh.worksheet("incomes").get_all_records(),
        "transfers":  sh.worksheet("transfers").get_all_records(),
        "splits":     sh.worksheet("splits").get_all_records(),
        "accounts":   sh.worksheet("accounts").get_all_records(),
        "categories": sh.worksheet("categories").get_all_records(),
        "budgets":    sh.worksheet("budgets").get_all_records(),
    }

    _cache["data"] = data
    _cache["ts"]   = now
    return data


def invalidate_cache():
    _cache.clear()


# ---------- Constants ----------
INCOME_ACCOUNT    = "Account 3"
EXPENSE_ACCOUNT   = "Account 1"
SPLITWISE_ACCOUNT = "Account 4"
DEFAULT_ACCOUNTS  = ["Account 1", "Account 2", "Account 3", "Account 4"]
DEFAULT_EXPENSE_CATS = ["Food", "Transportation", "Entertainment", "Shopping", "Utilities", "Other"]
DEFAULT_INCOME_CATS  = ["Salary", "Freelance", "Investment", "Gift", "Other"]

EXPENSE_HEADERS  = ["id","date","description","amount","category","account","is_split","split_id","your_share","direction"]
INCOME_HEADERS   = ["id","date","description","amount","category","account"]
TRANSFER_HEADERS = ["id","date","from_acc","to_acc","amount","note","is_settlement","split_id"]
SPLIT_HEADERS    = ["id","date","description","total","your_share","other_share","category","direction","status","settle_date","settle_account"]
ACCOUNT_HEADERS  = ["name","opening_balance"]
CATEGORY_HEADERS = ["id","name","kind"]
BUDGET_HEADERS   = ["id","category","amount"]


# ---------- Sheet helpers ----------
def ensure_headers(ws, headers):
    vals = ws.row_values(1) if ws.row_count > 0 else []
    if vals != headers:
        if ws.row_count == 0:
            ws.insert_row(headers, 1)
        else:
            ws.update("A1", [headers])


def sheet_to_dicts(ws):
    return ws.get_all_records()


def next_id(ws):
    rows = ws.get_all_records()
    if not rows:
        return 1
    ids = [int(r.get("id", 0)) for r in rows if str(r.get("id", "")).isdigit()]
    return max(ids) + 1 if ids else 1


def append_row(ws, headers, data_dict):
    row = [str(data_dict.get(h, "")) for h in headers]
    ws.append_row(row, value_input_option="USER_ENTERED")


def update_row_by_id(ws, row_id, headers, data_dict):
    rows = ws.get_all_values()
    for i, row in enumerate(rows):
        if i == 0:
            continue
        if str(row[0]) == str(row_id):
            new_row = [str(data_dict.get(h, row[j] if j < len(row) else "")) for j, h in enumerate(headers)]
            ws.update(f"A{i+1}", [new_row])
            return


def delete_row_by_id(ws, row_id):
    rows = ws.get_all_values()
    for i, row in enumerate(rows):
        if i == 0:
            continue
        if str(row[0]) == str(row_id):
            ws.delete_rows(i + 1)
            return


def find_row_by_id(rows, row_id):
    for r in rows:
        if str(r.get("id", "")) == str(row_id):
            return r
    return None


# ---------- Init sheets ----------
def init_sheets():
    global _sh_cache
    if _sh_cache is None:
        _sh_cache = get_gc().open(SHEET_NAME)
    sh = _sh_cache

    tabs = {
        "expenses":   EXPENSE_HEADERS,
        "incomes":    INCOME_HEADERS,
        "transfers":  TRANSFER_HEADERS,
        "splits":     SPLIT_HEADERS,
        "accounts":   ACCOUNT_HEADERS,
        "categories": CATEGORY_HEADERS,
        "budgets":    BUDGET_HEADERS,
    }

    existing = [ws.title for ws in sh.worksheets()]

    for tab, headers in tabs.items():
        if tab not in existing:
            ws = sh.add_worksheet(title=tab, rows=1000, cols=len(headers))
        else:
            ws = sh.worksheet(tab)
        ensure_headers(ws, headers)

    acc_ws       = sh.worksheet("accounts")
    acc_rows     = acc_ws.get_all_records()
    existing_acc = [r["name"] for r in acc_rows]
    for name in DEFAULT_ACCOUNTS:
        if name not in existing_acc:
            acc_ws.append_row([name, "0.0"])

    cat_ws   = sh.worksheet("categories")
    cat_rows = cat_ws.get_all_records()
    if not cat_rows:
        nid = 1
        for n in DEFAULT_EXPENSE_CATS:
            cat_ws.append_row([nid, n, "expense"])
            nid += 1
        for n in DEFAULT_INCOME_CATS:
            cat_ws.append_row([nid, n, "income"])
            nid += 1


# ---------- Data helpers ----------
def get_categories(kind):
    data = get_cached_data()
    return [r["name"] for r in data["categories"] if r["kind"] == kind]


def get_opening_balances():
    data = get_cached_data()
    return {r["name"]: float(r["opening_balance"] or 0) for r in data["accounts"]}


def get_account_balances():
    data     = get_cached_data()
    opening  = {r["name"]: float(r["opening_balance"] or 0) for r in data["accounts"]}
    balances = dict(opening)

    for i in data["incomes"]:
        balances[i["account"]] = balances.get(i["account"], 0) + float(i["amount"] or 0)

    for e in data["expenses"]:
        balances[e["account"]] = balances.get(e["account"], 0) - float(e["amount"] or 0)

    for t in data["transfers"]:
        balances[t["from_acc"]] = balances.get(t["from_acc"], 0) - float(t["amount"] or 0)
        balances[t["to_acc"]]   = balances.get(t["to_acc"], 0)   + float(t["amount"] or 0)

    for s in data["splits"]:
        if s["direction"] == "you_paid":
            balances[SPLITWISE_ACCOUNT] = balances.get(SPLITWISE_ACCOUNT, 0) + float(s["other_share"] or 0)
        else:
            balances[SPLITWISE_ACCOUNT] = balances.get(SPLITWISE_ACCOUNT, 0) - float(s["your_share"] or 0)

    return balances


def get_totals():
    data     = get_cached_data()
    balances = get_account_balances()
    opening  = get_opening_balances()

    real_expense  = sum(float(e["amount"] or 0) for e in data["expenses"] if str(e["is_split"]).lower() != "true")
    real_expense += sum(float(s["your_share"] or 0) for s in data["splits"])

    splitwise_net = 0
    for s in data["splits"]:
        if s["status"] == "pending":
            if s["direction"] == "you_paid":
                splitwise_net += float(s["other_share"] or 0)
            else:
                splitwise_net -= float(s["your_share"] or 0)

    return {
        "opening":       sum(opening.values()),
        "income":        sum(float(i["amount"] or 0) for i in data["incomes"]),
        "expenses":      real_expense,
        "splitwise_net": splitwise_net,
        "balance":       sum(balances.values()),
    }


def get_budgets_with_progress(year, month):
    data   = get_cached_data()
    by_cat = {}
    for e in data["expenses"]:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d")
        except:
            continue
        if d.year == year and d.month == month:
            amt = float(e["your_share"] or 0) if str(e["is_split"]).lower() == "true" else float(e["amount"] or 0)
            by_cat[e["category"]] = by_cat.get(e["category"], 0) + amt

    result = []
    for b in data["budgets"]:
        spent      = by_cat.get(b["category"], 0)
        budget_amt = float(b["amount"] or 0)
        pct        = (spent / budget_amt * 100) if budget_amt > 0 else 0
        status     = "green"
        if pct >= 100: status = "red"
        elif pct >= 75: status = "yellow"
        result.append({
            "id": b["id"], "category": b["category"],
            "amount": budget_amt, "spent": spent,
            "remaining": budget_amt - spent,
            "pct": min(pct, 100), "pct_raw": pct, "status": status,
        })
    return result


def get_mom_comparison():
    data  = get_cached_data()
    today = date.today()

    def month_spend(y, m):
        total = 0
        for e in data["expenses"]:
            try:
                d = datetime.strptime(e["date"], "%Y-%m-%d")
            except:
                continue
            if d.year == y and d.month == m:
                total += float(e["your_share"] or 0) if str(e["is_split"]).lower() == "true" else float(e["amount"] or 0)
        return total

    cur        = month_spend(today.year, today.month)
    prev_year  = today.year if today.month > 1 else today.year - 1
    prev_month = today.month - 1 if today.month > 1 else 12
    prev       = month_spend(prev_year, prev_month)
    change_pct = ((cur - prev) / prev * 100) if prev > 0 else None

    return {
        "current": cur, "previous": prev,
        "change_pct": change_pct,
        "prev_month_name": datetime(prev_year, prev_month, 1).strftime("%B"),
    }


# ---------- Home ----------
@app.route("/")
def home():
    today_str  = date.today().strftime("%Y-%m-%d")
    today_date = date.today()

    search          = request.args.get("search", "").strip().lower()
    filter_category = request.args.get("filter_category", "")
    filter_from     = request.args.get("filter_from", "")
    filter_to       = request.args.get("filter_to", "")
    search_type     = request.args.get("search_type", "expense")

    data = get_cached_data()

    def filter_items(items, fields):
        out = []
        for it in items:
            if filter_from and it.get("date", "") < filter_from:
                continue
            if filter_to and it.get("date", "") > filter_to:
                continue
            if filter_category and it.get("category", "") != filter_category:
                continue
            if search:
                blob = " ".join(str(it.get(f, "")).lower() for f in fields)
                if search not in blob:
                    continue
            out.append(it)
        return out

    filtered_expenses  = filter_items(data["expenses"],  ["description", "category", "account"])
    filtered_incomes   = filter_items(data["incomes"],   ["description", "category", "account"])
    filtered_transfers = filter_items(data["transfers"], ["from_acc", "to_acc", "note"])
    filtered_splits    = filter_items(data["splits"],    ["description", "category"])

    has_filters = bool(search or filter_category or filter_from or filter_to)

    return render_template(
        "add_expense.html",
        expenses=list(reversed(data["expenses"])),
        incomes=list(reversed(data["incomes"])),
        transfers=list(reversed(data["transfers"])),
        splits=list(reversed(data["splits"])),
        today=today_str,
        categories=get_categories("expense"),
        income_categories=get_categories("income"),
        accounts=get_account_balances(),
        account_names=list(get_opening_balances().keys()),
        totals=get_totals(),
        income_account=INCOME_ACCOUNT,
        expense_account=EXPENSE_ACCOUNT,
        splitwise_account=SPLITWISE_ACCOUNT,
        budgets=get_budgets_with_progress(today_date.year, today_date.month),
        mom=get_mom_comparison(),
        search=search,
        filter_category=filter_category,
        filter_from=filter_from,
        filter_to=filter_to,
        search_type=search_type,
        has_filters=has_filters,
        filtered_expenses=filtered_expenses,
        filtered_incomes=filtered_incomes,
        filtered_transfers=filtered_transfers,
        filtered_splits=filtered_splits,
    )


# ---------- Expenses ----------
@app.route("/add", methods=["POST"])
def add_expense():
    ws    = get_sheet("expenses")
    total = float(request.form["amount"])
    is_split = request.form.get("is_split") == "on"

    if is_split:
        direction   = request.form.get("direction", "you_paid")
        your_share  = float(request.form["your_share"])
        other_share = total - your_share

        split_ws = get_sheet("splits")
        split_id = next_id(split_ws)
        append_row(split_ws, SPLIT_HEADERS, {
            "id": split_id, "date": request.form["date"],
            "description": request.form["description"],
            "total": total, "your_share": your_share,
            "other_share": other_share,
            "category": request.form["category"],
            "direction": direction, "status": "pending",
            "settle_date": "", "settle_account": "",
        })

        append_row(ws, EXPENSE_HEADERS, {
            "id": next_id(ws), "date": request.form["date"],
            "description": request.form["description"],
            "amount": total if direction == "you_paid" else 0,
            "category": request.form["category"],
            "account": EXPENSE_ACCOUNT,
            "is_split": True, "split_id": split_id,
            "your_share": your_share, "direction": direction,
        })
    else:
        append_row(ws, EXPENSE_HEADERS, {
            "id": next_id(ws), "date": request.form["date"],
            "description": request.form["description"],
            "amount": total, "category": request.form["category"],
            "account": EXPENSE_ACCOUNT,
            "is_split": False, "split_id": "",
            "your_share": "", "direction": "",
        })

    invalidate_cache()
    return redirect("/")


@app.route("/edit/<row_id>", methods=["POST"])
def edit_expense(row_id):
    data    = get_cached_data()
    expense = find_row_by_id(data["expenses"], row_id)
    if not expense:
        return redirect("/")

    expense["date"]        = request.form["date"]
    expense["description"] = request.form["description"]
    expense["amount"]      = float(request.form["amount"])
    expense["category"]    = request.form["category"]
    update_row_by_id(get_sheet("expenses"), row_id, EXPENSE_HEADERS, expense)
    invalidate_cache()
    return redirect("/")


@app.route("/delete/<row_id>")
def delete_expense(row_id):
    data = get_cached_data()
    e    = find_row_by_id(data["expenses"], row_id)
    if e and str(e.get("is_split", "")).lower() != "true":
        delete_row_by_id(get_sheet("expenses"), row_id)
        invalidate_cache()
    return redirect("/")


# ---------- Income ----------
@app.route("/add_income", methods=["POST"])
def add_income():
    ws = get_sheet("incomes")
    append_row(ws, INCOME_HEADERS, {
        "id": next_id(ws), "date": request.form["date"],
        "description": request.form["description"],
        "amount": float(request.form["amount"]),
        "category": request.form["category"],
        "account": INCOME_ACCOUNT,
    })
    invalidate_cache()
    return redirect("/")


@app.route("/edit_income/<row_id>", methods=["POST"])
def edit_income(row_id):
    data   = get_cached_data()
    income = find_row_by_id(data["incomes"], row_id)
    if not income:
        return redirect("/")

    income["date"]        = request.form["date"]
    income["description"] = request.form["description"]
    income["amount"]      = float(request.form["amount"])
    income["category"]    = request.form["category"]
    update_row_by_id(get_sheet("incomes"), row_id, INCOME_HEADERS, income)
    invalidate_cache()
    return redirect("/")


@app.route("/delete_income/<row_id>")
def delete_income(row_id):
    delete_row_by_id(get_sheet("incomes"), row_id)
    invalidate_cache()
    return redirect("/")


# ---------- Splitwise ----------
@app.route("/edit_split/<split_id>", methods=["POST"])
def edit_split(split_id):
    data = get_cached_data()
    s    = find_row_by_id(data["splits"], split_id)
    if not s:
        return redirect("/")

    new_total       = float(request.form["total"])
    new_your_share  = float(request.form["your_share"])
    new_description = request.form["description"]
    new_category    = request.form["category"]
    new_date        = request.form["date"]
    new_direction   = request.form.get("direction", s["direction"])
    new_other_share = new_total - new_your_share

    s["date"]        = new_date
    s["description"] = new_description
    s["category"]    = new_category
    s["total"]       = new_total
    s["your_share"]  = new_your_share
    s["other_share"] = new_other_share
    s["direction"]   = new_direction
    update_row_by_id(get_sheet("splits"), split_id, SPLIT_HEADERS, s)

    exp_ws = get_sheet("expenses")
    for e in data["expenses"]:
        if str(e.get("split_id")) == str(split_id) and str(e.get("is_split", "")).lower() == "true":
            e["date"]        = new_date
            e["description"] = new_description
            e["category"]    = new_category
            e["amount"]      = new_total if new_direction == "you_paid" else 0
            e["your_share"]  = new_your_share
            e["direction"]   = new_direction
            update_row_by_id(exp_ws, e["id"], EXPENSE_HEADERS, e)
            break

    invalidate_cache()
    return redirect("/")


@app.route("/settle_split/<split_id>", methods=["POST"])
def settle_split(split_id):
    data = get_cached_data()
    s    = find_row_by_id(data["splits"], split_id)
    if not s or s["status"] != "pending":
        return redirect("/")

    settle_account     = request.form.get("settle_account", EXPENSE_ACCOUNT)
    s["status"]        = "settled"
    s["settle_date"]   = date.today().strftime("%Y-%m-%d")
    s["settle_account"] = settle_account
    update_row_by_id(get_sheet("splits"), split_id, SPLIT_HEADERS, s)

    tr_ws = get_sheet("transfers")
    if s["direction"] == "you_paid":
        append_row(tr_ws, TRANSFER_HEADERS, {
            "id": next_id(tr_ws), "date": s["settle_date"],
            "from_acc": SPLITWISE_ACCOUNT, "to_acc": settle_account,
            "amount": s["other_share"],
            "note": f"Splitwise settlement: {s['description']}",
            "is_settlement": True, "split_id": split_id,
        })
    else:
        append_row(tr_ws, TRANSFER_HEADERS, {
            "id": next_id(tr_ws), "date": s["settle_date"],
            "from_acc": settle_account, "to_acc": SPLITWISE_ACCOUNT,
            "amount": s["your_share"],
            "note": f"Splitwise settlement: {s['description']}",
            "is_settlement": True, "split_id": split_id,
        })

    invalidate_cache()
    return redirect("/")


@app.route("/unsettle_split/<split_id>")
def unsettle_split(split_id):
    data = get_cached_data()
    s    = find_row_by_id(data["splits"], split_id)
    if not s or s["status"] != "settled":
        return redirect("/")

    tr_ws = get_sheet("transfers")
    for t in data["transfers"]:
        if str(t.get("split_id")) == str(split_id) and str(t.get("is_settlement", "")).lower() == "true":
            delete_row_by_id(tr_ws, t["id"])

    s["status"]       = "pending"
    s["settle_date"]  = ""
    s["settle_account"] = ""
    update_row_by_id(get_sheet("splits"), split_id, SPLIT_HEADERS, s)
    invalidate_cache()
    return redirect("/")


@app.route("/delete_split/<split_id>")
def delete_split(split_id):
    data  = get_cached_data()
    tr_ws = get_sheet("transfers")
    for t in data["transfers"]:
        if str(t.get("split_id")) == str(split_id) and str(t.get("is_settlement", "")).lower() == "true":
            delete_row_by_id(tr_ws, t["id"])

    exp_ws = get_sheet("expenses")
    for e in data["expenses"]:
        if str(e.get("split_id")) == str(split_id) and str(e.get("is_split", "")).lower() == "true":
            delete_row_by_id(exp_ws, e["id"])

    delete_row_by_id(get_sheet("splits"), split_id)
    invalidate_cache()
    return redirect("/")


# ---------- Transfers ----------
@app.route("/add_transfer", methods=["POST"])
def add_transfer():
    f = request.form["from"]
    t = request.form["to"]
    if f != t:
        ws = get_sheet("transfers")
        append_row(ws, TRANSFER_HEADERS, {
            "id": next_id(ws), "date": request.form["date"],
            "from_acc": f, "to_acc": t,
            "amount": float(request.form["amount"]),
            "note": request.form.get("note", ""),
            "is_settlement": False, "split_id": "",
        })
        invalidate_cache()
    return redirect("/")


@app.route("/delete_transfer/<row_id>")
def delete_transfer(row_id):
    data = get_cached_data()
    t    = find_row_by_id(data["transfers"], row_id)
    if t and str(t.get("is_settlement", "")).lower() != "true":
        delete_row_by_id(get_sheet("transfers"), row_id)
        invalidate_cache()
    return redirect("/")


# ---------- Accounts ----------
@app.route("/accounts", methods=["GET", "POST"])
def manage_accounts():
    if request.method == "POST":
        ws   = get_sheet("accounts")
        rows = ws.get_all_values()
        for i, row in enumerate(rows):
            if i == 0:
                continue
            name    = row[0]
            new_bal = request.form.get(name, "0")
            ws.update_cell(i + 1, 2, new_bal)
        invalidate_cache()
        return redirect("/")
    return render_template("accounts.html", accounts=get_opening_balances())


# ---------- Categories ----------
@app.route("/categories", methods=["GET", "POST"])
def manage_categories():
    if request.method == "POST":
        ws   = get_sheet("categories")
        name = request.form["name"].strip()
        kind = request.form["kind"]
        data = get_cached_data()
        exists = any(r["name"] == name and r["kind"] == kind for r in data["categories"])
        if name and not exists:
            append_row(ws, CATEGORY_HEADERS, {
                "id": next_id(ws), "name": name, "kind": kind
            })
            invalidate_cache()
        return redirect("/categories")

    data = get_cached_data()
    return render_template(
        "categories.html",
        expense_cats=[r for r in data["categories"] if r["kind"] == "expense"],
        income_cats=[r for r in data["categories"] if r["kind"] == "income"],
    )


@app.route("/categories/delete/<row_id>")
def delete_category(row_id):
    data = get_cached_data()
    c    = find_row_by_id(data["categories"], row_id)
    if not c:
        return redirect("/categories")

    in_use = (
        any(e["category"] == c["name"] for e in data["expenses"]) or
        any(i["category"] == c["name"] for i in data["incomes"])  or
        any(s["category"] == c["name"] for s in data["splits"])
    )
    if not in_use:
        delete_row_by_id(get_sheet("categories"), row_id)
        for b in data["budgets"]:
            if b["category"] == c["name"]:
                delete_row_by_id(get_sheet("budgets"), b["id"])
        invalidate_cache()

    return redirect("/categories")


@app.route("/categories/rename/<row_id>", methods=["POST"])
def rename_category(row_id):
    data     = get_cached_data()
    c        = find_row_by_id(data["categories"], row_id)
    new_name = request.form["new_name"].strip()
    if not c or not new_name or new_name == c["name"]:
        return redirect("/categories")

    old_name = c["name"]

    def bulk_rename(tab, rows, headers):
        ws = get_sheet(tab)
        for r in rows:
            if r.get("category") == old_name:
                r["category"] = new_name
                update_row_by_id(ws, r["id"], headers, r)

    bulk_rename("expenses",  data["expenses"],  EXPENSE_HEADERS)
    bulk_rename("incomes",   data["incomes"],   INCOME_HEADERS)
    bulk_rename("splits",    data["splits"],    SPLIT_HEADERS)
    bulk_rename("budgets",   data["budgets"],   BUDGET_HEADERS)

    c["name"] = new_name
    update_row_by_id(get_sheet("categories"), row_id, CATEGORY_HEADERS, c)
    invalidate_cache()
    return redirect("/categories")


# ---------- Budgets ----------
@app.route("/budgets", methods=["GET", "POST"])
def manage_budgets():
    if request.method == "POST":
        data     = get_cached_data()
        category = request.form["category"]
        amount   = float(request.form["amount"])
        existing = next((r for r in data["budgets"] if r["category"] == category), None)
        if existing:
            existing["amount"] = amount
            update_row_by_id(get_sheet("budgets"), existing["id"], BUDGET_HEADERS, existing)
        else:
            ws = get_sheet("budgets")
            append_row(ws, BUDGET_HEADERS, {
                "id": next_id(ws), "category": category, "amount": amount
            })
        invalidate_cache()
        return redirect("/budgets")

    today = date.today()
    return render_template(
        "budgets.html",
        budgets=get_budgets_with_progress(today.year, today.month),
        categories=get_categories("expense"),
    )


@app.route("/budgets/delete/<row_id>")
def delete_budget(row_id):
    delete_row_by_id(get_sheet("budgets"), row_id)
    invalidate_cache()
    return redirect("/budgets")


# ---------- Insights ----------
@app.route("/insights")
def insights():
    now   = datetime.now()
    month = int(request.args.get("month", now.month))
    year  = int(request.args.get("year", now.year))

    data = get_cached_data()

    month_expenses = []
    for e in data["expenses"]:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d")
        except:
            continue
        if d.month == month and d.year == year:
            amount = float(e["your_share"] or 0) if str(e["is_split"]).lower() == "true" else float(e["amount"] or 0)
            month_expenses.append({
                "date": e["date"], "description": e["description"],
                "category": e["category"], "amount": amount,
                "is_split": str(e["is_split"]).lower() == "true",
            })

    total = sum(e["amount"] for e in month_expenses)

    category_totals = {}
    for e in month_expenses:
        category_totals[e["category"]] = category_totals.get(e["category"], 0) + e["amount"]

    fig = Figure(figsize=(7, 5))
    ax  = fig.add_subplot(1, 1, 1)
    if category_totals:
        colors = ["#4f8ef7","#34c97b","#f5a623","#f05252","#9b6ef3","#0987a0","#dd6b20","#319795"]
        ax.pie(
            list(category_totals.values()),
            labels=list(category_totals.keys()),
            autopct="%1.1f%%",
            colors=colors[:len(category_totals)],
            startangle=90,
            wedgeprops={"edgecolor": "#0f1117", "linewidth": 2},
        )
        fig.patch.set_facecolor("#181c27")
        ax.set_facecolor("#181c27")
        for text in ax.texts:
            text.set_color("#e8eaf0")
    ax.set_title(f"Expenses — {month}/{year}", fontsize=14, fontweight="bold", color="#e8eaf0")

    png   = io.BytesIO()
    FigureCanvas(fig).print_png(png)
    chart = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode("utf8")

    # Month-over-month bar chart (last 6 months)
    def total_for(y, m):
        t = 0
        for e in data["expenses"]:
            try:
                d = datetime.strptime(e["date"], "%Y-%m-%d")
            except:
                continue
            if d.year == y and d.month == m:
                t += float(e["your_share"] or 0) if str(e["is_split"]).lower() == "true" else float(e["amount"] or 0)
        return t

    months_data = []
    cy, cm = year, month
    for _ in range(6):
        months_data.append((cy, cm, total_for(cy, cm)))
        cm -= 1
        if cm == 0:
            cm = 12
            cy -= 1
    months_data.reverse()

    labels = [datetime(y, m, 1).strftime("%b %y") for y, m, _ in months_data]
    values = [v for _, _, v in months_data]

    fig2 = Figure(figsize=(8, 4))
    ax2  = fig2.add_subplot(1, 1, 1)
    bar_colors = ["#4f8ef7"] * 5 + ["#f5a623"]
    bars = ax2.bar(labels, values, color=bar_colors, edgecolor="#0f1117", linewidth=1.5)

    fig2.patch.set_facecolor("#181c27")
    ax2.set_facecolor("#181c27")
    ax2.tick_params(colors="#e8eaf0")
    for spine in ax2.spines.values():
        spine.set_color("#2a2f42")
    ax2.set_title("Monthly Spending — Last 6 Months", fontsize=13, fontweight="bold", color="#e8eaf0")
    ax2.set_ylabel("Amount ($)", color="#e8eaf0")
    ax2.grid(axis="y", color="#2a2f42", linestyle="--", linewidth=0.5, alpha=0.7)

    max_val = max(values) if values else 0
    for bar, v in zip(bars, values):
        if v > 0:
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max_val*0.02,
                     f"${v:.0f}", ha="center", color="#e8eaf0", fontsize=10, fontweight="bold")

    fig2.tight_layout()
    png2 = io.BytesIO()
    FigureCanvas(fig2).print_png(png2)
    mom_chart = "data:image/png;base64," + base64.b64encode(png2.getvalue()).decode("utf8")

    avg_6m   = sum(values) / len(values) if values else 0
    cur_val  = values[-1] if values else 0
    prev_val = values[-2] if len(values) > 1 else 0
    diff     = cur_val - prev_val
    diff_pct = (diff / prev_val * 100) if prev_val > 0 else None

    return render_template(
        "insights.html",
        month=month, year=year,
        expenses=month_expenses,
        total=total, chart=chart,
        category_totals=category_totals,
        mom_chart=mom_chart,
        months_data=months_data,
        avg_6m=avg_6m,
        cur_val=cur_val,
        prev_val=prev_val,
        diff=diff,
        diff_pct=diff_pct,
    )


# ---------- Run ----------
init_sheets()

if __name__ == "__main__":
    app.run(debug=True)