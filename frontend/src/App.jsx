import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import MobileNav from "./components/MobileNav.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import DevicesPage from "./pages/DevicesPage.jsx";
import MemoryPage from "./pages/MemoryPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";

const PAGES = {
  chat: ChatPage,
  devices: DevicesPage,
  memory: MemoryPage,
  settings: SettingsPage,
};

export default function App() {
  const [active, setActive] = useState("chat");
  const Page = PAGES[active];

  return (
    <div className="h-[100dvh] h-screen w-screen flex bg-app text-white overflow-hidden overscroll-none">
      <Sidebar active={active} onChange={setActive} />

      <main className="flex-1 min-w-0 overflow-y-auto">
        <div className="p-4 sm:p-6 lg:p-8 pb-24 md:pb-8 h-full">
          <div className="max-w-5xl mx-auto h-full flex flex-col">
            <Page />
          </div>
        </div>
      </main>

      <MobileNav active={active} onChange={setActive} />
    </div>
  );
}