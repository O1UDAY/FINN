import { useEffect, useState } from "react";
import { api, local } from "./api";
import Masthead from "./Masthead";
import { Bars, crore, fmt, IconDot, IconDown, IconSearch, IconUp, PairBars } from "./ui";

const SUGGEST = ["TRENT", "PERSISTENT", "KAYNES", "CDSL", "DIXON", "POLYCAB"];
const VERDICTS = ["delivered", "partly", "missed", "too_early", "not_disclosed"];
const VERDICT_LABEL = { delivered: "Delivered", partly: "Partly", partial: "Partly", missed: "Missed", too_early: "Too early", pending: "Too early", not_disclosed: "Not disclosed" };

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
      <Masthead>Company research</Masthead>
      <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); go(); }}>
        <IconSearch />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="NSE symbol, e.g. TRENT" aria-label="NSE symbol"
          autoCapitalize="characters" autoCorrect="off" spellCheck={false} />
        <button type="submit">Search</button>
      </form>
      <div className="recent">
        {[...new Set([...recent, ...SUGGEST])].slice(0, 8).map((s) => (
          <button key={s} className={s === symbol ? "on" : ""} onClick={() => go(s)}>{s}</button>
        ))}
      </div>

      {!symbol && (
        <div className="empty">
          <h2>Did they do what they said?</h2>
          <p>Pick a company. FINN reads its last four earnings calls, lists what management committed to, and checks each one against the reported numbers.</p>
        </div>
      )}
      {err && <p className="note warn">{err === `${symbol} not found on screener.in` ? `No listed company found for “${symbol}”. Check the NSE symbol.` : err}</p>}
      {symbol && !num && !err && <div className="loading">Pulling {symbol}'s financials</div>}
      {num && <Header n={num} />}
      {num && <Analysis a={ana} />}
      {num && <Charts n={num} />}
      {num && <Sources n={num} a={ana} />}
    </>
  );
}

function Header({ n }) {
  const s = n.snapshot;
  return (
    <>
      <h1 className="co-name">{n.name}</h1>
      <div className="co-line">NSE: {n.symbol} · ₹{fmt(s["Current Price"], 2)}</div>
      <div className="keyfigs">
        <div><div className="k">Market cap</div><div className="v">{crore(s["Market Cap"])}</div></div>
        <div><div className="k">P/E</div><div className="v">{fmt(s["Stock P/E"], 1)}</div></div>
        <div><div className="k">{n.lender ? "ROE" : "ROCE"}</div><div className="v">{fmt(n.lender ? s.ROE : s.ROCE, 1)}%</div></div>
        <div><div className="k">Sales, last 12m</div><div className="v">{crore(n.ttm.sales)}</div></div>
        <div><div className="k">Profit, last 12m</div><div className="v">{crore(n.ttm.pat)}</div></div>
        <div><div className="k">Sales growth, 3y</div><div className="v">{n.trajectory.sales_cagr_3y ?? "–"}% a yr</div></div>
      </div>
      {n.signals.length > 0 && (
        <section className="sec">
          <h2>What the numbers say</h2>
          <ul className="points">
            {n.signals.map((x) => (
              <li key={x.text}>
                {x.kind === "good" ? <IconUp className="up" /> : x.kind === "bad" ? <IconDown className="down" />
                  : <IconDot className={x.kind === "check" ? "warn-ico" : "faint"} />}
                <span>{x.text}{x.note && <span className="sig-note">{x.note}</span>}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function Analysis({ a }) {
  if (!a) {
    return (
      <section className="sec">
        <h2>Promises and delivery</h2>
        <div className="loading">Reading the last four earnings calls. This takes a minute the first time.</div>
      </section>
    );
  }
  if (a.error) return <p className="note warn">The earnings-call analysis failed: {a.error}</p>;

  const pvd = a.promised_vs_delivered || [];
  const raw = a.promises || [];
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, pvd.filter((p) => p.verdict === v).length]));
  const src = a.source_kind === "transcript" ? "earnings-call transcripts" : "investor presentations (this company doesn't publish call transcripts)";
  return (
    <>
      {a.business?.summary && (
        <section className="sec">
          <h2>The business</h2>
          <p className="prose">{a.business.summary}</p>
          {a.business.segments?.length > 0 && <p className="note">{a.business.segments.join(" · ")}</p>}
        </section>
      )}

      <section className="sec">
        <h2>Promises and delivery</h2>
        <p className="dek">What management said on {a.sources.length} {src}, {a.sources.map((s) => s.period).join(", ")}, set against what they reported.</p>
        {pvd.length > 0 && (
          <div className="tally">{VERDICTS.filter((v) => counts[v]).map((v) => <span key={v}><b>{counts[v]}</b>{VERDICT_LABEL[v].toLowerCase()}</span>)}</div>
        )}
        <ul className="ledger">
          {pvd.map((p, i) => <Commitment key={i} p={p} />)}
          {!pvd.length && raw.map((p, i) => <Commitment key={i} p={p} />)}
        </ul>
        {!pvd.length && !raw.length && <p className="muted">No specific, checkable commitments in the filed documents.</p>}
        {a.note && <p className="note warn">{a.note}</p>}
      </section>

      {a.narrative_vs_numbers?.length > 0 && (
        <section className="sec">
          <h2>Story against numbers</h2>
          <ul className="ledger">
            {a.narrative_vs_numbers.map((x, i) => (
              <li key={i}>
                <span className={"verdict " + (x.agrees ? "v-delivered" : "v-missed")}>{x.agrees ? "Holds up" : "Doesn't add up"}</span>
                <div className="what">{x.claim}</div>
                <div className="ev">{x.reality}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {a.guidance?.length > 0 && (
        <section className="sec">
          <h2>Current guidance</h2>
          <div className="rows">{a.guidance.map((g, i) => <div className="row" key={i}><span className="muted">{g.metric}</span><span>{g.guidance}</span></div>)}</div>
        </section>
      )}

      {(a.bull?.length > 0 || a.bear?.length > 0) && (
        <section className="sec">
          <h2>The case for and against</h2>
          <div className="case">
            <div><h3 className="up">For</h3><ul>{(a.bull || []).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
            <div><h3 className="down">Against</h3><ul>{(a.bear || []).map((x, i) => <li key={i}>{x}</li>)}</ul></div>
          </div>
        </section>
      )}
    </>
  );
}

function Commitment({ p }) {
  const [quote, setQuote] = useState(!p.promise);
  const v = p.verdict && p.verdict !== "unverified" ? p.verdict : null;
  const k = p.kpi;
  return (
    <li>
      <span className={"verdict v-" + (v || "on")}>{v ? VERDICT_LABEL[v] || v : "Said on the call"}</span>
      {p.promise && <div className="what">{p.promise}</div>}
      {(p.evidence || p.outcome) && <div className="ev">{p.evidence || p.outcome}</div>}
      {k && (
        <div className="kpi">
          <span className="kpi-src">Reported {k.quarter}{k.page ? `, p. ${k.page}` : ""}:</span> {k.reported_value}
          {k.quote && <blockquote>{k.quote}</blockquote>}
          {k.source_doc && <a href={k.source_doc} target="_blank" rel="noreferrer">Open {k.quarter} document</a>}
        </div>
      )}
      {p.quote && quote && <blockquote>{p.quote}</blockquote>}
      <div className="meta">
        <span>Said {p.said_in}{p.page ? `, p. ${p.page}` : ""}{p.metric ? ` · ${p.metric}` : ""}</span>
        {p.quote && p.promise && <button onClick={() => setQuote((x) => !x)}>{quote ? "Hide quote" : "Their words"}</button>}
        {p.url && <a href={p.url} target="_blank" rel="noreferrer">Source</a>}
      </div>
    </li>
  );
}

function Charts({ n }) {
  const pct = (x) => `${fmt(x)}%`;
  return (
    <>
      <section className="sec">
        <h2>Over the years</h2>
        <div className="chart-title">Revenue <span>₹ cr, by fiscal year</span></div>
        <Bars series={n.trajectory.sales} />
        <div className="chart-title">Profit after tax <span>₹ cr</span></div>
        <Bars series={n.trajectory.pat} />
        {!n.lender && <><div className="chart-title">Operating margin <span>%</span></div><Bars series={n.trajectory.opm} format={pct} /></>}
        <div className="chart-title">Revenue, last eight quarters <span>₹ cr</span></div>
        <Bars series={n.quarters.sales} />
      </section>
      {!n.lender && (
        <section className="sec">
          <h2>Cash and debt</h2>
          <div className="chart-title">Does profit turn into cash? <span>{(n.lease_flag ? n.cash.conversion_ex_lease : n.cash.conversion) != null ? `${Math.round((n.lease_flag ? n.cash.conversion_ex_lease : n.cash.conversion) * 100)}% over 5 yrs` : ""}</span></div>
          {n.lease_flag && n.cash.cfo_ex_lease?.length > 0
            ? <PairBars a={n.cash.cfo_ex_lease} b={n.cash.pat} la="Cash from operations after lease payments" lb="Reported profit" />
            : <PairBars a={n.cash.cfo} b={n.cash.pat} la="Cash from operations" lb="Reported profit" />}
          {n.lease_flag && <p className="note warn">Lease-heavy ({n.lease_reason}): figures above are after lease payments.</p>}
          <div className="chart-title">Debt to equity <span>{n.lease_flag && n.balance.de_ex_lease?.length ? "times, excluding leases" : "times"}</span></div>
          <Bars series={n.lease_flag && n.balance.de_ex_lease?.length ? n.balance.de_ex_lease : n.balance.de} format={(x) => fmt(x, 2)} />
          <div className="chart-title">Cash conversion cycle <span>days</span></div>
          <Bars series={n.balance.ccc} />
        </section>
      )}
    </>
  );
}

function Sources({ n, a }) {
  const ar = n.documents.find((d) => d.kind === "annual_report");
  const docs = n.documents.filter((d) => d.kind !== "annual_report").slice(0, 5);
  return (
    <section className="sec">
      <h2>Sources</h2>
      <div className="rows">
        {ar && <div className="row"><span>{ar.period}</span><a href={ar.url} target="_blank" rel="noreferrer">Open PDF</a></div>}
        {docs.map((d) => <div className="row" key={d.url}><span>{d.kind === "transcript" ? "Earnings call" : "Investor presentation"}, {d.period}</span><a href={d.url} target="_blank" rel="noreferrer">Open PDF</a></div>)}
      </div>
      <p className="note">Figures from screener.in, compiled from exchange filings. {a?.llm ? "Commentary read from the company's own transcripts." : "No language model connected, so commitments are shown without verdicts."} No news or broker research is used.</p>
    </section>
  );
}
