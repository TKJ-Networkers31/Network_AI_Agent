// src/App.jsx
//
// PERUBAHAN (UI Layout & Code Splitting):
// - Sidebar menempel penuh ke kiri/atas/bawah; state `collapsed` dipegang di sini
//   dan disimpan ke localStorage. Shortcut Ctrl/Cmd+B untuk toggle.
// - Padding halaman dikecilkan (px-3 sm:px-5 lg:px-6) dan max-w-5xl dihapus.
//   TopBar & ChatInput memakai margin negatif yang SAMA supaya bisa
//   menempel ke tepi.
// - Halaman chat/workspace/logs memakai tinggi tetap (h-full, scroll internal).
//   Halaman lain memakai min-h-full (menyatu dengan scroll <main>).
// - ConnectionIndicator dipindah ke TopBar (klik -> event "aira:navigate").
// - Ruang bawah untuk MobileNav (h-14 + safe area) dipindah ke <main>.
// - Code Splitting: Halaman ChatPage di-load eager (default landing),
//   sedangkan 10 halaman sekunder di-load on-demand via React.lazy() + Suspense
//   dengan retry logic otomatis dan ErrorBoundary untuk chunk recovery.
// - VoiceCompanionHost diposisikan di luar <main> dan <Suspense> agar TIDAK
//   pernah remount saat navigasi antar-halaman.

import React, { Component, Suspense, lazy, useCallback, useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import MobileNav from "./components/MobileNav.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import { SessionsProvider } from "./context/SessionsContext.jsx";
import { ChatRuntimeProvider } from "./context/ChatRuntimeContext.jsx";
import { ToastProvider } from "./components/Toast.jsx";
import BootGate from "./components/boot/BootGate.jsx";
import AccessLocationReporter from "./components/location/AccessLocationReporter.jsx";
import VoiceCompanionHost from "./components/voice/VoiceCompanionHost.jsx";

// Helper lazy loader dengan toleransi retry saat kendala jaringan / chunk load error
function lazyWithRetry(componentImport) {
  return lazy(async () => {
    try {
      return await componentImport();
    } catch (error) {
      console.warn("[AIRA CodeSplitting] Chunk load failed, retrying once...", error);
      try {
        return await componentImport();
      } catch (retryError) {
        console.error("[AIRA CodeSplitting] Chunk load retry failed:", retryError);
        throw retryError;
      }
    }
  });
}

// Secondary pages loaded on demand via dynamic imports
const WorkspacePage = lazyWithRetry(() => import("./pages/WorkspacePage.jsx"));
const DevicesPage = lazyWithRetry(() => import("./pages/DevicesPage.jsx"));
const TopologyPage = lazyWithRetry(() => import("./pages/TopologyPage.jsx"));
const NmsPage = lazyWithRetry(() => import("./pages/NmsPage.jsx"));
const NetworkIntelligencePage = lazyWithRetry(() => import("./pages/NetworkIntelligencePage.jsx"));
const AkaneWorkspace = lazyWithRetry(() => import("./pages/AkaneWorkspace.jsx"));
const ModelsPage = lazyWithRetry(() => import("./pages/ModelsPage.jsx"));
const PersonaPage = lazyWithRetry(() => import("./pages/PersonaPage.jsx"));
const MemoryPage = lazyWithRetry(() => import("./pages/MemoryPage.jsx"));
const SettingsPage = lazyWithRetry(() => import("./pages/SettingsPage.jsx"));
const LogsPage = lazyWithRetry(() => import("./pages/LogsPage.jsx"));

const PAGES = {
  chat: ChatPage,
  workspace: WorkspacePage,
  topology: TopologyPage,
  nms: NmsPage,
  devices: DevicesPage,
  intelligence: NetworkIntelligencePage,
  akane: AkaneWorkspace,
  models: ModelsPage,
  persona: PersonaPage,
  memory: MemoryPage,
  logs: LogsPage,
  settings: SettingsPage,
};

// Halaman yang mengatur scroll-nya sendiri di dalam (butuh tinggi tetap).
const FIXED_HEIGHT_PAGES = new Set(["chat", "workspace", "logs", "topology", "nms"]);

const SIDEBAR_KEY = "aira_sidebar_collapsed";

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

// Fallback visual saat chunk halaman sedang diunduh
function PageLoadingFallback({ label = "Memuat halaman..." }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-neutral-400 select-none animate-in fade-in duration-200">
      <div className="relative w-10 h-10 mb-4 flex items-center justify-center">
        <div className="absolute inset-0 rounded-full border-2 border-cyan-500/20 border-t-cyan-400 animate-spin" />
        <span className="text-[10px] font-mono text-cyan-400 font-semibold tracking-wider">AIRA</span>
      </div>
      <p className="text-xs tracking-wider uppercase text-neutral-400">{label}</p>
    </div>
  );
}

// Boundary error untuk menangani kegagalan jaringan saat unduh chunk
class PageErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[AIRA PageErrorBoundary] Uncaught chunk load error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-neutral-400 text-center">
          <div className="w-12 h-12 mb-3 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 font-mono text-lg font-bold">
            !
          </div>
          <h3 className="text-sm font-medium text-white mb-1">Gagal memuat modul halaman</h3>
          <p className="text-xs text-neutral-400 max-w-sm mb-4">
            Terjadi kendala jaringan saat mengunduh komponen halaman. Silakan muat ulang.
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.reload();
            }}
            className="px-3.5 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs font-medium text-white border border-neutral-700 transition-colors shadow-sm"
          >
            Muat Ulang Halaman
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [active, setActive] = useState("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const Page = PAGES[active] || ChatPage;
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
          <AccessLocationReporter />
          <VoiceCompanionHost onNavigate={setActive} />
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
                    <PageErrorBoundary key={active}>
                      <Suspense fallback={<PageLoadingFallback label={`Memuat ${active}...`} />}>
                        <Page onOpenMenu={() => setDrawerOpen(true)} />
                      </Suspense>
                    </PageErrorBoundary>
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
