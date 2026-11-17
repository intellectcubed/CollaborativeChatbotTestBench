import { useState } from "react";

// The trace ID, shortened, with a button that copies the whole ID. Used on the Bot tab bubbles and the Batch rows.
// The click does not reach the row or bubble under it, so copying never selects a Batch row.
export default function TraceId({ id }) {
  const [copied, setCopied] = useState(false);
  async function copy(e) {
    e.stopPropagation();
    let ok = false;
    try {
      await navigator.clipboard.writeText(id);
      ok = true;
    } catch (err) {
      // the clipboard API can be refused (no focus, no permission): fall back to a hidden text box
      const box = document.createElement("textarea");
      box.value = id;
      box.style.position = "fixed";
      box.style.opacity = "0";
      document.body.appendChild(box);
      box.select();
      try { ok = document.execCommand("copy"); } catch (err2) { ok = false; }
      box.remove();
    }
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1000);
    }
  }
  return (
    <span className="traceid">
      trace {String(id).slice(0, 8)}
      <button className="copy" onClick={copy} title="Copy the full trace ID" aria-label="Copy trace ID">
        {copied ? "Copied" : "⧉"}
      </button>
    </span>
  );
}
