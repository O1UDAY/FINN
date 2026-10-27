import { useEffect, useState } from "react";
import { useAppearance } from "./theme";
import { IconMoon, IconSun } from "./ui";

/** Wordmark, dateline and a one-tap switch between light and dark paper. */
export default function Masthead({ children }) {
  const { mode, save } = useAppearance(useState, useEffect);
  const dark = mode === "dark";
  return (
    <header className="mast">
      <span className="wordmark">FINN</span>
      <span className="mast-right">
        <span className="dateline" aria-live="polite">{children}</span>
        <button className="mode-btn" onClick={() => save({ mode: dark ? "light" : "dark" })}
          aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}>
          {dark ? <IconSun /> : <IconMoon />}
        </button>
      </span>
    </header>
  );
}
