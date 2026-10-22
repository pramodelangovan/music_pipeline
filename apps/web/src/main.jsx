import React from "react";
import ReactDOM from "react-dom/client";
import { createTheme, CssBaseline, ThemeProvider } from "@mui/material";
import App from "./App.jsx";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0b5ed7" },
    secondary: { main: "#c44569" },
    background: { default: "#f4f6fb" },
  },
  typography: {
    fontFamily: "'Poppins', 'Segoe UI', sans-serif",
    h4: { fontWeight: 700 },
    h6: { fontWeight: 600 },
  },
  shape: {
    borderRadius: 14,
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
