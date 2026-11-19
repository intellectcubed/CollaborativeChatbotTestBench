import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../../api.js";
import { sundayOf, todayNY } from "./dates.js";

// The week preview: which week is shown, its seven days, and the changes found at the last refresh.
// The driver compares each read with the one before it, so a refresh after a reply says what that reply changed.
export function useWeek() {
  const [start, setStartRaw] = useState(() => sundayOf(todayNY()));
  const [days, setDays] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [outside, setOutside] = useState([]);  // changes on days outside the week shown
  const startRef = useRef(start);

  const load = useCallback(async (sunday, recheck) => {
    setLoading(true);
    try {
      const r = await call(`/api/calendar/week?start=${sunday}${recheck ? "&recheck=true" : ""}`);
      if (r.start === startRef.current) setDays(r.days);
      setError("");
      return r.changes;
    } catch (e) {
      setError(e.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  const setStart = useCallback(iso => {
    const sunday = sundayOf(iso);
    startRef.current = sunday;
    setStartRaw(sunday);
    setOutside(prev => prev.filter(c => sundayOf(c.date) !== sunday));
  }, []);

  useEffect(() => { load(start, false); }, [start, load]);

  // After a reply: read the week again, and the other days seen lately. Returns every change found.
  const refresh = useCallback(async () => {
    const changes = await load(startRef.current, true);
    const away = changes.filter(c => !c.in_week);
    if (away.length) setOutside(away);
    return changes;
  }, [load]);

  return { start, setStart, days, error, loading, outside, dismissOutside: () => setOutside([]), refresh };
}
