import { useRef, useState } from "react";
import { api } from "./api";
import { ago, cat, Delta, fmt, Spark, VolBars } from "./ui";

/** One item in the Brief. Swipe right (or tap Done) to clear it; tap to expand into the "so what". */
export default function Card({ item, onDone, onAsk }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);
  const [dx, setDx] = useState(0);
  const drag = useRef(null);
  const c = cat(item.category);

  async function toggle() {
    setOpen((o) => !o);
    if (!detail && item.kind === "filing") {
      try { setDetail(await api.card(item.id)); } catch (e) { setErr(e.message); }
    }
  }

  const down = (e) => { drag.current = { x: e.clientX, y: e.clientY, moved: false }; };
  const move = (e) => {
    const d = drag.current;
    if (!d) return;
    const mx = e.clientX - d.x, my = e.clientY - d.y;
    if (!d.moved && Math.abs(my) > Math.abs(mx)) { drag.current = null; return; }
    if (Math.abs(mx) > 6) d.moved = true;
    if (d.moved) setDx(Math.max(0, mx));
  };
  const up = () => {
    const d = drag.current;
    drag.current = null;
    if (d?.moved) {
      if (dx > 110) { setDx(480); setTimeout(() => onDone(item.id), 200); } else setDx(0);
    } else if (d) toggle();
  };

  return (
    <div className="swipe">
      <div className="under" aria-hidden>CLEARED ✓</div>
      <div
        className={"card" + (drag.current?.moved ? " dragging" : "")}
        style={{ "--accent": c.color, transform: `translateX(${dx}px)`, opacity: 1 - dx / 600 }}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => { drag.current = null; setDx(0); }}
      >
        <div className="meta">
          {item.alert && <span className="bell" title="Matches your alert rules" />}
          <span className="tick">{item.symbol}</span>
          <span className="cat">{c.label}</span>
          <span className="when">{ago(item.ts)}</span>
        </div>

        {item.kind === "move" ? <Move item={item} /> : (
          <div className="title">{detail?.headline || item.text || item.subject}</div>
        )}

        {open && item.kind === "filing" && (
          <div className="body" onPointerDown={(e) => e.stopPropagation()}>
            {err && <div className="note warn">{err}</div>}
            {!detail && !err && <><div className="skel" style={{ height: 70 }} /><div className="loading-line">reading the filing…</div></>}
            {detail?.type === "results" && <Results d={detail} />}
            {detail?.type === "management" && <People d={detail} />}
            {detail?.type === "summary" && <div className="muted" style={{ fontSize: 14, lineHeight: 1.45 }}>{detail.text}</div>}
            <div className="actions">
              {item.url && <a className="btn" href={item.url} target="_blank" rel="noreferrer">Filing ↗</a>}
              <button className="btn" onClick={() => onAsk(item.symbol)}>Research {item.symbol}</button>
              <button className="btn gold" style={{ marginLeft: "auto" }} onClick={() => onDone(item.id)}>Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Move({ item }) {
  const m = item.move;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
      <div style={{ flex: 1 }}>
        <div className="title">
          <span className={m.pct >= 0 ? "up" : "down"}>{m.pct >= 0 ? "▲" : "▼"} {Math.abs(m.pct).toFixed(1)}%</span>
          <span className="faint"> · </span>
          <span className={m.volume_x >= 2 ? "" : "muted"}>{m.volume_x.toFixed(1)}× volume</span>
        </div>
        <div className="note" style={{ marginTop: 3 }}>Close ₹{fmt(m.close, 1)} · {m.reasons.join(" · ")}</div>
      </div>
      <div style={{ display: "grid", gap: 2, justifyItems: "end" }}>
        <Spark values={item.spark.close} w={92} h={28} color={m.pct >= 0 ? "var(--up)" : "var(--down)"} />
        <VolBars values={item.spark.volume} w={92} h={16} />
      </div>
    </div>
  );
}

function Results({ d }) {
  return (
    <>
      <table className="rt">
        <thead><tr><th>{d.period || "Latest"}</th><th>{d.unit || ""}</th><th>QoQ</th><th>YoY</th></tr></thead>
        <tbody>
          {d.rows.map((r) => (
            <tr key={r.metric}>
              <td>{r.metric}</td>
              <td>{fmt(r.current)}</td>
              <td><Delta v={r.qoq} /></td>
              <td><Delta v={r.yoy} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {d.note && <div className={"note" + (d.stale ? " warn" : "")}>{d.note}</div>}
      <div className="note">Source: {d.source}{d.basis ? ` · ${d.basis}` : ""}</div>
    </>
  );
}

function People({ d }) {
  if (!d.people?.length) return <div className="muted">{d.text}</div>;
  return (
    <>
      {d.people.map((p) => (
        <div className="person" key={p.name}>
          <div className="avatar">{p.name.split(" ").map((x) => x[0]).slice(0, 2).join("")}</div>
          <div>
            <div><span className="nm">{p.name}</span>{p.change && <span className="pill">{p.change}</span>}</div>
            {p.role && <div className="muted" style={{ fontSize: 13 }}>{p.role}{p.effective ? ` · from ${p.effective}` : ""}</div>}
            {p.background && <div style={{ fontSize: 13.5, marginTop: 5, lineHeight: 1.45 }}>{p.background}</div>}
            {p.web?.slice(0, 2).map((w) => <a key={w.url} className="src" href={w.url} target="_blank" rel="noreferrer" style={{ display: "block" }}>{w.title} ↗</a>)}
          </div>
        </div>
      ))}
      <div className="note">{d.text}</div>
    </>
  );
}
