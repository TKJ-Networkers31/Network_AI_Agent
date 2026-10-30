import { useCallback, useEffect, useMemo, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";
import { inventoryApi } from "../inventoryApi.js";

const INPUT =
  "w-full bg-white/5 border border-border rounded-control px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-sakura/60 focus:ring-1 focus:ring-sakura/30 transition placeholder-text-secondary/40";
const BTN =
  "text-xs px-3.5 py-2 rounded-pill bg-white/5 text-text-secondary hover:text-text-primary hover:bg-white/10 transition disabled:opacity-40";
const BTN_PRIMARY =
  "bg-sakura-gradient text-white text-xs font-semibold px-5 py-2.5 rounded-pill shadow-sakura-glow hover:brightness-105 transition disabled:opacity-50 flex items-center gap-1.5";
const BTN_DANGER =
  "text-xs px-3.5 py-2 rounded-pill bg-red-500/10 text-red-300 hover:bg-red-500/20 border border-red-500/20 transition";

const CRED_TYPES = [
  { value: "ssh_password", label: "SSH Password", color: "bg-sky-500/10 text-sky-300 border-sky-500/20" },
  { value: "ssh_key", label: "SSH Key (Private Key)", color: "bg-violet-500/10 text-violet-300 border-violet-500/20" },
  { value: "api_key", label: "API Key / Token", color: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20" },
  { value: "snmp_community", label: "SNMP Community", color: "bg-amber-500/10 text-amber-300 border-amber-500/20" },
  { value: "token", label: "Token Khusus", color: "bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/20" },
  { value: "other", label: "Lainnya", color: "bg-white/5 text-text-secondary border-white/10" },
];

const DEVICE_TYPES = ["mikrotik", "linux", "cisco", "switch", "olt", "server", "access_point", "other"];

function getCredBadgeClass(type) {
  const found = CRED_TYPES.find((c) => c.value === type);
  return found ? found.color : "bg-white/5 text-text-secondary border-white/10";
}

function Field({ label, hint, children }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-text-secondary block font-medium">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-text-secondary/60 leading-tight">{hint}</p>}
    </div>
  );
}

// ============================================================
// DEDICATED SUB-PAGE: TAMBAH / EDIT PERANGKAT (Terpisah, Tidak Menumpuk)
// ============================================================
function DeviceEditPage({ initial, credentials, saving, onSubmit, onCancel, onOpenMenu }) {
  const isEdit = Boolean(initial);
  const [form, setForm] = useState({
    name: initial?.name || "",
    host: initial?.host || "",
    port: initial?.port || 22,
    username: initial?.username || "admin",
    device_type: initial?.device_type || "mikrotik",
    snmp_community: "",
    note: initial?.note || "",
    enabled: initial?.enabled ?? true,
    credential_names: (initial?.credentials || []).map((c) => c.name),
    // Input kredensial langsung
    directPassword: "",
    directNoPassword: false,
    directSshKey: "",
    directApiKey: "",
  });

  const [activeCredTab, setActiveCredTab] = useState("password");
  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  function toggleExistingCred(name) {
    set(
      "credential_names",
      form.credential_names.includes(name)
        ? form.credential_names.filter((n) => n !== name)
        : [...form.credential_names, name]
    );
  }

  function submit(e) {
    e.preventDefault();

    const payload = {
      host: form.host.trim(),
      port: Number(form.port) || 22,
      username: form.username.trim(),
      device_type: form.device_type,
      note: form.note.trim(),
      enabled: form.enabled,
      credential_names: form.credential_names,
    };

    if (form.snmp_community.trim()) {
      payload.snmp_community = form.snmp_community.trim();
    }

    if (isEdit) {
      if (form.name.trim() !== initial.name) payload.new_name = form.name.trim();
    } else {
      payload.name = form.name.trim();
    }

    // Bangun kredensial baru jika diisi
    const newCreds = [];
    if (form.directNoPassword) {
      newCreds.push({
        type: "ssh_password",
        username: form.username.trim(),
        secret: "",
        note: "Login SSH tanpa password",
      });
    } else if (form.directPassword.trim()) {
      newCreds.push({
        type: "ssh_password",
        username: form.username.trim(),
        secret: form.directPassword,
        note: `Password SSH untuk ${form.name || "perangkat"}`,
      });
    }

    if (form.directSshKey.trim()) {
      newCreds.push({
        type: "ssh_key",
        username: form.username.trim(),
        secret: form.directSshKey.trim(),
        note: `SSH Key untuk ${form.name || "perangkat"}`,
      });
    }

    if (form.directApiKey.trim()) {
      newCreds.push({
        type: "api_key",
        username: form.username.trim(),
        secret: form.directApiKey.trim(),
        note: `API Key untuk ${form.name || "perangkat"}`,
      });
    }

    if (newCreds.length > 0) {
      payload.new_credentials = newCreds;
    }

    onSubmit(payload);
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-16 animate-fadeIn">
      <TopBar
        title={isEdit ? `Edit: ${initial.name}` : "Tambah Perangkat"}
        subtitle="Konfigurasi perangkat dan kredensial terhubung di database SQLite"
        onMenuClick={onOpenMenu}
      />

      {/* Navigasi Breadcrumb Kembali */}
      <div className="flex items-center justify-between px-1">
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-2 text-xs font-medium text-text-secondary hover:text-text-primary px-3 py-1.5 rounded-pill bg-white/5 border border-border transition"
        >
          <span>←</span>
          <span>Kembali ke Daftar Perangkat</span>
        </button>

        <span className="text-xs text-text-secondary/70">
          Mode: <strong className="text-sakura">{isEdit ? "Penyuntingan Perangkat" : "Pendaftaran Baru"}</strong>
        </span>
      </div>

      <form onSubmit={submit} className="bg-surface border border-border rounded-card p-6 space-y-6 shadow-floating">
        {/* Header Form */}
        <div className="border-b border-border/70 pb-4">
          <h3 className="font-semibold text-text-primary text-lg">
            {isEdit ? `Perbarui Konfigurasi: ${initial.name}` : "Informasi Perangkat Jaringan"}
          </h3>
          <p className="text-xs text-text-secondary/80 mt-1">
            Data perangkat dan kredensial akan disimpan langsung di SQLite <code className="text-sakura">inventory.db</code> dengan enkripsi Fernet.
          </p>
        </div>

        {/* Section 1: Informasi Dasar & Network */}
        <div className="space-y-4">
          <h4 className="text-xs font-bold text-sakura uppercase tracking-wider">
            1. Parameter Jaringan & Identitas
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            <Field label="Nama Perangkat *" hint="Unik, tanpa spasi, mis. R1-Utama">
              <input
                required
                className={INPUT}
                placeholder="mis. Core-Router-1"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </Field>

            <Field label="Alamat Host / IP *" hint="IPv4, IPv6, atau hostname">
              <input
                required
                className={INPUT}
                placeholder="192.168.88.1"
                value={form.host}
                onChange={(e) => set("host", e.target.value)}
              />
            </Field>

            <Field label="Port SSH" hint="Port standar SSH (22)">
              <input
                type="number"
                min={1}
                max={65535}
                className={INPUT}
                value={form.port}
                onChange={(e) => set("port", e.target.value)}
              />
            </Field>

            <Field label="Username Default" hint="Username login perangkat">
              <input
                className={INPUT}
                placeholder="admin"
                value={form.username}
                onChange={(e) => set("username", e.target.value)}
              />
            </Field>

            <Field label="Tipe Perangkat / OS" hint="Tipe sistem operasi jaringan">
              <select
                className={INPUT}
                value={form.device_type}
                onChange={(e) => set("device_type", e.target.value)}
              >
                {DEVICE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.toUpperCase()}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="SNMP Community (Opsional)" hint="Community string untuk monitoring">
              <input
                className={INPUT}
                placeholder="public"
                value={form.snmp_community}
                onChange={(e) => set("snmp_community", e.target.value)}
              />
            </Field>

            <div className="sm:col-span-2 md:col-span-3">
              <Field label="Catatan / Deskripsi / Lokasi" hint="Informasi penempatan rak, site, atau keterangan fungsi">
                <input
                  className={INPUT}
                  placeholder="mis. Rak 2 POP Jakarta, Router Gateway Utama"
                  value={form.note}
                  onChange={(e) => set("note", e.target.value)}
                />
              </Field>
            </div>
          </div>
        </div>

        {/* Section 2: Kredensial Baru Langsung */}
        <div className="space-y-4 pt-4 border-t border-border/70">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h4 className="text-xs font-bold text-sakura uppercase tracking-wider">
                2. Buat Kredensial Baru (Langsung Terhubung)
              </h4>
              <p className="text-xs text-text-secondary/70">
                Kredensial yang diisi di sini akan otomatis dibuat dan dikaitkan ke perangkat ini.
              </p>
            </div>

            <div className="flex bg-white/5 border border-border rounded-pill p-1 gap-1 shrink-0">
              <button
                type="button"
                onClick={() => setActiveCredTab("password")}
                className={`text-xs px-3 py-1 rounded-pill transition ${
                  activeCredTab === "password"
                    ? "bg-sakura text-surface font-semibold shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                Password
              </button>
              <button
                type="button"
                onClick={() => setActiveCredTab("key")}
                className={`text-xs px-3 py-1 rounded-pill transition ${
                  activeCredTab === "key"
                    ? "bg-sakura text-surface font-semibold shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                SSH Key
              </button>
              <button
                type="button"
                onClick={() => setActiveCredTab("api")}
                className={`text-xs px-3 py-1 rounded-pill transition ${
                  activeCredTab === "api"
                    ? "bg-sakura text-surface font-semibold shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                API Key
              </button>
            </div>
          </div>

          <div className="bg-white/[0.02] border border-border rounded-control p-4">
            {activeCredTab === "password" && (
              <div className="space-y-3">
                <Field
                  label="Password SSH Perangkat"
                  hint={isEdit ? "Isi hanya jika ingin menambahkan credential password baru." : "Password untuk otentikasi SSH."}
                >
                  <input
                    type="password"
                    disabled={form.directNoPassword}
                    placeholder="Masukkan password perangkat..."
                    autoComplete="new-password"
                    className={INPUT}
                    value={form.directPassword}
                    onChange={(e) => set("directPassword", e.target.value)}
                  />
                </Field>

                <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={form.directNoPassword}
                    onChange={(e) => set("directNoPassword", e.target.checked)}
                    className="accent-sakura rounded w-4 h-4"
                  />
                  <span>Tanpa password (login kosong, misal MikroTik default sebelum diset password)</span>
                </label>
              </div>
            )}

            {activeCredTab === "key" && (
              <Field
                label="SSH Private / Public Key"
                hint="Tempelkan isi file private key (OpenSSH / RSA) lengkap termasuk header & footer."
              >
                <textarea
                  rows={4}
                  placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;...&#10;-----END OPENSSH PRIVATE KEY-----"
                  className={`${INPUT} font-mono text-xs`}
                  value={form.directSshKey}
                  onChange={(e) => set("directSshKey", e.target.value)}
                />
              </Field>
            )}

            {activeCredTab === "api" && (
              <Field
                label="API Key / REST Token"
                hint="Token untuk mengakses RouterOS REST API, Winbox API, atau webhook perangkat."
              >
                <input
                  type="password"
                  placeholder="Masukkan API Key / Access Token..."
                  className={INPUT}
                  value={form.directApiKey}
                  onChange={(e) => set("directApiKey", e.target.value)}
                />
              </Field>
            )}
          </div>
        </div>

        {/* Section 3: Kredensial Tersimpan (Shared) */}
        {credentials.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-border/70">
            <div>
              <h4 className="text-xs font-bold text-sakura uppercase tracking-wider">
                3. Tautkan Kredensial Tersimpan (Shared)
              </h4>
              <p className="text-xs text-text-secondary/70">
                Pilih kredensial dari brankas yang ingin digunakan bersama oleh perangkat ini:
              </p>
            </div>

            <div className="flex flex-wrap gap-2 pt-1">
              {credentials.map((c) => {
                const active = form.credential_names.includes(c.name);
                return (
                  <button
                    type="button"
                    key={c.name}
                    onClick={() => toggleExistingCred(c.name)}
                    className={`text-xs px-3.5 py-1.5 rounded-pill border transition flex items-center gap-2 ${
                      active
                        ? "border-sakura bg-sakura/15 text-text-primary shadow-sm ring-1 ring-sakura/30"
                        : "border-border bg-white/[0.03] text-text-secondary hover:text-text-primary hover:border-sakura/40"
                    }`}
                  >
                    <span className="font-bold">{active ? "✓" : "+"}</span>
                    <span className="font-medium">{c.name}</span>
                    <span className="text-[10px] opacity-70">({c.type})</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Status Aktif & Action Buttons */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-6 border-t border-border">
          <label className="flex items-center gap-2.5 text-sm text-text-primary cursor-pointer select-none">
            <input
              type="checkbox"
              className="accent-sakura rounded w-4 h-4"
              checked={form.enabled}
              onChange={(e) => set("enabled", e.target.checked)}
            />
            <span>Status Aktif (dapat diakses tool dan otomasi AIRA)</span>
          </label>

          <div className="flex items-center gap-2.5 ml-auto">
            <button
              type="button"
              onClick={onCancel}
              className={BTN}
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={saving}
              className={BTN_PRIMARY}
            >
              {saving ? "Menyimpan ke SQLite..." : isEdit ? "Simpan Perubahan" : "Simpan Perangkat"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

// ============================================================
// DEDICATED SUB-PAGE: TAMBAH / EDIT KREDENSIAL (Terpisah)
// ============================================================
function CredentialEditPage({ initial, saving, onSubmit, onCancel, onOpenMenu }) {
  const isEdit = Boolean(initial);
  const [form, setForm] = useState({
    name: initial?.name || "",
    type: initial?.type || "ssh_password",
    username: initial?.username || "",
    secret: "",
    noPassword: false,
    note: initial?.note || "",
  });
  const [error, setError] = useState("");

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const isPassword = form.type === "ssh_password";
  const isKey = form.type === "ssh_key";

  function submit(e) {
    e.preventDefault();
    setError("");

    const payload = { username: form.username.trim(), note: form.note.trim() };

    if (form.noPassword && isPassword) payload.secret = "";
    else if (form.secret !== "") payload.secret = form.secret;
    else if (!isEdit) {
      setError(isPassword ? "Isi password, atau centang 'Tanpa password'." : "Secret wajib diisi.");
      return;
    }

    if (isEdit) {
      if (form.name.trim() !== initial.name) payload.new_name = form.name.trim();
    } else {
      payload.name = form.name.trim();
      payload.type = form.type;
    }

    onSubmit(payload);
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto pb-16 animate-fadeIn">
      <TopBar
        title={isEdit ? `Edit Kredensial: ${initial.name}` : "Tambah Kredensial Baru"}
        subtitle="Brankas Kredensial terenkripsi Fernet (SQLite)"
        onMenuClick={onOpenMenu}
      />

      <div className="flex items-center justify-between px-1">
        <button
          type="button"
          onClick={onCancel}
          className="inline-flex items-center gap-2 text-xs font-medium text-text-secondary hover:text-text-primary px-3 py-1.5 rounded-pill bg-white/5 border border-border transition"
        >
          <span>←</span>
          <span>Kembali ke Inventory</span>
        </button>
      </div>

      <form onSubmit={submit} className="bg-surface border border-border rounded-card p-6 space-y-5 shadow-floating">
        <div className="border-b border-border/70 pb-3">
          <h3 className="font-semibold text-text-primary text-base">
            {isEdit ? `Perbarui Kredensial: ${initial.name}` : "Rincian Kredensial Baru"}
          </h3>
          <p className="text-xs text-text-secondary/70 mt-0.5">
            Kredensial disimpan terenkripsi dan dapat ditautkan ke banyak perangkat.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Nama Kredensial *" hint="Unik, mis. pass-mikrotik-pusat">
            <input required className={INPUT} value={form.name} onChange={(e) => set("name", e.target.value)} />
          </Field>

          <Field label="Tipe Kredensial" hint="Jenis otentikasi">
            <select
              className={INPUT}
              value={form.type}
              disabled={isEdit}
              onChange={(e) => set("type", e.target.value)}
            >
              {CRED_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Username (Opsional)" hint="Username bawaan untuk kredensial ini">
            <input className={INPUT} value={form.username} onChange={(e) => set("username", e.target.value)} />
          </Field>

          <Field label="Catatan (Opsional)" hint="Keterangan penggunaan">
            <input className={INPUT} value={form.note} onChange={(e) => set("note", e.target.value)} />
          </Field>
        </div>

        <Field
          label={isKey ? "Private Key" : isPassword ? "Password" : "Secret / Token"}
          hint={
            isEdit
              ? "Kosongkan jika secret tidak diubah. Secret tersimpan terenkripsi dan tidak pernah ditampilkan mentah."
              : "Tersimpan terenkripsi dengan Fernet di SQLite."
          }
        >
          {isKey ? (
            <textarea
              rows={5}
              className={`${INPUT} font-mono text-xs`}
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----..."
              value={form.secret}
              onChange={(e) => set("secret", e.target.value)}
            />
          ) : (
            <input
              type="password"
              autoComplete="new-password"
              className={INPUT}
              disabled={form.noPassword && isPassword}
              value={form.secret}
              onChange={(e) => set("secret", e.target.value)}
            />
          )}
        </Field>

        {isPassword && (
          <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              className="accent-sakura rounded w-4 h-4"
              checked={form.noPassword}
              onChange={(e) => set("noPassword", e.target.checked)}
            />
            Tanpa password (login kosong)
          </label>
        )}

        {error && (
          <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 px-3.5 py-2 rounded-control">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2.5 pt-4 border-t border-border">
          <button type="button" onClick={onCancel} className={BTN}>
            Batal
          </button>
          <button type="submit" disabled={saving} className={BTN_PRIMARY}>
            {saving ? "Menyimpan..." : "Simpan Kredensial"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ============================================================
// HALAMAN UTAMA DEVICES (LIST VIEW BERSIH)
// ============================================================
export default function DevicesPage({ onOpenMenu }) {
  const { notify } = useToast();

  const [devices, setDevices] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deviceForm, setDeviceForm] = useState(null); // null | {device?: ...}
  const [credForm, setCredForm] = useState(null);     // null | {credential?: ...}
  const [tests, setTests] = useState({});
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      const [d, c] = await Promise.all([inventoryApi.devices.list(), inventoryApi.credentials.list()]);
      setDevices(d.devices || []);
      setCredentials(c.credentials || []);
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action, successMessage) {
    setSaving(true);
    try {
      await action();
      if (successMessage) notify({ type: "success", message: successMessage, duration: 2500 });
      await load();
      return true;
    } catch (err) {
      notify({ type: "error", message: err.message });
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function saveDevice(payload) {
    const editing = deviceForm?.device;
    const ok = await run(
      () => (editing ? inventoryApi.devices.update(editing.name, payload) : inventoryApi.devices.create(payload)),
      editing ? "Data perangkat diperbarui." : "Perangkat berhasil ditambahkan ke inventory."
    );
    if (ok) setDeviceForm(null);
  }

  async function saveCredential(payload) {
    const editing = credForm?.credential;
    const ok = await run(
      () => (editing ? inventoryApi.credentials.update(editing.name, payload) : inventoryApi.credentials.create(payload)),
      editing ? "Kredensial diperbarui." : "Kredensial berhasil ditambahkan."
    );
    if (ok) setCredForm(null);
  }

  function removeDevice(device) {
    if (!window.confirm(`Hapus perangkat "${device.name}" dari inventory? Kredensialnya tetap aman di database.`)) return;
    run(() => inventoryApi.devices.remove(device.name), `"${device.name}" dihapus dari inventory.`);
  }

  function removeCredential(credential) {
    const used = credential.used_by.length ? ` Sedang dipakai oleh: ${credential.used_by.join(", ")}.` : "";
    if (!window.confirm(`Hapus kredensial "${credential.name}"?${used}`)) return;
    run(() => inventoryApi.credentials.remove(credential.name), `Kredensial "${credential.name}" dihapus.`);
  }

  async function testDevice(device) {
    setTests((t) => ({ ...t, [device.name]: { state: "running", text: "Menghubungkan via SSH..." } }));
    try {
      const res = await inventoryApi.devices.test(device.name);
      setTests((t) => ({
        ...t,
        [device.name]: {
          state: res.success ? "ok" : "fail",
          text: res.success ? `Tersambung: ${res.output || "Identitas OK"}` : res.error || "Gagal terkoneksi.",
        },
      }));
    } catch (err) {
      setTests((t) => ({ ...t, [device.name]: { state: "fail", text: err.message } }));
    }
  }

  const filteredDevices = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return devices;
    return devices.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        d.host.toLowerCase().includes(q) ||
        (d.device_type && d.device_type.toLowerCase().includes(q)) ||
        (d.note && d.note.toLowerCase().includes(q))
    );
  }, [devices, search]);

  // JIKA SEDANG MEMBUKA FORM EDIT / TAMBAH PERANGKAT:
  // Render sebagai halaman terpisah (dedicated page), tidak menyatu di atas list!
  if (deviceForm !== null) {
    return (
      <DeviceEditPage
        initial={deviceForm.device}
        credentials={credentials}
        saving={saving}
        onSubmit={saveDevice}
        onCancel={() => setDeviceForm(null)}
        onOpenMenu={onOpenMenu}
      />
    );
  }

  // JIKA SEDANG MEMBUKA FORM EDIT / TAMBAH KREDENSIAL:
  // Render sebagai halaman terpisah (dedicated page)
  if (credForm !== null) {
    return (
      <CredentialEditPage
        initial={credForm.credential}
        saving={saving}
        onSubmit={saveCredential}
        onCancel={() => setCredForm(null)}
        onOpenMenu={onOpenMenu}
      />
    );
  }

  // HALAMAN DAFTAR PERANGKAT UTAMA (BERSIH & LAPANG)
  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      <TopBar
        title="Inventory Perangkat"
        subtitle="Kelola perangkat jaringan & kredensial terenkripsi (SQLite)"
        onMenuClick={onOpenMenu}
      />

      {/* ------------------------------------------------ SECTION PERANGKAT */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-1">
          <div>
            <h3 className="font-semibold text-text-primary text-lg">Daftar Perangkat Jaringan</h3>
            <p className="text-xs text-text-secondary">
              Total {devices.length} perangkat terdaftar di sistem AIRA
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Cari perangkat / IP..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-white/5 border border-border rounded-pill px-3.5 py-1.5 text-xs text-text-primary outline-none focus:border-sakura/50 w-48 sm:w-60 transition"
            />
            <button className={BTN_PRIMARY} onClick={() => setDeviceForm({})}>
              <span>+</span>
              <span>Tambah Perangkat</span>
            </button>
          </div>
        </div>

        {loading && <p className="text-text-secondary text-sm px-1 animate-pulse">Memuat data inventory...</p>}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredDevices.map((d) => {
            const unlinked = credentials.filter((c) => !d.credentials.some((x) => x.name === c.name));
            const test = tests[d.name];

            return (
              <div
                key={d.name}
                className={`bg-surface border border-border rounded-card p-5 space-y-3.5 transition shadow-card hover:border-sakura/40 ${
                  d.enabled ? "" : "opacity-60"
                }`}
              >
                <div className="flex items-start justify-between gap-2 border-b border-border/50 pb-2.5">
                  <div>
                    <h4 className="font-semibold text-text-primary text-base truncate" title={d.name}>
                      {d.name}
                    </h4>
                    <span className="text-xs font-mono text-sakura">
                      {d.host}:{d.port}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2.5 py-0.5 rounded-pill bg-sakura/10 text-sakura border border-sakura/20">
                      {d.device_type}
                    </span>
                    {!d.enabled && (
                      <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-pill bg-white/10 text-text-secondary">
                        Nonaktif
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
                  <div>
                    <span className="block text-[11px] opacity-60">Username</span>
                    <span className="text-text-primary font-medium">{d.username || "admin"}</span>
                  </div>
                  <div>
                    <span className="block text-[11px] opacity-60">SNMP Port</span>
                    <span className="text-text-primary font-medium">{d.snmp_port || 161}</span>
                  </div>
                  {d.note && (
                    <div className="col-span-2">
                      <span className="block text-[11px] opacity-60">Catatan</span>
                      <span className="text-text-primary italic truncate block">{d.note}</span>
                    </div>
                  )}
                </div>

                {/* Kredensial Terhubung */}
                <div className="pt-2 border-t border-border/40 space-y-1.5">
                  <span className="text-[11px] font-medium text-text-secondary flex items-center gap-1">
                    🔐 Kredensial Terhubung ({d.credentials.length}):
                  </span>
                  <div className="flex flex-wrap gap-1.5 items-center">
                    {d.credentials.length === 0 && (
                      <span className="text-[11px] text-amber-300/90 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-pill">
                        ⚠ Belum ada kredensial SSH / API
                      </span>
                    )}
                    {d.credentials.map((c) => (
                      <span
                        key={c.name}
                        className={`text-[11px] px-2.5 py-1 rounded-pill border flex items-center gap-1.5 ${getCredBadgeClass(
                          c.type
                        )}`}
                      >
                        <span>🔒</span>
                        <span className="font-medium">{c.name}</span>
                        <span className="text-[9px] opacity-75">({c.type})</span>
                        <button
                          title="Putuskan kredensial dari perangkat ini"
                          className="hover:text-red-400 ml-0.5 text-xs font-bold"
                          onClick={() => run(() => inventoryApi.devices.unlink(d.name, c.name), "Kredensial dilepas.")}
                        >
                          ✕
                        </button>
                      </span>
                    ))}

                    {unlinked.length > 0 && (
                      <select
                        className="text-[11px] bg-white/5 border border-border rounded-pill px-2.5 py-1 text-text-secondary hover:text-text-primary outline-none cursor-pointer transition"
                        value=""
                        onChange={(e) =>
                          e.target.value &&
                          run(() => inventoryApi.devices.link(d.name, e.target.value), "Kredensial dikaitkan.")
                        }
                      >
                        <option value="">+ Hubungkan Kredensial</option>
                        {unlinked.map((c) => (
                          <option key={c.name} value={c.name}>
                            {c.name} ({c.type})
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {/* Status Tes SSH */}
                {test && (
                  <div
                    className={`text-xs p-2.5 rounded-control break-words font-mono ${
                      test.state === "ok"
                        ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                        : test.state === "fail"
                        ? "bg-red-500/10 text-red-300 border border-red-500/20"
                        : "bg-white/5 text-text-secondary border border-border animate-pulse"
                    }`}
                  >
                    {test.text}
                  </div>
                )}

                {/* Tombol Aksi */}
                <div className="flex items-center justify-between pt-2 border-t border-border/40">
                  <button
                    className={`${BTN} text-sakura border border-sakura/20 hover:bg-sakura/10`}
                    disabled={test?.state === "running"}
                    onClick={() => testDevice(d)}
                  >
                    {test?.state === "running" ? "Menguji..." : "⚡ Tes SSH"}
                  </button>
                  <div className="flex gap-1.5">
                    <button
                      className={`${BTN} hover:border-sakura/40 text-text-primary`}
                      onClick={() => setDeviceForm({ device: d })}
                    >
                      ✏️ Edit
                    </button>
                    <button className={BTN_DANGER} onClick={() => removeDevice(d)}>
                      Hapus
                    </button>
                  </div>
                </div>
              </div>
            );
          })}

          {!loading && filteredDevices.length === 0 && (
            <div className="col-span-full py-10 text-center bg-surface border border-dashed border-border rounded-card">
              <p className="text-text-secondary text-sm">
                {search ? "Tidak ada perangkat yang cocok dengan pencarian." : "Belum ada perangkat terdaftar."}
              </p>
              <p className="text-xs text-text-secondary/60 mt-1">
                Klik "+ Tambah Perangkat" di atas atau ketik prompt ke AIRA di chat:
                <br />
                <span className="font-mono text-sakura mt-1 inline-block">
                  "Tambahkan router MikroTik IP 192.168.88.1 bernama Core-R1 password admin123"
                </span>
              </p>
            </div>
          )}
        </div>
      </section>

      {/* ------------------------------------------------ SECTION KREDENSIAL */}
      <section className="space-y-4 pt-6 border-t border-border">
        <div className="flex items-center justify-between px-1">
          <div>
            <h3 className="font-semibold text-text-primary text-lg">Brankas Kredensial (Credentials Vault)</h3>
            <p className="text-xs text-text-secondary">
              Kredensial mandiri yang dapat digunakan bersama (*shared credentials*) untuk multi-perangkat
            </p>
          </div>
          <button className={BTN_PRIMARY} onClick={() => setCredForm({})}>
            <span>+</span>
            <span>Tambah Kredensial</span>
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {credentials.map((c) => (
            <div
              key={c.name}
              className="bg-surface border border-border rounded-card p-4 space-y-2.5 shadow-card hover:border-sakura/30 transition"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="truncate">
                  <h5 className="font-semibold text-text-primary text-sm truncate" title={c.name}>
                    {c.name}
                  </h5>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-pill border uppercase font-medium inline-block mt-0.5 ${getCredBadgeClass(
                      c.type
                    )}`}
                  >
                    {c.type}
                  </span>
                </div>
                <span className="text-xs text-emerald-400 font-mono" title="Terenkripsi Fernet">
                  🔒 {c.has_secret ? "Tersimpan" : "Kosong"}
                </span>
              </div>

              <div className="text-xs text-text-secondary space-y-0.5">
                {c.username && <p>User: <span className="text-text-primary">{c.username}</span></p>}
                <p className="truncate" title={c.used_by.join(", ")}>
                  Dipakai: {c.used_by.length ? <span className="text-sakura">{c.used_by.join(", ")}</span> : <span className="opacity-50">Belum ditautkan</span>}
                </p>
              </div>

              <div className="flex justify-end gap-1.5 pt-2 border-t border-border/40">
                <button
                  className={`${BTN} hover:border-sakura/40 text-text-primary`}
                  onClick={() => setCredForm({ credential: c })}
                >
                  ✏️ Edit
                </button>
                <button className={BTN_DANGER} onClick={() => removeCredential(c)}>
                  Hapus
                </button>
              </div>
            </div>
          ))}

          {!loading && credentials.length === 0 && (
            <p className="text-text-secondary text-xs px-1 col-span-full">
              Belum ada kredensial mandiri yang dibuat.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
