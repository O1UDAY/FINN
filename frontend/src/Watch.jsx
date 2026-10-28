import { useEffect, useState } from "react";
import { api, local } from "./api";
import Appearance from "./Appearance";
import Masthead from "./Masthead";
import { CATS } from "./ui";

const ALERTABLE = ["results", "M&A", "management_change", "fund_raise", "litigation", "credit_rating", "pledging", "insider_trading", "capex", "dividend", "bonus_split", "press_release"];

export default function Watch() {
  const [s, setS] = useState(null);
  const [status, setStatus] = useState(null);
  const [add, setAdd] = useState("");
  const [saved, setSaved] = useState(false);
  const [addMsg, setAddMsg] = useState(null);
  const [adding, setAdding] = useState(false);
  const [testMsg, setTestMsg] = useState(null);

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
      <Masthead>{saved ? "Saved" : "Settings"}</Masthead>
      <h1 className="page-title">Settings</h1>
      <p className="standfirst">What counts as unusual, and which companies FINN watches.</p>

      <Appearance />

      <section className="sec">
        <h2>Price and volume alerts</h2>
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
        <h2>Filing alerts</h2>
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
        <form className="search" onSubmit={async (e) => {
          e.preventDefault();
          const v = add.trim().toUpperCase();
          if (!v) return;
          if (s.portfolio.includes(v)) { setAddMsg({ ok: false, text: `${v} is already in your holdings.` }); return; }
          setAdding(true); setAddMsg(null);
          try {
            const r = await api.addHolding(v);
            setS(r.settings); setAdd("");
            setAddMsg({ ok: true, text: `Added ${v}: ${r.price_rows} days of prices and ${r.filings} filings loaded.` });
          } catch (err) { setAddMsg({ ok: false, text: err.message }); }
          setAdding(false);
        }}>
          <input value={add} onChange={(e) => { setAdd(e.target.value); setAddMsg(null); }} placeholder="Add an NSE symbol" aria-label="Add an NSE symbol" autoCapitalize="characters" />
          <button type="submit" disabled={adding}>{adding ? "Checking…" : "Add"}</button>
        </form>
        {addMsg && <p className={"note" + (addMsg.ok ? "" : " warn")} role="status">{addMsg.text}</p>}
      </section>

      <section className="sec">
        <h2>Data</h2>
        <div className="rows">
          <div className="row"><span className="muted">Last updated</span><span>{status?.refreshing ? "Updating…" : status?.last_refresh?.replace("T", " ").slice(0, 16) || "Not yet today"}</span></div>
          <div className="row"><span className="muted">Language model</span><span>{status?.llm?.provider ? `${status.llm.provider}${status.own_key ? " (your key)" : ""}` : "None, rules only"}</span></div>
          <div className="row"><span className="muted">Telegram alerts</span><span>{status?.telegram ? "Connected" : "Not set up"}</span></div>
          <div className="row"><span className="muted">Model spend so far</span><span>${status?.llm?.total_usd?.toFixed(4) ?? "0.0000"}</span></div>
        </div>
        <p className="btn-row">
          <button className="primary" onClick={refresh} disabled={status?.refreshing}>{status?.refreshing ? "Updating…" : "Update now"}</button>
          <button className="secondary" onClick={async () => { setTestMsg(null); const r = await api.testAlert().catch((e) => ({ ok: false, error: e.message })); setTestMsg(r); }}>Send test alert</button>
        </p>
        {testMsg && <p className={"note" + (testMsg.ok ? "" : " warn")} role="status">{testMsg.ok ? "Test alert sent. Check Telegram." : testMsg.error}</p>}
        <OwnKey onChange={() => api.status().then(setStatus).catch(() => {})} />
      </section>
    </>
  );
}

/** Optional: bring your own Gemini key, so research and questions don't share the app's free daily limit. */
function OwnKey({ onChange }) {
  const [key, setKey] = useState(() => local.get("gemini_key", null));
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  async function save(e) {
    e.preventDefault();
    const v = draft.trim();
    if (!v) return;
    setBusy(true); setMsg(null);
    const r = await api.checkKey(v).catch((err) => ({ ok: false, error: err.message }));
    setBusy(false);
    if (!r.ok) { setMsg({ ok: false, text: r.error }); return; }
    local.set("gemini_key", v); setKey(v); setDraft("");
    setMsg({ ok: true, text: r.note || "Key saved. Research and questions now use it." });
    onChange();
  }
  const remove = () => { local.set("gemini_key", null); setKey(null); setMsg({ ok: true, text: "Key removed. FINN is back on the app's own key." }); onChange(); };

  return (
    <div className="own-key">
      <h3>Your own AI key <span>optional</span></h3>
      {key ? (
        <div className="row"><span>Using your Gemini key ending {key.slice(-4)}</span><button className="link-btn" onClick={remove}>Remove</button></div>
      ) : (
        <form className="search" onSubmit={save}>
          <input type="password" value={draft} onChange={(e) => { setDraft(e.target.value); setMsg(null); }} placeholder="Paste a Gemini API key"
            aria-label="Your Gemini API key" autoComplete="off" spellCheck={false} style={{ textTransform: "none" }} />
          <button type="submit" disabled={busy}>{busy ? "Checking…" : "Save"}</button>
        </form>
      )}
      {msg && <p className={"note" + (msg.ok ? "" : " warn")} role="status">{msg.text}</p>}
      <p className="note">
        Use your own free key from <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Google AI Studio</a> if
        the app's daily limit runs out. It stays in this browser only and is sent with your requests; FINN never saves it.
      </p>
    </div>
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
