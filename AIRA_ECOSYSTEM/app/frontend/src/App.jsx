import { useState } from "react";
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
import ConnectionIndicator from "./components/connection/ConnectionIndicator.jsx";
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

export default function App() {
  const [active, setActive] = useState("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const Page = PAGES[active] || ChatPage;

  return (
    <ToastProvider>
      <SessionsProvider>
        <ChatRuntimeProvider isOnChatPage={active === "chat"}>
          <BootGate>
            <div className="min-h-[100dvh] h-screen w-screen overflow-hidden overscroll-none bg-app text-white">
              <div className="flex h-full">
                <Sidebar
                  active={active}
                  onChange={setActive}
                  isOpen={drawerOpen}
                  onClose={() => setDrawerOpen(false)}
                />

                <main className="relative min-w-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_50%_0%,rgba(159,122,234,0.10),transparent_42%)]">
                  <div className="sticky top-0 z-30 px-3 pt-3 sm:px-5 lg:px-7">
                    <div className="aira-panel flex min-h-12 items-center justify-between gap-3 px-3 py-2 sm:px-4">
                      <div className="flex min-w-0 items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setDrawerOpen(true)}
                          className="aira-control rounded-full px-3 py-1.5 text-xs text-white/65 transition hover:bg-white/10 md:hidden"
                          aria-label="Buka menu"
                        >
                          ☰
                        </button>
                        <span className="truncate text-xs font-medium text-white/60">AIRA OS</span>
                        <span className="hidden rounded-full border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] text-white/40 sm:inline-flex">AI Operating System</span>
                      </div>
                      <ConnectionIndicator onClick={() => setActive("akane")} />
                    </div>
                  </div>

                  <div className="min-h-full px-3 pb-24 pt-3 sm:px-5 sm:pb-8 lg:px-7">
                    <div className="mx-auto flex min-h-full w-full max-w-[1100px] flex-col">
                      <Page onOpenMenu={() => setDrawerOpen(true)} />
                    </div>
                  </div>
                </main>

                <MobileNav active={active} onChange={setActive} />
              </div>
            </div>
          </BootGate>
        </ChatRuntimeProvider>
      </SessionsProvider>
    </ToastProvider>
  );
}
