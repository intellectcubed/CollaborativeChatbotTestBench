import Panel from "../../components/Panel.jsx";

// Run Selected sends the highlighted (blue) row. Run All Checked starts at it and runs each checked row below it.
export default function RunPanel({ runSelected, runAllChecked, selectedDisabled, allDisabled }) {
  return (
    <Panel title="Run">
      <button onClick={runSelected} disabled={selectedDisabled}>Run Selected</button>
      <button onClick={runAllChecked} disabled={allDisabled}>Run All Checked</button>
    </Panel>
  );
}
