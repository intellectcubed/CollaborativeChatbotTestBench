import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../api.js";
import { defaultGoal } from "./bot/constants.js";
import { dayLabel, todayNY } from "./bot/dates.js";
import { useWeek } from "./bot/useWeek.js";
import WeekCalendar from "./bot/WeekCalendar.jsx";
import Conversation from "./bot/Conversation.jsx";
import ManualPanel from "./bot/ManualPanel.jsx";
import AutomatedPanel from "./bot/AutomatedPanel.jsx";

const MODE_KEY = "botTab.mode";
const readMode = () => { try { return localStorage.getItem(MODE_KEY) === "automated" ? "automated" : "manual"; } catch (e) { return "manual"; } };
const saveMode = m => { try { localStorage.setItem(MODE_KEY, m); } catch (e) { /* not kept: fine */ } };
const bySquad = (a, b) => (/^\d+$/.test(a) && /^\d+$/.test(b) ? Number(a) - Number(b) : a.localeCompare(b));
const slug = text => (text || "").toLowerCase().replace(/\.[^.]+$/, "").replace(/[^a-z0-9_-]+/g, "_").replace(/^[^a-z0-9]+/, "").slice(0, 60);

// One line for a day's calendar change, for the note under the reply that caused it.
function changeText(c) {
  const parts = c.added.length ? c.added : c.removed.map(x => `removed ${x}`);
  return `${dayLabel(c.date)} · ${parts.join(" · ")}`;
}

// The Bot tab: the week of the test calendar, the conversation, and either the Manual or the Automated panel.
// Manual messages and bot runs share the conversation window and the calendar.
export default function BotTab({ bot, manual, live, batchBlocked }) {
  const week = useWeek();
  const [mode, setModeRaw] = useState(readMode);
  const [calOpen, setCalOpen] = useState(true);
  const [roster, setRoster] = useState([]);
  const [rosterError, setRosterError] = useState("");
  const [items, setItems] = useState([]);
  const keyRef = useRef(0);
  const liveRef = useRef(live);
  liveRef.current = live;

  // manual draft
  const [draft, setDraft] = useState({ date: todayNY(), time: "09:00", gap: 5, squad: "", name: "", text: "" });
  // automated goal
  const [goal, setGoal] = useState(defaultGoal());
  const [autoSquad, setAutoSquad] = useState("");
  const [driving, setDriving] = useState("same");
  const [fileName, setFileName] = useState("");
  const [autoError, setAutoError] = useState("");
  const [saveMsg, setSaveMsg] = useState("");

  // The roster file's members, sorted by name; squads sort as numbers.
  const squads = [...new Set(roster.map(m => m.squad))].sort(bySquad);
  const membersOf = useCallback(s => roster.filter(m => m.squad === String(s)), [roster]);

  useEffect(() => {
    call("/api/roster").then(r => {
      setRoster(r);
      const first = [...new Set(r.map(m => m.squad))].sort(bySquad)[0];
      if (first !== undefined) {
        setDraft(d => (d.squad ? d : { ...d, squad: first, name: r.find(m => m.squad === first)?.name || "" }));
        setAutoSquad(s => s || first);
      }
    }).catch(e => setRosterError(`roster: ${e.message}`));
  }, []);

  const setMode = m => { setModeRaw(m); saveMode(m); };

  // ---- the conversation: manual events and bot events are added as they arrive

  const append = useCallback(evs => {
    if (!evs.length) return;
    setItems(prev => prev.concat(evs.map(e => ({ ...e, key: ++keyRef.current }))));
  }, []);

  const refreshCalendar = useCallback(async () => {
    if (!liveRef.current) return;  // Live Calendar off: the calendar does not change
    const changes = await week.refresh();
    append(changes.map(c => ({ kind: "calendar", text: changeText(c) })));
  }, [week.refresh, append]);

  // A manual message's bubble goes up as soon as Send returns its trace ID; the post event that the status poll
  // brings later for the same trace is then skipped, so the bubble is not shown twice.
  const shownPosts = useRef(new Set());
  const sendManual = body => manual.send(body, sent => {
    if (sent.trace_id) shownPosts.current.add(sent.trace_id);
    append([{ kind: "post", source: "manual", persona: sent.name, name: sent.name, squad: sent.squad,
      text: body.text, sent_at: sent.sent_at, trace_id: sent.trace_id, setting: "wait" }]);
  });

  const seenManual = useRef({ session: null, count: 0 });
  useEffect(() => {
    if (manual.session !== seenManual.current.session) seenManual.current = { session: manual.session, count: 0 };
    const fresh = manual.events.slice(seenManual.current.count);
    seenManual.current.count = manual.events.length;
    append(fresh.filter(e => !(e.kind === "post" && shownPosts.current.has(e.trace_id))));
  }, [manual.events, manual.session, append]);

  // a manual message is done (reply, timeout or failure): read the calendar again
  const wasWaiting = useRef(false);
  useEffect(() => {
    if (wasWaiting.current && !manual.waiting) refreshCalendar();
    wasWaiting.current = manual.waiting;
  }, [manual.waiting, refreshCalendar]);

  const seenBot = useRef({ run: null, count: 0 });
  useEffect(() => {
    const run = bot.state?.run ?? null;
    if (run !== seenBot.current.run) seenBot.current = { run, count: 0 };
    const fresh = bot.events.slice(seenBot.current.count);
    seenBot.current.count = bot.events.length;
    append(fresh);
    if (fresh.some(e => e.kind === "reply")) refreshCalendar();
  }, [bot.events, bot.state?.run, append, refreshCalendar]);

  // a bot run has ended: read the calendar once more
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !bot.busy) refreshCalendar();
    wasRunning.current = bot.busy;
  }, [bot.busy, refreshCalendar]);

  const busy = manual.waiting || bot.busy;
  const locked = busy || batchBlocked;

  async function clear() {
    await manual.clear();
    shownPosts.current.clear();
    setItems([]);
  }

  // ---- automated: goal file, Go, Stop, Save

  async function openGoalFile(file) {
    try {
      const g = JSON.parse(await file.text());
      const merged = { ...defaultGoal(), ...g, window: { ...defaultGoal().window, ...(g.window || {}) } };
      setGoal(merged);
      setFileName(file.name);
      const lead = roster.find(m => m.member === merged.my_squad);
      if (lead) setAutoSquad(String(lead.squad));
      setDriving((merged.personas || []).length > 1 ? "many" : "same");
      setAutoError("");
    } catch (e) {
      setAutoError(`not opened: ${e.message}`);
    }
  }

  function builtGoal() {
    // the bot writes as the chatbot's member ids (Member-N), never real names
    const members = membersOf(autoSquad).map(m => m.member).filter(Boolean);
    const lead = members.includes(goal.my_squad) ? goal.my_squad : members[0] || "";
    const personas = driving === "same" ? [lead] : [lead, ...members.filter(m => m !== lead)];
    return {
      ...goal,
      name: slug(goal.name) || slug(fileName) || "untitled",
      my_squad: lead, personas,
      expected_results: goal.expected_results.map(s => s.trim()).filter(Boolean),
      time_between_min: Number(goal.time_between_min) || 0,
    };
  }

  async function go() {
    if (!goal.gate_date) { setAutoError("Gate date is empty: set it under Advanced."); return; }
    setAutoError("");
    await clear();
    await bot.go(builtGoal());
  }

  async function saveGoal() {
    const g = builtGoal();
    try {
      await call(`/api/bot/goals/${encodeURIComponent(g.name)}`, "PUT", g);
      setGoal({ ...goal, name: g.name });
      setSaveMsg(`saved ${g.name}`);
    } catch (e) {
      setSaveMsg(e.message);
    }
  }

  const s = bot.state;
  const counts = { pass: 0, fail: 0, unclear: 0 };
  for (const v of s?.verdicts || []) counts[v.verdict] = (counts[v.verdict] || 0) + 1;
  const statusLine = !s ? "" : [
    s.state === "idle" ? "idle" : s.state + (s.reason ? ` · ${s.reason}` : ""),
    s.run_spent_usd != null && s.state !== "idle" ? `this run $${Number(s.run_spent_usd).toFixed(4)}` +
      (s.budget_cap_usd != null ? ` · budget $${Number(s.budget_spent_usd).toFixed(2)} of $${Number(s.budget_cap_usd).toFixed(2)}` : "") : "",
    s.checks?.length && s.verdicts?.length ? `judge: ${s.checks.length} checks · ${counts.pass} pass · ${counts.fail} fail` +
      (counts.unclear ? ` · ${counts.unclear} unclear` : "") : "",
    batchBlocked ? "a batch run is going" : "",
  ].filter(Boolean).join(" · ");

  const messageWeek = () => week.setStart(mode === "manual" ? draft.date || todayNY() : goal.window.start || goal.gate_date || todayNY());

  // the bot's last post is waiting for its reply
  const last = items[items.length - 1];
  const botWaiting = bot.busy && last?.kind === "post" && last.source !== "manual" && last.setting !== "none";

  return (
    <section className="bot">
      <WeekCalendar week={week} open={calOpen} setOpen={setCalOpen} live={live} messageWeek={messageWeek} />
      <Conversation items={items} waiting={manual.waiting || botWaiting} onClear={clear} canClear={!busy && items.length > 0} />
      <div className="modeswitch" role="radiogroup" aria-label="Mode">
        {["manual", "automated"].map(m => (
          <button key={m} role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""}
            disabled={locked && mode !== m} onClick={() => setMode(m)}>
            {m === "manual" ? "Manual" : "Automated"}
          </button>
        ))}
        {locked && <span className="status">
          {batchBlocked ? "A batch run is going." : manual.waiting ? "Waiting for the chatbot's reply." : "A bot run is going."}
        </span>}
        {rosterError && <span className="err">{rosterError}</span>}
      </div>
      {mode === "manual" ? (
        <ManualPanel draft={draft} setDraft={setDraft} squads={squads} roster={roster}
          onSend={sendManual} blocked={batchBlocked || bot.busy} waiting={manual.waiting} error={manual.error} />
      ) : (
        <AutomatedPanel goal={goal} setGoal={setGoal} squad={autoSquad} setSquad={setAutoSquad}
          driving={driving} setDriving={setDriving} squads={squads} fileName={fileName} onOpenFile={openGoalFile}
          onGo={go} onStop={bot.stop} onSave={saveGoal} canGo={!locked && !!autoSquad} canStop={bot.busy}
          statusLine={statusLine} error={autoError || bot.error} saveMsg={saveMsg} />
      )}
    </section>
  );
}
