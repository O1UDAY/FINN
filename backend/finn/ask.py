"""Ask the documents: a question answered only from the company's own filings, with page citations.

Not a chatbot. The answer must quote the documents searched, every quote is checked verbatim against them, and when
nothing in them answers the question it says so instead of reaching for the model's own knowledge.
"""
import re

from . import llm
from .db import connect
from .pdftext import pages
from .research import _grounded, _sources, numbers

STOP = set("""a an and are as at be been but by can could did do does for from had has have how i if in into is it its
of on or our over said say says should so than that the their them then there these they this those to up was we were
what when where which who why will with would you your company management about any much many more most last next
year years quarter quarters""".split())

# Plain words an investor types, and the words filings actually use.
SYNONYMS = {"amount": ["crore", "lakh", "rs", "inr", "₹", "consideration"], "debt": ["borrowings", "loan", "leverage"],
            "effect": ["effective", "w.e.f", "with effect", "date"], "margin": ["margins", "ebitda", "ebit"],
            "margins": ["margin", "ebitda"], "guide": ["guidance", "expect", "target", "outlook"],
            "guidance": ["guide", "expect", "target", "outlook"], "risks": ["risk", "headwind", "challenge", "concern"],
            "stores": ["store", "restaurants", "outlets"], "capex": ["capital expenditure", "investment"]}

KIND = {"transcript": "call", "presentation": "presentation", "annual_report": "annual report"}


def _terms(question):
    words = re.findall(r"[a-z0-9%]+", question.lower())
    terms = [w for w in words if len(w) > 2 and w not in STOP]
    return terms + [x for t in terms for x in SYNONYMS.get(t, []) if x not in terms]


def _chunks(text):
    """Paragraph-sized pieces: transcripts break on speaker turns, presentations on lines."""
    parts = re.split(r"\n\s*\n|(?<=[.?!])\s+(?=[A-Z])", text)
    out, cur = [], ""
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if not p:
            continue
        cur = f"{cur} {p}".strip()
        if len(cur) > 220:
            out.append(cur[:700])
            cur = ""
    if cur:
        out.append(cur[:700])
    return out


def _score(chunk, terms):
    low = chunk.lower()
    hits = [t for t in terms if t in low]
    # Distinct terms matter more than repeats; a figure in the chunk makes it likelier to answer "how much".
    return len(set(hits)) * 3 + sum(low.count(t) for t in hits) + (1 if re.search(r"\d", chunk) else 0)


def _docs(symbol, aid):
    if aid:
        r = connect().execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone()
        if r and r["attachment"]:
            return [{"label": f"this filing ({r['subject'][:60]})", "url": r["attachment"]}]
    c_docs = numbers(symbol)["documents"]
    docs, _ = _sources(c_docs)
    pres = [d for d in c_docs if d["kind"] == "presentation" and d not in docs][:2]
    return [{"label": f"{d['period']} {KIND.get(d['kind'], d['kind'])}", "url": d["url"]} for d in docs + pres]


def ask(symbol: str, question: str, aid: str | None = None) -> dict:
    symbol = symbol.upper().strip()
    question = question.strip()[:300]
    docs = _docs(symbol, aid)
    searched = [{"label": d["label"], "url": d["url"]} for d in docs]
    terms = _terms(question)
    texts, ranked = {}, []
    for i, d in enumerate(docs, 1):
        texts[i] = pages(d["url"])
        for pn, page in enumerate(texts[i], 1):
            for ch in _chunks(page):
                s = _score(ch, terms) if terms else 0
                if aid and pn <= 3:
                    s += 4  # a single filing is short: its opening pages always go in, so "what is this?" works
                if s >= 4:
                    ranked.append((s, i, pn, ch))
    none = {"found": False, "answer": "Not in the documents searched.", "cites": [], "searched": searched}
    if not any(texts.values()):
        return {**none, "answer": "Couldn't read the text of these documents (they may be scanned images, or the "
                                  "exchange refused the download). Open them directly."}
    if not ranked:
        return none
    if not llm.available():
        return {**none, "answer": "No model key configured, so FINN can't answer questions. The documents are linked below."}
    ranked.sort(key=lambda x: -x[0])
    excerpts, used = [], 0
    for s, i, pn, ch in ranked:
        if used > 8000:
            break
        excerpts.append(f"[D{i} p{pn}] {ch}")
        used += len(ch)
    prompt = (
        f"Question about {symbol}: {question}\n\n"
        "Answer ONLY from the excerpts below, which come from the company's own filings. No outside knowledge, no "
        "guessing. At most 70 words, plain English, figures exactly as written. If the excerpts don't answer it, say "
        "found=false.\nFor every claim give the excerpt tag and a short exact quote (max 20 words) that supports it.\n"
        '{"found": true, "answer": "...", "cites": [{"doc": 1, "page": 7, "quote": "exact words"}]}\n\n'
        + "\n".join(excerpts))
    got = llm.complete_json(prompt, tier="cheap", max_tokens=500)
    if got is None:
        return {**none, "answer": "The AI model couldn't answer just now (its free limit may be used up, or the key "
                                  "was refused). Try again shortly, or check the key in Settings."}
    if not isinstance(got, dict) or not got.get("found"):
        return none
    cites = []
    for c in got.get("cites") or []:
        try:
            i, pn = int(c.get("doc")), int(c.get("page"))
        except (TypeError, ValueError):
            continue
        if i in texts and 1 <= pn <= len(texts[i]) and _grounded(c.get("quote"), [texts[i][pn - 1]]):
            cites.append({"doc": docs[i - 1]["label"], "url": docs[i - 1]["url"], "page": pn, "quote": c["quote"]})
    if not cites:
        # The model answered but none of its quotes are in the documents: treat that as no answer.
        return {**none, "answer": "Found related passages, but no quotable answer. Open the documents below."}
    return {"found": True, "answer": str(got.get("answer", "")).strip(), "cites": cites, "searched": searched}
