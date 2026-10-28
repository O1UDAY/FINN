import { useEffect, useState } from "react";
import { DARK_ONLY, EXTRA_APPEARANCE, useAppearance } from "./theme";

const MODES = [["system", "Match phone"], ["light", "Light"], ["dark", "Dark"]];
// Swatch colours are literal so each option previews itself regardless of the current theme.
const PAPERS = [
  ["salmon", "Salmon", { light: ["#fff1e5", "#33302e"], dark: ["#1d1a18", "#f2e9e1"] }],
  ["ivory", "Ivory", { light: ["#f8f4ec", "#2b2925"], dark: ["#1c1c1a", "#ecebe6"] }],
  ["white", "White", { light: ["#ffffff", "#1a1a1a"], dark: ["#121519", "#eef1f4"] }],
  ["stocks", "Stocks", { light: ["#000000", "#ffffff"], dark: ["#000000", "#ffffff"] }],
];
const ACCENTS = [["claret", "Claret", "#990f3d"], ["oxford", "Oxford blue", "#0f5499"], ["teal", "Teal", "#0d7680"]];
const SIZES = [["s", "Small"], ["m", "Default"], ["l", "Large"]];

export default function Appearance() {
  const { prefs, save } = useAppearance(useState, useEffect);
  // Previews show what each paper will look like when picked, i.e. in the saved theme, not the forced one.
  // The default look is dark-only and the other papers are behind the flag: there is nothing to choose.
  if (!EXTRA_APPEARANCE && DARK_ONLY.has(prefs.paper)) return null;
  const previewMode = prefs.mode === "dark" || (prefs.mode === "system" && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  return (
    <section className="sec">
      <h2>Appearance</h2>

      <fieldset className="field">
        <legend>Theme</legend>
        <div className="segmented" aria-disabled={DARK_ONLY.has(prefs.paper)}>
          {MODES.map(([v, label]) => (
            <label key={v} className={prefs.mode === v ? "on" : ""}>
              <input type="radio" name="mode" value={v} checked={prefs.mode === v} onChange={() => save({ mode: v })} />{label}
            </label>
          ))}
        </div>
        {DARK_ONLY.has(prefs.paper) && <p className="forced-note">Stocks is always dark, like the app it's modelled on. Pick another paper to use light mode.</p>}
      </fieldset>

      {EXTRA_APPEARANCE && <>
      <fieldset className="field">
        <legend>Paper</legend>
        <div className="swatches">
          {PAPERS.map(([v, label, c]) => {
            const [bg, ink] = c[previewMode] || c.light;
            return (
              <label key={v} className={"paper-opt" + (prefs.paper === v ? " on" : "")}>
                <input type="radio" name="paper" value={v} checked={prefs.paper === v} onChange={() => save({ paper: v })} />
                <span className="sheet" style={{ background: bg, color: ink }} aria-hidden>
                  <b style={{ background: ink }} /><i style={{ background: ink }} /><i style={{ background: ink, width: "60%" }} />
                </span>
                {label}
              </label>
            );
          })}
        </div>
      </fieldset>

      <fieldset className="field">
        <legend>Accent</legend>
        <div className="segmented">
          {ACCENTS.map(([v, label, color]) => (
            <label key={v} className={prefs.accent === v ? "on" : ""}>
              <input type="radio" name="accent" value={v} checked={prefs.accent === v} onChange={() => save({ accent: v })} />
              <span className="chip-color" style={{ background: color }} aria-hidden />{label}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="field">
        <legend>Text size</legend>
        <div className="segmented">
          {SIZES.map(([v, label]) => (
            <label key={v} className={prefs.size === v ? "on" : ""} style={{ fontSize: { s: 13, m: 15, l: 17 }[v] }}>
              <input type="radio" name="size" value={v} checked={prefs.size === v} onChange={() => save({ size: v })} />{label}
            </label>
          ))}
        </div>
      </fieldset>
      </>}
    </section>
  );
}
