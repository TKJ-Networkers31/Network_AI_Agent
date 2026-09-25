// src/hooks/useCapabilities.js
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Hook generik: mengambil daftar kapabilitas dari backend untuk satu `area`
// UI tertentu ("hero", "chat_input", "capability_dock", "message_actions",
// "file_actions"), beserta sinyal konteks yang relevan (attachment,
// selection, artifact, location, conversation, file_path, dst).
//
// PENTING: hook ini TIDAK mendefinisikan kapabilitas apa pun. Backend adalah
// satu-satunya sumber kebenaran - hook ini hanya fetch + debounce + reaksi
// terhadap perubahan konteks, lalu mengembalikan apa pun yang dikirim
// backend apa adanya (termasuk field `enabled` / `disabled_reason`).
//
// Kalau endpoint belum ada di backend (404) atau gagal, hook ini diam-diam
// mengembalikan capabilities=[] supaya UI yang memakainya bisa hide secara
// graceful tanpa crash (lihat catatan keterbatasan di laporan pengiriman).

import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const DEBOUNCE_MS = 180;

export function useCapabilities(area, context = {}) {
  const [capabilities, setCapabilities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const timerRef = useRef(null);
  const reqIdRef = useRef(0);
  const contextKey = JSON.stringify(context);

  useEffect(() => {
    if (!area) return undefined;

    clearTimeout(timerRef.current);

    timerRef.current = setTimeout(() => {
      const reqId = ++reqIdRef.current;
      setLoading(true);
      setError(null);

      api.capabilities
        .list({ area, ...context })
        .then((res) => {
          if (reqId !== reqIdRef.current) return; // konteks sudah berubah lagi, buang hasil basi
          setCapabilities(Array.isArray(res?.capabilities) ? res.capabilities : []);
        })
        .catch((err) => {
          if (reqId !== reqIdRef.current) return;
          setError(err);
          setCapabilities([]);
        })
        .finally(() => {
          if (reqId === reqIdRef.current) setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [area, contextKey]);

  return { capabilities, loading, error };
}
