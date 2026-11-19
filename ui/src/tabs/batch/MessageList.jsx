import TraceId from "../../components/TraceId.jsx";
// The scrollable list of messages. The highlighted row is blue (the one Run Selected sends), a row being sent is yellow,
// a failed row is red. A click on a row selects it. Each row has a check box for Run All Checked.
export default function MessageList({ lines, current, onSelect, onCheck, empty }) {
  if (!lines.length) return <p className="placeholder">{empty}</p>;
  return (
    <div className="messages">
      <table>
        <thead>
          <tr>
            <th>Run</th><th>When (New York)</th><th>Name</th><th>Squad</th><th>Message</th><th>Status</th><th>Chatbot</th>
          </tr>
        </thead>
        <tbody>
          {lines.map(ln => {
            const cls = [ln.status, ln.index === current ? "current" : ""].filter(Boolean).join(" ");
            return (
              <tr key={ln.index} className={cls} onClick={e => { if (!e.target.closest("input, button")) onSelect(ln.index); }}>
                <td><input type="checkbox" checked={ln.checked} onChange={e => onCheck(ln.index, e.target.checked)} /></td>
                <td>{ln.display_time}</td>
                <td>{ln.name}<br /><span className="status">{ln.member}</span></td>
                <td>{ln.squad}</td>
                <td className="text">{ln.text}</td>
                <td>
                  {ln.status === "done" && !ln.replies.length ? "done (no reply)" : ln.status}
                  {ln.trace_id && <div className="status"><TraceId id={ln.trace_id} /> · {ln.trace_status || ""}</div>}
                  {ln.tokens && <div className="status">model tokens in {ln.tokens.input} · out {ln.tokens.output}</div>}
                  {ln.error && <div className="err">{ln.error}</div>}
                </td>
                <td>
                  {ln.replies.map((r, i) => (
                    <div className="reply" key={i}>
                      <b>{r.kind}</b> → {r.channel} ({r.status}){r.error ? ` · ${r.error}` : ""}<br />{r.text}
                    </div>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
