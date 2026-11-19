import Panel from "../../components/Panel.jsx";

// Pause and Resume hold the run between messages. Stop ends it. Mark All Pending puts every line back to pending.
export default function ControlPanel({ state, pause, resume, stop, markAllPending, markDisabled, message }) {
  const running = state === "running";
  const paused = state === "paused";
  const busy = running || paused;
  return (
    <Panel title="Control">
      <button onClick={pause} disabled={!running}>Pause</button>
      <button onClick={resume} disabled={!paused}>Resume</button>
      <button onClick={stop} disabled={!busy} className="danger">Stop</button>
      <button onClick={markAllPending} disabled={markDisabled}>Mark All Pending</button>
      {message && <p className="err">{message}</p>}
    </Panel>
  );
}
