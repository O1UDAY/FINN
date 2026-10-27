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


def numbers(symbol: str) -> dict:
    c = company(symbol)
    t = c["tables"]
    pl, bs, cf, rt, q = (t.get(k) for k in ("profit-loss", "balance-sheet", "cash-flow", "ratios", "quarters"))
    lender = bool(q and "Financing Profit" in q["rows"])

    # Annual tables end with a TTM column; trajectory uses fiscal years only.
    pl_cols = [x for x in pl["cols"] if x != "TTM"] if pl else []
    sales = (_series(pl, "Sales", "Revenue") or [])[:len(pl_cols)]
    pat = (_series(pl, "Net Profit") or [])[:len(pl_cols)]
    opm = (_series(pl, "OPM %", "Financing Margin %") or [])[:len(pl_cols)]

    equity = [(a or 0) + (b or 0) for a, b in zip(_series(bs, "Equity Capital") or [], _series(bs, "Reserves") or [])]
    debt = _series(bs, "Borrowings", "Borrowing") or []
    de = [round(d / e, 2) if e else None for d, e in zip(debt, equity)]
    cfo = _series(cf, "Cash from Operating Activity") or []
    fcf = _series(cf, "Free Cash Flow") or []
    ccc = _series(rt, "Cash Conversion Cycle") or []
    roce = _series(rt, "ROCE %", "ROE %") or []

    # CFO vs PAT over matching fiscal years (cash-flow columns align with the last N P&L years).
    n = min(len(cfo), len(pat), 5)
    cash_conv = round(sum(x or 0 for x in cfo[-n:]) / sum(x or 0 for x in pat[-n:]), 2) if n and sum(x or 0 for x in pat[-n:]) > 0 else None

    signals = []
    def sig(kind, text):
        signals.append({"kind": kind, "text": text})
    g3, p3 = _cagr(sales, 3), _cagr(pat, 3)
    if g3 is not None:
        sig("good" if g3 >= 15 else "bad" if g3 < 5 else "neutral", f"Revenue 3y CAGR {g3}%")
    if p3 is not None and g3 is not None:
        sig("good" if p3 > g3 else "bad", f"Profit 3y CAGR {p3}% {'ahead of' if p3 > g3 else 'behind'} revenue")
    if not lender and cash_conv is not None:
        sig("good" if cash_conv >= 0.9 else "bad" if cash_conv < 0.7 else "neutral",
            f"{n}y cash from ops = {cash_conv:.0%} of reported profit")
    if not lender and len(de) >= 3 and de[-1] is not None and de[-3] is not None:
        if de[-1] > de[-3] + 0.15:
            sig("bad", f"Leverage rising: D/E {de[-3]} → {de[-1]}")
        elif de[-1] < 0.3:
            sig("good", f"Low leverage: D/E {de[-1]}")
    if len(ccc) >= 3 and None not in (ccc[-1], ccc[-3]) and abs(ccc[-1] - ccc[-3]) >= 10:
        sig("bad" if ccc[-1] > ccc[-3] else "good", f"Cash conversion cycle {ccc[-3]:.0f} → {ccc[-1]:.0f} days")
    if not lender and len(opm) >= 3 and None not in (opm[-1], opm[-3]) and abs(opm[-1] - opm[-3]) >= 2:
        sig("good" if opm[-1] > opm[-3] else "bad", f"Margin {'expanding' if opm[-1] > opm[-3] else 'compressing'}: {opm[-3]:.0f}% → {opm[-1]:.0f}%")

    qcols = q["cols"] if q else []
    return {
        "symbol": c["symbol"], "name": c["name"], "lender": lender,
        "snapshot": {k: c["ratios"].get(k) for k in ("Market Cap", "Current Price", "Stock P/E", "ROCE", "ROE", "Dividend Yield")},
        "ttm": {"sales": (_series(pl, "Sales", "Revenue") or [None])[-1], "pat": (_series(pl, "Net Profit") or [None])[-1]},
        "trajectory": {"sales": _last(pl_cols, sales, 7), "pat": _last(pl_cols, pat, 7), "opm": _last(pl_cols, opm, 7),
                       "sales_cagr_3y": g3, "pat_cagr_3y": p3, "sales_cagr_5y": _cagr(sales, 5)},
        "quarters": {"sales": _last(qcols, _series(q, "Sales", "Revenue"), 8), "pat": _last(qcols, _series(q, "Net Profit"), 8),
                     "opm": _last(qcols, _series(q, "OPM %", "Financing Margin %"), 8)},
        "balance": {"debt": _last(bs["cols"] if bs else [], debt, 5), "de": _last(bs["cols"] if bs else [], de, 5),
                    "ccc": _last(rt["cols"] if rt else [], ccc, 5), "roce": _last(rt["cols"] if rt else [], roce, 5)},
        "cash": {"cfo": _last(cf["cols"] if cf else [], cfo, 5), "pat": _last(pl_cols, pat, 5),
                 "fcf": _last(cf["cols"] if cf else [], fcf, 5), "conversion": cash_conv},
        "signals": signals,
        "documents": c["documents"][:24],
    }


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


def analysis(symbol: str, refresh=False) -> dict:
    symbol = symbol.upper().strip()
    conn = connect()
    if not refresh:
        row = conn.execute("SELECT payload FROM research WHERE symbol=?", (symbol,)).fetchone()
        if row:
            return json.loads(row["payload"])

    num = numbers(symbol)
    docs, source_kind = _sources(num["documents"])
    per_doc = []
    opening = ""
    for d in docs:
        text = "\n".join(pages(d["url"]))
        if not text:
            continue
        if not opening:
            opening = re.sub(r"\s+", " ", text)[:9000]
        per_doc.append({"period": d["period"], "url": d["url"], "candidates": forward_statements(text)})

    out = {"symbol": symbol, "source_kind": source_kind, "sources": [{"period": d["period"], "url": d["url"]} for d in per_doc],
           "llm": llm.available(), "generated": datetime.now().isoformat(timespec="seconds")}

    if not llm.available():
        out["promises"] = [{"said_in": d["period"], "quote": q, "url": d["url"], "verdict": "unverified"}
                           for d in per_doc for q in d["candidates"][:4]]
        out["note"] = "No LLM key configured: showing raw forward-looking statements without verdicts."
        _save(conn, symbol, out)
        return out

    # Step 2: cheap model structures promises per document.
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
                promises.append({**p, "said_in": d["period"], "url": d["url"]})

    # Step 3: one strong call does the judging.
    actuals = {"quarterly": num["quarters"], "annual": num["trajectory"], "balance": num["balance"], "cash": num["cash"]}
    judged = llm.complete_json(
        f"Company: {num['name']} ({symbol}). Use ONLY the material below - no outside knowledge.\n\n"
        f"OPENING OF LATEST {source_kind.upper()} (for business description):\n{opening[:6000]}\n\n"
        f"MANAGEMENT PROMISES (oldest calls are the most checkable):\n{json.dumps(promises, ensure_ascii=False)[:9000]}\n\n"
        f"REPORTED NUMBERS (₹ crore, % for margins):\n{json.dumps(actuals)[:7000]}\n\n"
        "Tasks:\n"
        "1. business: 2-sentence plain-English description and main segments/revenue drivers.\n"
        "2. promised_vs_delivered: for each checkable promise, compare with reported numbers. verdict is one of "
        "delivered | missed | partial | pending (pending = horizon not reached or numbers not available). evidence cites the numbers.\n"
        "3. narrative_vs_numbers: up to 3 places where management's story and the numbers agree or diverge.\n"
        "4. guidance: the current explicit guidance from the LATEST call only.\n"
        "5. bull and bear: 3 tight points each, grounded in the material.\n"
        'JSON: {"business": {"summary": "", "segments": [""]}, "promised_vs_delivered": [{"said_in": "", "metric": "", '
        '"promise": "", "quote": "", "outcome": "", "verdict": "", "evidence": ""}], "narrative_vs_numbers": '
        '[{"claim": "", "reality": "", "agrees": true}], "guidance": [{"metric": "", "guidance": ""}], "bull": [""], "bear": [""]}',
        tier="strong", max_tokens=3500,
        system="You are a sceptical buy-side analyst. You judge management by what they delivered, citing numbers. Be terse.")
    if judged:
        urls = {p["said_in"]: p["url"] for p in promises}
        for p in judged.get("promised_vs_delivered", []):
            p["url"] = urls.get(p.get("said_in"))
        out.update(judged)
    else:
        out["promises"] = promises
    _save(conn, symbol, out)
    return out


def _save(conn, symbol, out):
    conn.execute("INSERT OR REPLACE INTO research VALUES (?,?,?)", (symbol, json.dumps(out), out["generated"]))
    conn.commit()
