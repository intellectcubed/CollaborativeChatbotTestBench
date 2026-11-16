import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../../api.js";

// The bot run as the page sees it: the conversation so far, the judge's state, and Go and Stop.
// It polls only while a run is going. A new run starts the conversation again.
export function useBot() {
  const [events, setEvents] = useState([]);
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const sinceRef = useRef(0);
  const runRef = useRef("");

  const poll = useCallback(async () => {
    let s;
    try {
      s = await call(`/api/bot/status?since=${sinceRef.current}`);
      let fresh = false;
      if (s.run !== runRef.current) {  // a new run: start the conversation again
        runRef.current = s.run;
        sinceRef.current = 0;
        fresh = true;
        s = await call("/api/bot/status?since=0");
      }
      sinceRef.current = s.next;
      setEvents(prev => (fresh ? [] : prev).concat(s.events));
      setState(s);
      return s;
    } catch (e) {
      return null;
    }
  }, []);

  useEffect(() => { poll(); }, [poll]);

  useEffect(() => {
    if (state?.state !== "running") return undefined;
    const t = setTimeout(poll, 1000);
    return () => clearTimeout(t);
  }, [state, poll]);

  async function go(goal) {
    try {
      await call("/api/bot/go", "POST", goal);
      setError("");
    } catch (e) {
      setError(e.message);
    }
    await poll();
  }

  async function stop() {
    try {
      await call("/api/bot/stop", "POST");
      setError("");
    } catch (e) {
      setError(e.message);
    }
    await poll();
  }

  return {
    events, state, error, go, stop,
    busy: state?.state === "running",
  };
}
