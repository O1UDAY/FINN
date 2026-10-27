"""SQLite storage. One file, no server: cheap and good enough for a prototype."""
import sqlite3

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS announcements (
    id TEXT PRIMARY KEY, symbol TEXT, ts TEXT, subject TEXT, detail TEXT,
    attachment TEXT, category TEXT, importance INTEGER, summary TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    symbol TEXT, kind TEXT, period TEXT, url TEXT,
    PRIMARY KEY (symbol, kind, url)
);
CREATE TABLE IF NOT EXISTS pages (symbol TEXT PRIMARY KEY, html TEXT, fetched TEXT);
CREATE TABLE IF NOT EXISTS enrichments (id TEXT PRIMARY KEY, payload TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS research (symbol TEXT PRIMARY KEY, payload TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS notified_alerts (id TEXT PRIMARY KEY, kind TEXT, sent_at TEXT, channel TEXT);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY, model TEXT, output TEXT, cost_usd REAL, created TEXT
);
"""


# Columns added after the first release; added in place so existing databases keep working.
MIGRATIONS = [
    "ALTER TABLE announcements ADD COLUMN amount_cr REAL",   # largest ₹ amount found in the filing, in crore
    "ALTER TABLE announcements ADD COLUMN mcap_cr REAL",     # market cap used for the materiality check
    "ALTER TABLE announcements ADD COLUMN material INTEGER", # 1 material, 0 immaterial vs size, NULL not checked/no amount
]


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for m in MIGRATIONS:
        try:
            conn.execute(m)
        except sqlite3.OperationalError:
            pass  # already applied
    return conn


def set_meta(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, str(value)))
    conn.commit()


def get_meta(conn, key, default=None):
    r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default
