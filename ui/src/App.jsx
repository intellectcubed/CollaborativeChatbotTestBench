import { useEffect, useRef, useState } from "react";
import Banner from "./components/Banner.jsx";
import Tabs from "./components/Tabs.jsx";
import BatchTab from "./tabs/BatchTab.jsx";
import BotTab from "./tabs/BotTab.jsx";
import CreateTab from "./tabs/CreateTab.jsx";
import { useSettings } from "./hooks/useSettings.js";
import { useUsage } from "./hooks/useUsage.js";
import { useSessionTokens } from "./hooks/useSessionTokens.js";
import { useBatch } from "./hooks/useBatch.js";
import { useBot } from "./tabs/bot/useBot.js";
import { useManual } from "./tabs/bot/useManual.js";

const TABS = [
  { id: "batch", label: "Batch" },
  { id: "create", label: "Create" },
  { id: "bot", label: "Bot" },
];

// The page: the banner across the top and the tabs full width below it. Only one run goes at a time,
// across the batch and the bot, so each tab is told whether the other one is busy.
export default function App() {
  const [tab, setTab] = useState("batch");
  const settings = useSettings();
  const usage = useUsage();
  const bot = useBot();
  const manual = useManual();
  // a manual message waiting for its reply holds the run lock, like a bot run
  const botTabBusy = bot.busy || manual.waiting;
  const batch = useBatch({ botBusy: botTabBusy });

  // The chatbot's tokens for this session, from the status answers: Bot tab replies and Batch tab rows.
  const tokens = useSessionTokens();
  useEffect(() => { tokens.add(manual.events); }, [manual.events, tokens.add]);
  useEffect(() => { tokens.add(bot.events); }, [bot.events, tokens.add]);
  useEffect(() => { tokens.add(batch.rows.filter(Boolean)); }, [batch.rows, tokens.add]);

  // The bot's own model use and budget change only during a bot run: read them again when one ends.
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !bot.busy) usage.refresh();
    wasRunning.current = bot.busy;
  }, [bot.busy, usage.refresh]);

  const resetUsage = async () => { tokens.reset(); await usage.reset(); };

  return (
    <div className="app">
      <Banner live={settings.live} setLiveSetting={settings.setLiveSetting} liveError={settings.error}
        usage={usage.usage} chatTokens={tokens.totals} resetUsage={resetUsage} usageError={usage.error}
        blocked={batch.blocked || botTabBusy} />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      <main>
        <div hidden={tab !== "batch"}><BatchTab batch={batch} botBusy={botTabBusy} /></div>
        <div hidden={tab !== "create"}><CreateTab /></div>
        <div hidden={tab !== "bot"}><BotTab bot={bot} manual={manual} live={settings.live}
          batchBlocked={batch.busy || batch.runLoop} /></div>
      </main>
    </div>
  );
}
