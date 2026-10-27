"""Annual report and concall transcript links from screener.in (primary documents only)."""
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (FINN research prototype)"}


def fetch_documents(conn, symbol):
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code == 404:
        r = requests.get(f"https://www.screener.in/company/{symbol}/", headers=UA, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    docs = []

    ar = soup.select_one(".annual-reports")
    for a in (ar.select("a") if ar else []):
        docs.append(("annual_report", a.get_text(" ", strip=True)[:40], a["href"]))

    cc = soup.select_one(".concalls")
    for li in (cc.select("li") if cc else []):
        period = li.select_one(".ink-600")
        period = period.get_text(strip=True) if period else ""
        for a in li.select("a"):
            if a.get_text(strip=True).lower().startswith("transcript") and a.get("href"):
                docs.append(("transcript", period, a["href"]))

    for kind, period, href in docs:
        conn.execute("INSERT OR IGNORE INTO documents VALUES (?,?,?,?)", (symbol, kind, period, href))
    conn.commit()
    return docs
