"""Pull side: on-demand research for any NSE symbol, primary sources only.

numbers()  -> deterministic, free, instant: snapshot, trajectory, balance sheet, cash quality, red/green signals.
analysis() -> the judgement layer, built as a cost funnel:
    1. regex pre-filter keeps only forward-looking sentences from each transcript (~60k chars -> ~3k)
    2. cheap model turns those into structured promises, one call per transcript (cached)
    3. ONE strong-model call compares promises against reported quarterly numbers -> verdicts, bull/bear
"""
import json
import re
from datetime import datetime

from . import llm
from .db import connect
from .pdftext import pages
from .screener import company

FORWARD = re.compile(r"guid|expect|target|aspir|aim(ing)? (to|for)|we will|outlook|going forward|next (year|quarter|fiscal)|by fy|in fy\s?\d|plan to|confident", re.I)


def _series(table, *names):
    for n in names:
        if table and n in table["rows"]:
            return table["rows"][n]
    return None


def _cagr(series, years):
    vals = [v for v in (series or []) if v is not None]
    if len(vals) <= years or vals[-1 - years] <= 0 or vals[-1] <= 0:
        return None
    return round(((vals[-1] / vals[-1 - years]) ** (1 / years) - 1) * 100, 1)


def _last(cols, vals, n):
    return [{"period": c, "value": v} for c, v in list(zip(cols, vals or []))[-n:]]


PLAUSIBLE = {"cash_conversion": 3.0, "operating_margin": 80.0}
LEASE_HEAVY = {"restaurants", "retailing", "diversified retail", "specialty retail", "hotels & resorts", "airline",
               "airlines", "multiplex", "leisure services", "department stores", "pharmacy"}
LEASE_NOTE = ("Likely inflated by Ind AS 116: lease payments sit in financing cash flow. Compare CFO minus lease "
              "payments to PAT before reading this as strength.")
LEASE_DEBT_NOTE = "Lease liabilities are counted as borrowings under Ind AS 116; they are rent, not bank debt."


def margin_series(op, sales):
    """Operating profit / sales x 100, one decimal, per period."""
    return [round(o / s * 100, 1) if o is not None and s else None for o, s in zip(op or [], sales or [])]


def ratio_sum(num, den):
    d = sum(x or 0 for x in den)
    return round(sum(x or 0 for x in num) / d, 2) if d > 0 else None


def lease_flag(industry, conversions, lease_share, de_jump, lease_to_equity=None):
    """Pure rule: when should lease accounting make us distrust CFO/PAT and D/E? Returns (flag, reason).
    Leases must matter against equity too: a company whose only debt is a small office lease is not lease-heavy."""
    if lease_to_equity is not None and lease_to_equity < 0.15:
        return False, None
    if lease_share is not None and lease_share >= 0.3:
        return True, f"lease liabilities are {lease_share:.0%} of borrowings"
    if any(x.lower() in LEASE_HEAVY for x in industry or []):
        return True, "lease-heavy industry"
    vals = [x for x in conversions if x is not None]
    if len(vals) >= 3 and sum(x > 1.5 for x in vals[-5:]) >= 3:
        return True, "CFO above 150% of profit in most recent years"
    if de_jump is not None and de_jump > 0.5:
        return True, "D/E jumped by more than 0.5 in a year"
    return False, None


def lease_view(c, debt, equity, cfo, pat, lender):
    from .screener import schedule
    out = {"flag": False}
    if lender:
        return out
    sched_b = schedule(c, "Borrowings", "balance-sheet") if debt else {}
    leases = sched_b.get("Lease Liabilities") or []
    lease_share = lease_to_equity = None
    if leases and equity and equity[-1]:
        lease_to_equity = round((leases[-1] or 0) / equity[-1], 2)
    if leases and debt and debt[-1]:
        lease_share = round((leases[-1] or 0) / debt[-1], 2)
        out["de_ex_lease"] = [round(((d or 0) - (l or 0)) / e, 2) if e else None for d, l, e in zip(debt, leases, equity)]
    out["lease_share"] = lease_share
    sched_c = schedule(c, "Cash from Financing Activity", "cash-flow") if cfo else {}
    lease_pay = sched_c.get("Financial liabilities") or []  # screener's line for lease principal + interest repaid
    if lease_pay:
        out["cfo_ex_lease"] = [round((f or 0) + (p or 0), 1) for f, p in zip(cfo, lease_pay)]  # payments are negative
        n = min(len(out["cfo_ex_lease"]), len(pat), 5)
        out["conversion_ex_lease"] = ratio_sum(out["cfo_ex_lease"][-n:], pat[-n:])
    conv_by_year = [round(f / p, 2) if f is not None and p else None for f, p in zip(cfo[-5:], pat[-5:])]
    de = [round(d / e, 2) if e else None for d, e in zip(debt, equity)]
    jumps = [b - a for a, b in zip(de, de[1:]) if a is not None and b is not None]
    out["flag"], out["reason"] = lease_flag(c.get("industry"), conv_by_year, lease_share, max(jumps) if jumps else None, lease_to_equity)
    return out


def numbers(symbol: str) -> dict:
    c = company(symbol)
    t = c["tables"]
    pl, bs, cf, rt, q = (t.get(k) for k in ("profit-loss", "balance-sheet", "cash-flow", "ratios", "quarters"))
    lender = bool(q and "Financing Profit" in q["rows"])

    # Annual tables end with a TTM column; trajectory uses fiscal years only.
    pl_cols = [x for x in pl["cols"] if x != "TTM"] if pl else []
    sales = (_series(pl, "Sales", "Revenue") or [])[:len(pl_cols)]
    pat = (_series(pl, "Net Profit") or [])[:len(pl_cols)]
    # Margins are computed here to one decimal. Screener prints whole-number %, and a model fed "20%, 20%, 20%"
    # will happily call a business "stagnant at 20.0%".
    opm = margin_series(_series(pl, "Operating Profit", "Financing Profit"), _series(pl, "Sales", "Revenue"))[:len(pl_cols)]
    qcols = q["cols"] if q else []
    qopm = margin_series(_series(q, "Operating Profit", "Financing Profit"), _series(q, "Sales", "Revenue"))

    equity = [(a or 0) + (b or 0) for a, b in zip(_series(bs, "Equity Capital") or [], _series(bs, "Reserves") or [])]
    debt = _series(bs, "Borrowings", "Borrowing") or []
    de = [round(d / e, 2) if e else None for d, e in zip(debt, equity)]
    cfo = _series(cf, "Cash from Operating Activity") or []
    fcf = _series(cf, "Free Cash Flow") or []
    ccc = _series(rt, "Cash Conversion Cycle") or []

    # Ind AS 116: lease payments sit in financing cash flow and lease liabilities in borrowings, which flatters CFO
    # and inflates leverage for store- and outlet-heavy businesses. Use screener's line items to back it out.
    lease = lease_view(c, debt, equity, cfo, pat, lender)

    n = min(len(cfo), len(pat), 5)
    cash_conv = ratio_sum(cfo[-n:], pat[-n:]) if n else None

    signals = []
    def sig(kind, text, note=None):
        signals.append({"kind": kind, "text": text, **({"note": note} if note else {})})
    g3, p3 = _cagr(sales, 3), _cagr(pat, 3)
    if g3 is not None:
        sig("good" if g3 >= 15 else "bad" if g3 < 5 else "neutral", f"Revenue 3y CAGR {g3}%")
    if p3 is not None and g3 is not None:
        sig("good" if p3 > g3 else "bad", f"Profit 3y CAGR {p3}% {'ahead of' if p3 > g3 else 'behind'} revenue")
    if not lender and cash_conv is not None:
        if lease["flag"]:
            adj = lease.get("conversion_ex_lease")
            sig("check", f"Cash quality needs adjustment: {n}y CFO = {cash_conv:.0%} of profit as reported"
                + (f", {adj:.0%} after lease payments" if adj is not None else ""), LEASE_NOTE)
        elif cash_conv > PLAUSIBLE["cash_conversion"]:
            sig("check", f"Check: {n}y CFO = {cash_conv:.0%} of profit is outside the plausible range")
        else:
            sig("good" if cash_conv >= 0.9 else "bad" if cash_conv < 0.7 else "neutral",
                f"{n}y cash from ops = {cash_conv:.0%} of reported profit")
    de_used = lease["de_ex_lease"] if lease["flag"] and lease.get("de_ex_lease") else de
    if not lender and len(de_used) >= 3 and de_used[-1] is not None and de_used[-3] is not None:
        label = "D/E excluding leases" if de_used is not de else "D/E"
        if de_used[-1] > de_used[-3] + 0.15:
            sig("bad", f"Leverage rising: {label} {de_used[-3]} → {de_used[-1]}")
        elif de_used[-1] < 0.3:
            sig("good", f"Low leverage: {label} {de_used[-1]}")
        if lease["flag"] and de and de[-1] is not None:
            sig("check", f"Reported D/E {de[-1]} includes lease liabilities ({lease['lease_share']:.0%} of borrowings)", LEASE_DEBT_NOTE)
    if len(ccc) >= 3 and None not in (ccc[-1], ccc[-3]) and abs(ccc[-1] - ccc[-3]) >= 10:
        sig("bad" if ccc[-1] > ccc[-3] else "good", f"Cash conversion cycle {ccc[-3]:.0f} → {ccc[-1]:.0f} days")
    if not lender and len(opm) >= 3 and None not in (opm[-1], opm[-3]):
        if opm[-1] > PLAUSIBLE["operating_margin"]:
            sig("check", f"Check: operating margin {opm[-1]}% is outside the plausible range for a non-financial")
        elif abs(opm[-1] - opm[-3]) >= 1.5:
            sig("good" if opm[-1] > opm[-3] else "bad", f"Margin {'expanding' if opm[-1] > opm[-3] else 'compressing'}: {opm[-3]}% → {opm[-1]}%")
        else:
            sig("neutral", f"Margin roughly steady: {opm[-3]}% → {opm[-1]}%")

    # Annual margins lag; the latest quarter against the prior four catches a turn the annual series hides.
    qv = [x for x in qopm if x is not None]
    if not lender and len(qv) >= 5:
        base = round(sum(qv[-5:-1]) / 4, 1)
        if abs(qv[-1] - base) >= 2.5:
            sig("good" if qv[-1] > base else "bad", f"Latest-quarter margin {qv[-1]}% vs {base}% avg of prior 4 quarters")
    return {
        "symbol": c["symbol"], "name": c["name"], "lender": lender,
        "trend": quarter_trend(qcols, _series(q, "Sales", "Revenue"), _series(q, "Net Profit"), None if lender else qopm),
        "limits": limits(c, lease, lender),
        "snapshot": {k: c["ratios"].get(k) for k in ("Market Cap", "Current Price", "Stock P/E", "ROCE", "ROE", "Dividend Yield")},
        "ttm": {"sales": (_series(pl, "Sales", "Revenue") or [None])[-1], "pat": (_series(pl, "Net Profit") or [None])[-1]},
        "industry": c.get("industry", []),
        "trajectory": {"sales": _last(pl_cols, sales, 7), "pat": _last(pl_cols, pat, 7), "opm": _last(pl_cols, opm, 7),
                       "sales_cagr_3y": g3, "pat_cagr_3y": p3, "sales_cagr_5y": _cagr(sales, 5)},
        "quarters": {"sales": _last(qcols, _series(q, "Sales", "Revenue"), 8), "pat": _last(qcols, _series(q, "Net Profit"), 8),
                     "opm": _last(qcols, qopm, 8)},
        "balance": {"debt": _last(bs["cols"] if bs else [], debt, 5), "de": _last(bs["cols"] if bs else [], de, 5),
                    "de_ex_lease": _last(bs["cols"] if bs else [], lease.get("de_ex_lease") or [], 5),
                    "lease_share": lease.get("lease_share"), "ccc": _last(rt["cols"] if rt else [], ccc, 5)},
        "cash": {"cfo": _last(cf["cols"] if cf else [], cfo, 5), "pat": _last(pl_cols, pat, 5),
                 "cfo_ex_lease": _last(cf["cols"] if cf else [], lease.get("cfo_ex_lease") or [], 5),
                 "fcf": _last(cf["cols"] if cf else [], fcf, 5), "conversion": cash_conv,
                 "conversion_ex_lease": lease.get("conversion_ex_lease")},
        "lease_flag": lease["flag"], "lease_reason": lease.get("reason"),
        "signals": signals,
        "documents": c["documents"][:24],
    }


def _yoy(vals, i):
    if i - 4 < 0 or vals[i] is None or not vals[i - 4]:
        return None
    return round((vals[i] / vals[i - 4] - 1) * 100, 1)


def quarter_trend(cols, sales, pat, opm):
    """Eight-quarter trajectory labelled in code: latest YoY growth against the average YoY of the prior quarters,
    so a reader sees acceleration or slowdown without trusting the model's adjectives."""
    out = []
    for name, vals in (("Revenue", sales or []), ("Net profit", pat or [])):
        yoys = [_yoy(vals, i) for i in range(len(vals))]
        recent = [y for y in yoys[-4:] if y is not None]
        if len(recent) < 2:
            continue
        last, prior = recent[-1], round(sum(recent[:-1]) / len(recent[:-1]), 1)
        if any(abs(y) > 60 for y in recent[:-1]):  # a tiny year-ago quarter makes the average meaningless
            out.append({"metric": name, "kind": "neutral",
                        "text": f"{name} YoY {last:+.1f}% in {cols[-1]}; earlier quarters are off a low base, so no trend is called"})
            continue
        diff = last - prior
        label = "accelerating" if diff >= 3 else "slowing" if diff <= -3 else "steady"
        out.append({"metric": name, "kind": "good" if label == "accelerating" else "bad" if label == "slowing" else "neutral",
                    "text": f"{name} YoY {label}: {last:+.1f}% in {cols[-1]} vs {prior:+.1f}% avg of prior {len(recent) - 1} quarters"})
    m = [x for x in (opm or []) if x is not None]
    if len(m) >= 5:
        base = round(sum(m[-5:-1]) / 4, 1)
        d = m[-1] - base
        label = "up" if d >= 1 else "down" if d <= -1 else "flat"
        out.append({"metric": "Margin", "kind": "good" if label == "up" else "bad" if label == "down" else "neutral",
                    "text": f"Operating margin {label}: {m[-1]}% in {cols[-1]} vs {base}% avg of prior 4 quarters"})
    return out


def limits(c, lease, lender):
    """What the reader should know about where the numbers come from and what FINN assumes."""
    out = ["Financial tables: screener.in, compiled from the company's exchange filings. Check any number you act on "
           "against the filing.",
           "Transcripts and presentations: the company's own documents, linked on every promise with page numbers.",
           "Margins are operating profit ÷ sales to one decimal. Growth, CAGR and ratios are computed in code, never by the model."]
    if lease["flag"]:
        out.append("Lease adjustment (Ind AS 116): lease liabilities come from the Borrowings schedule; lease payments are "
                   "approximated by the 'Financial liabilities' line of financing cash flow, which can include other items. "
                   "Treat ex-lease figures as indicative.")
    if lender:
        out.append("Lender: cash conversion and D/E are not meaningful here and are not scored.")
    out.append("Verdicts and the written analysis come from a language model reading only these documents and numbers. "
               "KPIs are read twice and kept only when the quote is found word for word in the document.")
    return out


def _facts(num):
    """Numbered, code-computed facts the model must cite. Keeps the narrative and the case for and against honest."""
    f = [x["text"] for x in num["signals"]] + [x["text"] for x in num.get("trend", [])]
    t = num["trajectory"]
    if t.get("sales_cagr_5y") is not None:
        f.append(f"Revenue 5y CAGR {t['sales_cagr_5y']}%")
    snap = num.get("snapshot") or {}
    for k in ("ROCE", "ROE", "Stock P/E"):
        if snap.get(k) not in (None, ""):
            f.append(f"{k} {snap[k]}")
    return {f"F{i}": x for i, x in enumerate(f, 1)}


def attach_facts(judged, facts):
    """Swap the fact ids the model cited for the fact text; points that cite nothing real are marked as opinion."""
    def resolve(ids):
        ids = ids if isinstance(ids, list) else [ids]
        return [{"id": i, "text": facts[i]} for i in ids if isinstance(i, str) and i in facts]
    for e in judged.get("narrative_vs_numbers") or []:
        if isinstance(e, dict):
            e["facts"] = resolve(e.get("fact_ids") or [])
    for side in ("bull", "bear"):
        kept = []
        for x in judged.get(side) or []:
            if isinstance(x, str):
                x = {"point": x, "cites": []}
            if not isinstance(x, dict) or not x.get("point"):
                continue
            cites = x.get("cites") or []
            x["facts"] = resolve([c for c in cites if str(c).startswith("F")])
            x["promises"] = [c for c in cites if str(c).startswith("P")]
            x["uncited"] = not (x["facts"] or x["promises"])
            kept.append(x)
        judged[side] = kept


def _sentences(text):
    text = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)


def forward_statements(text, limit=40):
    """Keep forward-looking sentences that contain a number, with one sentence of context either side."""
    s = _sentences(text)
    keep = []
    for i, x in enumerate(s):
        if FORWARD.search(x) and re.search(r"\d", x) and 30 < len(x) < 600:
            keep.append(" ".join(s[max(0, i - 1): i + 2]))
    return keep[:limit]


def _sources(c_docs, n=4):
    """Latest n transcripts; companies that don't host calls fall back to investor presentations."""
    tr = [d for d in c_docs if d["kind"] == "transcript"][:n]
    if len(tr) >= 2:
        return tr, "transcript"
    return [d for d in c_docs if d["kind"] == "presentation"][:n], "presentation"


def _flag_text(num):
    flags = [f"- {x['text']}. {x.get('note', '')}".strip() for x in num["signals"] if x["kind"] == "check"]
    return "\n".join(flags) or "- none"


STEPS = ["Fetching documents", "Extracting guidance", "Checking delivery", "Writing analysis"]


def analysis(symbol: str, refresh=False, progress=lambda step: None) -> dict:
    symbol = symbol.upper().strip()
    conn = connect()
    if not refresh:
        row = conn.execute("SELECT payload FROM research WHERE symbol=?", (symbol,)).fetchone()
        if row:
            return json.loads(row["payload"])

    progress(STEPS[0])
    num = numbers(symbol)
    docs, source_kind = _sources(num["documents"])
    per_doc = []
    opening = ""
    for d in docs:
        pg = pages(d["url"])
        text = "\n".join(pg)
        if not text:
            continue
        if not opening:
            opening = re.sub(r"\s+", " ", text)[:9000]
        per_doc.append({"period": d["period"], "url": d["url"], "candidates": forward_statements(text), "pages": pg})

    out = {"symbol": symbol, "source_kind": source_kind, "sources": [{"period": d["period"], "url": d["url"]} for d in per_doc],
           "llm": llm.available(), "generated": datetime.now().isoformat(timespec="seconds")}

    if not llm.available():
        out["promises"] = [{"said_in": d["period"], "quote": q, "url": d["url"], "verdict": "unverified"}
                           for d in per_doc for q in d["candidates"][:4]]
        out["note"] = "No LLM key configured: showing raw forward-looking statements without verdicts."
        _save(conn, symbol, out)
        return out

    # Step 2: cheap model structures promises per document.
    progress(STEPS[1])
    promises = []
    for d in per_doc:
        if not d["candidates"]:
            continue
        got = llm.complete_json(
            f"These are forward-looking statements by management of {num['name']} from their {d['period']} {source_kind}.\n"
            "Extract concrete, checkable promises about revenue/growth, margins, profit, capex, debt, store/capacity additions, "
            "or other headline numbers. Skip vague optimism and anything said by analysts.\n"
            'Format: [{"metric": "...", "promise": "short paraphrase with the number", "horizon": "e.g. FY27 / next 2 quarters", '
            '"quote": "exact short quote"}]\n\n' + "\n".join(f"- {x}" for x in d["candidates"]),
            tier="cheap", max_tokens=1200)
        for p in got or []:
            if isinstance(p, dict) and p.get("promise"):
                promises.append({**p, "said_in": d["period"], "url": d["url"], "page": page_of(p.get("quote"), d["pages"])})
    for i, p in enumerate(promises, 1):
        p["id"] = f"P{i}"

    # Step 2b: what management later said it actually achieved. Operating KPIs (stores, like-for-like growth, brand
    # margins) never appear in the financial tables, so without this every KPI promise ends up "no data".
    progress(STEPS[2])
    # Companies often put quarterly KPI tables in the investor presentation rather than the call, so scan both.
    kpi_docs = list(per_doc)
    if source_kind == "transcript":
        for d in [x for x in num["documents"] if x["kind"] == "presentation"][:4]:
            pg = pages(d["url"])
            if pg:
                kpi_docs.append({"period": d["period"], "url": d["url"], "pages": pg, "kind": "presentation"})
    kpi_stats = {}
    reported = reported_kpis(num["name"], promises, kpi_docs, source_kind, kpi_stats)

    # Step 3: one strong call does the judging.
    progress(STEPS[3])
    facts = _facts(num)
    actuals = {"quarterly": num["quarters"], "annual": num["trajectory"], "balance": num["balance"], "cash": num["cash"]}
    judged = llm.complete_json(
        f"Company: {num['name']} ({symbol}). Use ONLY the material below - no outside knowledge.\n"
        f"Today is {datetime.now():%d %b %Y}; the latest reported quarter is {(num['quarters']['sales'] or [{}])[-1].get('period', 'unknown')}. "
        "Verdict rules, one of delivered | partly | missed | too_early | not_disclosed:\n"
        "- delivered: reported numbers or later-call KPIs already meet the target, even before its deadline.\n"
        "- missed: the deadline has passed and the numbers fall short. partly: deadline passed, partly met.\n"
        "- too_early: deadline not reached; say in the evidence which way it is trending, using the later-call KPIs.\n"
        "- not_disclosed: ONLY when neither the reported numbers nor any LATER-CALL KPI covers the metric.\n"
        "Evidence must use numbers that measure the same thing as the promise. Prefer later-call KPIs for operating "
        "metrics (stores, like-for-like growth, segment margins) and the reported numbers for financial ones.\n"
        "Ledger rules: at most 7 entries. Merge repeats of the same target into one entry (keep the earliest said_in, mention "
        "it was reaffirmed). Leave out descriptions that are not commitments (headcount after a merger, company size).\n"
        "Note: reported margins are operating (EBITDA) margins computed to one decimal; flag it if management guided on a "
        "different margin.\n"
        f"DATA FLAGS (computed from the statements; you must respect them):\n{_flag_text(num)}\n"
        "A metric listed under DATA FLAGS must never be described as a strength or used as bull-case evidence. Where an "
        "ex-lease figure is given, reason from that one.\n\n"
        f"OPENING OF LATEST {source_kind.upper()} (for business description):\n{opening[:6000]}\n\n"
        f"MANAGEMENT PROMISES (oldest calls are the most checkable):\n{json.dumps(promises, ensure_ascii=False)[:9000]}\n\n"
        f"REPORTED NUMBERS (₹ crore, % for margins):\n{json.dumps(actuals)[:7000]}\n\n"
        f"LATER-CALL KPIs (what management said it achieved, keyed by promise id):\n{json.dumps(reported, ensure_ascii=False)[:5000]}\n\n"
        "COMPUTED FACTS (cite these by id; never state a number that is not here or in the reported numbers):\n"
        + "\n".join(f"{k}: {v}" for k, v in facts.items()) + "\n\n"
        "Tasks:\n"
        "1. business: 2-sentence plain-English description and main segments/revenue drivers.\n"
        "2. promised_vs_delivered: for each checkable promise, apply the verdict rules. promise_ids lists the promise ids "
        "the entry covers (merged repeats). evidence cites the numbers or KPI values used.\n"
        "3. narrative_vs_numbers: up to 3 specific management claims (their words, and which call) set against the "
        "computed facts. fact_ids lists the facts used; agrees is false where the numbers contradict the claim.\n"
        "4. guidance: the current explicit guidance from the LATEST call only.\n"
        "5. bull and bear: 3 tight points each. Every point cites at least one fact id (F..) or promise id (P..).\n"
        'JSON: {"business": {"summary": "", "segments": [""]}, "promised_vs_delivered": [{"promise_ids": ["P1"], "said_in": "", '
        '"metric": "", "promise": "", "quote": "", "outcome": "", "verdict": "", "evidence": ""}], "narrative_vs_numbers": '
        '[{"claim": "", "said_in": "", "reality": "", "fact_ids": ["F1"], "agrees": true}], "guidance": [{"metric": "", '
        '"guidance": ""}], "bull": [{"point": "", "cites": ["F1"]}], "bear": [{"point": "", "cites": ["P2"]}]}',
        tier="strong", max_tokens=3500,
        system="You are a sceptical buy-side analyst. You judge management by what they delivered, citing numbers. Be terse.")
    if judged:
        attach_evidence(judged.get("promised_vs_delivered", []), promises, reported)
        attach_facts(judged, facts)
        out.update(judged)
        out["kpis_found"] = sum(len(v) for v in reported.values())
        out["kpi_passes"] = kpi_stats
        _save(conn, symbol, out)
        return out
    # Judging failed (quota, outage, unparseable): show what we have, but don't cache it, so the next open retries.
    out["promises"] = promises or [{"said_in": d["period"], "quote": q, "url": d["url"], "verdict": "unverified"}
                                   for d in per_doc for q in d["candidates"][:4]]
    out["note"] = "The model didn't return a verdict this time; showing extracted statements. Re-open to retry."
    return out


REPORTED = re.compile(r"\b(added|opened|grew|grown|growth|came in|stood|was|were|delivered|achieved|reported|reached|"
                      r"increased|declined|registered|clocked|recorded|ended|closed|net addition|this quarter|"
                      r"during the quarter|in the quarter|for the quarter|q[1-4])\b", re.I)
SYNONYMS = {"store": "store outlet restaurant network footprint", "lfl": "lfl like-for-like like for like same store ssg",
            "margin": "margin ebitda ebit", "capex": "capex capital expenditure", "revenue": "revenue sales topline growth",
            "debt": "debt borrowing leverage", "order": "order inflow book"}
STOP = set("will with that this from have been into over next year years quarter quarters target range about around "
           "least more than almost below above reach achieve expect expected".split())


def page_of(quote, pg):
    """1-based page where the quote's first words appear, for citations."""
    if not quote:
        return None
    probe = re.sub(r"\W+", "", quote.lower())[:40]
    for i, t in enumerate(pg, 1):
        if probe and probe in re.sub(r"\W+", "", t.lower()):
            return i
    return None


def _keywords(p):
    words = {w for w in re.findall(r"[a-z][a-z-]{3,}", f"{p.get('metric', '')} {p.get('promise', '')}".lower()) if w not in STOP}
    for key, syn in SYNONYMS.items():
        if any(key in w for w in words) or key in (p.get("metric") or "").lower():
            words |= set(syn.split())
    return words


ANALYST = re.compile(r"\b(can you|could you|wanted to understand|want to understand|like to understand|my question|"
                     r"just to understand|trying to understand|i wanted|if you can|would you|welcome to)\b", re.I)
GENERIC_KW = set("growth revenue sales topline margin ebitda ebit business company brand brands".split())


def backward_statements(pg, keywords, limit_chars=3000):
    """Sentences reporting what happened, that mention promise keywords and a number, with their page. Ranked by how
    specifically they match (stores, LFL, capex beat 'growth'), so a 3k budget isn't spent on generic lines."""
    scored = []
    for page_no, t in enumerate(pg, 1):
        # Slides have no full stops: split on line breaks too, so a KPI table row counts as a statement.
        for s in [x.strip() for chunk in t.split("\n") for x in _sentences(chunk)]:
            low = s.lower()
            if not (25 < len(s) < 400 and re.search(r"\d", s) and REPORTED.search(s)):
                continue
            if "?" in s or ANALYST.search(s):  # analysts quoting numbers back are not management reporting them
                continue
            score = sum(1 if k in GENERIC_KW else 3 for k in keywords if k in low)
            if score:
                scored.append((score, page_no, s))
    keep, used = [], 0
    for score, page_no, s in sorted(scored, key=lambda x: -x[0]):
        if used + len(s) > limit_chars:
            break
        keep.append((page_no, s))
        used += len(s)
    return sorted(keep)


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _grounded(quote, pages_):
    """A KPI quote must actually appear in the document (ignoring case, punctuation and spacing)."""
    q = _norm(quote)
    if len(q) < 8:
        return False
    hay = _norm(" ".join(pages_))
    words = q.split()
    # Allow the model to trim a word at either end; require the core run of words verbatim.
    return q in hay or (len(words) > 4 and " ".join(words[1:-1]) in hay)


def reported_kpis(name, promises, per_doc, source_kind, stats=None):
    """Cheap calls per LATER document, covering every promise made before it. Returns {promise_id: [kpi...]}.

    The cheap model misses lines between runs, so each document is read twice (lines in page order, then reversed)
    and the results merged. A KPI is kept only if its quote is found verbatim in the document."""
    from .screener import _period_key
    out = {}
    stats = stats if stats is not None else {}
    for key in ("first", "second", "both", "dropped_ungrounded"):
        stats.setdefault(key, 0)
    for d in per_doc:
        earlier = [p for p in promises if _period_key(p["said_in"]) < _period_key(d["period"])]
        if not earlier:
            continue
        kws = set().union(*(_keywords(p) for p in earlier))
        lines = backward_statements(d["pages"], kws)
        if not lines:
            continue
        head = (f"Earlier, management of {name} made these promises:\n"
                + "\n".join(f"{p['id']}: {p.get('metric')}: {p['promise']} (said {p['said_in']})" for p in earlier)
                + f"\n\nBelow are lines from their {d['period']} {d.get('kind', source_kind)}, each with its page. Report what management "
                "says it actually achieved: one entry per matching line (quarterly and full-year figures both count), only "
                "where a line states it. Do not infer, and omit promises with no matching line.\n"
                '[{"id": "P1", "reported_value": "e.g. opened 52 stores in the quarter", "quote": "exact words, max 25", "page": 7}]\n\n')
        found = {}
        for pass_no, order in enumerate((lines, list(reversed(lines)))):
            got = llm.complete_json(head + "\n".join(f"[p{pn}] {s}" for pn, s in order), tier="cheap", max_tokens=900)
            for k in got or []:
                if not isinstance(k, dict) or not k.get("id") or is_placeholder(k.get("reported_value")):
                    continue  # the model is told to skip these; it doesn't always
                quote = " ".join(str(k.get("quote", "")).split()[:25])
                if not _grounded(quote, d["pages"]):
                    stats["dropped_ungrounded"] += 1
                    continue
                sig = (k["id"], _norm(quote)[:60])
                if sig in found:
                    found[sig]["passes"].add(pass_no)
                    continue
                found[sig] = {"passes": {pass_no}, "kpi": {
                    "metric": next((p.get("metric") for p in promises if p["id"] == k["id"]), None),
                    "reported_value": k["reported_value"], "quarter": d["period"], "quote": quote,
                    "page": _page_int(k.get("page")), "source_doc": d["url"], "doc_kind": d.get("kind", source_kind)}}
        for (pid, _), v in found.items():
            stats["first"] += 0 in v["passes"]
            stats["second"] += 1 in v["passes"]
            stats["both"] += len(v["passes"]) == 2
            out.setdefault(pid, []).append({**v["kpi"], "confirmed": len(v["passes"]) == 2})
    return out


PLACEHOLDER = re.compile(r"^\W*(n/?a|none|nil|-+|unknown)\W*$|^(not|no)\b.*\b(stated|reported|mentioned|disclosed|available|given|found)|reaffirm", re.I)


def _page_int(v):
    m = re.search(r"\d+", str(v or ""))
    return int(m.group(0)) if m and int(m.group(0)) > 0 else None


def is_placeholder(val) -> bool:
    """The model is told to skip promises with no evidence; it sometimes answers 'not mentioned' instead."""
    return not str(val or "").strip() or bool(PLACEHOLDER.search(str(val).strip()))


def attach_evidence(entries, promises, reported):
    """Citations come from code, not the model: the promise's own source and page, plus the latest later-call KPI."""
    by_id = {p["id"]: p for p in promises}
    for e in entries:
        ids = [i for i in (e.get("promise_ids") or []) if i in by_id]
        src = by_id[ids[0]] if ids else next((p for p in promises if p["said_in"] == e.get("said_in")), None)
        if src:
            e["url"], e["page"] = src["url"], src.get("page")
        from .screener import _period_key
        kpis = sorted((k for i in ids for k in reported.get(i, []) if not is_placeholder(k.get("reported_value"))),
                      key=lambda k: _period_key(k["quarter"]))
        if kpis:
            e["kpi"] = kpis[-1]          # latest, shown first
            e["kpis"] = kpis[-4:]        # the trail, for the record
            if e.get("verdict") == "not_disclosed":  # a later call does mention it, so "not disclosed" is wrong
                e["verdict"] = "too_early"
                e["evidence"] = (e.get("evidence") or "") + f" Later call reports: {kpis[-1]['reported_value']}."


def _save(conn, symbol, out):
    conn.execute("INSERT OR REPLACE INTO research VALUES (?,?,?)", (symbol, json.dumps(out), out["generated"]))
    conn.commit()
