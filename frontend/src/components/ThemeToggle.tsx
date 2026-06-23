import { useEffect, useState } from "react";
import { readStorage, writeStorage } from "../lib/safeStorage";

const THEME_KEY = "makerspace.theme";

function applyTheme(theme: "light" | "dark") {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const stored = readStorage(THEME_KEY);
    return stored === "dark" ? "dark" : "light";
  });

  useEffect(() => {
    applyTheme(theme);
    writeStorage(THEME_KEY, theme);
  }, [theme]);

  return (
    <button
      className="desk-button"
      type="button"
      onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
    >
      {theme === "dark" ? "Light" : "Dark"}
    </button>
  );
}
