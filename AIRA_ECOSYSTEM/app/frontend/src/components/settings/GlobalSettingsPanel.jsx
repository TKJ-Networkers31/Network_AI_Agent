import { useCallback, useEffect, useState } from "react";
import { settingsApi } from "../../services/settingsApi.js";
import { useToast } from "../Toast.jsx";
import { applyGlobalSettingsUpdate } from "../../hooks/useGlobalSettings.js";

// Field yang boleh diedit lewat panel ini, dan tipe kontrol yang dipakai.
// Menambah setting baru cukup menambah baris di sini (backend sudah
// menervalidasi lewat SETTINGS_SCHEMA di core/global_settings.py).
const FIELDS = [
  { key: "display_name", label: "Nama Tampilan", type: "text", placeholder: "mis. Lingga" },
  { key: "nickname", label: "Panggilan", type: "text", placeholder: "mis. Rin-kun" },
  { key: "assistant_name", label: "Nama Asisten", type: "text", placeholder: "AIRA" },
  { key: "timezone", label: "Zona Waktu", type: "text", placeholder: "Asia/Jakarta" },
  { key: "language", label: "Bahasa", type: "text", placeholder: "id" },
  { key: "theme", label: "Tema", type: "text", placeholder: "arctic-blue" },
  {
    key: "greeting_style",
    label: "Gaya Sapaan",
    type: "select",
    options: ["default", "casual", "formal"],
  },
  { key: "voice_enabled", label: "Suara Aktif", type: "switch" },
];

const INPUT_CLASS =
  "w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-accent";

export default function GlobalSettingsPanel() {
  const [values, setValues] = useState(null);
  const [saving, setSaving] = useState(null); // key yang sedang disimpan
  const [errors, setErrors] = useState({});
  const { notify } = useToast();

  const load = useCallback(() => {
    settingsApi
      .getAll()
      .then((res) => setValues(res.settings))
      .catch((err) => notify({ type: "error", message: err.message }));
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  async function commit(key, value) {
    setSaving(key);
    setErrors((prev) => ({ ...prev, [key]: null }));

    try {
      const res = await settingsApi.update(key, value);
      setValues((prev) => ({ ...prev, [key]: res.value }));
      applyGlobalSettingsUpdate(key, res.value);
      notify({ type: "success", message: "Pengaturan disimpan.", duration: 1800 });
    } catch (err) {
      setErrors((prev) => ({ ...prev, [key]: err.message }));
      // Kembalikan ke nilai server (tolak perubahan lokal yang tidak valid).
      load();
    } finally {
      setSaving(null);
    }
  }

  if (!values) {
    return (
      <div className="bg-card border border-border rounded-xl2 p-5">
        <p className="text-white/40 text-sm">Memuat pengaturan...</p>
      </div>
    );
  }

  return (
    <section className="bg-card border border-border rounded-xl2 p-5">
      <h3 className="font-semibold text-white mb-1">Global &amp; Profil</h3>
      <p className="text-xs text-white/40 mb-4">
        Identitas, bahasa, dan preferensi tampilan — tersimpan lintas sesi.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {FIELDS.map((field) => (
          <div key={field.key} className={field.type === "switch" ? "sm:col-span-2" : ""}>
            <label className="text-xs text-white/50 block mb-1">{field.label}</label>

            {field.type === "text" && (
              <input
                defaultValue={values[field.key] ?? ""}
                placeholder={field.placeholder}
                onBlur={(e) => {
                  const next = e.target.value;
                  if (next !== values[field.key]) commit(field.key, next);
                }}
                disabled={saving === field.key}
                className={INPUT_CLASS}
              />
            )}

            {field.type === "select" && (
              <select
                value={values[field.key] ?? ""}
                onChange={(e) => commit(field.key, e.target.value)}
                disabled={saving === field.key}
                className={INPUT_CLASS}
              >
                {field.options.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            )}

            {field.type === "switch" && (
              <label className="flex items-center gap-2.5 text-sm text-white/80 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(values[field.key])}
                  onChange={(e) => commit(field.key, e.target.checked)}
                  disabled={saving === field.key}
                  className="accent-accent w-4 h-4"
                />
                {values[field.key] ? "Aktif" : "Nonaktif"}
              </label>
            )}

            {errors[field.key] && (
              <p className="text-[11px] text-red-300 mt-1">{errors[field.key]}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
