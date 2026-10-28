import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";

const COMPANY_QS = ["What did they guide for next year?", "What did they say about margins?", "Why did debt change?", "What risks did they mention?"];
const FILING_QS = ["What is this about?", "What amount is involved?", "When does it take effect?"];
// Typing suggestions: the questions investors ask most, matched against what's being typed.
const POOL = [
  ...COMPANY_QS, ...FILING_QS,
  "How many stores did they open?", "What is the capex plan?", "What did they say about demand?", "What is the revenue growth guidance?",
  "What did they say about competition?", "How is the order book?", "What did they say about pricing?", "What is the dividend?",
  "What did they say about raw material costs?", "What is the debt reduction plan?", "Any new products or launches?",
  "What did they say about exports?", "What is the margin guidance?", "Who is the new appointee?", "What are the growth drivers?",
  "What did they say about working capital?", "How did the new businesses do?", "What is the outlook for next quarter?",
];

function suggest(text, extra) {
  const words = text.toLowerCase().split(/\W+/).filter((w) => w.length > 1);
  if (!words.length) return [];
  const pool = [...new Set([...extra, ...POOL])];
  return pool
    .map((q) => {
      const low = q.toLowerCase();
      // Every typed word must appear; the last one may be half-typed.
      const ok = words.every((w, i) => (i === words.length - 1 ? low.includes(w) : new RegExp(`\\b${w}`).test(low)));
      return ok ? [q, low.startsWith(text.toLowerCase()) ? 0 : 1] : null;
    })
    .filter(Boolean).sort((a, b) => a[1] - b[1]).slice(0, 4).map((x) => x[0]);
}

/** A conversation with the company's own documents. Follow-ups ("and last year?") use the earlier turns;
    every answer carries the quotes it rests on, checked against the documents. */
export default function Ask({ symbol, aid }) {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState([]); // [{ q, res, err }]
  const [busy, setBusy] = useState(false);
  const [focus, setFocus] = useState(false);
  const end = useRef(null);
  const last = turns[turns.length - 1];
  const followUps = last?.res?.follow_ups || [];
  const typed = useMemo(() => (focus && q.trim().length >= 2 ? suggest(q.trim(), followUps) : []), [q, focus, followUps]);

  useEffect(() => { if (turns.length > 1) end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [turns]);

  async function go(question) {
    const v = (question ?? q).trim();
    if (v.length < 3 || busy) return;
    setQ(""); setBusy(true);
    const history = turns.filter((t) => t.res?.found).map((t) => ({ q: t.q, a: t.res.answer }));
    setTurns((ts) => [...ts, { q: v }]);
    let res = null, err = null;
    try { res = await api.ask(symbol, v, aid, history); } catch (e) { err = e.message; }
    setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? { ...t, res, err } : t)));
    setBusy(false);
  }

  const starters = aid ? FILING_QS : COMPANY_QS;
  return (
    <div className="ask">
      <div className="ask-head">
        <h3>Ask {aid ? "this filing" : "the documents"}</h3>
        {turns.length > 0 && <button className="link-btn" onClick={() => setTurns([])} disabled={busy}>New conversation</button>}
      </div>

      {turns.map((t, i) => (
        <div className="turn" key={i}>
          <p className="you">{t.q}</p>
          {!t.res && !t.err && <div className="loading">Reading {aid ? "the filing" : "the calls and presentations"}</div>}
          {t.err && <p className="note warn">{t.err}</p>}
          {t.res && <Answer res={t.res} latest={i === turns.length - 1} />}
        </div>
      ))}
      <div ref={end} />

      <form onSubmit={(e) => { e.preventDefault(); go(); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
          placeholder={turns.length ? "Ask a follow-up, e.g. “and last year?”" : aid ? "Ask about this filing" : `Ask about ${symbol}`}
          aria-label={`Question about ${symbol}`} maxLength={300} autoComplete="off" />
        <button type="submit" disabled={busy}>Ask</button>
      </form>
      {typed.length > 0 && (
        <ul className="ask-typed" role="listbox" aria-label="Suggested questions">
          {typed.map((x) => <li key={x}><button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => go(x)}>{x}</button></li>)}
        </ul>
      )}
      {!typed.length && !busy && (
        <div className="ask-qs">
          {(turns.length ? followUps : starters).map((x) => <button key={x} onClick={() => go(x)}>{x}</button>)}
        </div>
      )}
    </div>
  );
}

function Answer({ res, latest }) {
  return (
    <div className="ask-ans">
      <p className={res.found ? "prose" : "note"}>{res.answer}</p>
      {res.cites.map((c, i) => (
        <blockquote key={i}>
          “{c.quote}”
          <cite><a href={`${c.url}#page=${c.page}`} target="_blank" rel="noreferrer">{c.doc}, p. {c.page}</a></cite>
        </blockquote>
      ))}
      {latest && <p className="note">
        Searched: {res.searched.length ? res.searched.map((d, i) => <span key={d.url}>{i > 0 && ", "}<a href={d.url} target="_blank" rel="noreferrer">{d.label}</a></span>) : "nothing available"}.
        {" "}Answers come only from these documents; every quote is checked against them.
      </p>}
    </div>
  );
}
