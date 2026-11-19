import Panel from "../../components/Panel.jsx";

// Filter by New York date. It only changes what is shown, not what runs.
export default function FilterPanel({ draft, setDraft, apply, clear, message, disabled }) {
  return (
    <Panel title="Filter">
      <label>From <input type="date" value={draft.from} onChange={e => setDraft({ ...draft, from: e.target.value })} /></label>
      <label>To <input type="date" value={draft.to} onChange={e => setDraft({ ...draft, to: e.target.value })} /></label>
      <div>
        <button onClick={apply} disabled={disabled}>Filter</button>
        <button onClick={clear} disabled={disabled}>Clear</button>
      </div>
      {message && <p className="err">{message}</p>}
    </Panel>
  );
}
