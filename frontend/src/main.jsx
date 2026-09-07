import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Fade out the static boot loader once React has mounted.
const boot = document.getElementById("boot-loader");
if (boot) {
  boot.style.transition = "opacity 0.3s ease";
  boot.style.opacity = "0";
  setTimeout(() => boot.remove(), 350);
}