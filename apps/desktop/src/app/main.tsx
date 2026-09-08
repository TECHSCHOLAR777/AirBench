import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@wdio/tauri-plugin";
import App from "./App";
import { DesktopErrorBoundary } from "./DesktopErrorBoundary";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DesktopErrorBoundary>
      <App />
    </DesktopErrorBoundary>
  </StrictMode>,
);
