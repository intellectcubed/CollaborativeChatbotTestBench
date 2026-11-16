import { useRef, useState } from "react";
import Panel from "../../components/Panel.jsx";

// Choose File: the browser reads the file, and the driver parses and checks it.
export default function BatchFilePanel({ name, total, openFile, blocked }) {
  const input = useRef(null);
  const [result, setResult] = useState("");

  async function onChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    setResult("opening...");
    const r = await openFile(file);
    setResult(r.text);
    e.target.value = "";  // so the same file can be chosen again
  }

  return (
    <Panel title="Batch File">
      <button onClick={() => input.current.click()} disabled={blocked}>Choose File</button>
      <input ref={input} type="file" accept=".jsonl,.json,application/json" hidden onChange={onChange} />
      <p className="status">{name ? `${name}.jsonl` : "no file open"}</p>
      <p className="status">{result || (name ? `${total} messages` : "")}</p>
    </Panel>
  );
}
