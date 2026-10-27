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
    setS((x) => ({ ...x, ...patch }));
    setS(await api.saveSettings(patch));
    setSaved(true); setTimeout(() => setSaved(false), 1500);
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

  if (!s) return <div className="loading">Loading your alerts</div>;
  const toggleCat = (c) => save({ categories: s.categories.includes(c) ? s.categories.filter((x) => x !== c) : [...s.categories, c] });

  return (
    <>
      <header className="mast">
        <span className="wordmark">FINN</span>
        <span className="dateline" aria-live="polite">{saved ? "Saved" : "Alerts & holdings"}</span>
      </header>
      <h1 className="page-title">Alerts</h1>
      <p className="standfirst">Flag a stock when it moves more than you'd expect, or files something you care about.</p>

      <section className="sec">
        <h2>Price and volume</h2>
        <div className="setting">
          <div><div>Volume spike</div><div className="d">Compared with the 20-day average</div></div>
          <Stepper value={s.volume_multiple} step={0.25} min={1.25} max={6} fmt={(v) => `${v}×`} onChange={(v) => save({ volume_multiple: v })} />
        </div>
        <div className="setting">
          <div><div>Daily price move</div><div className="d">Up or down, close to close</div></div>
          <Stepper value={s.price_move_pct} step={0.5} min={1} max={20} fmt={(v) => `${v}%`} onChange={(v) => save({ price_move_pct: v })} />
        </div>
      </section>

      <section className="sec">
        <h2>Filings</h2>
        <p className="dek">These go to the top of the Brief and are marked “Your alert”.</p>
        <ul className="checks">
          {ALERTABLE.map((c) => (
            <li key={c}><label><input type="checkbox" checked={s.categories.includes(c)} onChange={() => toggleCat(c)} />{CATS[c] || c}</label></li>
          ))}
        </ul>
      </section>

      <section className="sec">
        <h2>Holdings ({s.portfolio.length})</h2>
        <div className="holdings">
          {s.portfolio.map((p) => (
            <span key={p}>{p}<button aria-label={`Remove ${p}`} onClick={() => save({ portfolio: s.portfolio.filter((x) => x !== p) })}>remove</button></span>
          ))}
        </div>
        <form className="search" onSubmit={(e) => { e.preventDefault(); const v = add.trim().toUpperCase(); if (v && !s.portfolio.includes(v)) save({ portfolio: [...s.portfolio, v] }); setAdd(""); }}>
          <input value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Add an NSE symbol" aria-label="Add an NSE symbol" autoCapitalize="characters" />
          <button type="submit">Add</button>
        </form>
      </section>

      <section className="sec">
        <h2>Data</h2>
        <div className="rows">
          <div className="row"><span className="muted">Last updated</span><span>{status?.refreshing ? "Updating…" : status?.last_refresh?.replace("T", " ").slice(0, 16) || "Not yet today"}</span></div>
          <div className="row"><span className="muted">Language model</span><span>{status?.llm?.provider || "None, rules only"}</span></div>
          <div className="row"><span className="muted">Model spend so far</span><span>${status?.llm?.total_usd?.toFixed(4) ?? "0.0000"}</span></div>
        </div>
        <p style={{ marginTop: 14 }}><button className="primary" onClick={refresh} disabled={status?.refreshing}>{status?.refreshing ? "Updating…" : "Update now"}</button></p>
      </section>
    </>
  );
}

function Stepper({ value, step, min, max, fmt, onChange }) {
  const set = (v) => onChange(Math.round(Math.min(max, Math.max(min, v)) * 100) / 100);
  return (
    <div className="stepper">
      <button onClick={() => set(value - step)} disabled={value <= min} aria-label="Lower">−</button>
      <span className="v">{fmt(value)}</span>
      <button onClick={() => set(value + step)} disabled={value >= max} aria-label="Higher">+</button>
    </div>
  );
}
