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
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY, model TEXT, output TEXT, cost_usd REAL, created TEXT
);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
