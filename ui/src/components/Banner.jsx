import Panel from "./Panel.jsx";

// The top banner: the title, the global Live Calendar checkbox, and the token totals and budget.
export default function Banner({ live, setLiveSetting, liveError, usage, chatTokens, resetUsage, usageError, blocked }) {
  const money = v => (v == null ? "" : `$${Number(v).toFixed(2)}`);
  const n = v => Number(v || 0).toLocaleString();
  return (
    <header className="banner">
      <div className="title">
        <h1>Chatbot Testing Workbench</h1>
        <label className="live">
          <input type="checkbox" checked={live} disabled={blocked}
            onChange={e => setLiveSetting(e.target.checked)} />
          Live Calendar
          <span className="status">{live ? "changes apply to the test calendar" : "off: calendar is only previewed"}</span>
        </label>
      </div>
      <Panel title="Model usage">
        <div className="usage">
          <span title="The chatbot's model calls, added up from each message's trace">
            Chatbot tokens in <b>{n(chatTokens.input)}</b></span>
          <span>out <b>{n(chatTokens.output)}</b></span>
          <span className="status">{chatTokens.messages} message{chatTokens.messages === 1 ? "" : "s"} this session</span>
          <button onClick={resetUsage}>Reset tokens</button>
        </div>
        <div className="usage">
          {usage && usage.key_set === false ? (
            <span className="status">Bot models: no API key set, the bot is off.</span>
          ) : (
            <>
              <span title="The bot's own tester and judge models">Bot tokens in <b>{n(usage?.tokens_in)}</b></span>
              <span>out <b>{n(usage?.tokens_out)}</b></span>
              <span>Budget <b>{money(usage?.spent_usd)}</b> of {money(usage?.cap_usd)}</span>
            </>
          )}
        </div>
        {(liveError || usageError) && <p className="err">{liveError || usageError}</p>}
      </Panel>
    </header>
  );
}
