import { useCallback, useEffect, useState } from "react";
import { call } from "../api.js";

// The bot's own model use (tester and judge) and the budget, from the driver. Read once when the page opens, then
// only when something can have changed it (a bot run ends, or Reset): no polling.
export function useUsage() {
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setUsage(await call("/api/usage"));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function reset() {
    try {
      await call("/api/usage/reset", "POST");
      setError("");
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }

  return { usage, reset, refresh, error };
}
