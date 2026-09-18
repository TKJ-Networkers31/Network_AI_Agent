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
  const Page = PAGES[active];

  return (
    <ToastProvider>
      <SessionsProvider>
        <ChatRuntimeProvider isOnChatPage={active === "chat"}>
          <BootGate>
            <div className="min-h-[100dvh] h-screen w-screen flex bg-app text-white overflow-hidden overscroll-none">
              <Sidebar
                active={active}
                onChange={setActive}
                isOpen={drawerOpen}
                onClose={() => setDrawerOpen(false)}
              />

              <main className="flex-1 min-w-0 overflow-y-auto relative bg-[radial-gradient(circle_at_50%_0%,rgba(159,122,234,0.08),transparent_42%)]">
                <div className="fixed top-3 right-3 z-30">
                  <ConnectionIndicator onClick={() => setActive("akane")} />
                </div>

                <div className="p-3 sm:p-5 lg:p-7 pb-24 md:pb-8 min-h-full">
                  <div className="max-w-[1100px] mx-auto min-h-full flex flex-col">
                    <Page onOpenMenu={() => setDrawerOpen(true)} />
                  </div>
                </div>
              </main>

              <MobileNav active={active} onChange={setActive} />
            </div>
          </BootGate>
        </ChatRuntimeProvider>
      </SessionsProvider>
    </ToastProvider>
  );
}
