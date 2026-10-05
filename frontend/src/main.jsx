import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";
import "./features.css";
import "./timeline.css";
import "./scenarios.css";
import "./simulation.css";
import "./adaptive.css";
import "./agents.css";
import "./advanced-controls.css";
import "./print.css";
import "./history.css";
import "./ai.css";
import "./polish.css";

createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
