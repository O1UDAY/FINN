import { useRef, useState } from "react";
import { api } from "./api";
import { ago, cat, Delta, fmt, IconCheck, Spark } from "./ui";

/** One story in the Brief. Tap to read it; swipe right, or press Done, to file it away. */
export default function Card({ item, lead, onDone, onAsk }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);
  const [dx, setDx] = useState(0);
  const [dragging, setDragging] = useState(false);
  const drag = useRef(null);

  async function toggle() {
    setOpen((o) => !o);
    if (!detail && item.kind === "filing") {
      try { setDetail(await api.card(item.id)); } catch (e) { setErr(e.message); }
    }
  }

  const down = (e) => { if (e.target.closest(".body")) return; drag.current = { x: e.clientX, y: e.clientY, moved: false }; };
  const move = (e) => {
    const d = drag.current;
    if (!d) return;
    const mx = e.clientX - d.x, my = e.clientY - d.y;
    if (!d.moved && Math.abs(my) > Math.abs(mx)) { drag.current = null; return; }
    if (Math.abs(mx) > 8) { d.moved = true; setDragging(true); }
    if (d.moved) setDx(Math.max(0, mx));
  };
  const up = () => {
    const d = drag.current;
    drag.current = null;
    setDragging(false);
    if (d?.moved) {
      if (dx > 110) { setDx(600); setTimeout(() => onDone(item.id), 220); } else setDx(0);
    } else if (d) toggle();
  };

  const hed = detail?.headline || item.text || item.subject;
  return (
    <li className="swipe">
      <div className="under" aria-hidden><IconCheck /> Done</div>
      <article
        className={"story" + (lead ? " lead" : "") + (dragging ? " dragging" : "")}
        style={{ transform: `translateX(${dx}px)` }}
        onPointerDown={down} onPointerMove={move} onPointerUp={up}
        onPointerCancel={() => { drag.current = null; setDragging(false); setDx(0); }}
        aria-expanded={open}
      >
        {item.kind === "move" ? <Move item={item} lead={lead} /> : <div className="hed">{hed}</div>}

        <div className="byline">
          <span className="co">{item.symbol}</span>
          <span className="sep">|</span>
          <span>{cat(item.category)}</span>
          <span className="sep">|</span>
          <span>{ago(item.ts)}</span>
          {item.alert && <><span className="sep">|</span><span className="alert">Your alert</span></>}
        </div>

        {open && item.kind === "filing" && (
          <div className="body">
            {err && <p className="note warn">Couldn't open this filing: {err}</p>}
            {!detail && !err && <div className="loading">Reading the filing</div>}
            {detail?.type === "results" && <Results d={detail} />}
            {detail?.type === "management" && <People d={detail} />}
            {detail?.type === "summary" && detail.text !== hed && <p className="prose" style={{ fontSize: 16 }}>{detail.text}</p>}
            <div className="actions">
              {item.url && <a href={item.url} target="_blank" rel="noreferrer">Read filing</a>}
              <button onClick={() => onAsk(item.symbol)}>Research {item.symbol}</button>
              <button className="done" onClick={() => onDone(item.id)}>Done</button>
            </div>
          </div>
        )}
      </article>
    </li>
  );
}

function Move({ item }) {
  const m = item.move;
  const dir = m.pct >= 0 ? "up" : "down";
  return (
    <div className="move">
      <div>
        <div className="hed">
          {item.symbol} {m.pct >= 0 ? "rose" : "fell"} <span className={dir}>{Math.abs(m.pct).toFixed(1)}%</span>
          {m.volume_x >= 1.5 && <> on {m.volume_x.toFixed(1)}× normal volume</>}
        </div>
        <div className="note" style={{ marginTop: 4 }}>Closed at ₹{fmt(m.close, 2)}</div>
      </div>
      <Spark values={item.spark.close} color={m.pct >= 0 ? "var(--up)" : "var(--down)"} />
    </div>
  );
}

function Results({ d }) {
  return (
    <>
      <table className="figs">
        <caption>{d.period || "Latest quarter"}{d.basis ? `, ${d.basis}` : ""} · {d.unit || "₹ cr"}</caption>
        <thead><tr><th></th><th>This quarter</th><th>vs last qtr</th><th>vs last year</th></tr></thead>
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
      {d.note && <p className={"note" + (d.stale ? " warn" : "")}>{d.note}</p>}
      <p className="note">Source: {d.source}</p>
    </>
  );
}

function People({ d }) {
  if (!d.people?.length) return <p className="prose" style={{ fontSize: 16 }}>{d.text}</p>;
  return (
    <>
      {d.people.map((p) => (
        <div className="person" key={p.name}>
          <div><span className="nm">{p.name}</span>{p.change && <span className={"tag " + (p.change === "appointed" ? "up" : "faint")}>{p.change}</span>}</div>
          {p.role && <div className="role">{p.role}{p.effective ? `, from ${p.effective}` : ""}</div>}
          {p.background && <p>{p.background}</p>}
          {p.web?.slice(0, 2).map((w) => <a key={w.url} className="note" style={{ display: "block" }} href={w.url} target="_blank" rel="noreferrer">{w.title}</a>)}
        </div>
      ))}
    </>
  );
}
