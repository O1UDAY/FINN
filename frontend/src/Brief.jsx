import { useEffect, useMemo, useState } from "react";
import { api, local } from "./api";
import Card from "./Card";
import Listen from "./Listen";
import Masthead from "./Masthead";
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
  const [speaking, setSpeaking] = useState(null);
  // Telegram alerts link to /?story=<id>: open that story once the brief has loaded.
  const [focusId] = useState(() => new URLSearchParams(window.location.search).get("story"));

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
      <Masthead>
        {data?.data?.mode === "snapshot"
          ? <span className="snap">Data as of {new Date(data.data.as_of).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })} (snapshot)</span>
          : new Date().toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "long", year: "numeric" })}
      </Masthead>

      <h1 className="page-title">The Brief</h1>
      <p className="standfirst">
        {!data ? " " : open.length
          ? <>{open.length} {open.length === 1 ? "item" : "items"} across your {holdings} holdings{data.counts.alerts ? `, ${data.counts.alerts} matching your alerts` : ""}. {data.counts.routine} more filed, folded at the bottom.</>
          : total ? "You've read everything in this window." : "No material filings or unusual moves in this window."}
      </p>

      <nav className="sections" aria-label="Time window">
        {WINDOWS.map((w) => <button key={w.h} className={hours === w.h ? "on" : ""} onClick={() => setHours(w.h)}>{w.label}</button>)}
      </nav>

      {open.length > 0 && <Listen cards={open} onCurrent={setSpeaking} onDone={clear} />}

      {err && <p className="note warn">The brief didn't load ({err}). Pull down or switch window to try again.</p>}
      {!data && !err && <div className="loading">Collecting filings</div>}

      <ul className="story-list">
        {open.map((c, i) => <Card key={c.id} item={c} lead={i === 0} focus={c.id === focusId} speaking={c.id === speaking} onDone={clear} onAsk={onAsk} />)}
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
            <span>Also filed ({data.routine.length})</span><span>{showRoutine ? "Hide" : "Show"}</span>
          </button>
          <p className="fold-counts">
            {Object.entries(data.folded_by_category || {}).sort((a, b) => b[1] - a[1])
              .map(([c, n]) => `${cat(c)} ${n}`).join(" · ")}
          </p>
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
