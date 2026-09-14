import { useEffect, useState } from "react";
import { useSessionsContext } from "../../context/SessionsContext.jsx";
import { useChatRuntime } from "../../context/ChatRuntimeContext.jsx";
import SplashScreen from "./SplashScreen.jsx";
import BootScreen from "./BootScreen.jsx";
import FirstBoot from "./FirstBoot.jsx";
import {
  hasBootedThisSession,
  markBootedThisSession,
  hasSeenFirstBoot,
  markFirstBootSeen,
} from "../../store/bootStore.js";

// Sesuai spesifikasi: transisi 250-350ms per fase fade, splash total
// ~1.6s (lihat public/assets/animations/splash.css).
const SPLASH_DURATION_MS = 1600;

/**
 * BootGate — dipasang SEKALI di App.jsx, membungkus seluruh UI utama.
 *
 * Flow: splash -> boot (menunggu sessionsReady + personaReady, yang
 * SUDAH ada masing-masing di SessionsContext & ChatRuntimeContext -
 * BootGate tidak menambah loading logic baru, cuma menonton context
 * yang sudah ada) -> firstboot (sekali seumur install) -> app.
 *
 * Boot TIDAK muncul lagi setelah fase "app" tercapai dalam sesi ini,
 * karena App.jsx tidak pernah unmount BootGate saat pindah menu -
 * cukup konsisten dengan requirement "tidak muncul saat pindah halaman".
 */
export default function BootGate({ children }) {
  const { sessionsReady } = useSessionsContext();
  const { personaReady } = useChatRuntime();

  const [phase, setPhase] = useState(() =>
    hasBootedThisSession() ? "app" : "splash"
  );

  useEffect(() => {
    if (phase !== "splash") return undefined;
    const timer = setTimeout(() => setPhase("boot"), SPLASH_DURATION_MS);
    return () => clearTimeout(timer);
  }, [phase]);

  useEffect(() => {
    if (phase !== "boot") return;
    if (!sessionsReady || !personaReady) return;

    markBootedThisSession();
    setPhase(hasSeenFirstBoot() ? "app" : "firstboot");
  }, [phase, sessionsReady, personaReady]);

  if (phase === "splash") return <SplashScreen />;

  if (phase === "boot") return <BootScreen label="Menyiapkan AIRA..." />;

  if (phase === "firstboot") {
    return (
      <FirstBoot
        onDone={() => {
          markFirstBootSeen();
          setPhase("app");
        }}
      />
    );
  }

  return children;
}