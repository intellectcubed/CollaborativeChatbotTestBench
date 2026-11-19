import { useRef, useState } from "react";
import { MODELS, SETTINGS } from "./constants.js";

// The goal settings that are not on the main panel. Collapsed by default.
function Advanced({ goal, set, onSave, saveMsg }) {
  const num = (v, fallback) => (Number.isFinite(v) ? v : fallback);
  const togglePosting = s => {
    const has = goal.posting_allowed.includes(s);
    set({ posting_allowed: has ? goal.posting_allowed.filter(x => x !== s) : [...goal.posting_allowed, s] });
  };
  const lim = patch => set({ limits: { ...goal.limits, ...patch } });
  const temp = patch => set({ temperature: { ...goal.temperature, ...patch } });
  return (
    <div className="advanced">
      <div className="row">
        <label>Goal name <input type="text" value={goal.name} placeholder="lower_case_name"
          onChange={e => set({ name: e.target.value })} /></label>
        <button onClick={onSave}>Save goal</button>
        <span className="status">{saveMsg}</span>
      </div>
      <div className="row">
        <label>Gate date <input type="date" value={goal.gate_date} onChange={e => set({ gate_date: e.target.value })} /></label>
        <span>Posting allowed</span>
        {SETTINGS.map(s => (
          <label key={s} className="chip">
            <input type="checkbox" checked={goal.posting_allowed.includes(s)} onChange={() => togglePosting(s)} /> {s}
          </label>
        ))}
        <label className="chip"><input type="checkbox" checked={goal.setup_allowed}
          onChange={e => set({ setup_allowed: e.target.checked })} /> setup changes allowed</label>
      </div>
      <div className="row">
        <label>Tester temp <input className="num" value={goal.temperature.tester}
          onChange={e => temp({ tester: parseFloat(e.target.value) })} /></label>
        <label>Judge temp <input className="num" value={goal.temperature.judge}
          onChange={e => temp({ judge: parseFloat(e.target.value) })} /></label>
        <label>Max messages <input className="num" value={goal.limits.max_messages}
          onChange={e => lim({ max_messages: num(parseInt(e.target.value, 10), 12) })} /></label>
        <label>Max turns <input className="num" value={goal.limits.max_turns}
          onChange={e => lim({ max_turns: num(parseInt(e.target.value, 10), 30) })} /></label>
        <label>Reply timeout (s) <input className="num" value={goal.limits.reply_timeout_s}
          onChange={e => lim({ reply_timeout_s: num(parseFloat(e.target.value), 120) })} /></label>
        <label>Max cost (USD) <input className="num" value={goal.limits.max_cost_usd}
          onChange={e => lim({ max_cost_usd: num(parseFloat(e.target.value), 0.5) })} /></label>
      </div>
    </div>
  );
}

// Automated mode: the goal the AI tester follows, the models, and Go and Stop.
export default function AutomatedPanel({ goal, setGoal, squad, setSquad, driving, setDriving, squads, fileName,
  onOpenFile, onGo, onStop, onSave, canGo, canStop, statusLine, error, saveMsg }) {
  const [advanced, setAdvanced] = useState(false);
  const fileRef = useRef(null);
  const set = patch => setGoal({ ...goal, ...patch });

  return (
    <div className="chatpanel automated">
      <div className="row">
        <button onClick={() => fileRef.current?.click()}>Choose File</button>
        <input ref={fileRef} type="file" accept=".json,application/json" hidden
          onChange={e => { const f = e.target.files?.[0]; if (f) onOpenFile(f); e.target.value = ""; }} />
        <span className="filename">{fileName || "no goal file loaded"}</span>
        <label>Noise
          <select value={goal.noise} onChange={e => set({ noise: e.target.value })}>
            <option>none</option><option>some</option><option>heavy</option>
          </select>
        </label>
        <label>Squad
          <select value={squad} onChange={e => setSquad(e.target.value)}>
            {squads.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <span className="switchlabel">Member driving conversation</span>
        <div className="seg" role="radiogroup" aria-label="Member driving conversation">
          {["same", "many"].map(v => (
            <button key={v} role="radio" aria-checked={driving === v} className={driving === v ? "on" : ""}
              onClick={() => setDriving(v)}
              title={v === "same" ? "Always the same member of the squad" : "Members of the squad take turns"}>
              {v === "same" ? "Same" : "Many"}
            </button>
          ))}
        </div>
      </div>
      <div className="row">
        <label>Date Range
          <input type="date" value={goal.window.start} onChange={e => set({ window: { ...goal.window, start: e.target.value } })} />
        </label>
        <label>To
          <input type="date" value={goal.window.end} onChange={e => set({ window: { ...goal.window, end: e.target.value } })} />
        </label>
        <label>Time Between
          <input type="number" min="0" step="1" className="num" value={goal.time_between_min}
            onChange={e => set({ time_between_min: e.target.value === "" ? "" : Number(e.target.value) })} /> min
        </label>
      </div>
      <div className="goalgrid">
        <div className="texts">
          <label className="block">Goal</label>
          <textarea rows={2} value={goal.goal} onChange={e => set({ goal: e.target.value })} />
          <label className="block">Stop When</label>
          <textarea rows={2} value={goal.stop_condition} onChange={e => set({ stop_condition: e.target.value })} />
          <label className="block">Expected Results <span className="status">(judge only, one per line)</span></label>
          <textarea rows={2} value={goal.expected_results.join("\n")}
            onChange={e => set({ expected_results: e.target.value.split("\n") })} />
        </div>
        <div className="models">
          <label className="block">Tester Model</label>
          <select value={goal.models.tester} onChange={e => set({ models: { ...goal.models, tester: e.target.value } })}>
            {MODELS.map(m => <option key={m}>{m}</option>)}
          </select>
          <label className="block">Judge Model</label>
          <select value={goal.models.judge} onChange={e => set({ models: { ...goal.models, judge: e.target.value } })}>
            {MODELS.map(m => <option key={m}>{m}</option>)}
          </select>
        </div>
      </div>
      <div className="row">
        <button className="primary" onClick={onGo} disabled={!canGo}>Go</button>
        <button className="danger" onClick={onStop} disabled={!canStop}>Stop</button>
        <button onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}>Advanced {advanced ? "▾" : "▸"}</button>
        <span className="status">{statusLine}</span>
        {error && <span className="err">{error}</span>}
      </div>
      {advanced && <Advanced goal={goal} set={set} onSave={onSave} saveMsg={saveMsg} />}
    </div>
  );
}
