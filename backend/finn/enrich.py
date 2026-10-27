"""Per-card enrichment for the Brief. Each result is cached in `enrichments`, so a card is processed once.

results           -> Revenue/EBITDA/PBT/PAT, QoQ and YoY (LLM reads the filing; screener table is the fallback)
management_change -> who, what role, in or out, and a short background (filing annexure + optional web lookup)
anything material -> one-line "so what"
"""
import json
import os
import re
from datetime import datetime

import requests

from . import llm
from .db import connect
from .pdftext import best_pages, pages
from .screener import _row, company, quarter_compare

RESULT_WORDS = ["revenue from operations", "profit before tax", "total income", "net profit", "quarter ended", "consolidated", "ebitda"]
BOILER = re.compile(r"^.*?has (informed|submitted to) the Exchange,?\s*(about|regarding|that)?\s*", re.I)
REGULATION = re.compile(r"^(disclosure|intimation)\b[^-–:]*?regulations?,?\s*\d{4}\s*(\([^)]*\))?\s*[-–:]\s*", re.I)


def clean_detail(detail: str) -> str:
    d = BOILER.sub("", detail or "").strip(" .'\"")
    d = REGULATION.sub("", d)
    return d[:1].upper() + d[1:] if d else ""


def enrich(ann: dict, refresh=False) -> dict:
    conn = connect()
    if not refresh:
        row = conn.execute("SELECT payload FROM enrichments WHERE id=?", (ann["id"],)).fetchone()
        if row:
            return json.loads(row["payload"])
    cat = ann.get("category")
    if cat == "results":
        out = _results(ann)
    elif cat == "management_change":
        out = _management(ann)
    else:
        out = _one_liner(ann)
    out["llm"] = llm.available()
    conn.execute("INSERT OR REPLACE INTO enrichments VALUES (?,?,?)",
                 (ann["id"], json.dumps(out, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return out


def _filing_text(ann, keywords, k=2, chars=9000):
    texts = pages(ann.get("attachment") or "")
    if not texts:
        return ""
    idx = best_pages(texts, keywords, k) if keywords else range(min(k, len(texts)))
    return "\n---\n".join(texts[i] for i in idx)[:chars]


def _results(ann):
    if llm.available():
        text = _filing_text(ann, RESULT_WORDS, k=2)
        if text:
            got = llm.complete_json(
                "From this quarterly results filing, extract CONSOLIDATED figures if present (else standalone) for the latest quarter, "
                "the previous quarter, and the same quarter last year. EBITDA = profit before tax + finance costs + depreciation - other income "
                "if not stated. Use the filing's unit.\n"
                '{"basis": "consolidated|standalone", "unit": "e.g. ₹ crore", "period": "e.g. Q2 FY27", '
                '"revenue": [cur, prev_q, year_ago], "ebitda": [..], "pbt": [..], "pat": [..], '
                '"one_liner": "what an investor should notice, max 18 words"}\n\n' + text,
                tier="cheap", max_tokens=600)
            if got and got.get("revenue"):
                rows = []
                for key, label in (("revenue", "Revenue"), ("ebitda", "EBITDA"), ("pbt", "PBT"), ("pat", "PAT")):
                    v = got.get(key) or []
                    if len(v) == 3 and all(isinstance(x, (int, float)) for x in v):
                        rows.append(_row(label, *v))  # growth computed here, not by the model
                return {"type": "results", "period": got.get("period"), "unit": got.get("unit"), "basis": got.get("basis"),
                        "rows": rows, "headline": got.get("one_liner"), "source": "results filing"}
    try:
        qc = quarter_compare(company(ann["symbol"]))
    except Exception:
        qc = None
    if qc:
        from .brief import parse_ts
        filed = parse_ts(ann.get("ts") or "")
        qend = datetime.strptime(qc["period"], "%b %Y")
        if filed and (filed - qend).days > 75:
            qc["note"] = (f"This filing is newer than the last compiled quarter ({qc['period']}). "
                          "Showing that quarter; the LLM reader extracts the new numbers from the filing itself.")
            qc["stale"] = True
        return {"type": "results", **qc, "headline": None}
    return {"type": "summary", "text": clean_detail(ann.get("detail"))}


NAME = re.compile(r"\b(?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+([A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+){0,3})")


def _web_profile(name, company_name):
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return None
    try:
        r = requests.post("https://api.tavily.com/search", timeout=20, json={
            "api_key": key, "query": f"{name} {company_name} linkedin career background", "max_results": 4})
        return [{"title": x["title"], "url": x["url"], "snippet": x.get("content", "")[:400]} for x in r.json().get("results", [])]
    except Exception:
        return None


def _management(ann):
    text = _filing_text(ann, ["appoint", "resign", "profile", "experience", "cessation", "superannuat", "brief"], k=3, chars=10000)
    people = []
    if llm.available() and text:
        got = llm.complete_json(
            "From this management-change filing, list each person whose role changes.\n"
            '[{"name": "", "role": "", "change": "appointed|resigned|retired|redesignated", "effective": "", '
            '"background": "2 lines from the filing\'s profile annexure if present, else empty", "replaces": ""}]\n\n' + text,
            tier="cheap", max_tokens=700)
        people = [p for p in (got or []) if isinstance(p, dict) and p.get("name")]
    if not people and text:
        names = list(dict.fromkeys(NAME.findall(text)))[:2]
        people = [{"name": n, "role": None, "change": None, "background": None} for n in names]

    cname = ann["symbol"]
    for p in people[:2]:
        web = _web_profile(p["name"], cname)
        if web:
            p["web"] = web
            if llm.available():
                p["background"] = llm.complete(
                    f"In 2 short lines, who is {p['name']} ({p.get('role')}, {cname})? Career path only, from these search results:\n"
                    + json.dumps(web), tier="cheap", max_tokens=150)
    headline = None
    if people:
        p = people[0]
        headline = " · ".join(x for x in [p["name"], p.get("role"), p.get("change")] if x)
    return {"type": "management", "people": people, "headline": headline, "text": clean_detail(ann.get("detail"))}


def _one_liner(ann):
    base = clean_detail(ann.get("detail"))
    if llm.available() and (ann.get("importance") or 0) >= 40:
        text = _filing_text(ann, None, k=2, chars=5000)
        if text:
            s = llm.complete("In at most 20 words, what does this filing mean for a shareholder? No preamble.\n\n" + text,
                             tier="cheap", max_tokens=80)
            if s:
                return {"type": "summary", "text": s.strip(), "headline": s.strip()}
    return {"type": "summary", "text": base}
