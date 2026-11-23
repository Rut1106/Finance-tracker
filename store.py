"""
Storage layer for Rut Finance v2.

Two backends with the same interface:
  - GoogleStore: a Google Sheet (production, on Render)
  - JsonStore:   a local data.json file (offline testing, no credentials)

The app reads every tab in ONE API call and caches it for a short time,
so a page load costs at most one Google request.
"""

import json
import os
import threading
import time

# Tab name -> column headers. Every row is stored as text (RAW) so ids,
# dates and amounts come back exactly as written.
SCHEMA = {
    "ledger":    ["id", "created", "date", "kind", "amount", "account", "to_account",
                  "category", "note", "merchant", "source", "status",
                  "your_share", "total", "ext_id"],
    "accounts":  ["name", "role", "opening", "label"],
    "rules":     ["key", "category"],
    "cards":     ["match", "account"],
    "recurring": ["id", "kind", "amount", "category", "note", "account",
                  "to_account", "day", "auto", "last_posted"],
    "budgets":   ["category", "amount"],
    "meta":      ["key", "value"],
}

CACHE_SECONDS = 30
_id_lock = threading.Lock()
_last_id = [0]


def new_id():
    """Millisecond timestamp id — unique, and sorts in the order entries were made."""
    with _id_lock:
        candidate = int(time.time() * 1000)
        if candidate <= _last_id[0]:
            candidate = _last_id[0] + 1
        _last_id[0] = candidate
        return str(candidate)


def _rows_to_dicts(values, headers):
    out = []
    for row in values[1:] if values else []:
        if not any(str(c).strip() for c in row):
            continue
        row = list(row) + [""] * (len(headers) - len(row))
        out.append({h: str(row[i]) for i, h in enumerate(headers)})
    return out


class _Base:
    key_col = {"ledger": "id", "recurring": "id", "accounts": "name",
               "rules": "key", "cards": "match", "budgets": "category", "meta": "key"}

    def __init__(self):
        self._cache = None
        self._ts = 0.0

    # ---- reads ----
    def all(self):
        if self._cache is None or time.time() - self._ts > CACHE_SECONDS:
            self._cache = self._load_all()
            self._ts = time.time()
        return self._cache

    def rows(self, tab):
        return self.all()[tab]

    def find(self, tab, key):
        k = self.key_col[tab]
        return next((r for r in self.rows(tab) if r[k] == str(key)), None)

    def meta(self, key, default=""):
        r = self.find("meta", key)
        return r["value"] if r else default

    def set_meta(self, key, value):
        self.upsert("meta", {"key": key, "value": str(value)})

    def upsert(self, tab, row):
        if self.find(tab, row[self.key_col[tab]]):
            self.update(tab, row)
        else:
            self.append(tab, row)

    def invalidate(self):
        self._cache = None


class JsonStore(_Base):
    def __init__(self, path="data.json"):
        super().__init__()
        self.path = path
        if not os.path.exists(path):
            self._save({t: [] for t in SCHEMA})

    def _read(self):
        with open(self.path) as f:
            data = json.load(f)
        for t in SCHEMA:
            data.setdefault(t, [])
        return data

    def _save(self, data):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, self.path)

    def _load_all(self):
        data = self._read()
        return {t: [{h: str(r.get(h, "")) for h in SCHEMA[t]} for r in data[t]] for t in SCHEMA}

    def append(self, tab, row, rows=None):
        data = self._read()
        for r in (rows or [row]):
            data[tab].append({h: str(r.get(h, "")) for h in SCHEMA[tab]})
        self._save(data)
        self.invalidate()

    def update(self, tab, row):
        k = self.key_col[tab]
        data = self._read()
        for i, r in enumerate(data[tab]):
            if str(r.get(k)) == str(row[k]):
                data[tab][i] = {h: str(row.get(h, r.get(h, ""))) for h in SCHEMA[tab]}
        self._save(data)
        self.invalidate()

    def delete(self, tab, key):
        k = self.key_col[tab]
        data = self._read()
        data[tab] = [r for r in data[tab] if str(r.get(k)) != str(key)]
        self._save(data)
        self.invalidate()


class GoogleStore(_Base):
    def __init__(self, sheet_name):
        super().__init__()
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        raw = os.environ.get("GOOGLE_CREDENTIALS")
        if raw:
            creds = Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
        else:
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        try:
            self.sh = gspread.authorize(creds).open(sheet_name)
        except gspread.SpreadsheetNotFound:
            raise RuntimeError(
                f'Google Sheet "{sheet_name}" not found. Create a blank sheet with that exact '
                f'name and share it (Editor) with {creds.service_account_email}') from None
        self._ws = {}
        self._ensure_tabs()

    def _ensure_tabs(self):
        existing = {ws.title: ws for ws in self.sh.worksheets()}
        for tab, headers in SCHEMA.items():
            ws = existing.get(tab) or self.sh.add_worksheet(title=tab, rows=500, cols=len(headers))
            if ws.row_values(1) != headers:
                ws.update(range_name="A1", values=[headers], value_input_option="RAW")
            self._ws[tab] = ws
        # Remove the default empty "Sheet1" if it is still there
        if "Sheet1" in existing and len(existing) == 1:
            try:
                self.sh.del_worksheet(existing["Sheet1"])
            except Exception:
                pass

    def _load_all(self):
        tabs = list(SCHEMA)
        try:
            resp = self.sh.values_batch_get(tabs)  # one API call for every tab
            ranges = resp.get("valueRanges", [])
            return {t: _rows_to_dicts(ranges[i].get("values", []), SCHEMA[t])
                    for i, t in enumerate(tabs)}
        except Exception:
            return {t: _rows_to_dicts(self._ws[t].get_all_values(), SCHEMA[t]) for t in tabs}

    def append(self, tab, row, rows=None):
        values = [[str(r.get(h, "")) for h in SCHEMA[tab]] for r in (rows or [row])]
        self._ws[tab].append_rows(values, value_input_option="RAW")
        self.invalidate()

    def _row_number(self, tab, key):
        col = SCHEMA[tab].index(self.key_col[tab]) + 1
        for i, v in enumerate(self._ws[tab].col_values(col)):
            if i > 0 and str(v) == str(key):
                return i + 1
        return None

    def update(self, tab, row):
        n = self._row_number(tab, row[self.key_col[tab]])
        if n:
            old = self.find(tab, row[self.key_col[tab]]) or {}
            values = [[str(row.get(h, old.get(h, ""))) for h in SCHEMA[tab]]]
            self._ws[tab].update(range_name=f"A{n}", values=values, value_input_option="RAW")
        self.invalidate()

    def delete(self, tab, key):
        n = self._row_number(tab, key)
        if n:
            self._ws[tab].delete_rows(n)
        self.invalidate()


def make_store():
    """Google Sheets when credentials exist, otherwise a local JSON file."""
    if os.environ.get("GOOGLE_CREDENTIALS") or os.path.exists("credentials.json"):
        if os.environ.get("USE_JSON_STORE") != "1":
            return GoogleStore(os.environ.get("SHEET_NAME", "Rut Finance v2"))
    return JsonStore(os.environ.get("JSON_STORE_PATH", "data.json"))
