# from flask import Flask, render_template, request, redirect
# from flask_sqlalchemy import SQLAlchemy
# from datetime import datetime, date
# import io
# import base64
# from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
# from matplotlib.figure import Figure

# app = Flask(__name__)
# app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///finance.db"
# app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# db = SQLAlchemy(app)


# # ---------- Constants ----------
# INCOME_ACCOUNT = "Account 3"
# EXPENSE_ACCOUNT = "Account 1"
# SPLITWISE_ACCOUNT = "Account 4"
# DEFAULT_ACCOUNTS = ["Account 1", "Account 2", "Account 3", "Account 4"]
# DEFAULT_EXPENSE_CATS = ["Food", "Transportation", "Entertainment", "Shopping", "Utilities", "Other"]
# DEFAULT_INCOME_CATS = ["Salary", "Freelance", "Investment", "Gift", "Other"]


# # ---------- Models ----------
# class Account(db.Model):
#     name = db.Column(db.String(50), primary_key=True)
#     opening_balance = db.Column(db.Float, default=0.0)


# class Category(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(50), nullable=False)
#     kind = db.Column(db.String(20), nullable=False)  # "expense" or "income"


# class Expense(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     date = db.Column(db.String(10), nullable=False)
#     description = db.Column(db.String(200), nullable=False)
#     amount = db.Column(db.Float, nullable=False)
#     category = db.Column(db.String(50), nullable=False)
#     account = db.Column(db.String(50), nullable=False)
#     is_split = db.Column(db.Boolean, default=False)
#     split_id = db.Column(db.Integer, db.ForeignKey("split.id"), nullable=True)
#     your_share = db.Column(db.Float, nullable=True)
#     direction = db.Column(db.String(20), nullable=True)


# class Income(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     date = db.Column(db.String(10), nullable=False)
#     description = db.Column(db.String(200), nullable=False)
#     amount = db.Column(db.Float, nullable=False)
#     category = db.Column(db.String(50), nullable=False)
#     account = db.Column(db.String(50), nullable=False)


# class Transfer(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     date = db.Column(db.String(10), nullable=False)
#     from_acc = db.Column("from_account", db.String(50), nullable=False)
#     to_acc = db.Column("to_account", db.String(50), nullable=False)
#     amount = db.Column(db.Float, nullable=False)
#     note = db.Column(db.String(200), default="")
#     is_settlement = db.Column(db.Boolean, default=False)
#     split_id = db.Column(db.Integer, db.ForeignKey("split.id"), nullable=True)


# class Split(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     date = db.Column(db.String(10), nullable=False)
#     description = db.Column(db.String(200), nullable=False)
#     total = db.Column(db.Float, nullable=False)
#     your_share = db.Column(db.Float, nullable=False)
#     other_share = db.Column(db.Float, nullable=False)
#     category = db.Column(db.String(50), nullable=False)
#     direction = db.Column(db.String(20), nullable=False)
#     status = db.Column(db.String(20), default="pending")
#     settle_date = db.Column(db.String(10), nullable=True)
#     settle_account = db.Column(db.String(50), nullable=True)


# # ---------- Init DB ----------
# def init_db():
#     with app.app_context():
#         db.create_all()

#         for name in DEFAULT_ACCOUNTS:
#             if not Account.query.get(name):
#                 db.session.add(Account(name=name, opening_balance=0.0))

#         if Category.query.count() == 0:
#             for n in DEFAULT_EXPENSE_CATS:
#                 db.session.add(Category(name=n, kind="expense"))
#             for n in DEFAULT_INCOME_CATS:
#                 db.session.add(Category(name=n, kind="income"))

#         db.session.commit()


# # ---------- Helpers ----------
# def get_categories(kind):
#     return [c.name for c in Category.query.filter_by(kind=kind).order_by(Category.name).all()]


# def get_opening_balances():
#     return {a.name: a.opening_balance for a in Account.query.order_by(Account.name).all()}


# def get_account_balances():
#     opening = get_opening_balances()
#     balances = dict(opening)

#     for i in Income.query.all():
#         balances[i.account] = balances.get(i.account, 0) + i.amount

#     for e in Expense.query.all():
#         balances[e.account] = balances.get(e.account, 0) - e.amount

#     for t in Transfer.query.all():
#         balances[t.from_acc] = balances.get(t.from_acc, 0) - t.amount
#         balances[t.to_acc]   = balances.get(t.to_acc, 0)   + t.amount

#     # Splitwise virtual — all splits count (pending + settled)
#     for s in Split.query.all():
#         if s.direction == "you_paid":
#             balances[SPLITWISE_ACCOUNT] = balances.get(SPLITWISE_ACCOUNT, 0) + s.other_share
#         else:
#             balances[SPLITWISE_ACCOUNT] = balances.get(SPLITWISE_ACCOUNT, 0) - s.your_share

#     return balances


# def get_totals():
#     balances = get_account_balances()
#     opening = get_opening_balances()

#     real_expense = sum(e.amount for e in Expense.query.filter_by(is_split=False).all())
#     real_expense += sum(s.your_share for s in Split.query.all())

#     splitwise_net = 0
#     for s in Split.query.filter_by(status="pending").all():
#         if s.direction == "you_paid":
#             splitwise_net += s.other_share
#         else:
#             splitwise_net -= s.your_share

#     return {
#         "opening": sum(opening.values()),
#         "income": sum(i.amount for i in Income.query.all()),
#         "expenses": real_expense,
#         "splitwise_net": splitwise_net,
#         "balance": sum(balances.values()),
#     }


# # ---------- Home ----------
# @app.route("/")
# def home():
#     today = date.today().strftime("%Y-%m-%d")
#     return render_template(
#         "add_expense.html",
#         expenses=Expense.query.order_by(Expense.id.desc()).all(),
#         incomes=Income.query.order_by(Income.id.desc()).all(),
#         transfers=Transfer.query.order_by(Transfer.id.desc()).all(),
#         splits=Split.query.order_by(Split.id.desc()).all(),
#         today=today,
#         categories=get_categories("expense"),
#         income_categories=get_categories("income"),
#         accounts=get_account_balances(),
#         account_names=list(get_opening_balances().keys()),
#         totals=get_totals(),
#         income_account=INCOME_ACCOUNT,
#         expense_account=EXPENSE_ACCOUNT,
#         splitwise_account=SPLITWISE_ACCOUNT,
#     )


# # ---------- Expenses ----------
# @app.route("/add", methods=["POST"])
# def add_expense():
#     total = float(request.form["amount"])
#     is_split = request.form.get("is_split") == "on"

#     if is_split:
#         direction = request.form.get("direction", "you_paid")
#         your_share = float(request.form["your_share"])
#         other_share = total - your_share

#         split = Split(
#             date=request.form["date"],
#             description=request.form["description"],
#             total=total,
#             your_share=your_share,
#             other_share=other_share,
#             category=request.form["category"],
#             direction=direction,
#             status="pending",
#         )
#         db.session.add(split)
#         db.session.flush()

#         expense = Expense(
#             date=request.form["date"],
#             description=request.form["description"],
#             amount=total if direction == "you_paid" else 0,
#             category=request.form["category"],
#             account=EXPENSE_ACCOUNT,
#             is_split=True,
#             split_id=split.id,
#             your_share=your_share,
#             direction=direction,
#         )
#         db.session.add(expense)
#     else:
#         db.session.add(Expense(
#             date=request.form["date"],
#             description=request.form["description"],
#             amount=total,
#             category=request.form["category"],
#             account=EXPENSE_ACCOUNT,
#             is_split=False,
#         ))

#     db.session.commit()
#     return redirect("/")


# @app.route("/edit/<int:id>", methods=["GET", "POST"])
# def edit_expense(id):
#     expense = Expense.query.get_or_404(id)
#     if request.method == "POST":
#         expense.date = request.form["date"]
#         expense.description = request.form["description"]
#         expense.amount = float(request.form["amount"])
#         expense.category = request.form["category"]
#         db.session.commit()
#         return redirect("/")
#     return render_template("edit_expense.html", expense=expense, categories=get_categories("expense"))


# @app.route("/delete/<int:id>")
# def delete_expense(id):
#     expense = Expense.query.get_or_404(id)
#     if expense.is_split:
#         return redirect("/")
#     db.session.delete(expense)
#     db.session.commit()
#     return redirect("/")


# # ---------- Splitwise ----------
# @app.route("/settle_split/<int:split_id>", methods=["POST"])
# def settle_split(split_id):
#     s = Split.query.get_or_404(split_id)
#     if s.status != "pending":
#         return redirect("/")

#     settle_account = request.form.get("settle_account", EXPENSE_ACCOUNT)
#     s.status = "settled"
#     s.settle_date = date.today().strftime("%Y-%m-%d")
#     s.settle_account = settle_account

#     if s.direction == "you_paid":
#         db.session.add(Transfer(
#             date=s.settle_date,
#             from_acc=SPLITWISE_ACCOUNT,
#             to_acc=settle_account,
#             amount=s.other_share,
#             note=f"Splitwise settlement: {s.description}",
#             is_settlement=True,
#             split_id=split_id,
#         ))
#     else:
#         db.session.add(Transfer(
#             date=s.settle_date,
#             from_acc=settle_account,
#             to_acc=SPLITWISE_ACCOUNT,
#             amount=s.your_share,
#             note=f"Splitwise settlement: {s.description}",
#             is_settlement=True,
#             split_id=split_id,
#         ))

#     db.session.commit()
#     return redirect("/")


# @app.route("/unsettle_split/<int:split_id>")
# def unsettle_split(split_id):
#     s = Split.query.get_or_404(split_id)
#     if s.status != "settled":
#         return redirect("/")

#     Transfer.query.filter_by(is_settlement=True, split_id=split_id).delete()
#     s.status = "pending"
#     s.settle_date = None
#     s.settle_account = None
#     db.session.commit()
#     return redirect("/")


# @app.route("/delete_split/<int:split_id>")
# def delete_split(split_id):
#     s = Split.query.get_or_404(split_id)
#     Transfer.query.filter_by(is_settlement=True, split_id=split_id).delete()
#     Expense.query.filter_by(is_split=True, split_id=split_id).delete()
#     db.session.delete(s)
#     db.session.commit()
#     return redirect("/")


# # ---------- Income ----------
# @app.route("/add_income", methods=["POST"])
# def add_income():
#     db.session.add(Income(
#         date=request.form["date"],
#         description=request.form["description"],
#         amount=float(request.form["amount"]),
#         category=request.form["category"],
#         account=INCOME_ACCOUNT,
#     ))
#     db.session.commit()
#     return redirect("/")


# @app.route("/delete_income/<int:id>")
# def delete_income(id):
#     income = Income.query.get_or_404(id)
#     db.session.delete(income)
#     db.session.commit()
#     return redirect("/")


# # ---------- Transfers ----------
# @app.route("/add_transfer", methods=["POST"])
# def add_transfer():
#     f = request.form["from"]
#     t = request.form["to"]
#     if f != t:
#         db.session.add(Transfer(
#             date=request.form["date"],
#             from_acc=f,
#             to_acc=t,
#             amount=float(request.form["amount"]),
#             note=request.form.get("note", ""),
#         ))
#         db.session.commit()
#     return redirect("/")


# @app.route("/delete_transfer/<int:id>")
# def delete_transfer(id):
#     transfer = Transfer.query.get_or_404(id)
#     if transfer.is_settlement:
#         return redirect("/")
#     db.session.delete(transfer)
#     db.session.commit()
#     return redirect("/")


# # ---------- Accounts ----------
# @app.route("/accounts", methods=["GET", "POST"])
# def manage_accounts():
#     if request.method == "POST":
#         for acc in Account.query.all():
#             acc.opening_balance = float(request.form.get(acc.name, 0))
#         db.session.commit()
#         return redirect("/")
#     return render_template("accounts.html", accounts=get_opening_balances())


# # ---------- Categories ----------
# @app.route("/categories", methods=["GET", "POST"])
# def manage_categories():
#     if request.method == "POST":
#         name = request.form["name"].strip()
#         kind = request.form["kind"]
#         if name and not Category.query.filter_by(name=name, kind=kind).first():
#             db.session.add(Category(name=name, kind=kind))
#             db.session.commit()
#         return redirect("/categories")
#     return render_template(
#         "categories.html",
#         expense_cats=Category.query.filter_by(kind="expense").order_by(Category.name).all(),
#         income_cats=Category.query.filter_by(kind="income").order_by(Category.name).all(),
#     )


# @app.route("/categories/delete/<int:id>")
# def delete_category(id):
#     c = Category.query.get_or_404(id)
#     in_use_exp = Expense.query.filter_by(category=c.name).first()
#     in_use_inc = Income.query.filter_by(category=c.name).first()
#     in_use_split = Split.query.filter_by(category=c.name).first()
#     if not in_use_exp and not in_use_inc and not in_use_split:
#         db.session.delete(c)
#         db.session.commit()
#     return redirect("/categories")


# @app.route("/categories/rename/<int:id>", methods=["POST"])
# def rename_category(id):
#     c = Category.query.get_or_404(id)
#     new_name = request.form["new_name"].strip()
#     if new_name and new_name != c.name:
#         Expense.query.filter_by(category=c.name).update({"category": new_name})
#         Income.query.filter_by(category=c.name).update({"category": new_name})
#         Split.query.filter_by(category=c.name).update({"category": new_name})
#         c.name = new_name
#         db.session.commit()
#     return redirect("/categories")


# # ---------- Insights ----------
# @app.route("/insights")
# def insights():
#     now = datetime.now()
#     month = int(request.args.get("month", now.month))
#     year = int(request.args.get("year", now.year))

#     month_expenses = []
#     for e in Expense.query.all():
#         d = datetime.strptime(e.date, "%Y-%m-%d")
#         if d.month == month and d.year == year:
#             amount = e.your_share if e.is_split else e.amount
#             month_expenses.append({
#                 "date": e.date,
#                 "description": e.description,
#                 "category": e.category,
#                 "amount": amount,
#                 "is_split": e.is_split,
#             })

#     total = sum(e["amount"] for e in month_expenses)

#     category_totals = {}
#     for e in month_expenses:
#         category_totals[e["category"]] = category_totals.get(e["category"], 0) + e["amount"]

#     fig = Figure(figsize=(7, 5))
#     ax = fig.add_subplot(1, 1, 1)
#     if category_totals:
#         colors = ["#3182ce", "#38a169", "#d69e2e", "#e53e3e", "#805ad5", "#0987a0", "#dd6b20", "#319795"]
#         ax.pie(
#             list(category_totals.values()),
#             labels=list(category_totals.keys()),
#             autopct="%1.1f%%",
#             colors=colors[:len(category_totals)],
#             startangle=90,
#             wedgeprops={"edgecolor": "white", "linewidth": 2},
#         )
#     ax.set_title(f"Expenses by Category — {month}/{year}", fontsize=14, fontweight="bold")

#     png = io.BytesIO()
#     FigureCanvas(fig).print_png(png)
#     chart = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode("utf8")

#     return render_template(
#         "insights.html",
#         month=month,
#         year=year,
#         expenses=month_expenses,
#         total=total,
#         chart=chart,
#         category_totals=category_totals,
#     )


# if __name__ == "__main__":
#     init_db()
#     app.run(debug=True)



from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from calendar import monthrange
import io
import os
import base64
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure

app = Flask(__name__)

# DB path — works locally and on Render (persistent disk mount)
db_path = os.environ.get("DATABASE_PATH", "finance.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# ---------- Constants ----------
INCOME_ACCOUNT = "Account 3"
EXPENSE_ACCOUNT = "Account 1"
SPLITWISE_ACCOUNT = "Account 4"
DEFAULT_ACCOUNTS = ["Account 1", "Account 2", "Account 3", "Account 4"]
DEFAULT_EXPENSE_CATS = ["Food", "Transportation", "Entertainment", "Shopping", "Utilities", "Other"]
DEFAULT_INCOME_CATS = ["Salary", "Freelance", "Investment", "Gift", "Other"]


# ---------- Models ----------
class Account(db.Model):
    name = db.Column(db.String(50), primary_key=True)
    opening_balance = db.Column(db.Float, default=0.0)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    kind = db.Column(db.String(20), nullable=False)


class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    account = db.Column(db.String(50), nullable=False)
    is_split = db.Column(db.Boolean, default=False)
    split_id = db.Column(db.Integer, db.ForeignKey("split.id"), nullable=True)
    your_share = db.Column(db.Float, nullable=True)
    direction = db.Column(db.String(20), nullable=True)


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    account = db.Column(db.String(50), nullable=False)


class Transfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    from_acc = db.Column("from_account", db.String(50), nullable=False)
    to_acc = db.Column("to_account", db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(200), default="")
    is_settlement = db.Column(db.Boolean, default=False)
    split_id = db.Column(db.Integer, db.ForeignKey("split.id"), nullable=True)


class Split(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    total = db.Column(db.Float, nullable=False)
    your_share = db.Column(db.Float, nullable=False)
    other_share = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    direction = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="pending")
    settle_date = db.Column(db.String(10), nullable=True)
    settle_account = db.Column(db.String(50), nullable=True)


# ---------- Init DB ----------
def init_db():
    with app.app_context():
        db.create_all()
        for name in DEFAULT_ACCOUNTS:
            if not Account.query.get(name):
                db.session.add(Account(name=name, opening_balance=0.0))
        if Category.query.count() == 0:
            for n in DEFAULT_EXPENSE_CATS:
                db.session.add(Category(name=n, kind="expense"))
            for n in DEFAULT_INCOME_CATS:
                db.session.add(Category(name=n, kind="income"))
        db.session.commit()


# ---------- Helpers ----------
def get_categories(kind):
    return [c.name for c in Category.query.filter_by(kind=kind).order_by(Category.name).all()]


def get_opening_balances():
    return {a.name: a.opening_balance for a in Account.query.order_by(Account.name).all()}


def get_account_balances():
    opening = get_opening_balances()
    balances = dict(opening)

    for i in Income.query.all():
        balances[i.account] = balances.get(i.account, 0) + i.amount

    for e in Expense.query.all():
        balances[e.account] = balances.get(e.account, 0) - e.amount

    for t in Transfer.query.all():
        balances[t.from_acc] = balances.get(t.from_acc, 0) - t.amount
        balances[t.to_acc]   = balances.get(t.to_acc, 0)   + t.amount

    for s in Split.query.all():
        if s.direction == "you_paid":
            balances[SPLITWISE_ACCOUNT] = balances.get(SPLITWISE_ACCOUNT, 0) + s.other_share
        else:
            balances[SPLITWISE_ACCOUNT] = balances.get(SPLITWISE_ACCOUNT, 0) - s.your_share

    return balances


def get_totals():
    balances = get_account_balances()
    opening = get_opening_balances()

    real_expense = sum(e.amount for e in Expense.query.filter_by(is_split=False).all())
    real_expense += sum(s.your_share for s in Split.query.all())

    splitwise_net = 0
    for s in Split.query.filter_by(status="pending").all():
        if s.direction == "you_paid":
            splitwise_net += s.other_share
        else:
            splitwise_net -= s.your_share

    return {
        "opening": sum(opening.values()),
        "income": sum(i.amount for i in Income.query.all()),
        "expenses": real_expense,
        "splitwise_net": splitwise_net,
        "balance": sum(balances.values()),
    }


def get_month_spending(year, month):
    """Sum real expenses for a given month (counts your_share only for splits)."""
    total = 0
    by_category = {}
    for e in Expense.query.all():
        d = datetime.strptime(e.date, "%Y-%m-%d")
        if d.year == year and d.month == month:
            amt = e.your_share if e.is_split else e.amount
            total += amt
            by_category[e.category] = by_category.get(e.category, 0) + amt
    return total, by_category


def get_budgets_with_progress(year, month):
    """For each budget, attach current spending for the month."""
    _, by_category = get_month_spending(year, month)
    result = []
    for b in Budget.query.order_by(Budget.category).all():
        spent = by_category.get(b.category, 0)
        pct = (spent / b.amount * 100) if b.amount > 0 else 0
        status = "green"
        if pct >= 100:
            status = "red"
        elif pct >= 75:
            status = "yellow"
        result.append({
            "id": b.id,
            "category": b.category,
            "amount": b.amount,
            "spent": spent,
            "remaining": b.amount - spent,
            "pct": min(pct, 100),
            "pct_raw": pct,
            "status": status,
        })
    return result


def get_mom_comparison():
    """Current month vs. previous month spending."""
    today = date.today()
    cur_total, _ = get_month_spending(today.year, today.month)

    # Previous month
    if today.month == 1:
        prev_year, prev_month = today.year - 1, 12
    else:
        prev_year, prev_month = today.year, today.month - 1
    prev_total, _ = get_month_spending(prev_year, prev_month)

    if prev_total > 0:
        change_pct = ((cur_total - prev_total) / prev_total) * 100
    else:
        change_pct = None  # nothing to compare to

    return {
        "current": cur_total,
        "previous": prev_total,
        "change_pct": change_pct,
        "prev_month_name": datetime(prev_year, prev_month, 1).strftime("%B"),
    }


# ---------- Home ----------
@app.route("/")
def home():
    today = date.today().strftime("%Y-%m-%d")
    today_date = date.today()

    # Search/filter params
    search = request.args.get("search", "").strip().lower()
    filter_category = request.args.get("filter_category", "")
    filter_from = request.args.get("filter_from", "")
    filter_to = request.args.get("filter_to", "")

    # Build filtered expense query
    expense_query = Expense.query
    if filter_category:
        expense_query = expense_query.filter_by(category=filter_category)
    if filter_from:
        expense_query = expense_query.filter(Expense.date >= filter_from)
    if filter_to:
        expense_query = expense_query.filter(Expense.date <= filter_to)

    expenses = expense_query.order_by(Expense.id.desc()).all()
    if search:
        expenses = [e for e in expenses if search in e.description.lower()]

    has_filters = bool(search or filter_category or filter_from or filter_to)

    return render_template(
        "add_expense.html",
        expenses=expenses,
        incomes=Income.query.order_by(Income.id.desc()).all(),
        transfers=Transfer.query.order_by(Transfer.id.desc()).all(),
        splits=Split.query.order_by(Split.id.desc()).all(),
        today=today,
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
        has_filters=has_filters,
    )


# ---------- Expenses ----------
@app.route("/add", methods=["POST"])
def add_expense():
    total = float(request.form["amount"])
    is_split = request.form.get("is_split") == "on"

    if is_split:
        direction = request.form.get("direction", "you_paid")
        your_share = float(request.form["your_share"])
        other_share = total - your_share

        split = Split(
            date=request.form["date"],
            description=request.form["description"],
            total=total,
            your_share=your_share,
            other_share=other_share,
            category=request.form["category"],
            direction=direction,
            status="pending",
        )
        db.session.add(split)
        db.session.flush()

        expense = Expense(
            date=request.form["date"],
            description=request.form["description"],
            amount=total if direction == "you_paid" else 0,
            category=request.form["category"],
            account=EXPENSE_ACCOUNT,
            is_split=True,
            split_id=split.id,
            your_share=your_share,
            direction=direction,
        )
        db.session.add(expense)
    else:
        db.session.add(Expense(
            date=request.form["date"],
            description=request.form["description"],
            amount=total,
            category=request.form["category"],
            account=EXPENSE_ACCOUNT,
            is_split=False,
        ))

    db.session.commit()
    return redirect("/")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_expense(id):
    expense = Expense.query.get_or_404(id)
    if request.method == "POST":
        expense.date = request.form["date"]
        expense.description = request.form["description"]
        expense.amount = float(request.form["amount"])
        expense.category = request.form["category"]
        db.session.commit()
        return redirect("/")
    return render_template("edit_expense.html", expense=expense, categories=get_categories("expense"))


@app.route("/delete/<int:id>")
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    if expense.is_split:
        return redirect("/")
    db.session.delete(expense)
    db.session.commit()
    return redirect("/")


# ---------- Splitwise ----------
@app.route("/settle_split/<int:split_id>", methods=["POST"])
def settle_split(split_id):
    s = Split.query.get_or_404(split_id)
    if s.status != "pending":
        return redirect("/")

    settle_account = request.form.get("settle_account", EXPENSE_ACCOUNT)
    s.status = "settled"
    s.settle_date = date.today().strftime("%Y-%m-%d")
    s.settle_account = settle_account

    if s.direction == "you_paid":
        db.session.add(Transfer(
            date=s.settle_date, from_acc=SPLITWISE_ACCOUNT, to_acc=settle_account,
            amount=s.other_share, note=f"Splitwise settlement: {s.description}",
            is_settlement=True, split_id=split_id,
        ))
    else:
        db.session.add(Transfer(
            date=s.settle_date, from_acc=settle_account, to_acc=SPLITWISE_ACCOUNT,
            amount=s.your_share, note=f"Splitwise settlement: {s.description}",
            is_settlement=True, split_id=split_id,
        ))

    db.session.commit()
    return redirect("/")


@app.route("/unsettle_split/<int:split_id>")
def unsettle_split(split_id):
    s = Split.query.get_or_404(split_id)
    if s.status != "settled":
        return redirect("/")
    Transfer.query.filter_by(is_settlement=True, split_id=split_id).delete()
    s.status = "pending"
    s.settle_date = None
    s.settle_account = None
    db.session.commit()
    return redirect("/")


@app.route("/delete_split/<int:split_id>")
def delete_split(split_id):
    s = Split.query.get_or_404(split_id)
    Transfer.query.filter_by(is_settlement=True, split_id=split_id).delete()
    Expense.query.filter_by(is_split=True, split_id=split_id).delete()
    db.session.delete(s)
    db.session.commit()
    return redirect("/")


# ---------- Income ----------
@app.route("/add_income", methods=["POST"])
def add_income():
    db.session.add(Income(
        date=request.form["date"],
        description=request.form["description"],
        amount=float(request.form["amount"]),
        category=request.form["category"],
        account=INCOME_ACCOUNT,
    ))
    db.session.commit()
    return redirect("/")


@app.route("/delete_income/<int:id>")
def delete_income(id):
    income = Income.query.get_or_404(id)
    db.session.delete(income)
    db.session.commit()
    return redirect("/")


# ---------- Transfers ----------
@app.route("/add_transfer", methods=["POST"])
def add_transfer():
    f = request.form["from"]
    t = request.form["to"]
    if f != t:
        db.session.add(Transfer(
            date=request.form["date"], from_acc=f, to_acc=t,
            amount=float(request.form["amount"]),
            note=request.form.get("note", ""),
        ))
        db.session.commit()
    return redirect("/")


@app.route("/delete_transfer/<int:id>")
def delete_transfer(id):
    transfer = Transfer.query.get_or_404(id)
    if transfer.is_settlement:
        return redirect("/")
    db.session.delete(transfer)
    db.session.commit()
    return redirect("/")


# ---------- Accounts ----------
@app.route("/accounts", methods=["GET", "POST"])
def manage_accounts():
    if request.method == "POST":
        for acc in Account.query.all():
            acc.opening_balance = float(request.form.get(acc.name, 0))
        db.session.commit()
        return redirect("/")
    return render_template("accounts.html", accounts=get_opening_balances())


# ---------- Categories ----------
@app.route("/categories", methods=["GET", "POST"])
def manage_categories():
    if request.method == "POST":
        name = request.form["name"].strip()
        kind = request.form["kind"]
        if name and not Category.query.filter_by(name=name, kind=kind).first():
            db.session.add(Category(name=name, kind=kind))
            db.session.commit()
        return redirect("/categories")
    return render_template(
        "categories.html",
        expense_cats=Category.query.filter_by(kind="expense").order_by(Category.name).all(),
        income_cats=Category.query.filter_by(kind="income").order_by(Category.name).all(),
    )


@app.route("/categories/delete/<int:id>")
def delete_category(id):
    c = Category.query.get_or_404(id)
    in_use = (
        Expense.query.filter_by(category=c.name).first()
        or Income.query.filter_by(category=c.name).first()
        or Split.query.filter_by(category=c.name).first()
    )
    if not in_use:
        # Also clean up any budget for this category
        Budget.query.filter_by(category=c.name).delete()
        db.session.delete(c)
        db.session.commit()
    return redirect("/categories")


@app.route("/categories/rename/<int:id>", methods=["POST"])
def rename_category(id):
    c = Category.query.get_or_404(id)
    new_name = request.form["new_name"].strip()
    if new_name and new_name != c.name:
        Expense.query.filter_by(category=c.name).update({"category": new_name})
        Income.query.filter_by(category=c.name).update({"category": new_name})
        Split.query.filter_by(category=c.name).update({"category": new_name})
        Budget.query.filter_by(category=c.name).update({"category": new_name})
        c.name = new_name
        db.session.commit()
    return redirect("/categories")


# ---------- Budgets ----------
@app.route("/budgets", methods=["GET", "POST"])
def manage_budgets():
    if request.method == "POST":
        category = request.form["category"]
        amount = float(request.form["amount"])
        existing = Budget.query.filter_by(category=category).first()
        if existing:
            existing.amount = amount
        else:
            db.session.add(Budget(category=category, amount=amount))
        db.session.commit()
        return redirect("/budgets")

    today = date.today()
    return render_template(
        "budgets.html",
        budgets=get_budgets_with_progress(today.year, today.month),
        categories=get_categories("expense"),
    )


@app.route("/budgets/delete/<int:id>")
def delete_budget(id):
    b = Budget.query.get_or_404(id)
    db.session.delete(b)
    db.session.commit()
    return redirect("/budgets")


# ---------- Insights ----------
@app.route("/insights")
def insights():
    now = datetime.now()
    month = int(request.args.get("month", now.month))
    year = int(request.args.get("year", now.year))

    month_expenses = []
    for e in Expense.query.all():
        d = datetime.strptime(e.date, "%Y-%m-%d")
        if d.month == month and d.year == year:
            amount = e.your_share if e.is_split else e.amount
            month_expenses.append({
                "date": e.date,
                "description": e.description,
                "category": e.category,
                "amount": amount,
                "is_split": e.is_split,
            })

    total = sum(e["amount"] for e in month_expenses)

    category_totals = {}
    for e in month_expenses:
        category_totals[e["category"]] = category_totals.get(e["category"], 0) + e["amount"]

    fig = Figure(figsize=(7, 5))
    ax = fig.add_subplot(1, 1, 1)
    if category_totals:
        colors = ["#3182ce", "#38a169", "#d69e2e", "#e53e3e", "#805ad5", "#0987a0", "#dd6b20", "#319795"]
        ax.pie(
            list(category_totals.values()),
            labels=list(category_totals.keys()),
            autopct="%1.1f%%",
            colors=colors[:len(category_totals)],
            startangle=90,
            wedgeprops={"edgecolor": "white", "linewidth": 2},
        )
    ax.set_title(f"Expenses by Category — {month}/{year}", fontsize=14, fontweight="bold")

    png = io.BytesIO()
    FigureCanvas(fig).print_png(png)
    chart = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode("utf8")

    return render_template(
        "insights.html",
        month=month,
        year=year,
        expenses=month_expenses,
        total=total,
        chart=chart,
        category_totals=category_totals,
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)