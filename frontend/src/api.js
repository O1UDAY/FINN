const BASE = import.meta.env.VITE_API_URL || "";

async function req(path, opts = {}) {
  // A visitor's own AI key, if they set one in Settings: kept in this browser, sent with each request.
  const key = local.get("ai_key", null);
  const headers = key ? { ...(opts.headers || {}), "X-AI-Key": key } : opts.headers;
  const r = await fetch(BASE + path, { ...opts, headers });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${r.status})`);
  }
  return r.json();
}

export const api = {
  brief: (hours) => req(`/api/brief?hours=${hours}`),
  card: (id) => req(`/api/card/${id}`),
  numbers: (sym) => req(`/api/research/${encodeURIComponent(sym)}`),
  analysis: (sym, refresh) => req(`/api/research/${encodeURIComponent(sym)}/analysis${refresh ? "?refresh=true" : ""}`),
  startResearch: (sym, refresh) => req(`/api/research/${encodeURIComponent(sym)}${refresh ? "?refresh=true" : ""}`, { method: "POST" }),
  ask: (sym, question, aid) => req(`/api/ask/${encodeURIComponent(sym)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, aid }) }),
  job: (id) => req(`/api/research/jobs/${id}`),
  addHolding: (symbol) => req("/api/holdings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol }) }),
  testAlert: () => req("/api/alerts/test", { method: "POST" }),
  settings: () => req("/api/settings"),
  saveSettings: (v) => req("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(v) }),
  status: () => req("/api/status"),
  checkKey: (key) => req("/api/key/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) }),
  refresh: () => req("/api/refresh", { method: "POST" }),
};

// Per-device conveniences only (cleared cards, last tab). Never required for the app to work.
export const local = {
  get(k, d) { try { const v = localStorage.getItem("finn:" + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("finn:" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
