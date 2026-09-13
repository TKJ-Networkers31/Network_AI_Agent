import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

if ("serviceWorker" in navigator) {
  if (import.meta.env.PROD) {
    // Hanya aktif di production build (npm run build + serve) - ini yang
    // memberi kemampuan PWA offline. Di dev server (npm run dev), SW
    // JANGAN pernah aktif karena strategi stale-while-revalidate di
    // service-worker.js akan menyajikan bundle JS/CSS LAMA dari cache
    // walau source code & Vite HMR sudah update - gejalanya: perubahan
    // UI (mis. menu Sidebar baru) tidak pernah muncul meski kode benar.
    window.addEventListener("load", () => {
      navigator.serviceWorker
        .register("/service-worker.js")
        .catch((err) => console.warn("Service worker gagal didaftarkan:", err));
    });
  } else {
    // Bersihkan registrasi SW lama yang mungkin masih nyangkut dari sesi
    // dev sebelumnya (sebelum fix ini ada), supaya tidak terus menyajikan
    // cache basi selama development.
    navigator.serviceWorker.getRegistrations().then((regs) => {
      regs.forEach((reg) => reg.unregister());
    });
  }
}