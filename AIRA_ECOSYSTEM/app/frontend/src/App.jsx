import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import MobileNav from "./components/MobileNav.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import DevicesPage from "./pages/DevicesPage.jsx";
import MemoryPage from "./pages/MemoryPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import LogsPage from "./pages/LogsPage.jsx";
import { SessionsProvider } from "./context/SessionsContext.jsx";
import { ChatRuntimeProvider } from "./context/ChatRuntimeContext.jsx";
import { ToastProvider } from "./components/Toast.jsx";

const PAGES = {
  chat: ChatPage,
  devices: DevicesPage,
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
        {/* ChatRuntimeProvider dipasang DI SINI (level App), bukan di
            dalam ChatPage - supaya state chat & koneksi WebSocket TIDAK
            ikut hilang saat Page berpindah (mis. ke Settings). */}
        <ChatRuntimeProvider isOnChatPage={active === "chat"}>
          <div className="h-[100dvh] h-screen w-screen flex bg-app text-white overflow-hidden overscroll-none">
            <Sidebar
              active={active}
              onChange={setActive}
              isOpen={drawerOpen}
              onClose={() => setDrawerOpen(false)}
            />

            <main className="flex-1 min-w-0 overflow-y-auto">
              <div className="p-4 sm:p-6 lg:p-8 pb-24 md:pb-8 h-full">
                <div className="max-w-5xl mx-auto h-full flex flex-col">
                  <Page onOpenMenu={() => setDrawerOpen(true)} />
                </div>
              </div>
            </main>

            <MobileNav active={active} onChange={setActive} />
          </div>
        </ChatRuntimeProvider>
      </SessionsProvider>
    </ToastProvider>
  );
}