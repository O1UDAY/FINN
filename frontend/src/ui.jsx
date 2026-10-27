export const CATS = {
  results: "Results",
  "M&A": "Deals",
  management_change: "Management",
  fund_raise: "Fundraising",
  litigation: "Legal",
  credit_rating: "Credit rating",
  pledging: "Pledges",
  insider_trading: "Insider dealing",
  capex: "Capex",
  price_move: "Market move",
  press_release: "Company news",
  dividend: "Dividend",
  bonus_split: "Bonus & split",
  earnings_call: "Earnings call",
  investor_meetings: "Investor meeting",
  agm_egm: "Shareholder meeting",
  postal_ballot: "Postal ballot",
  unclassified: "Routine",
  other: "Filing",
};

export const cat = (c) => CATS[c] || CATS.other;

export function ago(iso) {
  const d = new Date(iso);
  const h = (Date.now() - d) / 36e5;
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min ago`;
  if (h < 24) return `${Math.round(h)} hr ago`;
  if (h < 48) return "Yesterday";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export const fmt = (n, d = 0) =>
  n == null ? "–" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });

export function crore(n) {
  if (n == null) return "–";
  if (Math.abs(n) >= 1e5) return `₹${fmt(n / 1e5, 2)} lakh cr`;
  return `₹${fmt(n)} cr`;
}

export function Delta({ v }) {
  if (v == null) return <span className="faint">–</span>;
  return <span className={v >= 0 ? "up" : "down"}>{v >= 0 ? "+" : "−"}{Math.abs(v).toFixed(1)}%</span>;
}

/* Drawn icons, one 1.6px stroke throughout. */
const I = (d, size = 16) => ({ children, ...p }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden {...p}>{d}{children}</svg>
);
export const IconUp = I(<path d="M12 5l7 12H5z" fill="currentColor" stroke="none" />, 12);
export const IconDown = I(<path d="M12 19L5 7h14z" fill="currentColor" stroke="none" />, 12);
export const IconDot = I(<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />, 12);
export const IconCheck = I(<path d="M5 12.5l4.5 4.5L19 7.5" />, 18);
export const IconSearch = I(<><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></>, 20);
export const IconBrief = I(<><path d="M5 4h11l3 3v13H5z" /><path d="M8 9h8M8 13h8M8 17h5" /></>, 22);
export const IconResearch = I(<><path d="M4 19V9M10 19V5M16 19v-7M22 19H2" /></>, 22);
export const IconAlerts = I(<><path d="M6 16V11a6 6 0 1112 0v5l1.5 2h-15z" /><path d="M10 21h4" /></>, 22);

export function Spark({ values, w = 96, h = 30, color = "var(--ink)" }) {
  const v = (values || []).filter((x) => x != null);
  if (v.length < 2) return null;
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
  const pts = v.map((x, i) => `${((i / (v.length - 1)) * w).toFixed(1)},${(h - 2 - ((x - lo) / span) * (h - 4)).toFixed(1)}`);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="30-day closing price">
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

export const shortPeriod = (p) => (p || "").replace(/^([A-Z][a-z]{2}) 20(\d\d)$/, "$1 ’$2");

export function Bars({ series, format = (x) => fmt(x) }) {
  const v = (series || []).filter((p) => p.value != null);
  if (!v.length) return <p className="faint">Not reported.</p>;
  const hi = Math.max(...v.map((p) => Math.abs(p.value))) || 1;
  return (
    <>
      <div className="bars" role="img" aria-label={v.map((p) => `${p.period} ${format(p.value)}`).join(", ")}>
        {v.map((p, i) => (
          <div key={p.period} title={`${p.period}: ${format(p.value)}`}>
            <div className={"b" + (i === v.length - 1 ? " last" : "") + (p.value < 0 ? " neg" : "")} style={{ height: `${(Math.abs(p.value) / hi) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className="axis">{v.map((p) => <span key={p.period}>{shortPeriod(p.period)}</span>)}</div>
    </>
  );
}

export function PairBars({ a, b, la, lb }) {
  const periods = (a || []).map((p) => p.period).filter((p) => (b || []).some((q) => q.period === p));
  const get = (s, p) => s.find((x) => x.period === p)?.value ?? 0;
  const hi = Math.max(1, ...periods.flatMap((p) => [Math.abs(get(a, p)), Math.abs(get(b, p))]));
  return (
    <>
      <div className="bars">
        {periods.map((p) => (
          <div key={p}>
            <div className="pair">
              <div className="b" style={{ height: `${(Math.max(0, get(a, p)) / hi) * 100}%`, background: "var(--oxford)" }} />
              <div className="b" style={{ height: `${(Math.max(0, get(b, p)) / hi) * 100}%`, background: "var(--rule)" }} />
            </div>
          </div>
        ))}
      </div>
      <div className="axis">{periods.map((p) => <span key={p}>{shortPeriod(p)}</span>)}</div>
      <div className="legend"><span><i style={{ background: "var(--oxford)" }} />{la}</span><span><i style={{ background: "var(--rule)" }} />{lb}</span></div>
    </>
  );
}
