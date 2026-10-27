// Appearance preferences: per-device, so they live in localStorage (the inline script in index.html applies them
// before first paint; this module keeps them in sync afterwards).
import { local } from "./api";

export const DEFAULTS = { mode: "system", paper: "salmon", accent: "claret", size: "m" };
export const ZOOM = { s: 0.92, m: 1, l: 1.12 };
const media = window.matchMedia("(prefers-color-scheme: dark)");

export const getPrefs = () => ({ ...DEFAULTS, ...local.get("appearance", {}) });

export function applyPrefs(p = getPrefs()) {
  const root = document.documentElement;
  const mode = p.mode === "system" ? (media.matches ? "dark" : "light") : p.mode;
  root.dataset.mode = mode;
  root.dataset.paper = p.paper;
  root.dataset.accent = p.accent;
  root.style.setProperty("--zoom", ZOOM[p.size] || 1);
  // Browser chrome (address bar, status bar) follows the paper.
  const bg = getComputedStyle(root).getPropertyValue("--paper").trim();
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", bg);
  return mode;
}

export function savePrefs(patch) {
  const next = { ...getPrefs(), ...patch };
  local.set("appearance", next);
  applyPrefs(next);
  window.dispatchEvent(new CustomEvent("finn:appearance", { detail: next }));
  return next;
}

export function useAppearance(useState, useEffect) {
  const [prefs, setPrefs] = useState(getPrefs);
  const [mode, setMode] = useState(() => document.documentElement.dataset.mode || "light");
  useEffect(() => {
    const sync = () => { setPrefs(getPrefs()); setMode(document.documentElement.dataset.mode); };
    window.addEventListener("finn:appearance", sync);
    media.addEventListener?.("change", sync);
    return () => { window.removeEventListener("finn:appearance", sync); media.removeEventListener?.("change", sync); };
  }, []);
  return { prefs, mode, save: savePrefs };
}

// "System" follows the OS live, e.g. when the phone switches to dark at sunset.
media.addEventListener?.("change", () => { if (getPrefs().mode === "system") applyPrefs(); });
