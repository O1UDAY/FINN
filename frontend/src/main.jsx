import { useState } from "react";
import { createRoot } from "react-dom/client";
import { local } from "./api";
import Brief from "./Brief";
import Research from "./Research";
import Watch from "./Watch";
import "./styles.css";

function App() {
  const [tab, setTab] = useState(local.get("tab", "brief"));
  const [symbol, setSymbol] = useState(null);
  const go = (t) => { setTab(t); local.set("tab", t); window.scrollTo(0, 0); };
  const ask = (s) => { setSymbol(s); go("research"); };

  return (
    <div className="app">
      {tab === "brief" && <Brief onAsk={ask} />}
      {tab === "research" && <Research symbol={symbol} setSymbol={setSymbol} />}
      {tab === "watch" && <Watch />}
      <nav className="tabs">
        <button className={tab === "brief" ? "on" : ""} onClick={() => go("brief")}>Brief</button>
        <button className={tab === "research" ? "on" : ""} onClick={() => go("research")}>Interrogate</button>
        <button className={tab === "watch" ? "on" : ""} onClick={() => go("watch")}>Watch</button>
      </nav>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
