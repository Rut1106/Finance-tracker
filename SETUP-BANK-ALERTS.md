# Bank alerts + Safe to spend + 9 pm summary

One small action per line. About 15 minutes total.

---

## Part A — Update the app (laptop, 3 min)

1. Open PowerShell.
2. Paste this and press Enter:
   ```powershell
   cd "C:\Users\Admin\Desktop\Rut Finance"
   ```
3. Paste this and press Enter:
   ```powershell
   git add .
   ```
4. Paste this and press Enter:
   ```powershell
   git commit -m "Bank alerts, safe to spend, evening summary"
   ```
5. Paste this and press Enter:
   ```powershell
   git push
   ```
6. Wait about 3 minutes for Render to finish deploying.

---

## Part B — Turn on bank alert emails (iPhone, 5 min)

**Chase app**

1. Open the Chase app.
2. Tap the **person icon** (top right).
3. Tap **Alerts** (may be under "Profile & settings").
4. Open your checking / card account's alerts.
5. Turn on **"Transaction over…"** (purchases / debit card) → set the amount as low as it allows → delivery **Email**.
6. Turn on **Zelle** alerts ("Money received" and "Money sent") → **Email**.

**Wells Fargo app**

1. Open the Wells Fargo app.
2. Tap **Menu** → **Profile & Settings** → **Manage Alerts**.
3. Open your account's alerts.
4. Turn on **debit card purchase** alerts → lowest amount → **Email**.
5. Turn on **Zelle** and **direct deposit** alerts → **Email**.

**Chase credit card** (same Chase app)

1. Open your **Freedom Unlimited** card → **Alerts**.
2. Turn on **"Transaction over…"** → lowest amount → **Email**.

**Discover app**

1. Open the Discover app.
2. Tap **Profile** → **Alerts**.
3. Turn on **Transaction alert** (every purchase) → lowest amount → **Email**.

**Amex app**

1. Open the Amex app.
2. Tap **Account** → **Notifications** (or "Manage alerts").
3. Turn on **Large purchase** (or "Purchase") alert → set **$0** or the lowest amount → **Email**.

Card bill payments are ignored on purpose: a card purchase already counted when you swiped.

---

## Part C — Forward bank alerts to the bot (laptop, 2 min)

Do this in your **real** Gmail (rutpatel.34@gmail.com) in a browser.

1. Click the **sliders icon** at the right end of the Gmail search bar.
2. In **From**, paste:
   ```
   no.reply.alerts@chase.com OR noreplyalerts@chase.com OR alerts@notify.wellsfargo.com OR discover@services.discover.com OR AmericanExpress@welcome.americanexpress.com
   ```
3. Click **Create filter**.
4. Tick **Forward it to:** → pick the bot address.
5. Click **Create filter**.

Only these alert senders are forwarded. Offers and marketing (they come from other addresses) stay in your inbox only.

---

## Part D — Update the script in the bot account (laptop, 2 min)

1. Sign in to **script.google.com** as the **bot** account.
2. Open **Rut Finance bridge**.
3. Select all the code and delete it.
4. Paste all of `email-bridge.gs`.
5. Replace `PASTE_YOUR_API_KEY_HERE` with your API key (keep the quotes).
6. Click **Save** (disk icon).
7. In the function menu at the top, choose **setup**.
8. Click **Run**.
9. If it asks for permission: **Review permissions** → bot account → **Advanced** → **Go to Rut Finance bridge** → **Allow**.

It now checks every **1 minute** instead of 15.

---

## Weekly balance check (new box)

On **Check**, under Chase there's a new box **Credit cards owed**. Type the total you owe on Discover + Amex + Chase card. The app subtracts it from Chase for you.

---

## Part E — Set your monthly plan (iPhone, 1 min)

1. Open Rut Finance.
2. Tap **Settings**.
3. In **Monthly plan**, type how much you want to spend this month (for example `900`).
4. Optional: type how much you want to save.
5. Tap **Save plan**.

Home now shows **Safe to spend today** at the top.

---

## Part F — 9 pm summary notification (iPhone, 3 min)

1. Open the **Shortcuts** app.
2. Tap **Automation** (bottom).
3. Tap **+** (top right).
4. Tap **Time of Day**.
5. Set the time to **9:00 PM**, keep **Daily**.
6. Choose **Run Immediately**.
7. Tap **Next**.
8. Tap **New Blank Automation**.
9. Tap **Add Action**.
10. Search **Get Contents of URL** and tap it.
11. Tap the blue **URL** and type (use your real key):
    ```
    https://finance-tracker-ut8h.onrender.com/api/summary?key=YOUR_API_KEY
    ```
12. Tap the search bar at the bottom, search **Get Dictionary Value**, tap it.
13. Tap the blue **Key** and type `message`.
14. Search **Show Notification**, tap it. (It fills in "Dictionary Value" by itself.)
15. Tap **Done**.

Test it: open the automation and tap **▶** (bottom right). You should see something like
`Today $42.10 spent (3) · $28.00/day left for Nov · 2 waiting in Inbox`.

---

## What happens now

| Email | Becomes |
|---|---|
| Chase / Wells purchase you already paid with Apple Pay | Matched — not counted twice |
| Purchase without Apple Pay | New expense (Inbox if the place is new) |
| Zelle to yourself (Wells → Chase) | Transfer, both banks' emails matched to one entry |
| Zelle from a friend + Splitwise "paid you" | One settle-up, not income |
| Zelle to / from a friend, no Splitwise email | Inbox, with a button **"It was a Splitwise settle-up"** |
| Direct deposit | Income in the Inbox |
| Discover / Amex / Chase card purchase | Expense from Chase (Account 1), matched with Apple Pay |
| Card bill paid from Chase | Ignored (already counted at the swipe) |
| Card bill paid from Wells Fargo | Transfer Wells Fargo → Chase |
| Offers, statements, security emails | Ignored |

If a bank email can't be read, Home shows "Couldn't read a bank email". Send me the subject and I'll teach it.
