import { useState } from "react";
import TopBar from "../components/TopBar.jsx";
import Renderer from "../components/dio/Renderer.jsx";

// Contoh schema LOKAL untuk pengembangan - tidak memanggil backend
// sama sekali, sesuai spec ("Jangan memakai backend").
const EXAMPLES = {
  form: {
    title: "Tambah Perangkat Baru",
    description: "Isi detail perangkat yang ingin ditambahkan ke inventory.",
    sections: [
      {
        id: "basic",
        title: "Informasi Dasar",
        columns: 2,
        fields: [
          { id: "name", type: "text", label: "Nama Perangkat", placeholder: "mis. R1", required: true },
          { id: "host", type: "text", label: "Host / IP", placeholder: "192.168.1.1", required: true },
          { id: "port", type: "number", label: "Port", default: 22, min: 1, max: 65535 },
          { id: "username", type: "text", label: "Username", default: "admin", required: true },
          { id: "password", type: "password", label: "Password", span: "full" },
          {
            id: "note",
            type: "info",
            variant: "info",
            text: "Password opsional - kalau dikosongkan, sistem memakai SSH_PASSWORD dari .env.",
            span: "full",
          },
        ],
      },
    ],
    actions: [
      { id: "cancel", label: "Batal", style: "ghost" },
      { id: "submit", label: "Simpan Perangkat", style: "primary" },
    ],
  },

  choice: {
    title: "Pilih Mode Koneksi",
    description: "AIRA butuh tahu bagaimana kamu ingin menyambungkan perangkat ini.",
    sections: [
      {
        id: "mode",
        fields: [
          {
            id: "connection_mode",
            type: "radio",
            label: "Mode Koneksi",
            required: true,
            options: [
              { value: "ssh", label: "SSH (disarankan)" },
              { value: "snmp", label: "SNMP" },
              { value: "api", label: "RouterOS API" },
            ],
          },
        ],
      },
    ],
    actions: [{ id: "next", label: "Lanjut", style: "primary" }],
  },

  media: {
    title: "Contoh Field Media",
    sections: [{
      id: "media",
      fields: [
        { id: "img1", type: "image", label: "Foto perangkat", src: "https://picsum.photos/seed/router/480/300", caption: "MikroTik hAP ax3" },
        { id: "gal1", type: "gallery", label: "Galeri", images: [
          { url: "https://picsum.photos/seed/a/200/150", caption: "Sudut 1" },
          { url: "https://picsum.photos/seed/b/200/150", caption: "Sudut 2" },
          { url: "https://picsum.photos/seed/c/200/150", caption: "Sudut 3" },
        ]},
        { id: "prog1", type: "progress", label: "Backup konfigurasi", value: 62, helper_text: "Sedang mengunggah..." },
      ],
    }],
    actions: [{ id: "done", label: "Tutup", style: "secondary" }],
  },

  mixed: {
    title: "Konfigurasi Monitoring",
    sections: [
      {
        id: "general",
        title: "Umum",
        columns: 2,
        fields: [
          {
            id: "device",
            type: "select",
            label: "Perangkat",
            required: true,
            options: [
              { value: "r1", label: "R1" },
              { value: "r2", label: "R2" },
            ],
          },
          { id: "interval", type: "slider", label: "Interval Polling (detik)", min: 5, max: 300, step: 5, default: 30 },
          { id: "notify_email", type: "switch", label: "Kirim notifikasi email" },
          {
            id: "notify_channel",
            type: "checkbox",
            label: "Kirim ke channel",
            options: [
              { value: "chat", label: "Chat" },
              { value: "sms", label: "SMS" },
            ],
          },
          { id: "start_date", type: "date", label: "Mulai tanggal" },
          { id: "start_time", type: "time", label: "Jam mulai" },
        ],
      },
      { id: "divider1", fields: [{ id: "d1", type: "divider", label: "Lanjutan" }] },
      {
        id: "advanced",
        fields: [{ id: "config_file", type: "file", label: "Upload konfigurasi (opsional)" }],
      },
    ],
    actions: [
      { id: "cancel", label: "Batal", style: "ghost" },
      { id: "save", label: "Simpan", style: "primary" },
    ],
  },

  wizard: {
    title: "Langkah 2 dari 3 — Kredensial",
    description: "Masukkan kredensial akses untuk perangkat ini.",
    sections: [
      {
        id: "creds",
        columns: 2,
        fields: [
          { id: "username", type: "text", label: "Username", required: true },
          { id: "password", type: "password", label: "Password", required: true },
        ],
      },
    ],
    actions: [
      { id: "back", label: "Kembali", style: "ghost" },
      { id: "next", label: "Lanjut", style: "primary" },
    ],
  },

  approval: {
    title: "Konfirmasi Tindakan",
    sections: [
      {
        id: "warn",
        fields: [
          {
            id: "warning",
            type: "info",
            variant: "warning",
            text: "Tindakan ini akan menghapus 3 rule firewall di R1. Tindakan tidak bisa dibatalkan.",
          },
        ],
      },
    ],
    actions: [
      { id: "cancel", label: "Batal", style: "ghost" },
      { id: "confirm", label: "Ya, Hapus", style: "danger" },
    ],
  },

  review: {
    title: "Review Perangkat Terdaftar",
    sections: [
      {
        id: "table",
        fields: [
          {
            id: "devices",
            type: "table",
            label: "Daftar Perangkat",
            selectable: true,
            columns: [
              { key: "name", label: "Nama", editable: false },
              { key: "host", label: "Host", editable: false },
              { key: "note", label: "Catatan", editable: true },
            ],
            rows: [
              { name: "R1", host: "192.168.43.159", note: "" },
              { name: "R2", host: "192.168.1.1", note: "" },
            ],
          },
        ],
      },
    ],
    actions: [{ id: "done", label: "Selesai", style: "primary" }],
  },
};

export default function DioPreviewPage({ onOpenMenu }) {
  const [activeKey, setActiveKey] = useState("form");
  const [lastResult, setLastResult] = useState(null);

  const schema = EXAMPLES[activeKey];

  function handleSubmitAction(actionId, values) {
    setLastResult({ actionId, values, at: new Date().toLocaleTimeString("id-ID") });
  }

  return (
    <div className="space-y-4">
      <TopBar
        title="DIO Preview"
        subtitle="Halaman khusus developer - preview Universal Interaction Renderer"
        onMenuClick={onOpenMenu}
      />

      <div className="flex flex-wrap gap-2">
        {Object.keys(EXAMPLES).map((key) => (
          <button
            key={key}
            onClick={() => setActiveKey(key)}
            className={`text-xs px-3 py-1.5 rounded-full border transition capitalize ${
              activeKey === key
                ? "bg-[#2563EB] border-transparent text-white"
                : "border-white/10 text-white/50 hover:text-white"
            }`}
          >
            {key}
          </button>
        ))}
      </div>

      <div className="bg-[#020617] border border-white/10 rounded-2xl p-4 sm:p-6 flex justify-center">
        <Renderer schema={schema} onSubmitAction={handleSubmitAction} />
      </div>

      {lastResult && (
        <div>
          <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wide mb-2">
            Hasil submit terakhir ({lastResult.at})
          </h4>
          <pre className="text-xs bg-black/40 border border-white/10 rounded-2xl p-3 overflow-x-auto text-[#F9A8D4]">
{JSON.stringify({ action_id: lastResult.actionId, values: lastResult.values }, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}