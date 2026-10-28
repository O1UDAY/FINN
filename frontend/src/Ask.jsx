import { useState } from "react";
import { api } from "./api";

const COMPANY_QS = ["What did they guide for next year?", "What did they say about margins?", "Why did debt change?", "What risks did they mention?"];
const FILING_QS = ["What is this about?", "What amount is involved?", "When does it take effect?"];

/** Questions answered only from the company's own documents. Every answer carries the quotes it rests on. */
export default function Ask({ symbol, aid }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);

  async function go(question) {
    const v = (question ?? q).trim();
    if (v.length < 3 || busy) return;
    setQ(v); setBusy(true); setErr(null); setRes(null);
    try { setRes(await api.ask(symbol, v, aid)); } catch (e) { setErr(e.message); }
    setBusy(false);
  }

  return (
    <div className="ask">
      <h3>Ask {aid ? "this filing" : "the documents"}</h3>
      <form onSubmit={(e) => { e.preventDefault(); go(); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={aid ? "Ask about this filing" : `Ask about ${symbol}`}
          aria-label={`Question about ${symbol}`} maxLength={300} />
        <button type="submit" disabled={busy}>Ask</button>
      </form>
      <div className="ask-qs">
        {(aid ? FILING_QS : COMPANY_QS).map((x) => <button key={x} onClick={() => go(x)} disabled={busy}>{x}</button>)}
      </div>
      {busy && <div className="loading">Reading {aid ? "the filing" : "the calls and presentations"}</div>}
      {err && <p className="note warn">{err}</p>}
      {res && (
        <div className="ask-ans">
          <p className={res.found ? "prose" : "note"}>{res.answer}</p>
          {res.cites.map((c, i) => (
            <blockquote key={i}>
              “{c.quote}”
              <cite><a href={`${c.url}#page=${c.page}`} target="_blank" rel="noreferrer">{c.doc}, p. {c.page}</a></cite>
            </blockquote>
          ))}
          <p className="note">
            Searched: {res.searched.length ? res.searched.map((d, i) => <span key={d.url}>{i > 0 && ", "}<a href={d.url} target="_blank" rel="noreferrer">{d.label}</a></span>) : "nothing available"}.
            {" "}Answers come only from these documents; every quote is checked against them.
          </p>
        </div>
      )}
    </div>
  );
}
