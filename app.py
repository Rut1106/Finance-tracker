"""
Rut Finance v2 — low-effort money tracking.

Capture paths (fastest first):
  1. Apple Pay      -> iPhone Shortcut posts to /api/capture   (zero typing)
  2. Splitwise      -> auto-synced every few hours              (zero typing)
  3. Recurring      -> rent, salary, bills post on their day    (zero typing)
  4. Quick add      -> one line like "uber 18", or Siri via /api/quick
  5. Balance check  -> weekly, logs whatever slipped through as "Untracked"
"""

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import (Flask, flash, jsonify, redirect, render_template, request, session,
                   url_for)

import ledger as L
import splitwise as SW
from quickadd import describe, parse
from store import make_store, new_id

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.permanent_session_lifetime = timedelta(days=180)

TZ = ZoneInfo(os.environ.get("TZ_NAME", "America/Chicago"))
APP_PIN = os.environ.get("APP_PIN", "").strip()
API_KEY = os.environ.get("API_KEY", "").strip()
SYNC_EVERY = timedelta(hours=3)

store = make_store()


# ---------------------------------------------------------------- helpers
def today():
    return datetime.now(TZ).date()


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def money(x):
    return f"{round(L.f(x), 2):.2f}"


def start_date():
    return L.parse_date(store.meta("start_date"))


def make_row(e, source, status):
    d = e.get("date") or today()
    return {"id": new_id(), "created": now_iso(),
            "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "kind": e["kind"], "amount": money(e["amount"]), "account": e.get("account") or "",
            "to_account": e.get("to_account") or "", "category": e.get("category") or "",
            "note": e.get("note") or "", "merchant": e.get("merchant") or "",
            "source": source, "status": status,
            "your_share": money(e["your_share"]) if e.get("your_share") not in ("", None) else "",
            "total": money(e["total"]) if e.get("total") not in ("", None) else "",
            "ext_id": e.get("ext_id") or ""}


def learn(text, category):
    """Remember 'starbucks -> Food' so next time it needs zero taps."""
    key = L.rule_key(text)
    if key and category and category not in ("Other", "Untracked"):
        r = store.find("rules", key)
        if not r or r["category"] != category:
            store.upsert("rules", {"key": key, "category": category})


def account_for_card(card):
    low = str(card or "").lower()
    for r in store.rows("cards"):
        if r["match"] and r["match"].lower() in low:
            return r["account"]
    return L.SPEND_ACC


def api_key_ok():
    data = request.get_json(silent=True) or {}
    given = (request.headers.get("X-Key") or request.values.get("key") or data.get("key") or "")
    if not API_KEY:
        return not APP_PIN          # local dev with no secrets set
    return given.strip() == API_KEY


def sorted_desc(rows):
    return sorted(rows, key=lambda r: (r["date"], r["id"]), reverse=True)


# ---------------------------------------------------------------- auth + setup gate
OPEN_ENDPOINTS = {"login", "static", "manifest", "api_capture", "api_quick", "health"}


@app.before_request
def gate():
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    if APP_PIN and not session.get("ok"):
        return redirect(url_for("login", next=request.path))
    if request.endpoint not in ("setup", "logout") and not store.meta("start_date"):
        return redirect(url_for("setup"))
    return None


@app.context_processor
def inject():
    return {"labels": L.labels(store), "roles": L.ROLES, "accounts_list": L.ACCOUNTS,
            "expense_cats": L.EXPENSE_CATS, "income_cats": L.INCOME_CATS,
            "today": today(), "f": L.f, "no_pin": not APP_PIN,
            "inbox_count": sum(1 for r in store.rows("ledger") if r["status"] == "inbox")}


@app.template_filter("usd")
def usd(x, sign=False):
    v = L.f(x)
    s = f"${abs(v):,.2f}"
    if v < 0:
        return "−" + s
    return ("+" + s) if sign and v > 0 else s


@app.template_filter("nice_date")
def nice_date(s):
    d = L.parse_date(s)
    if not d:
        return s
    t = today()
    if d == t:
        return "Today"
    if d == t - timedelta(days=1):
        return "Yesterday"
    label = f"{d.strftime('%b')} {d.day}"      # portable (Windows has no %-d)
    return label if d.year == t.year else f"{label}, {d.year}"


# ---------------------------------------------------------------- automatic chores
def post_recurring():
    t = today()
    ym = t.strftime("%Y-%m")
    start = start_date()
    for r in store.rows("recurring"):
        if r["last_posted"] == ym:
            continue
        due = date(t.year, t.month, min(int(L.f(r["day"]) or 1), L.last_day(t.year, t.month).day))
        if t < due:
            continue
        if start and due < start:
            store.update("recurring", dict(r, last_posted=ym))
            continue
        e = {"kind": r["kind"], "amount": r["amount"], "category": r["category"],
             "note": r["note"], "account": r["account"], "to_account": r["to_account"], "date": due}
        store.append("ledger", make_row(e, "recurring", "ok" if r["auto"] == "1" else "inbox"))
        store.update("recurring", dict(r, last_posted=ym))


def maybe_sync_splitwise(force=False):
    if not SW.enabled():
        return None
    last = store.meta("sw_last")
    if not force and last:
        try:
            if datetime.now(TZ) - datetime.fromisoformat(last) < SYNC_EVERY:
                return None
        except ValueError:
            pass
    store.set_meta("sw_last", now_iso())
    try:
        imported, merged = SW.sync(store, start_date() or today(), new_id, now_iso())
        store.set_meta("sw_error", "")
        return imported, merged
    except Exception as ex:   # never break the dashboard because Splitwise is down
        store.set_meta("sw_error", str(ex)[:160])
        return None


# ---------------------------------------------------------------- pages
@app.route("/")
def home():
    post_recurring()
    res = maybe_sync_splitwise()
    if res and (res[0] or res[1]):
        flash(f"Splitwise: {res[0]} new, {res[1]} matched to Apple Pay — check the inbox.", "info")

    t = today()
    rows = store.rows("ledger")
    inbox = sorted_desc([r for r in rows if r["status"] == "inbox"])
    recent = sorted_desc([r for r in rows if r["status"] == "ok"])[:20]

    bal = L.balances(store)
    this = L.month_stats(store, t.year, t.month)
    py, pm = L.add_months(t.year, t.month, -1)
    prev_same_day = 0.0
    for r in L.month_rows(store, py, pm):
        d = L.parse_date(r["date"])
        if d.day <= t.day:
            prev_same_day += L.effects(r)[1]

    last_check = L.parse_date(store.meta("last_reconcile")) or start_date() or t
    return render_template(
        "home.html", inbox=inbox, recent=recent, bal=bal, total=sum(bal.values()),
        this=this, prev_same_day=prev_same_day, prev_name=date(py, pm, 1).strftime("%b"),
        month_name=t.strftime("%B"), days_since_check=(t - last_check).days,
        sw_on=SW.enabled(), sw_error=store.meta("sw_error"), sw_last=store.meta("sw_last"))


@app.route("/activity")
def activity():
    kind = request.args.get("kind", "")
    q = request.args.get("q", "").strip().lower()
    frm, to = request.args.get("from", ""), request.args.get("to", "")
    cat = request.args.get("cat", "")
    rows = [r for r in store.rows("ledger") if r["status"] == "ok"]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if cat:
        rows = [r for r in rows if r["category"] == cat]
    if frm:
        rows = [r for r in rows if r["date"] >= frm]
    if to:
        rows = [r for r in rows if r["date"] <= to]
    if q:
        rows = [r for r in rows if q in (r["note"] + " " + r["merchant"] + " " + r["category"]).lower()]
    rows = sorted_desc(rows)
    spend = sum(L.effects(r)[1] for r in rows)
    income = sum(L.effects(r)[2] for r in rows)
    return render_template("activity.html", rows=rows, kind=kind, q=q, frm=frm, to=to,
                           cat=cat, spend=spend, income=income)


@app.route("/insights")
def insights():
    t = today()
    try:
        y, m = [int(x) for x in request.args.get("m", "").split("-")]
        date(y, m, 1)
    except ValueError:
        y, m = t.year, t.month
    st = L.month_stats(store, y, m)
    current = (y, m) == (t.year, t.month)
    days_in = L.last_day(y, m).day
    elapsed = t.day if current else days_in
    start = start_date()
    if start and (start.year, start.month) == (y, m):
        elapsed = max(1, (min(t, L.last_day(y, m)) - start).days + 1)

    budgets = {b["category"]: L.f(b["amount"]) for b in store.rows("budgets")}
    cats = sorted(st["by_cat"].items(), key=lambda kv: -kv[1])
    for c in budgets:
        if c not in st["by_cat"]:
            cats.append((c, 0.0))
    merchants = sorted(st["by_merchant"].items(), key=lambda kv: -kv[1])[:5]

    trend = []
    for k in range(-5, 1):
        yy, mm = L.add_months(y, m, k)
        if start and (yy, mm) < (start.year, start.month):
            continue                       # nothing tracked before the fresh start
        s = L.month_stats(store, yy, mm)
        trend.append({"label": date(yy, mm, 1).strftime("%b"), "spend": s["spend"],
                      "income": s["income"], "current": k == 0})
    tmax = max([1.0] + [x["spend"] for x in trend] + [x["income"] for x in trend])

    py, pm = L.add_months(y, m, -1)
    prev = L.month_stats(store, py, pm)
    pace = None
    if current and prev["spend"]:
        prev_same = sum(L.effects(r)[1] for r in L.month_rows(store, py, pm)
                        if L.parse_date(r["date"]).day <= t.day)
        if prev_same:
            pace = (st["spend"] - prev_same) / prev_same * 100

    ny, nm = L.add_months(y, m, 1)
    return render_template(
        "insights.html", st=st, y=y, m=m, month_label=date(y, m, 1).strftime("%B %Y"),
        current=current, elapsed=elapsed, days_in=days_in, cats=cats, budgets=budgets,
        merchants=merchants, trend=trend, tmax=tmax, pace=pace, prev=prev,
        prev_label=date(py, pm, 1).strftime("%b"),
        prev_link=f"{py}-{pm:02d}", next_link=f"{ny}-{nm:02d}" if (ny, nm) <= (t.year, t.month) else None,
        snaps=L.snapshots(store, start or t, t),
        dow=list(zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], st["by_dow"])))


# ---------------------------------------------------------------- quick add + undo
@app.route("/quick", methods=["POST"])
def quick():
    e = parse(request.form.get("text"), store.rows("rules"), today())
    if e.get("error"):
        flash(e["error"], "error")
        return redirect(url_for("home"))
    row = make_row(e, "quick", "ok")
    store.append("ledger", row)
    if "#" in (request.form.get("text") or ""):
        learn(row["note"], row["category"])
    flash(describe(row, L.labels(store)), "ok:" + row["id"])
    return redirect(url_for("home"))


@app.route("/undo/<rid>", methods=["POST"])
def undo(rid):
    store.delete("ledger", rid)
    flash("Undone.", "info")
    return redirect(request.referrer or url_for("home"))


# ---------------------------------------------------------------- inbox
@app.route("/inbox/<rid>/ok", methods=["POST"])
def inbox_ok(rid):
    r = store.find("ledger", rid)
    if r:
        cat = request.form.get("category") or r["category"]
        amt = request.form.get("amount")
        r = dict(r, status="ok", category=cat, amount=money(amt) if amt else r["amount"])
        if request.form.get("account"):
            r["account"] = request.form["account"]
        store.update("ledger", r)
        if r["kind"] in ("expense", "split"):
            learn(r["merchant"] or r["note"], cat)
    return redirect(url_for("home") + "#inbox")


@app.route("/inbox/<rid>/drop", methods=["POST"])
def inbox_drop(rid):
    store.delete("ledger", rid)
    return redirect(url_for("home") + "#inbox")


@app.route("/inbox/all", methods=["POST"])
def inbox_all():
    for r in [r for r in store.rows("ledger") if r["status"] == "inbox"]:
        store.update("ledger", dict(r, status="ok"))
    flash("Inbox cleared.", "info")
    return redirect(url_for("home"))


# ---------------------------------------------------------------- edit / delete
@app.route("/entry/<rid>/edit", methods=["POST"])
def edit_entry(rid):
    r = store.find("ledger", rid)
    if r:
        fm = request.form
        old_cat = r["category"]
        r = dict(r, date=fm.get("date") or r["date"], note=fm.get("note", r["note"]).strip(),
                 amount=money(fm.get("amount") or r["amount"]),
                 category=fm.get("category", r["category"]),
                 account=fm.get("account") or r["account"])
        if r["kind"] == "split" and fm.get("your_share"):
            r["your_share"] = money(fm["your_share"])
        if r["kind"] == "transfer" and fm.get("to_account"):
            r["to_account"] = fm["to_account"]
        store.update("ledger", r)
        if r["category"] != old_cat and r["kind"] in ("expense", "split"):
            learn(r["merchant"] or r["note"], r["category"])
        flash("Saved.", "info")
    return redirect(request.referrer or url_for("home"))


@app.route("/entry/<rid>/delete", methods=["POST"])
def delete_entry(rid):
    store.delete("ledger", rid)
    flash("Deleted.", "info")
    return redirect(request.referrer or url_for("home"))


# ---------------------------------------------------------------- weekly balance check
@app.route("/check", methods=["GET", "POST"])
def check():
    bal = L.balances(store)
    if request.method == "POST":
        made = []
        for a in L.ACCOUNTS:
            val = request.form.get(a, "").strip()
            if val == "":
                continue
            diff = round(L.f(val) - bal[a], 2)
            if abs(diff) >= 0.01:
                row = make_row({"kind": "adjust", "amount": diff, "account": a,
                                "category": "Untracked",
                                "note": "Untracked spending" if diff < 0 else "Untracked money in"},
                               "check", "ok")
                store.append("ledger", row)
                made.append(f"{L.labels(store)[a]} {usd(diff, True)}")
        store.set_meta("last_reconcile", today().isoformat())
        flash(("Balanced. Adjusted: " + ", ".join(made)) if made else "All accounts match. Nice.", "info")
        return redirect(url_for("home"))
    return render_template("check.html", bal=bal)


# ---------------------------------------------------------------- settings
@app.route("/settings")
def settings():
    return render_template(
        "settings.html", opening=L.opening_balances(store), cards=store.rows("cards"),
        recurring=store.rows("recurring"), budgets=store.rows("budgets"),
        rules=sorted(store.rows("rules"), key=lambda r: r["key"]), start=start_date(),
        sw_on=SW.enabled(), sw_last=store.meta("sw_last"), sw_error=store.meta("sw_error"),
        api_ready=bool(API_KEY), base_url=request.url_root.rstrip("/"))


@app.route("/settings/accounts", methods=["POST"])
def settings_accounts():
    for a in L.ACCOUNTS:
        row = store.find("accounts", a) or {"name": a, "role": L.ROLES[a], "opening": "0", "label": ""}
        row = dict(row, label=request.form.get(f"label_{a}", row["label"]).strip(),
                   opening=money(request.form.get(f"opening_{a}", row["opening"])))
        store.upsert("accounts", row)
    flash("Accounts saved.", "info")
    return redirect(url_for("settings"))


@app.route("/settings/card", methods=["POST"])
def settings_card():
    match = request.form.get("match", "").strip()
    if match:
        store.upsert("cards", {"match": match, "account": request.form.get("account", L.SPEND_ACC)})
    return redirect(url_for("settings") + "#cards")


@app.route("/settings/recurring", methods=["POST"])
def settings_recurring():
    fm = request.form
    if L.f(fm.get("amount")) > 0:
        kind = fm.get("kind", "expense")
        store.append("recurring", {
            "id": new_id(), "kind": kind, "amount": money(fm["amount"]),
            "category": fm.get("category", "") if kind != "transfer" else "",
            "note": fm.get("note", "").strip() or fm.get("category", "Recurring"),
            "account": fm.get("account") or (L.INCOME_ACC if kind == "income" else L.SPEND_ACC),
            "to_account": fm.get("to_account", "") if kind == "transfer" else "",
            "day": str(max(1, min(31, int(L.f(fm.get("day")) or 1)))),
            "auto": "1" if fm.get("auto") else "0", "last_posted": ""})
    return redirect(url_for("settings") + "#recurring")


@app.route("/settings/budget", methods=["POST"])
def settings_budget():
    if request.form.get("category") and L.f(request.form.get("amount")) > 0:
        store.upsert("budgets", {"category": request.form["category"],
                                 "amount": money(request.form["amount"])})
    return redirect(url_for("settings") + "#budgets")


@app.route("/settings/<tab>/<key>/delete", methods=["POST"])
def settings_delete(tab, key):
    if tab in ("cards", "recurring", "budgets", "rules"):
        store.delete(tab, key)
    return redirect(url_for("settings") + "#" + tab)


@app.route("/settings/sync", methods=["POST"])
def settings_sync():
    res = maybe_sync_splitwise(force=True)
    if res:
        flash(f"Splitwise: {res[0]} new, {res[1]} matched to Apple Pay.", "info")
    else:
        flash("Splitwise sync failed: " + (store.meta("sw_error") or "token not set"), "error")
    return redirect(url_for("home"))


# ---------------------------------------------------------------- first run
@app.route("/setup", methods=["GET", "POST"])
def setup():
    if request.method == "POST":
        for a in L.ACCOUNTS:
            store.upsert("accounts", {"name": a, "role": L.ROLES[a],
                                      "opening": money(request.form.get(f"opening_{a}") or 0),
                                      "label": request.form.get(f"label_{a}", "").strip()})
        store.set_meta("start_date", today().isoformat())
        store.set_meta("last_reconcile", today().isoformat())
        flash("You're set. Everything from today is tracked.", "info")
        return redirect(url_for("home"))
    return render_template("setup.html")


# ---------------------------------------------------------------- login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if APP_PIN and request.form.get("pin", "").strip() == APP_PIN:
            session.permanent = True
            session["ok"] = True
            nxt = request.args.get("next", "/")
            return redirect(nxt if nxt.startswith("/") else "/")
        flash("Wrong PIN.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- iPhone Shortcut API
def _json_or_form():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else request.values


@app.route("/api/capture", methods=["POST"])
def api_capture():
    """Apple Pay Wallet automation: {amount, merchant, card, key}."""
    if not api_key_ok():
        return jsonify(ok=False, message="Bad key"), 401
    d = _json_or_form()
    amount = L.f(d.get("amount"))
    merchant = str(d.get("merchant") or "").strip() or "Apple Pay purchase"
    if amount <= 0:
        return jsonify(ok=False, message="No amount received"), 400
    cat, learned = L.guess_category(merchant, store.rows("rules"))
    row = make_row({"kind": "expense", "amount": amount, "merchant": merchant[:80],
                    "note": merchant[:80], "category": cat,
                    "account": account_for_card(d.get("card"))},
                   "applepay", "ok" if learned else "inbox")
    store.append("ledger", row)
    msg = describe(row, L.labels(store))
    return jsonify(ok=True, status=row["status"],
                   message=msg if learned else msg + " · tap to confirm in Rut Finance")


@app.route("/api/quick", methods=["POST"])
def api_quick():
    """Siri / Shortcut: {text: 'lunch 12', key}."""
    if not api_key_ok():
        return jsonify(ok=False, message="Bad key"), 401
    e = parse(_json_or_form().get("text"), store.rows("rules"), today())
    if e.get("error"):
        return jsonify(ok=False, message=e["error"]), 400
    row = make_row(e, "siri", "ok")
    store.append("ledger", row)
    return jsonify(ok=True, message="Logged " + describe(row, L.labels(store)))


# ---------------------------------------------------------------- misc
@app.route("/manifest.json")
def manifest():
    return jsonify(name="Rut Finance", short_name="Rut Finance", start_url="/", display="standalone",
                   background_color="#f5f1e8", theme_color="#f5f1e8",
                   icons=[{"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}])


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    app.run(debug=True)
