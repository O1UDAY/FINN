import { useEffect, useState } from "react";
import { api, local } from "./api";
import { Bars, crore, fmt, PairBars } from "./ui";

const SUGGEST = ["TRENT", "PERSISTENT", "KAYNES", "CDSL", "DIXON", "POLYCAB"];
const VERDICTS = ["delivered", "partial", "missed", "pending"];

export default function Research({ symbol, setSymbol }) {
  const [q, setQ] = useState(symbol || "");
  const [num, setNum] = useState(null);
  const [ana, setAna] = useState(null);
  const [err, setErr] = useState(null);
  const recent = local.get("recent", []);

  useEffect(() => {
    if (!symbol) return;
    setQ(symbol); setNum(null); setAna(null); setErr(null);
    local.set("recent", [symbol, ...recent.filter((s) => s !== symbol)].slice(0, 6));
    api.numbers(symbol).then(setNum).catch((e) => setErr(e.message));
    api.analysis(symbol).then(setAna).catch((e) => setAna({ error: e.message }));
  }, [symbol]);

  const go = (s) => { const v = (s || q).trim().toUpperCase(); if (v) setSymbol(v); };

  return (
    <>
      <div className="mast"><span className="brand">FINN · INTERROGATE</span><span className="date">primary sources only</span></div>
      <form className="search" onSubmit={(e) => { e.preventDefault(); go(); }}>
        <span className="faint mono">NSE:</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Any ticker" autoCapitalize="characters" autoCorrect="off" spellCheck={false} />
        <button className="btn gold" type="submit">Ask</button>
      </form>
      <div className="chips">
        {[...new Set([...recent, ...SUGGEST])].slice(0, 8).map((s) => (
          <button key={s} className={"chip" + (s === symbol ? " on" : "")} onClick={() => go(s)}>{s}</button>
        ))}
      </div>

      {!symbol && (
        <div className="empty" style={{ paddingTop: 30 }}>
          <div className="big">Hold management to their word.</div>
          <p className="muted">Pick a ticker. FINN reads its last four concalls, extracts what was promised, and checks it against what was reported.</p>
        </div>
      )}
      {err && <div className="panel note warn">{err}</div>}
      {symbol && !num && !err && <div className="skel" style={{ height: 160, marginTop: 10 }} />}
      {num && <Numbers n={num} />}
      {num && <Analysis a={ana} n={num} />}
      {num && <Charts n={num} />}
      {num && <Sources n={num} a={ana} />}
    </>
  );
}

function Numbers({ n }) {
  const s = n.snapshot;
  return (
    <>
      <h1 className="co-name">{n.name}</h1>
      <div className="muted mono" style={{ fontSize: 13 }}>{n.symbol} · ₹{fmt(s["Current Price"], 1)}</div>
      <div className="stats">
        <div><div className="k">Mkt cap</div><div className="v">{crore(s["Market Cap"])}</div></div>
        <div><div className="k">P/E</div><div className="v">{fmt(s["Stock P/E"], 1)}</div></div>
        <div><div className="k">{n.lender ? "ROE" : "ROCE"}</div><div className="v">{fmt(n.lender ? s.ROE : s.ROCE, 1)}%</div></div>
        <div><div className="k">TTM sales</div><div className="v">{crore(n.ttm.sales)}</div></div>
        <div><div className="k">TTM profit</div><div className="v">{crore(n.ttm.pat)}</div></div>
        <div><div className="k">3y sales CAGR</div><div className="v">{n.trajectory.sales_cagr_3y ?? "—"}%</div></div>
      </div>
      {n.signals.length > 0 && (
        <div className="sec">
          <h3>The read <span>computed, not generated</span></h3>
          <div className="panel signals">
            {n.signals.map((x) => (
              <div className="signal" key={x.text}>
                <i style={{ background: x.kind === "good" ? "var(--up)" : x.kind === "bad" ? "var(--down)" : "var(--ink-3)" }} />{x.text}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function Analysis({ a, n }) {
  if (!a) {
    return (
      <div className="sec">
        <h3>Promised vs delivered</h3>
        <div className="skel" style={{ height: 120 }} />
        <div className="loading-line">reading the last four {""}concalls · extracting promises · checking against reported numbers…</div>
      </div>
    );
  }
  if (a.error) return <div className="sec panel note warn">{a.error}</div>;

  const pvd = a.promised_vs_delivered || [];
  const raw = a.promises || [];
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, pvd.filter((p) => p.verdict === v).length]));
  return (
    <>
      {a.business?.summary && (
        <div className="sec">
          <h3>Business</h3>
          <div className="panel">
            <div style={{ lineHeight: 1.5 }}>{a.business.summary}</div>
            {a.business.segments?.length > 0 && <div className="wrap" style={{ marginTop: 10 }}>{a.business.segments.map((s) => <span key={s} className="pill" style={{ margin: 0 }}>{s}</span>)}</div>}
          </div>
        </div>
      )}

      <div className="sec">
        <h2>Promised <span className="faint">vs</span> delivered</h2>
        <div className="note" style={{ marginTop: 0 }}>
          From {a.sources.length} {a.source_kind === "transcript" ? "concall transcripts" : "investor presentations (no concall transcripts filed)"} · {a.sources.map((s) => s.period).join(", ")}
        </div>
        {pvd.length > 0 && (
          <div className="score">
            {VERDICTS.map((v) => <div key={v}><div className={"n " + (v === "delivered" ? "up" : v === "missed" ? "down" : "")}>{counts[v]}</div><div className="l">{v}</div></div>)}
          </div>
        )}
        <div className="panel">
          {pvd.map((p, i) => <PromiseRow key={i} p={p} />)}
          {!pvd.length && raw.map((p, i) => <PromiseRow key={i} p={{ ...p, promise: p.promise || null }} />)}
          {!pvd.length && !raw.length && <div className="muted">No checkable forward-looking statements found in the filed documents.</div>}
        </div>
        {a.note && <div className="note warn">{a.note}</div>}
      </div>

      {a.narrative_vs_numbers?.length > 0 && (
        <div className="sec">
          <h3>Narrative vs numbers</h3>
          <div className="panel">
            {a.narrative_vs_numbers.map((x, i) => (
              <div className="promise" key={i}>
                <div className="top"><span className={"verdict " + (x.agrees ? "v-delivered" : "v-missed")}>{x.agrees ? "agrees" : "diverges"}</span></div>
                <div className="what">{x.claim}</div>
                <div className="ev">{x.reality}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {a.guidance?.length > 0 && (
        <div className="sec">
          <h3>Current guidance</h3>
          <div className="panel">
            {a.guidance.map((g, i) => <div className="row" key={i}><span className="muted">{g.metric}</span><span style={{ textAlign: "right" }}>{g.guidance}</span></div>)}
          </div>
        </div>
      )}

      {(a.bull?.length > 0 || a.bear?.length > 0) && (
        <div className="sec">
          <h3>The case</h3>
          <div className="case">
            <div className="panel"><h4 className="up">Bull</h4><ul>{(a.bull || []).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div className="panel"><h4 className="down">Bear</h4><ul>{(a.bear || []).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          </div>
        </div>
      )}
    </>
  );
}

function PromiseRow({ p }) {
  const [showQuote, setShowQuote] = useState(!p.promise);
  return (
    <div className="promise">
      <div className="top">
        <span className={"verdict v-" + (p.verdict || "unverified")}>{p.verdict || "on record"}</span>
        <span className="mono">{p.said_in}</span>
        {p.metric && <span>· {p.metric}</span>}
      </div>
      {p.promise && <div className="what">{p.promise}</div>}
      {(p.evidence || p.outcome) && <div className="ev">{p.evidence || p.outcome}</div>}
      {p.quote && p.promise && !showQuote && <button className="src" onClick={() => setShowQuote(true)}>What they said ›</button>}
      {p.quote && showQuote && <div className="quote">“{p.quote}”</div>}
      {p.url && <a className="src" style={{ marginLeft: p.quote && !showQuote ? 12 : 0 }} href={p.url} target="_blank" rel="noreferrer">Source ↗</a>}
    </div>
  );
}

function Charts({ n }) {
  const pct = (x) => `${fmt(x)}%`;
  return (
    <>
      <div className="sec">
        <h3>Trajectory <span>annual, ₹ cr</span></h3>
        <div className="panel">
          <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Revenue</div>
          <Bars series={n.trajectory.sales} />
          <div className="muted" style={{ fontSize: 12, margin: "14px 0 6px" }}>Profit after tax</div>
          <Bars series={n.trajectory.pat} />
          {!n.lender && <><div className="muted" style={{ fontSize: 12, margin: "14px 0 6px" }}>Operating margin</div><Bars series={n.trajectory.opm} format={pct} /></>}
        </div>
      </div>
      <div className="sec">
        <h3>Last 8 quarters <span>revenue, ₹ cr</span></h3>
        <div className="panel"><Bars series={n.quarters.sales} /></div>
      </div>
      {!n.lender && (
        <div className="sec">
          <h3>Cash quality <span>{n.cash.conversion != null ? `CFO/PAT ${Math.round(n.cash.conversion * 100)}%` : ""}</span></h3>
          <div className="panel"><PairBars a={n.cash.cfo} b={n.cash.pat} la="Cash from operations" lb="Reported profit" /></div>
        </div>
      )}
      {!n.lender && (
        <div className="sec">
          <h3>Balance sheet</h3>
          <div className="panel">
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Debt / equity</div>
            <Bars series={n.balance.de} format={(x) => fmt(x, 2)} />
            <div className="muted" style={{ fontSize: 12, margin: "14px 0 6px" }}>Cash conversion cycle (days)</div>
            <Bars series={n.balance.ccc} />
          </div>
        </div>
      )}
    </>
  );
}

function Sources({ n, a }) {
  const docs = n.documents.filter((d) => d.kind !== "annual_report").slice(0, 6);
  const ar = n.documents.find((d) => d.kind === "annual_report");
  return (
    <div className="sec">
      <h3>Primary sources</h3>
      <div className="panel">
        {ar && <div className="row"><span>{ar.period}</span><a className="src" href={ar.url} target="_blank" rel="noreferrer">Open ↗</a></div>}
        {docs.map((d) => <div className="row" key={d.url}><span>{d.period} <span className="faint">· {d.kind}</span></span><a className="src" href={d.url} target="_blank" rel="noreferrer">Open ↗</a></div>)}
      </div>
      <div className="note">Numbers: screener.in tables compiled from exchange filings. Judgement: {a?.llm ? "LLM over transcripts, cached" : "no LLM configured"}. No news, no broker notes.</div>
    </div>
  );
}
