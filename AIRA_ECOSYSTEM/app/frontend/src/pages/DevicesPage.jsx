import { useCallback, useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";
import { inventoryApi } from "../inventoryApi.js";

const INPUT =
  "w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-accent";
const BTN =
  "text-xs px-3 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white hover:bg-white/10 transition disabled:opacity-40";
const BTN_PRIMARY =
  "bg-accent-gradient text-white text-sm font-semibold px-4 py-2 rounded-lg disabled:opacity-50";
const BTN_DANGER =
  "text-xs px-3 py-1.5 rounded-lg bg-red-500/10 text-red-300 hover:bg-red-500/20 border border-red-500/20";

const CRED_TYPES = [
  { value: "ssh_password", label: "SSH Password" },
  { value: "ssh_key", label: "SSH Key (private key)" },
  { value: "api_key", label: "API Key" },
  { value: "snmp_community", label: "SNMP Community" },
  { value: "token", label: "Token" },
  { value: "other", label: "Lainnya" },
];

const DEVICE_TYPES = ["mikrotik", "linux", "switch", "olt", "server", "other"];

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="text-xs text-white/50 block mb-1">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-white/30 mt-1">{hint}</p>}
    </div>
  );
}

// ------------------------------------------------------------ form device

function DeviceForm({ initial, credentials, saving, onSubmit, onCancel }) {
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
  });

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  function toggleCredential(name) {
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
      note: form.note,
      enabled: form.enabled,
      credential_names: form.credential_names,
    };

    if (form.snmp_community.trim()) payload.snmp_community = form.snmp_community.trim();

    if (isEdit) {
      if (form.name.trim() !== initial.name) payload.new_name = form.name.trim();
    } else {
      payload.name = form.name.trim();
    }

    onSubmit(payload);
  }

  return (
    <form onSubmit={submit} className="bg-card border border-accent/30 rounded-xl2 p-5 space-y-4">
      <h3 className="font-semibold text-white">{isEdit ? `Edit ${initial.name}` : "Tambah Device"}</h3>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Nama *" hint="Tanpa spasi, mis. R_tes">
          <input required className={INPUT} value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Host / IP *">
          <input required className={INPUT} value={form.host} onChange={(e) => set("host", e.target.value)} />
        </Field>
        <Field label="Port SSH">
          <input type="number" className={INPUT} value={form.port} onChange={(e) => set("port", e.target.value)} />
        </Field>
        <Field label="Username">
          <input className={INPUT} value={form.username} onChange={(e) => set("username", e.target.value)} />
        </Field>
        <Field label="Tipe">
          <select className={INPUT} value={form.device_type} onChange={(e) => set("device_type", e.target.value)}>
            {DEVICE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </Field>
        <Field label="SNMP community" hint={isEdit ? "Kosongkan = tidak diubah" : "Opsional"}>
          <input className={INPUT} value={form.snmp_community} onChange={(e) => set("snmp_community", e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Catatan">
            <input className={INPUT} value={form.note} onChange={(e) => set("note", e.target.value)} />
          </Field>
        </div>
      </div>

      <Field label="Credential yang dikaitkan">
        {credentials.length === 0 ? (
          <p className="text-xs text-white/40">Belum ada credential. Buat dulu di bagian Credentials di bawah.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {credentials.map((c) => (
              <label
                key={c.name}
                className={`text-xs px-3 py-1.5 rounded-full border cursor-pointer transition ${
                  form.credential_names.includes(c.name)
                    ? "border-accent bg-accent/10 text-accent-light"
                    : "border-border text-white/50 hover:text-white"
                }`}
              >
                <input
                  type="checkbox"
                  className="hidden"
                  checked={form.credential_names.includes(c.name)}
                  onChange={() => toggleCredential(c.name)}
                />
                {c.name} · {c.type}
              </label>
            ))}
          </div>
        )}
      </Field>

      <label className="flex items-center gap-2 text-sm text-white/70">
        <input type="checkbox" className="accent-accent" checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} />
        Aktif
      </label>

      <div className="flex gap-2">
        <button type="submit" disabled={saving} className={BTN_PRIMARY}>
          {saving ? "Menyimpan..." : "Simpan"}
        </button>
        <button type="button" onClick={onCancel} className={BTN}>Batal</button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------ form credential

function CredentialForm({ initial, saving, onSubmit, onCancel }) {
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

    const payload = { username: form.username.trim(), note: form.note };

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
    <form onSubmit={submit} className="bg-card border border-accent/30 rounded-xl2 p-5 space-y-4">
      <h3 className="font-semibold text-white">{isEdit ? `Edit ${initial.name}` : "Tambah Credential"}</h3>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Nama *">
          <input required className={INPUT} value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Tipe">
          <select className={INPUT} value={form.type} disabled={isEdit} onChange={(e) => set("type", e.target.value)}>
            {CRED_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Username (opsional)">
          <input className={INPUT} value={form.username} onChange={(e) => set("username", e.target.value)} />
        </Field>
        <Field label="Catatan">
          <input className={INPUT} value={form.note} onChange={(e) => set("note", e.target.value)} />
        </Field>
      </div>

      <Field
        label={isKey ? "Private key" : isPassword ? "Password" : "Secret"}
        hint={isEdit ? "Kosongkan = secret tidak diubah. Secret tersimpan terenkripsi dan tidak pernah ditampilkan." : "Disimpan terenkripsi."}
      >
        {isKey ? (
          <textarea
            rows={5}
            className={`${INPUT} font-mono text-xs`}
            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
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
        <label className="flex items-center gap-2 text-sm text-white/70">
          <input type="checkbox" className="accent-accent" checked={form.noPassword} onChange={(e) => set("noPassword", e.target.checked)} />
          Tanpa password (login kosong, mis. MikroTik default)
        </label>
      )}

      {error && <p className="text-xs text-red-300">{error}</p>}

      <div className="flex gap-2">
        <button type="submit" disabled={saving} className={BTN_PRIMARY}>
          {saving ? "Menyimpan..." : "Simpan"}
        </button>
        <button type="button" onClick={onCancel} className={BTN}>Batal</button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------ halaman

export default function DevicesPage({ onOpenMenu }) {
  const { notify } = useToast();

  const [devices, setDevices] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deviceForm, setDeviceForm] = useState(null); // null | {device?}
  const [credForm, setCredForm] = useState(null);     // null | {credential?}
  const [tests, setTests] = useState({});             // nama -> {state, text}

  const load = useCallback(async () => {
    try {
      const [d, c] = await Promise.all([inventoryApi.devices.list(), inventoryApi.credentials.list()]);
      setDevices(d.devices);
      setCredentials(c.credentials);
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
      editing ? "Device diperbarui." : "Device ditambahkan."
    );
    if (ok) setDeviceForm(null);
  }

  async function saveCredential(payload) {
    const editing = credForm?.credential;
    const ok = await run(
      () => (editing ? inventoryApi.credentials.update(editing.name, payload) : inventoryApi.credentials.create(payload)),
      editing ? "Credential diperbarui." : "Credential ditambahkan."
    );
    if (ok) setCredForm(null);
  }

  function removeDevice(device) {
    if (!window.confirm(`Hapus device "${device.name}"? Credential-nya tetap tersimpan.`)) return;
    run(() => inventoryApi.devices.remove(device.name), `"${device.name}" dihapus.`);
  }

  function removeCredential(credential) {
    const used = credential.used_by.length ? ` Dipakai oleh: ${credential.used_by.join(", ")}.` : "";
    if (!window.confirm(`Hapus credential "${credential.name}"?${used}`)) return;
    run(() => inventoryApi.credentials.remove(credential.name), `"${credential.name}" dihapus.`);
  }

  async function testDevice(device) {
    setTests((t) => ({ ...t, [device.name]: { state: "running", text: "Mengetes SSH..." } }));

    try {
      const res = await inventoryApi.devices.test(device.name);
      setTests((t) => ({
        ...t,
        [device.name]: {
          state: res.success ? "ok" : "fail",
          text: res.success ? `Berhasil: ${res.output || "(tanpa output)"}` : res.error || "Gagal.",
        },
      }));
    } catch (err) {
      setTests((t) => ({ ...t, [device.name]: { state: "fail", text: err.message } }));
    }
  }

  return (
    <div className="space-y-6">
      <TopBar
        title="Devices"
        subtitle="Inventory perangkat & credential (database SQLite)"
        onMenuClick={onOpenMenu}
      />

      {/* ------------------------------------------------ DEVICES */}
      <section className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h3 className="font-semibold text-white">Perangkat</h3>
          <button className={BTN_PRIMARY} onClick={() => setDeviceForm({})}>+ Tambah Device</button>
        </div>

        {deviceForm && (
          <DeviceForm
            key={deviceForm.device?.name || "new"}
            initial={deviceForm.device}
            credentials={credentials}
            saving={saving}
            onSubmit={saveDevice}
            onCancel={() => setDeviceForm(null)}
          />
        )}

        {loading && <p className="text-white/40 text-sm">Memuat...</p>}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {devices.map((d) => {
            const unlinked = credentials.filter((c) => !d.credentials.some((x) => x.name === c.name));
            const test = tests[d.name];

            return (
              <div key={d.name} className={`bg-card border border-border rounded-xl2 p-5 ${d.enabled ? "" : "opacity-60"}`}>
                <div className="flex items-center justify-between mb-3 gap-2">
                  <h3 className="font-semibold text-white truncate">{d.name}</h3>
                  <span className="text-[10px] uppercase tracking-wide bg-accent/10 text-accent-light px-2 py-1 rounded-full shrink-0">
                    {d.device_type}{d.enabled ? "" : " · nonaktif"}
                  </span>
                </div>

                <dl className="text-sm space-y-1 text-white/60">
                  <div className="flex justify-between"><dt>Host</dt><dd className="text-white/90 font-mono">{d.host}:{d.port}</dd></div>
                  <div className="flex justify-between"><dt>Username</dt><dd className="text-white/90">{d.username || "-"}</dd></div>
                  {d.note && <div className="flex justify-between gap-3"><dt>Catatan</dt><dd className="text-white/70 text-right truncate">{d.note}</dd></div>}
                </dl>

                <div className="mt-3 flex flex-wrap gap-1.5 items-center">
                  {d.credentials.length === 0 && (
                    <span className="text-[11px] text-amber-300/80">⚠ belum ada credential SSH</span>
                  )}
                  {d.credentials.map((c) => (
                    <span key={c.name} className="text-[11px] px-2 py-1 rounded-full bg-white/5 border border-border text-white/70 flex items-center gap-1.5">
                      {c.name} · {c.type}
                      <button
                        title="Lepas credential"
                        className="text-white/30 hover:text-red-300"
                        onClick={() => run(() => inventoryApi.devices.unlink(d.name, c.name), "Credential dilepas.")}
                      >
                        ✕
                      </button>
                    </span>
                  ))}

                  {unlinked.length > 0 && (
                    <select
                      className="text-[11px] bg-white/5 border border-border rounded-full px-2 py-1 text-white/60 outline-none"
                      value=""
                      onChange={(e) => e.target.value && run(() => inventoryApi.devices.link(d.name, e.target.value), "Credential dikaitkan.")}
                    >
                      <option value="">+ kaitkan credential</option>
                      {unlinked.map((c) => (
                        <option key={c.name} value={c.name}>{c.name} ({c.type})</option>
                      ))}
                    </select>
                  )}
                </div>

                {test && (
                  <p className={`mt-3 text-xs break-words ${
                    test.state === "ok" ? "text-emerald-300" : test.state === "fail" ? "text-red-300" : "text-white/50"
                  }`}>
                    {test.text}
                  </p>
                )}

                <div className="mt-4 flex flex-wrap gap-2">
                  <button className={BTN} disabled={test?.state === "running"} onClick={() => testDevice(d)}>Tes SSH</button>
                  <button className={BTN} onClick={() => setDeviceForm({ device: d })}>Edit</button>
                  <button className={BTN_DANGER} onClick={() => removeDevice(d)}>Hapus</button>
                </div>
              </div>
            );
          })}

          {!loading && devices.length === 0 && (
            <p className="text-white/40 text-sm">Belum ada device. Klik "+ Tambah Device" atau minta AIRA lewat chat.</p>
          )}
        </div>
      </section>

      {/* ------------------------------------------------ CREDENTIALS */}
      <section className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h3 className="font-semibold text-white">Credentials</h3>
          <button className={BTN_PRIMARY} onClick={() => setCredForm({})}>+ Tambah Credential</button>
        </div>

        {credForm && (
          <CredentialForm
            key={credForm.credential?.name || "new"}
            initial={credForm.credential}
            saving={saving}
            onSubmit={saveCredential}
            onCancel={() => setCredForm(null)}
          />
        )}

        <div className="space-y-2">
          {credentials.map((c) => (
            <div key={c.name} className="flex items-center justify-between gap-3 bg-card border border-border rounded-xl2 px-4 py-3">
              <div className="min-w-0">
                <div className="text-sm text-white truncate">
                  {c.name} <span className="text-[10px] uppercase text-accent-light ml-1">{c.type}</span>
                </div>
                <div className="text-xs text-white/40 truncate">
                  {c.username ? `user: ${c.username} · ` : ""}
                  secret: {c.has_secret ? "••••••••" : "kosong"} ·{" "}
                  {c.used_by.length ? `dipakai: ${c.used_by.join(", ")}` : "belum dikaitkan"}
                </div>
              </div>
              <div className="flex gap-2 shrink-0">
                <button className={BTN} onClick={() => setCredForm({ credential: c })}>Edit</button>
                <button className={BTN_DANGER} onClick={() => removeCredential(c)}>Hapus</button>
              </div>
            </div>
          ))}

          {!loading && credentials.length === 0 && (
            <p className="text-white/40 text-sm">Belum ada credential.</p>
          )}
        </div>
      </section>
    </div>
  );
}