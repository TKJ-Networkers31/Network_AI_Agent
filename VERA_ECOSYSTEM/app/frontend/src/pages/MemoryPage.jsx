import { useModalDialog } from "../context/ModalDialogContext.jsx";
// src/pages/MemoryPage.jsx
//
// AIRA OS — User Memory & Personal Knowledge Base (Workstream F).
// Authoritative single source of truth: UserMemoryService (`user_memories` table).
// Provides strict per-user logical isolation, category filtering, search, importance scoring,
// and real-time synchronization with Settings and Ask AIRA (DIO Context).

import React, { useCallback, useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import {
  Brain,
  CheckCircle2,
  Filter,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Tag,
  Trash2,
  X,
} from "lucide-react";

const CATEGORIES = [
  { id: "all", label: "Semua Kategori" },
  { id: "technical", label: "Technical" },
  { id: "project", label: "Project" },
  { id: "workflows", label: "Workflows" },
  { id: "learning", label: "Learning" },
  { id: "communication", label: "Communication" },
  { id: "general", label: "General" },
];

export default function MemoryPage({ onOpenMenu }) {
  const { alert: modalAlert, confirm: modalConfirm, prompt: modalPrompt } = useModalDialog();

  const { notify } = useToast();
  const { user } = useAuth();

  const [memories, setMemories] = useState([]);
  const [summary, setSummary] = useState(null);
  const [preferences, setPreferences] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");

  // Modal create memory state
  const [showAddModal, setShowAddModal] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newCategory, setNewCategory] = useState("technical");
  const [newImportance, setNewImportance] = useState(70);
  const [saving, setSaving] = useState(false);

  const fetchMemoryData = useCallback(async () => {
    setLoading(true);
    try {
      const [prefRes, memRes, sumRes] = await Promise.all([
        api.personalization.getPreferences().catch(() => ({ success: false })),
        api.personalization.getMemories({
          category: selectedCategory === "all" ? null : selectedCategory,
          query: searchQuery.trim() || null,
        }).catch(() => ({ success: false, memories: [] })),
        api.personalization.getMemorySummary().catch(() => ({ success: false, summary: null })),
      ]);

      if (prefRes.success && prefRes.preferences) {
        setPreferences(prefRes.preferences);
      }
      if (memRes.success) {
        setMemories(memRes.memories || []);
      }
      if (sumRes.success && sumRes.summary) {
        setSummary(sumRes.summary);
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal memuat memori: ${err.message}` });
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, searchQuery, notify]);

  useEffect(() => {
    fetchMemoryData();
  }, [fetchMemoryData]);

  const handleToggleMemory = async () => {
    if (!preferences) return;
    const nextState = !preferences.memory_enabled;
    try {
      const res = await api.personalization.updatePreferences({ memory_enabled: nextState });
      if (res.success) {
        setPreferences((prev) => ({ ...prev, memory_enabled: nextState }));
        notify({
          type: "success",
          message: nextState ? "Memori jangka-panjang diaktifkan." : "Memori dinonaktifkan.",
          duration: 2500,
        });
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal mengubah pengaturan: ${err.message}` });
    }
  };

  const handleAddMemory = async (e) => {
    e.preventDefault();
    if (!newContent.trim()) {
      notify({ type: "error", message: "Konten memori tidak boleh kosong." });
      return;
    }

    setSaving(true);
    try {
      const res = await api.personalization.addMemory({
        content: newContent.trim(),
        category: newCategory,
        importance: parseFloat(newImportance) / 100.0,
      });

      if (res.success) {
        notify({ type: "success", message: "Memori baru berhasil disimpan.", duration: 2500 });
        setNewContent("");
        setNewImportance(70);
        setShowAddModal(false);
        fetchMemoryData();
      } else {
        notify({ type: "error", message: res.error || "Gagal menyimpan memori." });
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal menyimpan: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteMemory = async (memoryId) => {
    try {
      const res = await api.personalization.deleteMemory(memoryId);
      if (res.success) {
        notify({ type: "success", message: "Memori berhasil dihapus.", duration: 2000 });
        setMemories((prev) => prev.filter((m) => m.memory_id !== memoryId));
        if (summary) {
          setSummary((prev) => ({
            ...prev,
            total_memories: Math.max(0, (prev.total_memories || 1) - 1),
          }));
        }
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal menghapus: ${err.message}` });
    }
  };

  const handleClearAll = async () => {
    if (!await modalConfirm({ message: "Yakin ingin menghapus seluruh memori Anda? Tindakan ini tidak dapat dibatalkan.", isDestructive: true })) {
      return;
    }
    try {
      const res = await api.personalization.clearMemories();
      if (res.success) {
        notify({ type: "success", message: "Seluruh memori Anda telah dihapus.", duration: 2500 });
        setMemories([]);
        if (summary) {
          setSummary((prev) => ({ ...prev, total_memories: 0 }));
        }
      }
    } catch (err) {
      notify({ type: "error", message: `Gagal menghapus memori: ${err.message}` });
    }
  };

  return (
    <div className="space-y-6 pb-12">
      <TopBar
        title="Personal Memory"
        subtitle="Memori terisolasi per user yang dipelajari VERA untuk mendukung keputusan operasional Anda"
        onMenuClick={onOpenMenu}
      />

      {/* Control Card */}
      <div className="bg-card border border-border rounded-xl2 p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center text-accent">
            <Brain className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-white">Status Memori VERA</h2>
              <span
                className={`px-2 py-0.5 rounded-full text-[11px] font-medium border ${
                  preferences?.memory_enabled
                    ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                    : "bg-white/5 border-white/10 text-white/50"
                }`}
              >
                {preferences?.memory_enabled ? "Aktif (Auto-Context)" : "Dinonaktifkan"}
              </span>
            </div>
            <p className="text-xs text-white/50 mt-0.5">
              Total {summary?.total_memories || memories.length} butir memori tersimpan untuk akun{" "}
              <span className="text-white/80 font-mono">{user?.username || "Anda"}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-stretch md:self-auto">
          <button
            onClick={handleToggleMemory}
            className="flex-1 md:flex-none text-xs px-3 py-2 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white transition-colors"
          >
            {preferences?.memory_enabled ? "Nonaktifkan Memori" : "Aktifkan Memori"}
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex-1 md:flex-none flex items-center justify-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-lg bg-accent text-white hover:bg-accent-light transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Tambah Memori
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Cari preferensi atau konteks teknis..."
            className="w-full bg-card border border-border rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-white/40 outline-none focus:border-accent"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
          <Filter className="w-3.5 h-3.5 text-white/40 shrink-0 hidden sm:block" />
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`text-xs px-2.5 py-1.5 rounded-lg whitespace-nowrap transition-colors border ${
                selectedCategory === cat.id
                  ? "bg-accent/15 border-accent text-white font-medium"
                  : "bg-white/5 border-border text-white/60 hover:bg-white/10"
              }`}
            >
              {cat.label}
            </button>
          ))}
          <button
            onClick={fetchMemoryData}
            title="Refresh Memori"
            className="p-1.5 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white/60 hover:text-white shrink-0 ml-1"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Memories List */}
      <div className="space-y-3">
        {loading && memories.length === 0 ? (
          <div className="bg-card border border-border rounded-xl2 p-8 text-center text-xs text-white/50">
            <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-accent" />
            Memuat data memori terisolasi...
          </div>
        ) : memories.length === 0 ? (
          <div className="bg-card border border-border rounded-xl2 p-10 text-center">
            <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-white/40 mx-auto mb-3">
              <Sparkles className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-white mb-1">Belum Ada Memori Tersimpan</h3>
            <p className="text-xs text-white/50 max-w-md mx-auto mb-4">
              VERA belum mencatat memori jangka panjang untuk akun Anda. Anda dapat menambahkan preferensi teknis, aturan subnet, atau alur troubleshooting secara manual.
            </p>
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 text-white transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Buat Memori Pertama
            </button>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between text-xs text-white/50 px-1">
              <span>Menampilkan {memories.length} butir memori</span>
              <button
                onClick={handleClearAll}
                className="text-red-400 hover:text-red-300 transition-colors"
              >
                Hapus Semua Memori Saya
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {memories.map((m) => (
                <div
                  key={m.memory_id}
                  className="bg-card border border-border hover:border-accent/30 rounded-xl2 p-4 flex flex-col justify-between transition-colors group"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <span className="inline-flex items-center gap-1 text-[10px] font-medium tracking-wide uppercase px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-accent-light">
                        <Tag className="w-2.5 h-2.5" />
                        {m.category_label || m.category}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-white/40">
                          Prioritas: {Math.round((m.importance || 0.5) * 100)}%
                        </span>
                        <button
                          onClick={() => handleDeleteMemory(m.memory_id)}
                          className="text-white/30 hover:text-red-400 p-1 rounded transition-colors"
                          title="Hapus memori ini"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <p className="text-xs text-white/90 leading-relaxed font-mono whitespace-pre-wrap break-words">
                      {m.content}
                    </p>
                  </div>
                  <div className="mt-3 pt-2.5 border-t border-white/5 flex items-center justify-between text-[10px] text-white/40">
                    <span>Sumber: {m.source || "USER"}</span>
                    <span>
                      {m.updated_at ? new Date(m.updated_at).toLocaleDateString("id-ID") : "-"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Modal Add Memory */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-card border border-border rounded-xl2 w-full max-w-lg p-6 shadow-2xl relative">
            <button
              onClick={() => setShowAddModal(false)}
              className="absolute top-4 right-4 text-white/40 hover:text-white p-1"
            >
              <X className="w-4 h-4" />
            </button>

            <h3 className="text-sm font-semibold text-white mb-1 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-accent" />
              Tambah Memori Jangka Panjang
            </h3>
            <p className="text-xs text-white/50 mb-4">
              Informasi ini disimpan secara terisolasi untuk akun Anda dan otomatis disuntikkan ke konteks penalaran Ask VERA.
            </p>

            <form onSubmit={handleAddMemory} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-white/70 mb-1">Kategori</label>
                <select
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-xs text-white outline-none focus:border-accent"
                >
                  <option value="technical" className="bg-card">Technical (Arsitektur & Konfigurasi)</option>
                  <option value="project" className="bg-card">Project (Konteks Topologi & Jaringan)</option>
                  <option value="workflows" className="bg-card">Workflows (Alur & Kebijakan NOC)</option>
                  <option value="learning" className="bg-card">Learning (Pola Error & Catatan)</option>
                  <option value="communication" className="bg-card">Communication (Gaya Penjelasan)</option>
                  <option value="general" className="bg-card">General (Preferensi Umum)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-white/70 mb-1">
                  Konten Memori
                </label>
                <textarea
                  value={newContent}
                  onChange={(e) => setNewContent(e.target.value)}
                  rows={4}
                  placeholder="Contoh: Core router R1 selalu menggunakan gateway 10.0.0.1. Jika latency > 50ms, periksa interface sfp-sfpplus1."
                  className="w-full bg-white/5 border border-border rounded-lg p-3 text-xs text-white placeholder-white/30 outline-none focus:border-accent"
                  required
                />
              </div>

              <div>
                <div className="flex items-center justify-between text-xs text-white/70 mb-1">
                  <span>Bobot Kepentingan (Importance)</span>
                  <span className="font-mono text-accent">{newImportance}%</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="100"
                  step="5"
                  value={newImportance}
                  onChange={(e) => setNewImportance(e.target.value)}
                  className="w-full accent-accent cursor-pointer"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="text-xs px-4 py-2 rounded-lg border border-border bg-white/5 hover:bg-white/10 text-white/70 transition-colors"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="text-xs font-semibold px-4 py-2 rounded-lg bg-accent hover:bg-accent-light text-white transition-colors disabled:opacity-50"
                >
                  {saving ? "Menyimpan..." : "Simpan Memori"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
