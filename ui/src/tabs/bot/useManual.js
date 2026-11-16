import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../../api.js";

// Manual chat as the page sees it: the driver holds the messages; the page polls only while a reply is awaited.
export function useManual() {
  const [events, setEvents] = useState([]);
  const [session, setSession] = useState(null);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState("");
  const sinceRef = useRef(0);
  const sessionRef = useRef(null);

  const poll = useCallback(async () => {
    try {
      let s = await call(`/api/manual/status?since=${sinceRef.current}`);
      let fresh = false;
      if (s.session !== sessionRef.current) {  // cleared, or a fresh page: start again
        sessionRef.current = s.session;
        sinceRef.current = 0;
        fresh = true;
        s = await call("/api/manual/status?since=0");
      }
      sinceRef.current = s.next;
      setEvents(prev => (fresh ? [] : prev).concat(s.events));
      setSession(s.session);
      setWaiting(s.waiting);
      return s;
    } catch (e) {
      return null;
    }
  }, []);

  useEffect(() => { poll(); }, [poll]);

  useEffect(() => {
    if (!waiting) return undefined;
    const t = setTimeout(poll, 700);
    return () => clearTimeout(t);
  }, [waiting, events, poll]);

  // `onSent` gets the driver's answer (trace_id, sent_at, name, squad) as soon as the chatbot has the message,
  // before the first status poll, so the page can show the member's bubble with its trace ID at once.
  async function send(body, onSent) {
    try {
      const sent = await call("/api/manual/send", "POST", body);
      onSent?.(sent);
      setError("");
      setWaiting(true);
      await poll();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    }
  }

  async function clear() {
    try {
      await call("/api/manual/clear", "POST");
      setError("");
    } catch (e) {
      setError(e.message);
    }
    await poll();
  }

  return { events, session, waiting, error, send, clear };
}
