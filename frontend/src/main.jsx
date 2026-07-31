import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider } from "@mui/material";
import App from "./App";
import { getTheme } from "./theme";
import { ThemeModeProvider, useThemeMode } from "./context/ThemeContext";
import "./index.css";

function Root() {
  const { mode } = useThemeMode();
  return <ThemeProvider theme={getTheme(mode)}><CssBaseline /><App /></ThemeProvider>;
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode><ThemeModeProvider><Root /></ThemeModeProvider></React.StrictMode>,
);
