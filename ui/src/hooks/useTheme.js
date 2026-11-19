import { useEffect, useState } from "react";

// Dark by default. The choice is kept in this browser; if storage is refused, it simply is not kept.
const KEY = "workbench.theme";

function readSaved() {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch (e) {
    return "dark";
  }
}

export function useTheme() {
  const [theme, setTheme] = useState(readSaved);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem(KEY, theme); } catch (e) { /* not kept: fine */ }
  }, [theme]);

  const toggleTheme = () => setTheme(t => (t === "light" ? "dark" : "light"));
  return { theme, toggleTheme };
}
