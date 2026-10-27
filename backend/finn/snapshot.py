"""Seed snapshot: a committed copy of filings, prices, enrichments and research so a cold or blocked server still
shows a real Brief. Loaded when the database is empty or a live fetch returns nothing; the UI then says
"Data as of <date> (snapshot)"."""
import sqlite3
from datetime import datetime
from pathlib import Path

from .db import connect, get_meta, set_meta

SEED = Path(__file__).resolve().parents[2] / "seed" / "finn_seed.db"
TABLES = ["announcements", "prices", "documents", "enrichments", "research", "pages", "llm_cache"]


def make(path=SEED):
    """Export the tables above into a compact standalone SQLite file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    src = connect()
    src.execute(f"VACUUM INTO '{path.as_posix()}'")
    dst = sqlite3.connect(path)
    keep = set(TABLES) | {"meta"}
    for (name,) in dst.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        if name not in keep:
            dst.execute(f"DELETE FROM {name}")
    dst.execute("DELETE FROM meta")
    dst.execute("INSERT INTO meta VALUES ('snapshot_created', ?)", (datetime.now().isoformat(timespec="minutes"),))
    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    return path


def load(reason):
    """Copy seed rows in without overwriting anything live (INSERT OR IGNORE). Returns rows added."""
    if not SEED.exists():
        print("snapshot: no seed file, nothing to load")
        return 0
    conn = connect()
    conn.execute("ATTACH DATABASE ? AS seed", (SEED.as_posix(),))
    added = 0
    for t in TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA seed.table_info({t})")]
        live = {r[1] for r in conn.execute(f"PRAGMA main.table_info({t})")}
        cols = [c for c in cols if c in live]
        if cols:
            cl = ",".join(cols)
            added += conn.execute(f"INSERT OR IGNORE INTO main.{t} ({cl}) SELECT {cl} FROM seed.{t}").rowcount
    created = conn.execute("SELECT value FROM seed.meta WHERE key='snapshot_created'").fetchone()
    conn.commit()
    conn.execute("DETACH DATABASE seed")
    set_meta(conn, "data_mode", "snapshot")
    set_meta(conn, "snapshot_as_of", created[0] if created else "")
    set_meta(conn, "snapshot_reason", reason)
    print(f"snapshot: loaded {added} rows ({reason})")
    return added


def status():
    conn = connect()
    return {"mode": get_meta(conn, "data_mode", "live"), "as_of": get_meta(conn, "snapshot_as_of"),
            "reason": get_meta(conn, "snapshot_reason")}
