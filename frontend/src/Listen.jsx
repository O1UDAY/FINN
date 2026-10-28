import { useEffect, useRef, useState } from "react";
import { cat } from "./ui";

const speech = typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;

// What a story sounds like: who, what, and why it made the paper. Symbols are spelled the way people say them.
function script(c) {
  // "L T", "T C S", "C D S L" are spelled out; "INFY", "TRENT" are said as words.
  const spell = c.symbol.length <= 3 || !/[AEIOU]/.test(c.symbol);
  const who = spell ? c.symbol.split("").join(" ") : c.symbol.charAt(0) + c.symbol.slice(1).toLowerCase();
  const what = c.kind === "move"
    ? `${c.move.pct >= 0 ? "rose" : "fell"} ${Math.abs(c.move.pct).toFixed(1)} percent${c.move.volume_x >= 1.5 ? `, on ${c.move.volume_x.toFixed(1)} times normal volume` : ""}.`
    : `${cat(c.category)}. ${c.text || c.subject}.`;
  return `${who}. ${what} ${c.why ? c.why.replace(/₹/g, "rupees ").replace(/×/g, " times") + "." : ""}`;
}

function voice() {
  const vs = speech.getVoices();
  return vs.find((v) => v.lang === "en-IN") || vs.find((v) => v.lang?.startsWith("en-GB")) || vs.find((v) => v.lang?.startsWith("en"));
}

/** The Brief, read aloud in order: for the commute, eyes elsewhere. Uses the phone's own voice; nothing leaves it. */
export default function Listen({ cards, onCurrent, onDone }) {
  const [i, setI] = useState(-1);
  const [paused, setPaused] = useState(false);
  const run = useRef(0);

  useEffect(() => () => speech?.cancel(), []);
  useEffect(() => { onCurrent(i >= 0 && cards[i] ? cards[i].id : null); }, [i, cards]);

  if (!speech || !cards.length) return null;

  function play(n) {
    const token = ++run.current;
    speech.cancel();
    setPaused(false);
    if (n >= cards.length) {
      setI(-1);
      const end = new SpeechSynthesisUtterance("That's the brief.");
      speech.speak(end);
      return;
    }
    setI(n);
    const u = new SpeechSynthesisUtterance(script(cards[n]));
    const v = voice();
    if (v) u.voice = v;
    u.rate = 1.02;
    u.onend = () => { if (run.current === token) play(n + 1); };
    speech.speak(u);
  }
  const stop = () => { run.current++; speech.cancel(); setI(-1); setPaused(false); };
  const pause = () => { if (paused) { speech.resume(); setPaused(false); } else { speech.pause(); setPaused(true); } };
  const done = () => { const id = cards[i].id; play(i + 1); onDone(id); };

  if (i < 0) {
    return (
      <button className="listen" onClick={() => play(0)}>
        <IconPlay /> Listen to the brief <span>{cards.length} {cards.length === 1 ? "story" : "stories"}, about {Math.max(1, Math.round(cards.length * 12 / 60))} min</span>
      </button>
    );
  }
  return (
    <div className="listen on" role="group" aria-label="Reading the brief aloud">
      <span className="pos">{i + 1} of {cards.length}</span>
      <button onClick={pause}>{paused ? "Resume" : "Pause"}</button>
      <button onClick={() => play(i + 1)}>Next</button>
      <button onClick={done}>Done, next</button>
      <button onClick={stop}>Stop</button>
    </div>
  );
}

const IconPlay = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden><path d="M7 4.5v15l12-7.5z" fill="currentColor" /></svg>
);
