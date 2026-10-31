import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/fraunces";
import "@fontsource-variable/hanken-grotesk";
import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";
import "./styles/tokens.css";
import "./styles/app.css";
import "./styles/odds.css";
import { App } from "./App";
import { DraftPage } from "./pages/DraftPage";

const element =
  window.location.pathname === "/draft" ? <DraftPage /> : <App />;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{element}</React.StrictMode>,
);
