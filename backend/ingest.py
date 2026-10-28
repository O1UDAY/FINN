"""Ingestion entry point. Safe to re-run: every write is an upsert, alerts are de-duplicated in notified_alerts.

    python ingest.py [--days 30] [--docs]      from backend/
    python -m backend.ingest --refresh          from the repo root (what an external cron runs)
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so `python -m backend.ingest` finds the finn package

from finn import env  # noqa: F401,E402
from finn.brief import classify_unknowns, get_settings  # noqa: E402
from finn.config import RESEARCH  # noqa: E402
from finn.db import connect, set_meta  # noqa: E402
from finn.enrich import enrich  # noqa: E402
from finn.ingest.announcements import fetch_announcements  # noqa: E402
from finn.ingest.prices import detect_moves, fetch_prices  # noqa: E402
from finn.screener import save_documents  # noqa: E402


def run(days=30, docs=False, notify=True, prices=True):
    conn = connect()
    s = get_settings(conn)
    pf = s["portfolio"]
    if conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0] == 0:
        from finn.snapshot import load
        load("empty database")  # show something real at once; the live fetch below tops it up
    if prices:  # end-of-day data: once a day is enough; filings are checked far more often
        print("prices:", fetch_prices(conn, pf), "rows")
    n = fetch_announcements(conn, pf, days=days)
    print("announcements:", n)
    if n == 0:
        from finn.snapshot import load
        load("live NSE and BSE fetch returned nothing")
    else:
        set_meta(conn, "data_mode", "live")
    print("llm-classified:", classify_unknowns(conn))

    # Size check for legal items, before anything is ranked.
    from finn.materiality import SIZE_CHECKED, check_filing
    for r in conn.execute("SELECT * FROM announcements WHERE material IS NULL AND amount_cr IS NULL").fetchall():
        if r["category"] in SIZE_CHECKED:
            check_filing(conn, dict(r))

    # Push is proactive: enrich every item that will render as a story (any window), so no card waits on a tap.
    from finn.brief import build_brief
    story_ids = {c["id"] for c in build_brief(24 * 30, enrich_missing=False)["cards"] if c["kind"] == "filing"}
    done = {r["id"] for r in conn.execute("SELECT id FROM enrichments")}
    for aid in story_ids - done:
        r = conn.execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone()
        try:
            enrich(dict(r))
        except Exception as e:
            print("enrich failed", aid, e)

    if docs:
        for sym in pf + RESEARCH:
            try:
                print(f"docs {sym}:", len(save_documents(conn, sym)))
            except Exception as e:  # one bad page shouldn't stop the run
                print(f"docs {sym}: failed ({e})")

    set_meta(conn, "last_refresh", datetime.now().isoformat(timespec="seconds"))
    if notify:
        from finn.notify import send_new_alerts
        print("notified:", send_new_alerts(conn))
    return detect_moves(conn, pf, s["volume_multiple"], s["price_move_pct"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--docs", action="store_true", help="also refresh screener document links")
    ap.add_argument("--refresh", action="store_true", help="one refresh for an external cron (same as no flags)")
    ap.add_argument("--no-notify", action="store_true", help="skip Telegram alerts")
    args = ap.parse_args()
    print("alerts:", json.dumps(run(args.days, args.docs, notify=not args.no_notify), indent=1))
