import { useEffect, useMemo, useState } from "react";
import { api, local } from "./api";
import Card from "./Card";
import { ago, cat } from "./ui";

const WINDOWS = [
  { h: 24, label: "Last 24h" }, { h: 72, label: "3 days" }, { h: 168, label: "Week" }, { h: 720, label: "Month" },
];
const WORDS = ["Nothing", "One thing", "Two things", "Three things", "Four things", "Five things", "Six things", "Seven things", "Eight things", "Nine things"];

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
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" });

  return (
    <>
      <div className="mast"><span className="brand">FINN · BRIEF</span><span className="date">{today}</span></div>
      <h1 className="headline">
        {!data ? "Reading the tape…" : open.length === 0 ? <>All <em>clear.</em></> :
          <><em>{open.length < 10 ? WORDS[open.length] : open.length + " things"}</em> {open.length === 1 ? "matters" : "matter"}.</>}
      </h1>
      <p className="sub">
        {data ? <>{data.counts.alerts} hit your alert rules · {data.counts.routine} routine filings folded away</> : " "}
      </p>

      <div className="chips">
        {WINDOWS.map((w) => <button key={w.h} className={"chip" + (hours === w.h ? " on" : "")} onClick={() => setHours(w.h)}>{w.label}</button>)}
      </div>

      {total > 0 && <div className="progress"><i style={{ width: `${((total - open.length) / total) * 100}%` }} /></div>}
      {err && <div className="panel note warn">Couldn't load the brief: {err}</div>}
      {!data && !err && <div className="stack">{[0, 1, 2].map((i) => <div key={i} className="skel" style={{ height: 92 }} />)}</div>}

      <div className="stack">
        {open.map((c) => <Card key={c.id} item={c} onDone={clear} onAsk={onAsk} />)}
      </div>

      {data && open.length === 0 && (
        <div className="empty">
          <div className="big">Nothing else needs you.</div>
          <p className="muted">{total ? `You cleared ${total} item${total > 1 ? "s" : ""}.` : "No material filings or unusual moves in this window."}</p>
          {total > 0 && <button className="btn" onClick={restore}>Bring them back</button>}
        </div>
      )}

      {data?.routine.length > 0 && (
        <div className="fold">
          <button onClick={() => setShowRoutine((s) => !s)}>
            <span>{data.routine.length} routine filings</span><span className="faint">{showRoutine ? "Hide" : "Show"}</span>
          </button>
          {showRoutine && (
            <ul>
              {data.routine.map((r) => (
                <li key={r.id}>
                  <span className="tick">{r.symbol}</span>
                  <a href={r.url} target="_blank" rel="noreferrer" style={{ flex: 1, textDecoration: "none" }} className="muted">{r.text || r.subject}</a>
                  <span className="faint mono" style={{ fontSize: 11 }}>{cat(r.category).label} · {ago(r.ts)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <p className="note" style={{ textAlign: "center", marginTop: 18 }}>Swipe a card right to clear it · tap to open</p>
    </>
  );
}
