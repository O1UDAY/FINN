"""Download-once PDF cache and text extraction."""
import hashlib
import re

import pymupdf
import requests

from .config import DATA_DIR

PDF_DIR = DATA_DIR / "pdf"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept": "application/pdf,*/*"}
_nse = None


def _get(url):
    global _nse
    if "nseindia.com" in url:
        if _nse is None:
            from .ingest.announcements import nse_session
            _nse = nse_session()
        return _nse.get(url, timeout=60)
    headers = dict(UA)
    if "bseindia.com" in url:
        headers["Referer"] = "https://www.bseindia.com/"
    return requests.get(url, headers=headers, timeout=60)


def _complete(data: bytes) -> bool:
    """A PDF ends with %%EOF. Exchange servers sometimes drop the connection mid-file; a cut-off copy opens as 0 pages."""
    return data.startswith(b"%PDF") and b"%%EOF" in data[-2048:]


def fetch_pdf(url: str) -> bytes | None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    path = PDF_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".pdf")
    if path.exists():
        data = path.read_bytes()
        if _complete(data):
            return data
        path.unlink()  # saved before this check existed: fetch it again
    for _ in range(2):
        try:
            r = _get(url)
        except requests.RequestException:
            continue
        if not r.ok or not r.content.startswith(b"%PDF"):
            return None
        if _complete(r.content):
            path.write_bytes(r.content)
            return r.content
    return None  # never cache a partial download


def pages(url: str) -> list[str]:
    data = fetch_pdf(url)
    if not data:
        return []
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return []
    return [re.sub(r"[ \t]+", " ", p.get_text()) for p in doc]


STATEMENT_ITEMS = ["revenue from operations", "other income", "total income", "finance costs", "depreciation",
                   "profit before", "tax expense", "total expenses", "net profit", "profit for the period"]


def statement_pages(texts: list[str], k=1) -> list[int]:
    """The financial-results table itself: many distinct P&L line items and dense numbers, never the auditor's report.
    Keyword counts alone pick commentary pages, which repeat 'revenue' and 'quarter ended' in prose."""
    def score(t):
        low = t.lower()
        if "did not review" in low or "we have reviewed" in low:
            return 0
        nums = len(re.findall(r"\d[\d,]*\.\d{2}\b", t))
        return sum(w in low for w in STATEMENT_ITEMS) * 2 + min(nums, 200) / 40 + ("consolidated" in low)
    ranked = sorted(range(len(texts)), key=lambda i: -score(texts[i]))
    return sorted(i for i in ranked[:k] if score(texts[i]) > 4)


def best_pages(texts: list[str], keywords: list[str], k=2) -> list[int]:
    """Indices of the k pages mentioning the most keywords, in document order."""
    scored = sorted(range(len(texts)), key=lambda i: -sum(texts[i].lower().count(w) for w in keywords))
    return sorted(scored[:k])
