import { useEffect, useState } from "react";
import { call } from "../api.js";

// The global Live Calendar setting. Batch runs and bot runs both read it from the driver.
export function useSettings() {
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    call("/api/settings").then(s => setLive(s.live)).catch(e => setError(e.message));
  }, []);

  async function setLiveSetting(value) {
    try {
      const s = await call("/api/settings", "PUT", { live: value });
      setLive(s.live);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  return { live, setLiveSetting, error };
}
