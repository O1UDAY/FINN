import { useEffect, useState } from "react";
import { api } from "./api";
import { CATS } from "./ui";

const ALERTABLE = ["results", "M&A", "management_change", "fund_raise", "litigation", "credit_rating", "pledging", "insider_trading", "capex", "dividend", "bonus_split", "press_release"];

export default function Watch() {
  const [s, setS] = useState(null);
  const [status, setStatus] = useState(null);
  const [add, setAdd] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.settings().then(setS); api.status().then(setStatus).catch(() => {}); }, []);

  async function save(patch) {
    const next = { ...s, ...patch };
    setS(next);
    setS(await api.saveSettings(patch));
    setSaved(true); setTimeout(() => setSaved(false), 1200);
  }
  async function refresh() {
    await api.refresh();
    setStatus((x) => ({ ...x, refreshing: true }));
    const t = setInterval(async () => {
      const st = await api.status();
      setStatus(st);
      if (!st.refreshing) clearInterval(t);
    }, 3000);
  }

  if (!s) return <div className="skel" style={{ height: 300 }} />;
  const toggleCat = (c) => save({ categories: s.categories.includes(c) ? s.categories.filter((x) => x !== c) : [...s.categories, c] });

  return (
    <>
      <div className="mast"><span className="brand">FINN · WATCH</span><span className="date">{saved ? "saved ✓" : " "}</span></div>
      <h1 className="headline" style={{ fontSize: 38 }}>You decide what <em>unusual</em> means.</h1>

      <div className="sec">
        <h3>Market triggers</h3>
        <div className="panel">
          <div className="row">
            <div><div>Volume spike</div><div className="note" style={{ marginTop: 2 }}>vs 20-day average</div></div>
            <Stepper value={s.volume_multiple} step={0.25} min={1.25} max={6} fmt={(v) => `${v}×`} onChange={(v) => save({ volume_multiple: v })} />
          </div>
          <div className="row">
            <div><div>Price move</div><div className="note" style={{ marginTop: 2 }}>absolute, one session</div></div>
            <Stepper value={s.price_move_pct} step={0.5} min={1} max={20} fmt={(v) => `±${v}%`} onChange={(v) => save({ price_move_pct: v })} />
          </div>
        </div>
      </div>

      <div className="sec">
        <h3>Alert me on filings about</h3>
        <div className="wrap">
          {ALERTABLE.map((c) => <button key={c} className={"toggle" + (s.categories.includes(c) ? " on" : "")} onClick={() => toggleCat(c)}>{CATS[c]?.label || c}</button>)}
        </div>
        <div className="note">Alerting categories get a gold dot and rank higher in the Brief. Everything else is still there, just quieter.</div>
      </div>

      <div className="sec">
        <h3>Portfolio <span>{s.portfolio.length} names</span></h3>
        <div className="wrap">
          {s.portfolio.map((p) => (
            <span key={p} className="chip mono">{p}<button className="x" aria-label={`Remove ${p}`} onClick={() => save({ portfolio: s.portfolio.filter((x) => x !== p) })}>×</button></span>
          ))}
        </div>
        <form className="search" onSubmit={(e) => { e.preventDefault(); const v = add.trim().toUpperCase(); if (v && !s.portfolio.includes(v)) save({ portfolio: [...s.portfolio, v] }); setAdd(""); }}>
          <input value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Add NSE ticker" autoCapitalize="characters" />
          <button className="btn" type="submit">Add</button>
        </form>
      </div>

      <div className="sec">
        <h3>Engine</h3>
        <div className="panel">
          <div className="row"><span className="muted">Data last refreshed</span><span className="mono" style={{ fontSize: 13 }}>{status?.refreshing ? "refreshing…" : status?.last_refresh?.replace("T", " ") || "—"}</span></div>
          <div className="row"><span className="muted">Model provider</span><span className="mono" style={{ fontSize: 13 }}>{status?.llm?.provider || "none (rules only)"}</span></div>
          <div className="row"><span className="muted">LLM spend to date</span><span className="mono" style={{ fontSize: 13 }}>${status?.llm?.total_usd?.toFixed(4) ?? "0"}</span></div>
          {status?.llm?.by_model?.map((m) => <div className="row" key={m.model}><span className="faint mono" style={{ fontSize: 12 }}>{m.model}</span><span className="faint mono" style={{ fontSize: 12 }}>{m.n} calls · ${m.usd}</span></div>)}
          <div className="row"><span /><button className="btn gold" onClick={refresh} disabled={status?.refreshing}>Refresh now</button></div>
        </div>
      </div>
    </>
  );
}

function Stepper({ value, step, min, max, fmt, onChange }) {
  const set = (v) => onChange(Math.round(Math.min(max, Math.max(min, v)) * 100) / 100);
  return (
    <div className="stepper">
      <button onClick={() => set(value - step)} aria-label="Decrease">−</button>
      <span className="v">{fmt(value)}</span>
      <button onClick={() => set(value + step)} aria-label="Increase">+</button>
    </div>
  );
}
