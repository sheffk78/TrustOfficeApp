import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { TracewayProvider } from "@tracewayapp/react";

const root = ReactDOM.createRoot(document.getElementById("root"));

// Traceway pilot (2026-09-18): mounted outside <StrictMode> per SDK docs
// (StrictMode double-invokes the provider constructor in dev → doubled reports).
// Inert unless REACT_APP_TRACEWAY_CONNECTION_STRING is set at build time.
const tracewayConn = process.env.REACT_APP_TRACEWAY_CONNECTION_STRING;
const appTree = (
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

root.render(
  tracewayConn ? (
    <TracewayProvider connectionString={tracewayConn}>{appTree}</TracewayProvider>
  ) : (
    appTree
  )
);
