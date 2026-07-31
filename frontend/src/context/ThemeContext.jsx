import { createContext, useContext, useEffect, useMemo, useState } from "react";

const ThemeModeContext = createContext(null);

export function ThemeModeProvider({ children }) {
  const [mode, setMode] = useState(
    () =>
      localStorage.getItem("takeoff-theme") ||
      localStorage.getItem("regex-theme") ||
      "light",
  );
  useEffect(() => {
    document.documentElement.classList.toggle("dark", mode === "dark");
    localStorage.setItem("takeoff-theme", mode);
    localStorage.removeItem("regex-theme");
  }, [mode]);
  const value = useMemo(() => ({ mode, toggleMode: () => setMode((current) => current === "light" ? "dark" : "light") }), [mode]);
  return <ThemeModeContext.Provider value={value}>{children}</ThemeModeContext.Provider>;
}

export function useThemeMode() {
  const context = useContext(ThemeModeContext);
  if (!context) throw new Error("useThemeMode must be used within ThemeModeProvider");
  return context;
}
