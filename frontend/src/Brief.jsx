import { useEffect, useMemo, useState } from "react";
import { api, local } from "./api";
import Card from "./Card";
import { ago, cat } from "./ui";

const WINDOWS = [
  { h: 24, label: "Since yesterday" }, { h: 72, label: "3 days" }, { h: 168, label: "This week" }, { h: 720, label: "This month" },
];

export default function Brief({ onAsk }) {
  const [hours, setHours] = useState(local.get("hours", 24));
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [done, setDone] = useState(() => new Set(local.get("done", [])));
  const [showRoutine, setShowRoutine] = useState(false);

  useEffect(() => {
    setData(null); setErr(null); local.set("hours", hours);
    api.brief(hours).then(setData).catch((e) => setErr(e.message));
  }, [hours]);

  const clear = (id) => setDone((s) => { const n = new Set(s).add(id); local.set("done", [...n].slice(-500)); return n; });
  const restore = () => { setDone(new Set()); local.set("done", []); };

  const open = useMemo(() => (data?.cards || []).filter((c) => !done.has(c.id)), [data, done]);
  const total = data?.cards.length || 0;
  const holdings = data?.settings.portfolio.length;

  return (
    <>
      <header className="mast">
        <span className="wordmark">FINN</span>
        <span className="dateline">{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</span>
      </header>

      <h1 className="page-title">The Brief</h1>
      <p className="standfirst">
        {!data ? " " : open.length
          ? <>{open.length} {open.length === 1 ? "item" : "items"} across your {holdings} holdings{data.counts.alerts ? `, ${data.counts.alerts} matching your alerts` : ""}. {data.counts.routine} routine filings are at the bottom.</>
          : total ? "You've read everything in this window." : "No material filings or unusual moves in this window."}
      </p>

      <nav className="sections" aria-label="Time window">
        {WINDOWS.map((w) => <button key={w.h} className={hours === w.h ? "on" : ""} onClick={() => setHours(w.h)}>{w.label}</button>)}
      </nav>

      {err && <p className="note warn">The brief didn't load ({err}). Pull down or switch window to try again.</p>}
      {!data && !err && <div className="loading">Collecting filings</div>}

      <ul className="story-list">
        {open.map((c, i) => <Card key={c.id} item={c} lead={i === 0} onDone={clear} onAsk={onAsk} />)}
      </ul>

      {data && total > 0 && open.length === 0 && (
        <div className="empty">
          <h2>You're up to date.</h2>
          <p>{total} {total === 1 ? "item" : "items"} read.</p>
          <button className="link-btn" onClick={restore}>Show them again</button>
        </div>
      )}

      {data?.routine.length > 0 && (
        <section className="notices">
          <button onClick={() => setShowRoutine((s) => !s)} aria-expanded={showRoutine}>
            <span>Routine filings ({data.routine.length})</span><span>{showRoutine ? "Hide" : "Show"}</span>
          </button>
          {showRoutine && (
            <ul>
              {data.routine.map((r) => (
                <li key={r.id}>
                  <span className="co">{r.symbol}</span>
                  <a href={r.url} target="_blank" rel="noreferrer">{r.text || r.subject}</a>
                  <span className="when">{cat(r.category)}, {ago(r.ts).toLowerCase()}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      {open.length > 1 && <p className="hint">Swipe a story right when you're done with it.</p>}
    </>
  );
}
