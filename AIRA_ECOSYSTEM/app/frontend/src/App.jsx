// src/App.jsx
//
// PERUBAHAN (UI Layout):
// - Sidebar menempel penuh ke kiri/atas/bawah; state `collapsed` dipegang di sini
//   dan disimpan ke localStorage. Shortcut Ctrl/Cmd+B untuk toggle.
// - Padding halaman dikecilkan (px-3 sm:px-5 lg:px-6) dan max-w-5xl dihapus.
//   TopBar & ChatInput memakai margin negatif yang SAMA supaya bisa
//   menempel ke tepi. Kalau angka padding di sini diubah, ubah juga di
//   TopBar.jsx, ChatInput.jsx, dan ChatPage.jsx.
// - Halaman chat/workspace/logs memakai tinggi tetap (h-full, scroll internal).
//   Halaman lain memakai min-h-full (menyatu dengan scroll <main>).
// - ConnectionIndicator dipindah ke TopBar (klik -> event "aira:navigate").
// - Ruang bawah untuk MobileNav (h-14 + safe area) dipindah ke <main>.

import { useCallback, useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import MobileNav from "./components/MobileNav.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import WorkspacePage from "./pages/WorkspacePage.jsx";
import DevicesPage from "./pages/DevicesPage.jsx";
import AkaneWorkspace from "./pages/AkaneWorkspace.jsx";
import ModelsPage from "./pages/ModelsPage.jsx";
import PersonaPage from "./pages/PersonaPage.jsx";
import MemoryPage from "./pages/MemoryPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import LogsPage from "./pages/LogsPage.jsx";
import { SessionsProvider } from "./context/SessionsContext.jsx";
import { ChatRuntimeProvider } from "./context/ChatRuntimeContext.jsx";
import { ToastProvider } from "./components/Toast.jsx";
import BootGate from "./components/boot/BootGate.jsx";

const PAGES = {
  chat: ChatPage,
  workspace: WorkspacePage,
  devices: DevicesPage,
  akane: AkaneWorkspace,
  models: ModelsPage,
  persona: PersonaPage,
  memory: MemoryPage,
  logs: LogsPage,
  settings: SettingsPage,
};

// Halaman yang mengatur scroll-nya sendiri di dalam (butuh tinggi tetap).
const FIXED_HEIGHT_PAGES = new Set(["chat", "workspace", "logs"]);

const SIDEBAR_KEY = "aira_sidebar_collapsed";

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

export default function App() {
  const [active, setActive] = useState("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const Page = PAGES[active];
  const isFixedHeight = FIXED_HEIGHT_PAGES.has(active);

  // Simpan pilihan collapse (di effect, BUKAN di dalam updater setState -
  // StrictMode memanggil updater dua kali).
  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    } catch {
      // abaikan
    }
  }, [collapsed]);

  const toggleCollapsed = useCallback(() => setCollapsed((v) => !v), []);

  // Shortcut Ctrl/Cmd + B
  useEffect(() => {
    function onKeyDown(e) {
      if (
        (e.ctrlKey || e.metaKey) &&
        !e.shiftKey &&
        !e.altKey &&
        e.key.toLowerCase() === "b"
      ) {
        e.preventDefault();
        setCollapsed((v) => !v);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Navigasi dari komponen yang tidak punya akses ke setActive (mis. TopBar).
  useEffect(() => {
    function onNavigate(e) {
      const id = e.detail;
      if (typeof id === "string" && PAGES[id]) setActive(id);
    }

    window.addEventListener("aira:navigate", onNavigate);
    return () => window.removeEventListener("aira:navigate", onNavigate);
  }, []);

  return (
    <ToastProvider>
      <SessionsProvider>
        <ChatRuntimeProvider isOnChatPage={active === "chat"}>
          <BootGate>
            <div className="h-[100dvh] h-screen w-screen flex bg-app text-white overflow-hidden overscroll-none">
              <Sidebar
                active={active}
                onChange={setActive}
                isOpen={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                collapsed={collapsed}
                onToggleCollapsed={toggleCollapsed}
              />

              <main className="flex-1 min-w-0 h-full flex flex-col pb-[calc(3.5rem+env(safe-area-inset-bottom))] md:pb-0">
                <div className="flex-1 min-h-0 overflow-y-auto">
                  <div
                    className={`flex flex-col px-3 sm:px-5 lg:px-6 pb-3 sm:pb-4 ${
                      isFixedHeight ? "h-full" : "min-h-full"
                    }`}
                  >
                    <Page onOpenMenu={() => setDrawerOpen(true)} />
                  </div>
                </div>
              </main>

              <MobileNav
                active={active}
                onChange={setActive}
                onOpenMenu={() => setDrawerOpen(true)}
              />
            </div>
          </BootGate>
        </ChatRuntimeProvider>
      </SessionsProvider>
    </ToastProvider>
  );
}