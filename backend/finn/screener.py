"""screener.in company page: standardised financial tables (from exchange filings) + primary document links.

Works for any NSE symbol screener covers. Pages are cached for 12h in SQLite.
"""
import json
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .db import connect

UA = {"User-Agent": "Mozilla/5.0 (FINN research prototype)"}
SECTIONS = ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]


def _num(s: str):
    s = s.replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _html(symbol: str) -> str:
    conn = connect()
    row = conn.execute("SELECT html, fetched FROM pages WHERE symbol=?", (symbol,)).fetchone()
    if row and datetime.fromisoformat(row["fetched"]) > datetime.now() - timedelta(hours=12):
        return row["html"]
    html = None
    for suffix in ("consolidated/", ""):
        r = requests.get(f"https://www.screener.in/company/{symbol}/{suffix}", headers=UA, timeout=20)
        # A standalone-only company's consolidated page exists but has empty tables; prefer one with quarters.
        if r.ok and "data-date-key" in r.text:
            html = r.text
            break
    if html is None:
        raise LookupError(f"{symbol} not found on screener.in")
    conn.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?)", (symbol, html, datetime.now().isoformat()))
    conn.commit()
    return html


def company(symbol: str) -> dict:
    symbol = symbol.upper().strip()
    soup = BeautifulSoup(_html(symbol), "html.parser")
    out = {"symbol": symbol, "name": (soup.select_one("h1") or soup.new_tag("x")).get_text(strip=True), "tables": {}}
    out["industry"] = [a.get_text(strip=True) for a in soup.select('#peers a[href*="/market/"]')]
    m = re.search(r'data-company-id="(\d+)"', str(soup))
    out["company_id"] = m.group(1) if m else None

    for sec in SECTIONS:
        t = soup.select_one(f"section#{sec} table")
        if not t:
            continue
        cols = [th.get_text(" ", strip=True) for th in t.select("thead th")][1:]
        rows = {}
        for tr in t.select("tbody tr"):
            tds = tr.select("td")
            if not tds:
                continue
            name = re.sub(r"\s*\+$", "", tds[0].get_text(" ", strip=True)).split("Share of")[0].strip()
            rows[name] = [_num(td.get_text(strip=True)) for td in tds[1:]]
        out["tables"][sec] = {"cols": cols, "rows": rows}

    ratios = {}
    for li in soup.select("#top-ratios li"):
        name = li.select_one(".name")
        val = li.select_one(".number")
        if name and val:
            ratios[name.get_text(strip=True)] = _num(val.get_text(strip=True))
    out["ratios"] = ratios

    docs = []
    ar = soup.select_one(".annual-reports")
    for a in (ar.select("a") if ar else []):
        docs.append({"kind": "annual_report", "period": a.get_text(" ", strip=True)[:40], "url": a["href"]})
    cc = soup.select_one(".concalls")
    for li in (cc.select("li") if cc else []):
        period = li.select_one(".ink-600")
        period = period.get_text(strip=True) if period else ""
        for a in li.select("a[href]"):
            label = a.get_text(strip=True).lower()
            kind = "transcript" if label.startswith("transcript") else "presentation" if label == "ppt" else None
            if kind:
                docs.append({"kind": kind, "period": period, "url": a["href"]})
    out["documents"] = sorted(docs, key=lambda d: _period_key(d["period"]), reverse=True)
    return out


def _period_key(p: str):
    m = re.search(r"([A-Z][a-z]{2}) (\d{4})", p)
    if m:
        return datetime.strptime(m.group(0), "%b %Y")
    m = re.search(r"(\d{4})", p)
    return datetime(int(m.group(1)), 12, 31) if m else datetime.min


def save_documents(conn, symbol: str):
    docs = company(symbol)["documents"]
    for d in docs:
        conn.execute("INSERT OR IGNORE INTO documents VALUES (?,?,?,?)", (symbol, d["kind"], d["period"], d["url"]))
    conn.commit()
    return docs


def quarter_compare(c: dict) -> dict | None:
    """Latest quarter vs previous quarter and the same quarter a year ago, from screener's quarterly table."""
    q = c["tables"].get("quarters")
    if not q or len(q["cols"]) < 5:
        return None
    r = q["rows"]
    rev = r.get("Sales") or r.get("Revenue")
    lender = "Financing Profit" in r
    metrics = {"Revenue": rev, "EBITDA": None if lender else r.get("Operating Profit"),
               "PBT": r.get("Profit before tax"), "PAT": r.get("Net Profit")}
    if lender:
        metrics["Gross NPA %"] = r.get("Gross NPA %")
    cur, prev, yago = -1, -2, -5
    rows = []
    for k, v in metrics.items():
        if not v:
            continue
        rows.append(_row(k, v[cur], v[prev], v[yago]))
    return {"period": q["cols"][cur], "prev_period": q["cols"][prev], "yoy_period": q["cols"][yago],
            "unit": "₹ cr", "rows": rows, "note": "Lender: EBITDA not meaningful, NPA shown instead." if lender else None,
            "source": "screener.in quarterly table (compiled from exchange filings)"}


def _row(metric, cur, prev, yago):
    pct = lambda a, b: round((a / b - 1) * 100, 1) if a is not None and b not in (None, 0) and b > 0 else None
    return {"metric": metric, "current": cur, "prev_q": prev, "year_ago": yago, "qoq": pct(cur, prev), "yoy": pct(cur, yago)}


def schedule(c: dict, parent: str, section: str) -> dict:
    """Line-item breakdown behind one of screener's '+' rows (e.g. lease liabilities inside Borrowings), cached 12h.
    Returns {item: [values aligned to that table's columns]}; empty when unavailable."""
    if not c.get("company_id"):
        return {}
    conn = connect()
    key = f"{c['symbol']}::{section}::{parent}"
    row = conn.execute("SELECT html, fetched FROM pages WHERE symbol=?", (key,)).fetchone()
    if row and datetime.fromisoformat(row["fetched"]) > datetime.now() - timedelta(hours=12):
        raw = json.loads(row["html"])
    else:
        try:
            r = requests.get(f"https://www.screener.in/api/company/{c['company_id']}/schedules/",
                             params={"parent": parent, "section": section, "consolidated": ""}, headers=UA, timeout=20)
            raw = r.json() if r.ok else {}
        except (requests.RequestException, ValueError):
            raw = {}
        conn.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?)", (key, json.dumps(raw), datetime.now().isoformat()))
        conn.commit()
    cols = c["tables"].get(section, {}).get("cols", [])
    return {k: [_num(str(v.get(col, ""))) if isinstance(v, dict) else None for col in cols]
            for k, v in raw.items() if isinstance(v, dict)}
