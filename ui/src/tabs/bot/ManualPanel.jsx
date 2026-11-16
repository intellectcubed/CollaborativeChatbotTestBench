import { addMinutes } from "./dates.js";

// Manual mode: when the next message is sent, who it is from, and the message itself.
// Time Between only moves the message's time on; the driver does not wait that long.
export default function ManualPanel({ draft, setDraft, squads, roster, onSend, blocked, waiting, error }) {
  const set = patch => setDraft({ ...draft, ...patch });
  const canSend = !!draft.text.trim() && !!draft.squad && !!draft.name && !!draft.date && !!draft.time && !blocked && !waiting;

  // Squad and Member follow each other: a squad picks its first member by name; a member picks their squad.
  const pickSquad = squad => set({ squad, name: roster.find(m => m.squad === squad)?.name || "" });
  const pickMember = name => set({ name, squad: roster.find(m => m.name === name)?.squad || draft.squad });

  async function send() {
    if (!canSend) return;
    const ok = await onSend({ squad: draft.squad, name: draft.name, text: draft.text, sent_at: `${draft.date}T${draft.time}` });
    if (ok) set({ text: "", ...addMinutes(draft.date, draft.time, Number(draft.gap) || 0) });
  }

  function onKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="chatpanel manual">
      <div className="row">
        <label>Date <input type="date" value={draft.date} onChange={e => set({ date: e.target.value })} /></label>
        <label>Time <input type="time" value={draft.time} onChange={e => set({ time: e.target.value })} /></label>
        <label>Time Between
          <input type="number" min="0" step="1" className="num" value={draft.gap}
            onChange={e => set({ gap: e.target.value })} /> min
        </label>
        <label>Squad
          <select value={draft.squad} onChange={e => pickSquad(e.target.value)}>
            {squads.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label>Member
          <select value={draft.name} onChange={e => pickMember(e.target.value)}>
            {roster.map(m => <option key={m.sender_id} value={m.name}>{m.name}</option>)}
          </select>
        </label>
        {error && <span className="err">{error}</span>}
      </div>
      <div className="row send">
        <textarea rows={2} value={draft.text} placeholder="Message (Enter sends, Shift+Enter for a new line)"
          onChange={e => set({ text: e.target.value })} onKeyDown={onKey} />
        <button className="primary" onClick={send} disabled={!canSend}>Send</button>
      </div>
    </div>
  );
}
