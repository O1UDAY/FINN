"""Corporate announcements from NSE's public JSON API (needs a warmed-up cookie session)."""
import hashlib
from datetime import datetime, timedelta

import requests

from .classify import classify

BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(BASE, timeout=15)  # sets the cookies the API checks
    return s


def fetch_announcements(conn, symbols, days=30, session=None):
    s = session or nse_session()
    to_d = datetime.now()
    from_d = to_d - timedelta(days=days)
    total = 0
    for sym in symbols:
        params = {"index": "equities", "symbol": sym,
                  "from_date": from_d.strftime("%d-%m-%Y"), "to_date": to_d.strftime("%d-%m-%Y")}
        try:
            r = s.get(f"{BASE}/api/corporate-announcements", params=params, timeout=20)
            items = r.json() if r.ok else []
        except (requests.RequestException, ValueError):
            items = []
        for it in items:
            subject = it.get("desc") or ""
            detail = it.get("attchmntText") or ""
            ts = it.get("an_dt") or it.get("sort_date") or ""
            att = it.get("attchmntFile") or ""
            aid = hashlib.sha1(f"{sym}|{ts}|{subject}|{att}".encode()).hexdigest()[:16]
            cat, imp = classify(subject, detail)
            conn.execute(
                "INSERT OR IGNORE INTO announcements (id, symbol, ts, subject, detail, attachment, category, importance) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (aid, sym, ts, subject, detail, att, cat, imp),
            )
            total += 1
    conn.commit()
    return total
