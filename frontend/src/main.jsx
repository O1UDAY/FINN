import { useState } from "react";
import { createRoot } from "react-dom/client";
import { local } from "./api";
import Brief from "./Brief";
import Research from "./Research";
import { IconBrief, IconResearch, IconSettings } from "./ui";
import Watch from "./Watch";
import "./styles.css";
import { applyPrefs } from "./theme";

applyPrefs();

const TABS = [
  { id: "brief", label: "Brief", Icon: IconBrief },
  { id: "research", label: "Research", Icon: IconResearch },
  { id: "watch", label: "Settings", Icon: IconSettings },
];

function App() {
  const [tab, setTab] = useState(local.get("tab", "brief"));
  const [symbol, setSymbol] = useState(null);
  const go = (t) => { setTab(t); local.set("tab", t); window.scrollTo(0, 0); };
  const ask = (s) => { setSymbol(s); go("research"); };

  return (
    <>
      <main className="app">
        {tab === "brief" && <Brief onAsk={ask} />}
        {tab === "research" && <Research symbol={symbol} setSymbol={setSymbol} />}
        {tab === "watch" && <Watch />}
      </main>
      <nav className="tabs" aria-label="Sections">
        <div>
          {TABS.map(({ id, label, Icon }) => (
            <button key={id} className={tab === id ? "on" : ""} aria-current={tab === id ? "page" : undefined} onClick={() => go(id)}>
              <Icon />{label}
            </button>
          ))}
        </div>
      </nav>
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
