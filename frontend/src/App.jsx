import { useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
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
    <div className="h-screen w-screen flex bg-app text-white overflow-hidden">
      <Sidebar active={active} onChange={setActive} />
      <main className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto h-full flex flex-col">
          <Page />
        </div>
      </main>
    </div>
  );
}
