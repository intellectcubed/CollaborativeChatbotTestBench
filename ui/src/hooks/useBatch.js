import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../api.js";
import { inFilter, isBusy } from "../format.js";

const sleep = ms => new Promise(r => setTimeout(r, ms));

// The batch as the page sees it: the driver keeps the rows, the page keeps a copy and asks only for rows that changed.
// It polls only while a run is going; otherwise it refreshes after each action.
export function useBatch({ botBusy }) {
  const [status, setStatus] = useState(null);
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState({ from: "", to: "" });
  const [filterDraft, setFilterDraft] = useState({ from: "", to: "" });
  const [filterMsg, setFilterMsg] = useState("");
  const [message, setMessage] = useState("");
  const [warnings, setWarnings] = useState([]);
  const [runLoop, setRunLoop] = useState(false);
  const versionRef = useRef(-1);
  const batchIdRef = useRef(null);
  const rowsRef = useRef([]);
  const stopRef = useRef(false);

  const refresh = useCallback(async () => {
    let s;
    try {
      s = await call(`/api/batch?since=${versionRef.current}`);
      if (s.batch_id !== batchIdRef.current) {  // another batch, or none: start the copy again
        batchIdRef.current = s.batch_id;
        versionRef.current = -1;
        rowsRef.current = [];
        s = await call("/api/batch?since=-1");
      }
    } catch (e) {
      return null;
    }
    const next = rowsRef.current.slice();
    for (const ln of s.lines) next[ln.index] = ln;
    rowsRef.current = next;
    versionRef.current = s.version;
    setRows(next);
    setStatus(s);
    return s;
  }, []);

  // A fresh page closes any batch left open. A run that is still going on the driver is kept and shown.
  useEffect(() => {
    (async () => {
      try { await call("/api/batch/close", "POST"); } catch (e) { /* a run is going: keep it */ }
      await refresh();
    })();
  }, [refresh]);

  const busy = !!status && isBusy(status.state);
  useEffect(() => {
    if (!busy) return undefined;
    const t = setInterval(refresh, 1000);
    return () => clearInterval(t);
  }, [busy, refresh]);

  const blocked = busy || runLoop || botBusy;

  async function act(path, body) {
    try {
      await call(path, "POST", body);
      setMessage("");
    } catch (e) {
      setMessage(e.message);
    }
    await refresh();
  }

  async function openFile(file) {
    try {
      const content = await file.text();
      const r = await call("/api/batch/open", "POST", { name: file.name.replace(/\.[^.]+$/, ""), content });
      setWarnings(r.warnings);
      setFilter({ from: "", to: "" });
      setFilterDraft({ from: "", to: "" });
      setFilterMsg("");
      await refresh();
      return { ok: true, text: `opened ${r.messages} messages` };
    } catch (e) {
      return { ok: false, text: `not opened: ${e.message}` };
    }
  }

  function applyFilter() {
    const { from, to } = filterDraft;
    if (!from && !to) { setFilterMsg("choose a From or To date"); return; }
    if (from && to && from > to) { setFilterMsg("From is after To"); return; }
    setFilterMsg("");
    setFilter({ from, to });
  }

  function clearFilter() {
    setFilterDraft({ from: "", to: "" });
    setFilter({ from: "", to: "" });
    setFilterMsg("");
  }

  // Run Selected: the highlighted row is sent, and the driver moves the highlight on.
  const runSelected = () => act("/api/batch/run", { mode: "current" });

  // Run All Checked: starts at the highlighted row and runs each checked, pending row below it that the filter shows.
  // The page sends one Run request per line and waits for each to finish.
  async function runAllChecked() {
    setRunLoop(true);
    stopRef.current = false;
    try {
      const s = await refresh();
      const from = s?.current ?? 0;
      const todo = rowsRef.current.filter(Boolean)
        .filter(ln => ln.index >= from && ln.checked && ln.status === "pending" && inFilter(ln, filter))
        .map(ln => ln.index);
      if (!todo.length) {
        setMessage("nothing to run: no checked, pending lines from the highlighted row on, in the filter");
        return;
      }
      for (const index of todo) {
        if (stopRef.current) break;
        await call("/api/batch/select", "POST", { index });
        await call("/api/batch/run", "POST", { mode: "current" });
        for (;;) {
          const cur = await refresh();
          if (!cur || !isBusy(cur.state)) break;
          await sleep(1000);
        }
      }
    } catch (e) {
      setMessage(e.message);
    } finally {
      setRunLoop(false);
      await refresh();
    }
  }

  const stop = () => { stopRef.current = true; return act("/api/batch/stop"); };

  async function setChecked(index, checked) {
    try {
      await call(`/api/batch/lines/${index}`, "POST", { checked });
    } catch (e) {
      setMessage(e.message);
    }
    await refresh();
  }

  const select = index => act("/api/batch/select", { index });

  const shown = rows.filter(Boolean).filter(ln => inFilter(ln, filter));

  return {
    status, rows, shown, filter, filterDraft, setFilterDraft, filterMsg, applyFilter, clearFilter,
    message, warnings, busy, runLoop, blocked, openFile, runSelected, runAllChecked, stop, setChecked, select,
    pause: () => act("/api/batch/pause"), resume: () => act("/api/batch/resume"),
    markAllPending: () => act("/api/batch/reset"),
  };
}
