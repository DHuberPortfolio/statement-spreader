import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/app.css";
import "./styles/finops.css";

const root = document.getElementById("root");
if (!root) throw new Error("No #root element");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
