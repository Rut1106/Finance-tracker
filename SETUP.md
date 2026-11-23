# Rut Finance v2 — setup

Same money paths as before (salary → Account 3 → move to Account 1 → spend; Splitwise lives in Account 4), but built so you barely type anything.

| How money gets in | Effort |
|---|---|
| Apple Pay tap → logged automatically | 0 taps (known places) or 1 tap (new places) |
| Splitwise → synced every 3 hours | 1 tap to confirm |
| Rent, paychecks, bills → post themselves | 0–1 taps |
| Everything else → type `uber 18` or tell Siri | ~5 seconds |
| Weekly balance check → catches anything you missed | ~2 minutes |

Your old Google Sheet ("Finance Tracker") is not touched. v2 uses a new sheet and starts fresh from the day you set it up.

---

## 1. Create the new Google Sheet (2 min)

1. Open Google Sheets and create a blank sheet named exactly **Rut Finance v2**.
2. Open your `credentials.json`, copy the `client_email` value (ends in `iam.gserviceaccount.com`).
3. In the new sheet, click **Share**, paste that email, give it **Editor**, untick "Notify", and share.

The app creates all its tabs (ledger, accounts, rules, …) on first start.

## 2. Replace the code

In `C:\Users\Admin\Desktop\Rut Finance`:

1. Delete the old `app.py`, `splitwise_sync.py`, the `templates` folder and the `static` folder.
   **Keep** `venv`, `credentials.json`, and the hidden `.git` folder.
2. Copy everything from this project into the folder (including `.gitignore`).

Then in PowerShell:

```powershell
cd "C:\Users\Admin\Desktop\Rut Finance"
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 — you'll land on **Fresh start**. Type what each bank account has right now, and you're tracking.

> Want to play without touching Google? Run `$env:USE_JSON_STORE = "1"` before `python app.py` and it saves to a local `data.json` instead.

## 3. Secrets on Render

Make two random strings in PowerShell (run it twice):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Render dashboard → your service → **Environment** → add:

| Key | Value |
|---|---|
| `GOOGLE_CREDENTIALS` | (already there) |
| `APP_PIN` | a PIN you'll type on your phone, e.g. `4821` |
| `API_KEY` | random string #1 — the iPhone Shortcuts use this |
| `SECRET_KEY` | random string #2 |
| `SPLITWISE_TOKEN` | your Splitwise API key (optional) |

Start command on Render should be: `gunicorn app:app --workers 1 --threads 4 --timeout 60`

Push:

```powershell
git add .
git status        # credentials.json must NOT be listed
git commit -m "Rut Finance v2: auto-capture"
git push
```

## 4. Keep Render awake (important for Apple Pay)

Render's free plan sleeps after 15 minutes. A sleeping app takes ~40 seconds to wake, which can make the Apple Pay shortcut time out and miss a purchase.

Fix (free, 3 min): sign up at **uptimerobot.com** → New monitor → HTTP(s) → URL `https://finance-tracker-ut8h.onrender.com/health` → every 5 minutes.

## 5. Put it on your home screen

On your iPhone, open your Render URL in **Safari** → Share → **Add to Home Screen**. It opens full-screen like an app, with the gold diamond icon. Log in with your PIN once; it remembers you for 6 months.

## 6. Apple Pay auto-log (the big one)

Shortcuts app → **Automation** tab → **+** → **Transaction** (Wallet).

1. **Cards:** select all your Apple Pay cards. **Categories:** all. Leave merchants as any.
2. Choose **Run Immediately**, tap **Next** → **New Blank Automation**.
3. Add action **Get Contents of URL**:
   - URL: `https://finance-tracker-ut8h.onrender.com/api/capture`
   - Tap the arrow → **Method: POST** → **Request Body: JSON**, add 4 Text fields:
     - `amount` → tap, choose variable **Shortcut Input**, then tap it and pick **Amount**
     - `merchant` → **Shortcut Input** → **Merchant**
     - `card` → **Shortcut Input** → **Card or Pass**
     - `key` → paste your `API_KEY`
4. (Optional) Add **Get Dictionary Value** → key `message` from Contents of URL, then **Show Notification** with it. You'll see "Logged $5.75 Starbucks → Food" after every tap.

What happens:
- **Known place** (you've categorized it before) → logged instantly, no taps.
- **New place** → lands in the Inbox with a guessed category. Tap the right chip once; the app remembers it forever.

Then in the app: **Settings → Apple Pay cards** → add each card's name (e.g. "Discover" → the account it pays from). Unmatched cards default to Account 1.

Online purchases with a typed card number don't trigger this — use quick add or the weekly check for those.

## 7. Siri quick-add

Shortcuts app → **+** (new shortcut) → name it **Log money**.

1. **Ask for Input** → Text → prompt "What did you spend?"
2. **Get Contents of URL** → `https://finance-tracker-ut8h.onrender.com/api/quick`, POST, JSON:
   - `text` → **Provided Input**
   - `key` → your `API_KEY`
3. **Get Dictionary Value** → `message` → **Show Result**

Now: "Hey Siri, log money" → "lunch 12". Works with everything quick add understands.

## 8. Recurring (one-time setup)

Settings → Recurring. Examples:
- **Rent** · expense · $650 · day 1 · Post automatically ✓
- **Paycheck** · income · $1,150 · day 1 · *untick* Post automatically (lands in Inbox so you can fix the exact amount)
- **Move pay** · transfer · Account 3 → Account 1 · day 2 · automatic

## Quick-add cheat sheet

```
uber 18                 expense, category guessed
lunch 12 #food          force a category
amazon 42 @2            pay from Account 2
coffee 5 yesterday      also 11/14
+2000 salary            income → Account 3
move 500                Account 3 → Account 1
move 200 1>2            any account → any account
split pizza 40 20       you paid 40, your share 20
split dinner 60 20 they they paid, your share 20
settle 40               friend paid you back
settle out 40           you paid a friend back
```

Every entry shows an **Undo** right after you add it. Tap any entry in the list to edit or delete it.

## Splitwise + Apple Pay don't double count

If you pay dinner with Apple Pay ($60) and then add it to Splitwise, the sync spots the matching $60 purchase within 3 days and turns it into a split (your share counted, the rest goes to Account 4) instead of adding it twice.
