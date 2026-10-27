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
from .pdftext import best_pages, pages, statement_pages
from .screener import _row, company, quarter_compare

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
    from .ingest.classify import rescore
    blob = " ".join(str(out.get(k) or "") for k in ("headline", "text"))
    imp = rescore(cat, blob, ann.get("importance") or 0)
    if imp != ann.get("importance"):
        conn.execute("UPDATE announcements SET importance=? WHERE id=?", (imp, ann["id"]))
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


def derive_ebitda(pbt, finance_costs, depreciation, other_income):
    """EBITDA when the filing doesn't print it: PBT + finance costs + depreciation - other income, per column.
    Other income is removed because it isn't operating; this is the method stated on the results card."""
    return [round(p + f + d - o, 2) for p, f, d, o in zip(pbt, finance_costs, depreciation, other_income)]


def results_headline(rows):
    """Plain, checkable headline from the computed YoY moves, e.g. 'Revenue up 16% on last year, EBITDA flat, PAT up 33%'.
    Written in code: a model asked for a one-liner called a flat-EBITDA quarter 'robust operational performance'."""
    def word(v):
        if v is None:
            return None
        if abs(v) < 2:
            return "flat"
        return f"{'up' if v > 0 else 'down'} {int(abs(v) + 0.5)}%"  # half-up, as investors expect
    bits = [(r["metric"], word(r["yoy"])) for r in rows if r["metric"] in ("Revenue", "EBITDA", "PAT")]
    bits = [f"{m} {w}" for m, w in bits if w]
    if not bits:
        return None
    return bits[0] + " on last year" + ("" if len(bits) == 1 else ", " + ", ".join(bits[1:]))


def _results(ann):
    if llm.available():
        texts = pages(ann.get("attachment") or "")
        text = "\n---\n".join(texts[i] for i in statement_pages(texts, k=1))[:12000]
        if text:
            # The model only copies line items; every derived number (EBITDA, growth, the headline) is computed here.
            got = llm.complete_json(
                "From this quarterly results filing, copy CONSOLIDATED figures if present (else standalone) for the latest quarter, "
                "the previous quarter, and the same quarter last year, exactly as printed. Quarter columns only, never six-month "
                "or full-year columns. PAT = profit attributable to owners of the company when shown, else net profit after tax. "
                "If EBITDA is printed as its own line, copy it; otherwise leave ebitda as null. Do not calculate anything.\n"
                '{"basis": "consolidated|standalone", "unit": "crore|lakh|million", "period": "e.g. Q2 FY27", '
                '"revenue": [cur, prev_q, year_ago], "other_income": [..], "finance_costs": [..], "depreciation": [..], '
                '"pbt": [..], "pat": [..], "ebitda": null}\n\n' + text,
                tier="cheap", max_tokens=700)
            if got and got.get("revenue"):
                trip = lambda k: v if isinstance(v := got.get(k), list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v) else None
                ebitda = trip("ebitda")
                parts = [trip(k) for k in ("pbt", "finance_costs", "depreciation", "other_income")]
                if not ebitda and all(parts):
                    ebitda = derive_ebitda(*parts)
                rows = [_row(label, *v) for label, v in
                        (("Revenue", trip("revenue")), ("EBITDA", ebitda), ("PBT", trip("pbt")), ("PAT", trip("pat"))) if v]
                # Grounding check: copied figures must literally appear in the filing (EBITDA may be derived).
                flat = re.sub(r"[,\s]", "", text)
                missing = [r["metric"] for r in rows if r["metric"] != "EBITDA" and
                           any(f"{x:.2f}".rstrip("0").rstrip(".") not in flat for x in (r["current"], r["prev_q"], r["year_ago"]))]
                unit = str(got.get("unit") or "").lower()
                unit = next((f"₹ {u}" for u in ("crore", "lakh", "million") if u in unit), "₹ crore")
                return {"type": "results", "period": got.get("period"), "unit": unit, "basis": got.get("basis"),
                        "rows": rows, "headline": results_headline(rows), "source": "results filing",
                        "note": f"Could not find {', '.join(missing)} figures verbatim in the filing; verify before relying." if missing else
                                "Every figure checked against the filing text.", "stale": bool(missing)}
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
        return {"type": "results", **qc, "headline": None if qc.get("stale") else results_headline(qc["rows"])}
    return {"type": "summary", "text": clean_detail(ann.get("detail"))}


NAME = re.compile(r"\b(?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+([A-Z][a-zA-Z.]+(?:[ ]+[A-Z][a-zA-Z.]+){0,3})")


def _web_profile(name, company_name):
    """Optional, UNTESTED: no Tavily key was available while building. Without TAVILY_API_KEY this returns None and the
    bio comes only from the filing's own profile annexure (the tested path)."""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return None
    try:
        r = requests.post("https://api.tavily.com/search", timeout=20, json={
            "api_key": key, "query": f"{name} {company_name} linkedin career background", "max_results": 4})
        return [{"title": x["title"], "url": x["url"], "snippet": x.get("content", "")[:400]} for x in r.json().get("results", [])]
    except Exception:
        return None


PROFILE_WORDS = ["appoint", "resign", "profile", "experience", "cessation", "superannuat", "brief", "qualification"]
EARLIER = re.compile(r"(?:intimation|letter|disclosure)s? dated ([A-Z][a-z]+ \d{1,2}, \d{4})")


def _referenced_profiles(ann, text):
    """Filings often say the profile was 'already provided in the intimation dated <date>'. Fetch that filing instead
    of leaving the investor with a bare name - it is still primary data from the same exchange feed."""
    from .brief import parse_ts
    extra = []
    for d in dict.fromkeys(EARLIER.findall(text)):
        try:
            day = datetime.strptime(d, "%B %d, %Y").date()
        except ValueError:
            continue
        for r in connect().execute("SELECT * FROM announcements WHERE symbol=? AND id<>?", (ann["symbol"], ann["id"])):
            ts = parse_ts(r["ts"])
            if ts and ts.date() == day:
                # Short filings: read them whole, since the profile usually sits on its own annexure page.
                t = _filing_text(dict(r), None, k=5, chars=9000)
                if "profile" in t.lower() or "experience" in t.lower():
                    extra.append(f"[Earlier filing {d}]\n{t}")
    return "\n---\n".join(extra)


TITLES = [(r"managing director (and|&) chief executive officer", "MD & CEO"), (r"chief executive officer", "CEO"),
          (r"chief financial officer", "CFO"), (r"chief operating officer", "COO"), (r"\bmanaging director\b", "MD"),
          (r"whole[- ]time director", "Whole-time Director")]


def short_title(role):
    """Filings spell titles out in full; headlines read better with the abbreviations investors use."""
    for pat, short in TITLES if role else []:
        role = re.sub(pat, short, role, flags=re.I)
    return role


def _management(ann):
    text = _filing_text(ann, PROFILE_WORDS, k=3, chars=10000)
    if text:
        text += "\n---\n" + _referenced_profiles(ann, text)
    people = []
    if llm.available() and text:
        got = llm.complete_json(
            "From this management-change filing, list each person whose role changes.\n"
            '[{"name": "", "role": "", "change": "appointed|resigned|retired|redesignated", "effective": "", '
            '"background": "if the filing has a profile, summarise it in your own words in at most 35 words: previous roles '
            'and education. Else empty.", "replaces": ""}]\n\n' + text,
            tier="cheap", max_tokens=700)
        people = [p for p in (got or []) if isinstance(p, dict) and p.get("name")]
    if not people and text:
        found = list(dict.fromkeys(NAME.findall(text)))
        names = [n for n in found if not any(n != m and n in m for m in found)][:2]  # drop bare surnames
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
        # Lead with the incoming person: that is who the investor needs to know about.
        p = next((x for x in people if x.get("change") == "appointed"), people[0])
        for x in people:
            x["name"] = re.sub(r"^(Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+", "", x["name"]).strip()
            x["role"] = short_title(x.get("role"))
            if x.get("replaces"):
                x["replaces"] = re.sub(r"^(Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+", "", x["replaces"]).strip()
        role, ch = re.sub(r"\s*\(.*?\)", "", p.get("role") or "") or None, p.get("change")
        if ch == "appointed" and role:
            headline = f"New {role}: {p['name']}" + (f", replacing {p['replaces']}" if p.get("replaces") else "")
        elif ch and role:
            headline = f"{p['name']} {ch} as {role}"
        else:
            headline = p["name"]
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
