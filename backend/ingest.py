"""Ingestion entry point: `python ingest.py [--days 30] [--docs]`. Safe to re-run; all writes are upserts."""
import argparse

from finn import env  # noqa: F401
import json
from datetime import datetime, timedelta

from finn.brief import classify_unknowns, get_settings, parse_ts
from finn.config import RESEARCH
from finn.db import connect
from finn.enrich import enrich
from finn.ingest.announcements import fetch_announcements
from finn.ingest.prices import detect_moves, fetch_prices
from finn.screener import save_documents


def run(days=30, docs=False, pre_enrich_hours=72):
    conn = connect()
    s = get_settings(conn)
    pf = s["portfolio"]
    print("prices:", fetch_prices(conn, pf), "rows")
    print("announcements:", fetch_announcements(conn, pf, days=days))
    print("llm-classified:", classify_unknowns(conn))

    # Push is proactive: pre-compute enrichment for recent material filings so cards open instantly.
    since = datetime.now() - timedelta(hours=pre_enrich_hours)
    for r in conn.execute("SELECT * FROM announcements WHERE importance >= 75").fetchall():
        ts = parse_ts(r["ts"])
        if ts and ts >= since:
            try:
                enrich(dict(r))
            except Exception as e:
                print("enrich failed", r["id"], e)

    if docs:
        for sym in pf + RESEARCH:
            try:
                print(f"docs {sym}:", len(save_documents(conn, sym)))
            except Exception as e:  # one bad page shouldn't stop the run
                print(f"docs {sym}: failed ({e})")
    return detect_moves(conn, pf, s["volume_multiple"], s["price_move_pct"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--docs", action="store_true", help="also refresh screener document links")
    args = ap.parse_args()
    print("alerts:", json.dumps(run(args.days, args.docs), indent=1))
