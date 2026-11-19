import BatchFilePanel from "./batch/BatchFilePanel.jsx";
import FilterPanel from "./batch/FilterPanel.jsx";
import RunPanel from "./batch/RunPanel.jsx";
import ControlPanel from "./batch/ControlPanel.jsx";
import MessageList from "./batch/MessageList.jsx";

// The Batch tab: the static panels across the top, and the scrollable list of messages below.
export default function BatchTab({ batch, botBusy }) {
  const b = batch;
  const status = b.status;
  const total = status?.total ?? 0;
  const hasBatch = !!status?.name;
  const filtering = b.filter.from || b.filter.to;
  const summary = hasBatch
    ? `${filtering ? `showing ${b.shown.length} of ${total}` : `${total} messages`} · ${status.pending} checked and pending${status.description ? ` · ${status.description}` : ""}`
    : "";
  return (
    <section className="batch">
      <div className="panels">
        <BatchFilePanel name={status?.name} total={total} openFile={b.openFile} blocked={b.blocked} />
        <FilterPanel draft={b.filterDraft} setDraft={b.setFilterDraft} apply={b.applyFilter} clear={b.clearFilter}
          message={b.filterMsg} disabled={!hasBatch} />
        <RunPanel runSelected={b.runSelected} runAllChecked={b.runAllChecked}
          selectedDisabled={b.blocked || status?.current == null}
          allDisabled={b.blocked || !hasBatch} />
        <ControlPanel state={status?.state} pause={b.pause} resume={b.resume} stop={b.stop}
          markAllPending={b.markAllPending} markDisabled={b.blocked || !hasBatch} message={b.message} />
      </div>
      <div className="summary status">{summary}</div>
      {b.warnings.map((w, i) => <div key={i} className="warn">{w}</div>)}
      <MessageList lines={b.shown} current={status?.current} onSelect={b.select} onCheck={b.setChecked}
        empty={hasBatch ? "No messages in this range." : "Open a batch file to see its messages."} />
      {botBusy && <p className="status">A bot run is going: batch runs wait for it to stop.</p>}
    </section>
  );
}
