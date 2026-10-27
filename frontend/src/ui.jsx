export const CATS = {
  results: { label: "Results", color: "var(--gold)" },
  "M&A": { label: "M&A", color: "var(--blue)" },
  management_change: { label: "Management", color: "#c9a4ff" },
  fund_raise: { label: "Fund raise", color: "var(--blue)" },
  litigation: { label: "Litigation", color: "var(--down)" },
  credit_rating: { label: "Credit rating", color: "var(--warn)" },
  pledging: { label: "Pledge", color: "var(--down)" },
  insider_trading: { label: "Insider", color: "var(--warn)" },
  capex: { label: "Capex", color: "var(--up)" },
  price_move: { label: "Unusual move", color: "var(--warn)" },
  press_release: { label: "News", color: "var(--ink-2)" },
  dividend: { label: "Dividend", color: "var(--up)" },
  bonus_split: { label: "Bonus / split", color: "var(--up)" },
  earnings_call: { label: "Concall", color: "var(--ink-2)" },
  investor_meetings: { label: "Investor meet", color: "var(--ink-3)" },
  agm_egm: { label: "AGM/EGM", color: "var(--ink-3)" },
  postal_ballot: { label: "Postal ballot", color: "var(--ink-3)" },
  unclassified: { label: "Routine", color: "var(--ink-3)" },
  other: { label: "Update", color: "var(--ink-2)" },
};

export const cat = (c) => CATS[c] || CATS.other;

export function ago(iso) {
  const d = new Date(iso);
  const h = (Date.now() - d) / 36e5;
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m`;
  if (h < 24) return `${Math.round(h)}h`;
  if (h < 24 * 7) return `${Math.round(h / 24)}d`;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export const fmt = (n, d = 0) =>
  n == null ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });

export function crore(n) {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e5) return `₹${fmt(n / 1e5, 2)}L cr`;
  return `₹${fmt(n)} cr`;
}

export function Delta({ v, suffix = "%" }) {
  if (v == null) return <span className="faint">—</span>;
  return <span className={v >= 0 ? "up" : "down"}>{v >= 0 ? "+" : ""}{v.toFixed(1)}{suffix}</span>;
}

export function Spark({ values, w = 120, h = 34, color = "var(--ink-2)" }) {
  const v = (values || []).filter((x) => x != null);
  if (v.length < 2) return null;
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - 3 - ((x - lo) / span) * (h - 6)}`).join(" ");
  const [lx, ly] = pts.split(" ").at(-1).split(",");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r="2.6" fill={color} />
    </svg>
  );
}

export function VolBars({ values, w = 120, h = 26 }) {
  const v = values || [];
  if (!v.length) return null;
  const hi = Math.max(...v), bw = w / v.length;
  return (
    <svg width={w} height={h} aria-hidden>
      {v.map((x, i) => (
        <rect key={i} x={i * bw + 0.5} width={Math.max(1, bw - 1.5)} y={h - (x / hi) * h} height={(x / hi) * h}
          fill={i === v.length - 1 ? "var(--warn)" : "var(--line)"} rx="1" />
      ))}
    </svg>
  );
}

export function Bars({ series, format = (x) => fmt(x) }) {
  const v = (series || []).filter((p) => p.value != null);
  if (!v.length) return <div className="faint">No data</div>;
  const hi = Math.max(...v.map((p) => Math.abs(p.value))) || 1;
  return (
    <div className="bars">
      {v.map((p, i) => (
        <div key={p.period} title={`${p.period}: ${format(p.value)}`}>
          <span className="lb">{i === v.length - 1 ? format(p.value) : ""}</span>
          <div className={"b" + (i === v.length - 1 ? " last" : "")} style={{ height: `${(Math.abs(p.value) / hi) * 70}%`, background: p.value < 0 ? "var(--down)" : undefined }} />
          <span className="lb">{shortPeriod(p.period)}</span>
        </div>
      ))}
    </div>
  );
}

export function PairBars({ a, b, la, lb, ca = "var(--gold)", cb = "var(--ink-3)" }) {
  const periods = (a || []).map((p) => p.period).filter((p) => (b || []).some((q) => q.period === p));
  const get = (s, p) => s.find((x) => x.period === p)?.value ?? 0;
  const hi = Math.max(1, ...periods.flatMap((p) => [Math.abs(get(a, p)), Math.abs(get(b, p))]));
  return (
    <>
      <div className="bars">
        {periods.map((p) => (
          <div key={p}>
            <div className="pair">
              <div className="b" style={{ height: `${(Math.max(0, get(a, p)) / hi) * 80}%`, background: ca }} />
              <div className="b" style={{ height: `${(Math.max(0, get(b, p)) / hi) * 80}%`, background: cb }} />
            </div>
            <span className="lb">{shortPeriod(p)}</span>
          </div>
        ))}
      </div>
      <div className="legend"><span><i style={{ background: ca }} />{la}</span><span><i style={{ background: cb }} />{lb}</span></div>
    </>
  );
}

export const shortPeriod = (p) => (p || "").replace(/^([A-Z][a-z]{2}) 20(\d\d)$/, "$1 ’$2");
