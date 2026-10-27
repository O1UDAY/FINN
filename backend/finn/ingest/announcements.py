"""Corporate announcements: NSE's public JSON API first (needs a warmed-up cookie session), BSE as the fallback.

NSE often refuses cloud IPs. Each symbol is retried with backoff; if NSE still gives nothing usable for the whole
portfolio, the run switches to BSE's announcements API (scrip codes in config.BSE_CODES). The source used is logged
and stored in `meta.announcements_source` for /api/health.
"""
import hashlib
import time
from datetime import datetime, timedelta

import requests

from ..config import BSE_CODES
from ..db import set_meta
from .classify import classify

BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_HEADERS = {**HEADERS, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}
BSE_PDF = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{}"


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(BASE, timeout=15)  # sets the cookies the API checks
    return s


def _store(conn, sym, ts, subject, detail, att):
    aid = hashlib.sha1(f"{sym}|{ts}|{subject}|{att}".encode()).hexdigest()[:16]
    cat, imp = classify(subject, detail)
    cur = conn.execute(
        "INSERT OR IGNORE INTO announcements (id, symbol, ts, subject, detail, attachment, category, importance) "
        "VALUES (?,?,?,?,?,?,?,?)", (aid, sym, ts, subject, detail, att, cat, imp))
    return cur.rowcount


def _nse_symbol(s, sym, from_d, to_d, attempts=3):
    params = {"index": "equities", "symbol": sym, "from_date": from_d.strftime("%d-%m-%Y"), "to_date": to_d.strftime("%d-%m-%Y")}
    last = None
    for i in range(attempts):
        try:
            r = s.get(f"{BASE}/api/corporate-announcements", params=params, timeout=20)
            if r.ok:
                return r.json()
            last = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            last = type(e).__name__
        if i < attempts - 1:
            time.sleep(2 * 2 ** i)
    raise RuntimeError(f"NSE {sym}: {last}")


def fetch_nse(conn, symbols, from_d, to_d, session=None):
    try:
        s = session or nse_session()
    except requests.RequestException as e:
        raise RuntimeError(f"NSE session: {type(e).__name__}") from e
    total, failed = 0, []
    for sym in symbols:
        try:
            items = _nse_symbol(s, sym, from_d, to_d)
        except RuntimeError as e:
            failed.append(str(e))
            continue
        for it in items:
            _store(conn, sym, it.get("an_dt") or it.get("sort_date") or "", it.get("desc") or "",
                   it.get("attchmntText") or "", it.get("attchmntFile") or "")
            total += 1
    conn.commit()
    return total, failed


def fetch_bse(conn, symbols, from_d, to_d):
    total, failed = 0, []
    for sym in symbols:
        code = BSE_CODES.get(sym)
        if not code:
            failed.append(f"BSE {sym}: no scrip code in config")
            continue
        try:
            r = requests.get(BSE_API, headers=BSE_HEADERS, timeout=20, params={
                "pageno": 1, "strCat": -1, "strPrevDate": from_d.strftime("%Y%m%d"), "strScrip": code,
                "strSearch": "P", "strToDate": to_d.strftime("%Y%m%d"), "strType": "C", "subcategory": -1})
            rows = r.json().get("Table", []) if r.ok else []
        except (requests.RequestException, ValueError) as e:
            failed.append(f"BSE {sym}: {type(e).__name__}")
            continue
        for it in rows:
            ts = (it.get("NEWS_DT") or "").split(".")[0]
            try:  # store in NSE's format so every timestamp parses the same way
                ts = datetime.fromisoformat(ts).strftime("%d-%b-%Y %H:%M:%S")
            except ValueError:
                pass
            att = BSE_PDF.format(it["ATTACHMENTNAME"]) if it.get("ATTACHMENTNAME") else ""
            # BSE's NEWSSUB carries the regulation boilerplate; HEADLINE is the human description.
            _store(conn, sym, ts, it.get("HEADLINE") or it.get("NEWSSUB") or "", it.get("NEWSSUB") or "", att)
            total += 1
    conn.commit()
    return total, failed


def fetch_announcements(conn, symbols, days=30, session=None):
    to_d = datetime.now()
    from_d = to_d - timedelta(days=days)
    source, errors = "nse", []
    try:
        total, failed = fetch_nse(conn, symbols, from_d, to_d, session)
        errors += failed
    except RuntimeError as e:
        total, errors = 0, [str(e)]
    if total == 0:  # NSE gave nothing for the whole portfolio: blocked, not a quiet month
        print(f"announcements: NSE returned nothing ({'; '.join(errors[:3]) or 'empty'}), falling back to BSE")
        total, failed = fetch_bse(conn, symbols, from_d, to_d)
        source, errors = "bse", errors + failed
    elif errors:
        print(f"announcements: NSE failed for {len(errors)} symbols: {'; '.join(errors[:3])}")
    print(f"announcements: {total} items from {source.upper()}")
    set_meta(conn, "announcements_source", source if total else "none")
    set_meta(conn, "announcements_errors", "; ".join(errors[:10]))
    return total
