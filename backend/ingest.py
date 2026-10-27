"""Daily ingestion entry point: `python ingest.py [--days 30]`. Safe to re-run; all writes are upserts."""
import argparse
import json

from finn.config import DEFAULT_THRESHOLDS, PORTFOLIO, RESEARCH
from finn.db import connect
from finn.ingest.announcements import fetch_announcements
from finn.ingest.fundamentals import fetch_documents
from finn.ingest.prices import detect_moves, fetch_prices


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    conn = connect()

    print("prices:", fetch_prices(conn, PORTFOLIO), "rows")
    print("announcements:", fetch_announcements(conn, PORTFOLIO, days=args.days))
    for sym in PORTFOLIO + RESEARCH:
        try:
            print(f"docs {sym}:", len(fetch_documents(conn, sym)))
        except Exception as e:  # one bad page shouldn't stop the run
            print(f"docs {sym}: failed ({e})")

    alerts = detect_moves(conn, PORTFOLIO, DEFAULT_THRESHOLDS["volume_multiple"], DEFAULT_THRESHOLDS["price_move_pct"])
    print("alerts:", json.dumps(alerts, indent=1))


if __name__ == "__main__":
    main()
