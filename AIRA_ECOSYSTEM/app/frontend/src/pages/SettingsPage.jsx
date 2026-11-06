import { useModalDialog } from "../context/ModalDialogContext.jsx";
import { useCallback, useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import LocationPanel from "../components/location/LocationPanel.jsx";
import GlobalSettingsPanel from "../components/settings/GlobalSettingsPanel.jsx";
import { api, getAuthHeaders } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import {
  Brain,
  CheckCircle2,
  Coins,
  Copy,
  CreditCard,
  Download,
  Eye,
  Key,
  Layers,
  Loader2,
  Lock,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  User,
  X,
} from "lucide-react";

const CATEGORY_COLORS = {
  general: "bg-neutral-800 text-neutral-300 border-neutral-700",
  learning: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  technical: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  project: "bg-purple-500/15 text-purple-300 border-purple-500/30",
  communication: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  workflows: "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

export default function SettingsPage({ onOpenMenu }) {
  const { alert: modalAlert, confirm: modalConfirm, prompt: modalPrompt } = useModalDialog();

  const { user, role, plan, hasNetworkingPlus, isAdmin, isGuest, hasPermission } = useAuth();
  const { notify } = useToast();

  const [activeTab, setActiveTab] = useState(() => {
    try {
      const stored = sessionStorage.getItem("aira_settings_tab");
      if (stored && ["general", "memory", "persona", "security", "account", "privacy"].includes(stored)) {
        sessionStorage.removeItem("aira_settings_tab");
        return stored;
      }
    } catch {}
    return "general";
  });

  useEffect(() => {
    function onTabChange(e) {
      if (typeof e.detail === "string" && ["general", "memory", "persona", "security", "account", "privacy"].includes(e.detail)) {
        setActiveTab(e.detail);
      }
    }
    window.addEventListener("aira:settings-tab", onTabChange);
    return () => window.removeEventListener("aira:settings-tab", onTabChange);
  }, []);

  const canEditMemory = isAdmin || !hasPermission || hasPermission("settings.memory.update");
  const canEditPersona = isAdmin || !hasPermission || hasPermission("settings.persona.update");

  // General & Quota State
  const [usage, setUsage] = useState(null);
  const [credits, setCredits] = useState(null);
  const [entitlements, setEntitlements] = useState(null);
  const [balance, setBalance] = useState(null);
  const [approvalPref, setApprovalPref] = useState(null);
  const [savingPref, setSavingPref] = useState(false);

  // Personalization: Preferences & Instructions
  const [preferences, setPreferences] = useState(null);
  const [customInstructions, setCustomInstructions] = useState("");
  const [savingInstructions, setSavingInstructions] = useState(false);

  // Personalization: Memories
  const [memories, setMemories] = useState([]);
  const [memorySummary, setMemorySummary] = useState(null);
  const [memorySearch, setMemorySearch] = useState("");
  const [memoryCategory, setMemoryCategory] = useState("");
  const [loadingMemories, setLoadingMemories] = useState(false);
  const [showAddMemoryModal, setShowAddMemoryModal] = useState(false);
  const [newMemoryContent, setNewMemoryContent] = useState("");
  const [newMemoryCategory, setNewMemoryCategory] = useState("general");
  const [newMemoryImportance, setNewMemoryImportance] = useState(70);
  const [savingMemory, setSavingMemory] = useState(false);

  // Personalization: Personas
  const [personasData, setPersonasData] = useState(null);
  const [loadingPersonas, setLoadingPersonas] = useState(false);
  const [showAddPersonaModal, setShowAddPersonaModal] = useState(false);
  const [newPersonaName, setNewPersonaName] = useState("");
  const [newPersonaStyle, setNewPersonaStyle] = useState("concise");
  const [newPersonaLanguage, setNewPersonaLanguage] = useState("id");
  const [newPersonaDepth, setNewPersonaDepth] = useState(80);
  const [newPersonaPreference, setNewPersonaPreference] = useState("technical");
  const [newPersonaInstructions, setNewPersonaInstructions] = useState("");
  const [savingPersona, setSavingPersona] = useState(false);
  const [previewPersonaText, setPreviewPersonaText] = useState(null);

  // Privacy & Data: Confirm Modals
  const [confirmModal, setConfirmModal] = useState(null);
  const [actionInProgress, setActionInProgress] = useState(false);

  // Fetch Core Entitlements & Preferences
  const fetchEntitlements = useCallback(async () => {
    try {
      const res = await fetch("/api/settings/entitlements/summary", {
        headers: getAuthHeaders(),
      });
      const data = await res.json();
      if (data.success) {
        setEntitlements(data.entitlements);
        setBalance(data.balance);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchApprovalPreferences = useCallback(async () => {
    try {
      const res = await fetch("/api/settings/approvals/preferences", {
        headers: getAuthHeaders(),
      });
      const data = await res.json();
      if (data.success) {
        setApprovalPref(data.preferences);
      }
    } catch {
      // silent
    }
  }, []);

  // Fetch Personalization Data
  const fetchPreferences = useCallback(async () => {
    try {
      const data = await api.personalization.getPreferences();
      if (data.success && data.preferences) {
        setPreferences(data.preferences);
        setCustomInstructions(data.preferences.custom_instructions || "");
      }
    } catch {
      // silent
    }
  }, []);

  const fetchMemories = useCallback(async () => {
    setLoadingMemories(true);
    try {
      const res = await api.personalization.getMemories({
        category: memoryCategory || null,
        query: memorySearch || null,
      });
      if (res.success) {
        setMemories(res.memories || []);
      }
      const sum = await api.personalization.getMemorySummary();
      if (sum.success) {
        setMemorySummary(sum.summary);
      }
    } catch {
      // silent
    } finally {
      setLoadingMemories(false);
    }
  }, [memoryCategory, memorySearch]);

  const fetchPersonas = useCallback(async () => {
    setLoadingPersonas(true);
    try {
      const res = await api.personalization.getPersonas();
      if (res.success) {
        setPersonasData(res);
      }
    } catch {
      // silent
    } finally {
      setLoadingPersonas(false);
    }
  }, []);

  useEffect(() => {
    api.tokenUsage().then(setUsage).catch(() => {});
    api.credits().then(setCredits).catch(() => {});
    fetchEntitlements();
    fetchApprovalPreferences();
    fetchPreferences();
    fetchMemories();
    fetchPersonas();
  }, [fetchEntitlements, fetchApprovalPreferences, fetchPreferences, fetchMemories, fetchPersonas]);

  // Handle Updates
  const handleToggleMemory = async () => {
    if (!canEditMemory) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin memperbarui memori." });
      return;
    }
    if (!preferences) return;
    const nextState = !preferences.memory_enabled;
    try {
      const res = await api.personalization.updatePreferences({ memory_enabled: nextState });
      if (res.success) {
        setPreferences((prev) => ({ ...prev, memory_enabled: nextState }));
        notify({
          type: "success",
          message: nextState ? "Memori personal AIRA diaktifkan." : "Memori personal AIRA dinonaktifkan.",
        });
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal mengubah status memori." });
    }
  };

  const handleSaveInstructions = async () => {
    if (!canEditPersona) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin memperbarui instruksi." });
      return;
    }
    setSavingInstructions(true);
    try {
      const res = await api.personalization.updatePreferences({ custom_instructions: customInstructions });
      if (res.success) {
        notify({ type: "success", message: "Instruksi personal AIRA berhasil disimpan." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal menyimpan instruksi." });
    } finally {
      setSavingInstructions(false);
    }
  };

  const handleAddMemory = async (e) => {
    e.preventDefault();
    if (!canEditMemory) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin memperbarui memori." });
      return;
    }
    if (!newMemoryContent.trim()) return;
    setSavingMemory(true);
    try {
      const res = await api.personalization.addMemory({
        content: newMemoryContent.trim(),
        category: newMemoryCategory,
        importance: parseInt(newMemoryImportance, 10) || 70,
      });
      if (res.success) {
        notify({ type: "success", message: "Memori baru berhasil disimpan." });
        setShowAddMemoryModal(false);
        setNewMemoryContent("");
        fetchMemories();
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal menambahkan memori." });
    } finally {
      setSavingMemory(false);
    }
  };

  const handleDeleteMemory = async (memoryId) => {
    if (!canEditMemory) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin menghapus memori." });
      return;
    }
    try {
      const res = await api.personalization.deleteMemory(memoryId);
      if (res.success) {
        notify({ type: "success", message: "Memori dihapus." });
        setMemories((prev) => prev.filter((m) => m.memory_id !== memoryId));
        fetchMemories();
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal menghapus memori." });
    }
  };

  const handleSetActivePersona = async (personaId) => {
    if (!canEditPersona) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin memperbarui persona." });
      return;
    }
    try {
      const res = await api.personalization.setActivePersona(personaId);
      if (res.success) {
        notify({ type: "success", message: "Persona aktif AIRA berhasil diperbarui." });
        fetchPersonas();
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal mengatur persona." });
    }
  };

  const handleDuplicatePersona = async (personaId, personaName) => {
    if (!canEditPersona) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin memperbarui persona." });
      return;
    }
    const cloneName = await modalPrompt({ message: `Nama untuk kloning persona '${personaName}':`, defaultValue: `${personaName} (Copy)` });
    if (!cloneName || !cloneName.trim()) return;
    try {
      const res = await api.personalization.duplicatePersona(personaId, cloneName.trim());
      if (res.success) {
        notify({ type: "success", message: `Persona '${cloneName}' berhasil diduplikasi!` });
        fetchPersonas();
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal menduplikasi persona." });
    }
  };

  const handleDeleteCustomPersona = async (personaId) => {
    if (!canEditPersona) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin menghapus persona." });
      return;
    }
    if (!await modalConfirm({ message: "Hapus custom persona ini?", isDestructive: true })) return;
    try {
      const res = await api.personalization.deletePersona(personaId);
      if (res.success) {
        notify({ type: "success", message: "Custom persona berhasil dihapus." });
        fetchPersonas();
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal menghapus persona." });
    }
  };

  const handleCreateCustomPersona = async (e) => {
    e.preventDefault();
    if (!canEditPersona) {
      notify({ type: "error", message: "Akses ditolak: Anda tidak memiliki izin membuat persona." });
      return;
    }
    if (!newPersonaName.trim()) return;
    setSavingPersona(true);
    try {
      const res = await api.personalization.createPersona({
        name: newPersonaName.trim(),
        response_style: newPersonaStyle,
        language: newPersonaLanguage,
        technical_depth: parseInt(newPersonaDepth, 10) || 80,
        explanation_preference: newPersonaPreference,
        custom_instructions: newPersonaInstructions.trim(),
      });
      if (res.success) {
        notify({ type: "success", message: "Custom persona berhasil dibuat!" });
        setShowAddPersonaModal(false);
        setNewPersonaName("");
        setNewPersonaInstructions("");
        fetchPersonas();
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal membuat custom persona." });
    } finally {
      setSavingPersona(false);
    }
  };

  const handlePreviewPersona = async (personaId) => {
    try {
      const res = await api.personalization.previewPersona(personaId);
      if (res.success) {
        setPreviewPersonaText(res.prompt_preview);
      }
    } catch (err) {
      notify({ type: "error", message: err.message || "Gagal melihat preview persona." });
    }
  };

  // Privacy Actions
  const handleExportData = async () => {
    try {
      const res = await fetch("/api/v1/personalization/data/export", {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error("Gagal mengunduh data.");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `aira_personal_data_${user?.username || "export"}_${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      notify({ type: "success", message: "Data personal berhasil diekspor (JSON)." });
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  };

  const executeDangerousAction = async () => {
    if (!confirmModal) return;
    setActionInProgress(true);
    try {
      if (confirmModal.type === "clear_memories") {
        const res = await api.personalization.clearMemories();
        if (res.success) {
          notify({ type: "success", message: `${res.deleted_count} memori berhasil dibersihkan.` });
          fetchMemories();
        }
      } else if (confirmModal.type === "delete_conversations") {
        const res = await api.personalization.deleteConversations();
        if (res.success) {
          notify({ type: "success", message: `${res.deleted_sessions} sesi percakapan berhasil dihapus.` });
        }
      } else if (confirmModal.type === "delete_personas") {
        const res = await api.personalization.deleteCustomPersonas();
        if (res.success) {
          notify({ type: "success", message: `${res.deleted_personas} custom persona berhasil dihapus.` });
          fetchPersonas();
        }
      } else if (confirmModal.type === "account_deletion") {
        const res = await api.personalization.requestAccountDeletion("User requested via settings");
        if (res.success) {
          notify({ type: "success", message: "Permintaan penghapusan akun telah dicatat." });
        }
      }
      setConfirmModal(null);
    } catch (err) {
      notify({ type: "error", message: err.message || "Operasi gagal." });
    } finally {
      setActionInProgress(false);
    }
  };

  const handleUpdateApprovalMode = async (mode) => {
    setSavingPref(true);
    try {
      const res = await fetch("/api/settings/approvals/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          mode,
          auto_approve_categories: mode === "ALWAYS_ASK" ? [] : ["A"],
          allowed_change_windows: [],
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || "Gagal memperbarui preferensi.");
      }
      setApprovalPref((prev) => ({ ...prev, mode }));
      notify({ type: "success", message: "Kebijakan persetujuan operasional disimpan!" });
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingPref(false);
    }
  };

  const currentBal = balance?.current_balance ?? 10000;
  const monthlyAllow = balance?.monthly_allowance ?? 10000;
  const usedTokens = balance?.tokens_used_this_period ?? 0;
  const usedPercent = Math.min(100, Math.round((usedTokens / Math.max(1, monthlyAllow)) * 100));

  const RAW_TABS = [
    { id: "general", label: "General & Autonomy", icon: Settings },
    { id: "memory", label: "Memory Settings", icon: Brain, requiredPermission: "settings.memory.view" },
    { id: "persona", label: "Persona Settings", icon: Sparkles, requiredPermission: "settings.persona.view" },
    { id: "security", label: "Security & Sessions", icon: Key },
    { id: "account", label: "Account Profile", icon: User },
    { id: "privacy", label: "Privacy & Data", icon: Shield },
  ];

  const TABS = RAW_TABS.filter((tab) => {
    if (!tab.requiredPermission) return true;
    if (isAdmin) return true;
    return hasPermission ? hasPermission(tab.requiredPermission) : true;
  });

  return (
    <div className="space-y-6 pb-16">
      <TopBar
        title="Settings & Personalization Center"
        subtitle="Kelola identitas, memori AI, persona personal, privasi data, dan kebijakan otonomi"
        onMenuClick={onOpenMenu}
      />

      {/* HORIZONTAL TAB NAVIGATION */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-white/[0.08] scrollbar-none">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all duration-200 ${
                isActive
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                  : "text-neutral-400 hover:text-white hover:bg-neutral-900 border border-transparent"
              }`}
            >
              <Icon size={14} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* ============================================================== */}
      {/* TAB: MEMORY SETTINGS (USER-ISOLATED)                           */}
      {/* ============================================================== */}
      {activeTab === "memory" && (
        <div className="space-y-6">
          {/* Section: AI Memory Management */}
          <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-5">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-white/[0.08]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                  <Brain size={20} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-white">Memori Jangka Panjang AI (User Memory)</h3>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        preferences?.memory_enabled
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-neutral-800 text-neutral-400 border border-white/10"
                      }`}
                    >
                      {preferences?.memory_enabled ? "AKTIF" : "NONAKTIF"}
                    </span>
                  </div>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    AIRA mengingat detail preferensi, arsitektur teknis, dan kebiasaan kerja Anda secara terisolasi.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleToggleMemory}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition ${
                    preferences?.memory_enabled
                      ? "bg-rose-500/15 text-rose-300 border-rose-500/30 hover:bg-rose-500/25"
                      : "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/25"
                  }`}
                >
                  {preferences?.memory_enabled ? "Matikan Memori" : "Aktifkan Memori"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddMemoryModal(true)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25 text-xs font-semibold transition"
                >
                  <Plus size={13} />
                  <span>Tambah Memori</span>
                </button>
              </div>
            </div>

            {/* Memory Filter & Search */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-2.5 text-neutral-400" />
                <input
                  type="text"
                  placeholder="Cari dalam memori AIRA..."
                  value={memorySearch}
                  onChange={(e) => setMemorySearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <select
                value={memoryCategory}
                onChange={(e) => setMemoryCategory(e.target.value)}
                className="px-3 py-2 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-neutral-300 focus:outline-none focus:border-cyan-500"
              >
                <option value="">Semua Kategori</option>
                <option value="technical">Technical</option>
                <option value="project">Project</option>
                <option value="workflows">Workflows</option>
                <option value="learning">Learning</option>
                <option value="communication">Communication</option>
                <option value="general">General</option>
              </select>

              {memories.length > 0 && (
                <button
                  type="button"
                  onClick={() =>
                    setConfirmModal({
                      type: "clear_memories",
                      title: "Bersihkan Semua Memori?",
                      description:
                        "Tindakan ini akan menghapus seluruh catatan memori personal Anda. AIRA tidak akan lagi mengingat preferensi yang telah disimpan.",
                      confirmText: "Bersihkan Semua",
                    })
                  }
                  className="px-3 py-2 text-xs text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 rounded-xl transition"
                >
                  Hapus Semua Memori
                </button>
              )}
            </div>

            {/* Memory List */}
            {loadingMemories ? (
              <div className="py-8 flex items-center justify-center gap-2 text-neutral-400 text-xs">
                <Loader2 size={16} className="animate-spin text-cyan-400" />
                <span>Memuat memori...</span>
              </div>
            ) : memories.length === 0 ? (
              <div className="py-8 text-center text-xs text-neutral-400 bg-neutral-950/40 rounded-xl border border-white/[0.04]">
                Belum ada memori yang tersimpan. Tambah memori manual atau biarkan AIRA belajar dari giliran obrolan.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-80 overflow-y-auto pr-1">
                {memories.map((m) => {
                  const catClass = CATEGORY_COLORS[m.category] || CATEGORY_COLORS.general;
                  return (
                    <div
                      key={m.memory_id}
                      className="p-3.5 rounded-xl bg-neutral-950/70 border border-white/[0.06] hover:border-white/15 transition flex flex-col justify-between gap-2.5"
                    >
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${catClass}`}>
                            {m.category.toUpperCase()}
                          </span>
                          <span className="text-[10px] font-mono text-neutral-400">
                            Penting: {m.importance}/100
                          </span>
                        </div>
                        <p className="text-xs text-neutral-200 leading-relaxed">{m.content}</p>
                      </div>
                      <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
                        <span className="text-[10px] text-neutral-400">
                          {new Date(m.updated_at).toLocaleDateString()}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDeleteMemory(m.memory_id)}
                          className="text-neutral-400 hover:text-rose-400 transition"
                          title="Hapus memori ini"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB: PERSONA SETTINGS (AI BEHAVIOR & PRESETS)                 */}
      {/* ============================================================== */}
      {activeTab === "persona" && (
        <div className="space-y-6">
          {/* Section: AI Persona Management */}
          <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-5">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-white/[0.08]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                  <Sparkles size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white">Profil & Gaya Interaksi AI (Persona Engine)</h3>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    Pilih preset bawaan atau ciptakan Persona khusus dengan gaya penjelasan dan kedalaman teknis Anda sendiri.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setShowAddPersonaModal(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25 text-xs font-semibold transition"
              >
                <Plus size={13} />
                <span>Buat Persona Kustom</span>
              </button>
            </div>

            {loadingPersonas ? (
              <div className="py-8 flex items-center justify-center gap-2 text-neutral-400 text-xs">
                <Loader2 size={16} className="animate-spin text-cyan-400" />
                <span>Memuat daftar persona...</span>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Built-in System Presets */}
                <div>
                  <h4 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2.5">
                    Preset Sistem Resmi (Built-in)
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {personasData?.builtin_presets?.map((p) => {
                      const isActive = p.is_active;
                      return (
                        <div
                          key={p.persona_id}
                          className={`p-4 rounded-xl border transition flex flex-col justify-between gap-3 ${
                            isActive
                              ? "bg-cyan-500/10 border-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.1)]"
                              : "bg-neutral-950/60 border-white/[0.06] hover:border-white/15"
                          }`}
                        >
                          <div>
                            <div className="flex items-center justify-between">
                              <h5 className="text-xs font-semibold text-white">{p.name}</h5>
                              {isActive ? (
                                <span className="flex items-center gap-1 text-[10px] font-bold text-cyan-400 bg-cyan-500/15 px-2 py-0.5 rounded border border-cyan-500/30">
                                  <CheckCircle2 size={11} /> AKTIF
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => handleSetActivePersona(p.persona_id)}
                                  className="text-[10px] text-neutral-400 hover:text-white bg-neutral-800 px-2 py-0.5 rounded border border-neutral-700 transition"
                                >
                                  Gunakan
                                </button>
                              )}
                            </div>
                            <p className="text-[11px] text-neutral-400 mt-1 leading-relaxed">
                              {p.custom_instructions || "Persona standar rekayasa jaringan AIRA."}
                            </p>
                          </div>

                          <div className="flex items-center justify-between pt-2 border-t border-white/[0.04] text-[10px] text-neutral-400">
                            <span>Kedalaman: {p.technical_depth}%</span>
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => handlePreviewPersona(p.persona_id)}
                                className="hover:text-cyan-400 transition"
                                title="Lihat prompt sistem"
                              >
                                <Eye size={12} />
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDuplicatePersona(p.persona_id, p.name)}
                                className="hover:text-cyan-400 transition"
                                title="Kloning jadi persona kustom"
                              >
                                <Copy size={12} />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Custom Personas */}
                <div>
                  <h4 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2.5">
                    Persona Kustom Anda
                  </h4>
                  {personasData?.custom_personas?.length === 0 ? (
                    <div className="py-6 text-center text-xs text-neutral-400 bg-neutral-950/40 rounded-xl border border-white/[0.04]">
                      Belum ada persona kustom. Tekan "Buat Persona Kustom" atau kloning salah satu preset di atas.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {personasData?.custom_personas?.map((p) => {
                        const isActive = p.is_active;
                        return (
                          <div
                            key={p.persona_id}
                            className={`p-4 rounded-xl border transition flex flex-col justify-between gap-3 ${
                              isActive
                                ? "bg-cyan-500/10 border-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.1)]"
                                : "bg-neutral-950/60 border-white/[0.06] hover:border-white/15"
                            }`}
                          >
                            <div>
                              <div className="flex items-center justify-between">
                                <h5 className="text-xs font-semibold text-white">{p.name}</h5>
                                {isActive ? (
                                  <span className="flex items-center gap-1 text-[10px] font-bold text-cyan-400 bg-cyan-500/15 px-2 py-0.5 rounded border border-cyan-500/30">
                                    <CheckCircle2 size={11} /> AKTIF
                                  </span>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => handleSetActivePersona(p.persona_id)}
                                    className="text-[10px] text-neutral-400 hover:text-white bg-neutral-800 px-2 py-0.5 rounded border border-neutral-700 transition"
                                  >
                                    Gunakan
                                  </button>
                                )}
                              </div>
                              <p className="text-[11px] text-neutral-400 mt-1 leading-relaxed">
                                {p.custom_instructions || "Instruksi spesifik persona kustom."}
                              </p>
                            </div>

                            <div className="flex items-center justify-between pt-2 border-t border-white/[0.04] text-[10px] text-neutral-400">
                              <span>Kedalaman: {p.technical_depth}%</span>
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  onClick={() => handlePreviewPersona(p.persona_id)}
                                  className="hover:text-cyan-400 transition"
                                  title="Lihat prompt sistem"
                                >
                                  <Eye size={12} />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDeleteCustomPersona(p.persona_id)}
                                  className="hover:text-rose-400 transition"
                                  title="Hapus persona kustom"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Section: Custom Instructions */}
          <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-white">Instruksi Khusus untuk AIRA (Custom Instructions)</h3>
              <p className="text-xs text-neutral-400 mt-1">
                Instruksi ini akan disuntikkan secara otomatis ke setiap giliran percakapan Anda dengan AIRA.
              </p>
            </div>

            <textarea
              rows={4}
              value={customInstructions}
              onChange={(e) => setCustomInstructions(e.target.value)}
              placeholder="Contoh: Selalu sertakan perintah CLI RouterOS v7 saat memberikan solusi konfigurasi; gunakan gaya bahasa teknis ringkas..."
              className="w-full p-3.5 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500 leading-relaxed font-sans"
            />

            <div className="flex justify-end">
              <button
                type="button"
                disabled={savingInstructions}
                onClick={handleSaveInstructions}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-neutral-950 text-xs font-semibold transition disabled:opacity-50"
              >
                {savingInstructions ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                <span>Simpan Instruksi</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 2: PRIVACY & DATA MANAGEMENT                             */}
      {/* ============================================================== */}
      {activeTab === "privacy" && (
        <div className="space-y-6">
          {/* Data Portability / Export */}
          <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <Download size={20} />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Portabilitas Data (Export JSON)</h3>
                <p className="text-xs text-neutral-400 mt-0.5">
                  Unduh seluruh arsip data akun Anda meliputi memori, preferensi, persona, riwayat sesi, dan workspace.
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-neutral-950/60 border border-white/[0.06] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="text-xs text-neutral-300">
                File JSON berisi ringkasan profil, seluruh catatan memori, sesi percakapan, dan persona kustom Anda.
              </div>
              <button
                type="button"
                onClick={handleExportData}
                className="flex items-center gap-2 px-4 py-2 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/30 rounded-xl text-xs font-semibold transition"
              >
                <Download size={13} />
                <span>Ekspor Semua Data (.JSON)</span>
              </button>
            </div>
          </div>

          {/* Danger Zone: Granular Deletion Controls */}
          <div className="bg-rose-950/20 border border-rose-500/20 rounded-2xl p-5 space-y-4 shadow-xl">
            <div className="flex items-center gap-2 text-rose-400">
              <ShieldAlert size={18} />
              <h3 className="text-sm font-bold uppercase tracking-wider">Zona Berbahaya (Danger Zone)</h3>
            </div>
            <p className="text-xs text-neutral-400">
              Tindakan di bawah ini bersifat permanen dan tidak dapat dibatalkan. Pastikan Anda telah mengekspor data terlebih dahulu jika diperlukan.
            </p>

            <div className="space-y-3 pt-2">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3.5 bg-neutral-950/70 rounded-xl border border-rose-500/10">
                <div>
                  <h4 className="text-xs font-semibold text-white">Bersihkan Seluruh Memori Personal</h4>
                  <p className="text-[11px] text-neutral-400">Hapus semua catatan memori jangka panjang tanpa menghapus riwayat percakapan.</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setConfirmModal({
                      type: "clear_memories",
                      title: "Bersihkan Semua Memori?",
                      description: "Seluruh fakta dan preferensi yang dipelajari AIRA akan dihapus secara permanen.",
                      confirmText: "Hapus Memori",
                    })
                  }
                  className="px-3.5 py-1.5 bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 rounded-lg text-xs font-semibold transition"
                >
                  Bersihkan Memori
                </button>
              </div>

              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3.5 bg-neutral-950/70 rounded-xl border border-rose-500/10">
                <div>
                  <h4 className="text-xs font-semibold text-white">Hapus Seluruh Riwayat Percakapan</h4>
                  <p className="text-[11px] text-neutral-400">Hapus semua sesi chat dan riwayat pesan milik akun Anda dari database.</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setConfirmModal({
                      type: "delete_conversations",
                      title: "Hapus Semua Percakapan?",
                      description: "Semua sesi chat dan pesan akan dihapus. Memori personal yang sudah dipelajari tetap aman.",
                      confirmText: "Hapus Percakapan",
                    })
                  }
                  className="px-3.5 py-1.5 bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 rounded-lg text-xs font-semibold transition"
                >
                  Hapus Chat
                </button>
              </div>

              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3.5 bg-neutral-950/70 rounded-xl border border-rose-500/10">
                <div>
                  <h4 className="text-xs font-semibold text-white">Hapus Seluruh Persona Kustom</h4>
                  <p className="text-[11px] text-neutral-400">Hapus semua profil persona buatan Anda dan kembalikan ke preset teknis bawaan.</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setConfirmModal({
                      type: "delete_personas",
                      title: "Hapus Semua Custom Persona?",
                      description: "Semua persona kustom akan dihapus permanen. AIRA akan kembali menggunakan preset bawaan.",
                      confirmText: "Hapus Persona",
                    })
                  }
                  className="px-3.5 py-1.5 bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 rounded-lg text-xs font-semibold transition"
                >
                  Hapus Persona
                </button>
              </div>

              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3.5 bg-neutral-950/70 rounded-xl border border-rose-500/10">
                <div>
                  <h4 className="text-xs font-semibold text-rose-400">Ajukan Permintaan Penghapusan Akun</h4>
                  <p className="text-[11px] text-neutral-400">Catat tiket permintaan penutupan akun permanen sesuai regulasi GDPR & Privasi Data.</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setConfirmModal({
                      type: "account_deletion",
                      title: "Ajukan Penghapusan Akun?",
                      description: "Akun Anda akan dijadwalkan untuk penutupan permanen beserta seluruh dependensi data.",
                      confirmText: "Ajukan Penghapusan",
                    })
                  }
                  className="px-3.5 py-1.5 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-bold transition"
                >
                  Tutup Akun
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 3: ACCOUNT & IDENTITY HIERARCHY                          */}
      {/* ============================================================== */}
      {activeTab === "account" && (
        <div className="space-y-6">
          <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-5">
            <div className="flex items-center gap-3 pb-4 border-b border-white/[0.08]">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <User size={20} />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Identitas & Hak Akses Pengguna</h3>
                <p className="text-xs text-neutral-400 mt-0.5">
                  Hierarki peran platform, paket langganan, dan entitlement fitur yang aktif pada akun ini.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3.5 rounded-xl bg-neutral-950/60 border border-white/[0.06] space-y-1">
                <span className="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider">Username</span>
                <p className="text-xs font-mono font-semibold text-white">{user?.username || (isGuest ? "Guest User" : "-")}</p>
              </div>

              <div className="p-3.5 rounded-xl bg-neutral-950/60 border border-white/[0.06] space-y-1">
                <span className="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider">Email Akun</span>
                <p className="text-xs font-semibold text-white truncate">{user?.email || (isGuest ? "Sesi Tamu Mandiri" : "-")}</p>
              </div>

              <div className="p-3.5 rounded-xl bg-neutral-950/60 border border-white/[0.06] space-y-1">
                <span className="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider">Peran (Role)</span>
                <div>
                  <span
                    className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      role === "PLATFORM_OWNER"
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                        : role === "SUPERADMIN" || role === "ADMIN"
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                        : "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                    }`}
                  >
                    {role || "USER"}
                  </span>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-neutral-950/60 border border-white/[0.06] space-y-1">
                <span className="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider">Paket Langganan (Plan)</span>
                <div>
                  <span
                    className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      plan === "ENTERPRISE"
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                        : plan === "PRO"
                        ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                        : "bg-neutral-800 text-neutral-400 border border-white/10"
                    }`}
                  >
                    {plan || "FREE"}
                  </span>
                </div>
              </div>
            </div>

            <div className="pt-2">
              <h4 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2">Entitlement Fitur</h4>
              <div className="flex flex-wrap gap-2">
                <div
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border ${
                    hasNetworkingPlus
                      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                      : "bg-neutral-900 text-neutral-500 border-white/[0.06]"
                  }`}
                >
                  <Sparkles size={13} />
                  <span>NETWORKING++ (MikroTik, Topology, NMS, Playbooks)</span>
                  {hasNetworkingPlus ? <CheckCircle2 size={13} /> : <Lock size={13} />}
                </div>

                {isAdmin && (
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
                    <Shield size={13} />
                    <span>CONTROL PLANE ADMIN SITE</span>
                    <CheckCircle2 size={13} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 4: SECURITY & PERSISTENT SESSIONS                         */}
      {/* ============================================================== */}
      {activeTab === "security" && (
        <div className="space-y-6">
          <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-5">
            <div className="flex items-center gap-3 pb-4 border-b border-white/[0.08]">
              <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <Key size={20} />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Keamanan Akun & Sesi Login Persisten</h3>
                <p className="text-xs text-neutral-400 mt-0.5">
                  Manajemen autentikasi token, pembatasan perangkat, dan revokasi sesi aktif.
                </p>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-neutral-950/60 border border-white/[0.06] space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-semibold text-white">Sesi Login Saat Ini</h4>
                  <p className="text-[11px] text-neutral-400 mt-0.5">Perangkat aktif: Browser web saat ini (terautentikasi).</p>
                </div>
                <span className="px-2.5 py-1 rounded text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  AKTIF & TERVERIFIKASI
                </span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-neutral-950/60 border border-white/[0.06] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <h4 className="text-xs font-semibold text-white">Keluar dari Seluruh Perangkat Lain</h4>
                <p className="text-[11px] text-neutral-400 mt-0.5">
                  Mencabut refresh token pada browser atau perangkat lain yang pernah login ke akun Anda.
                </p>
              </div>
              <button
                type="button"
                onClick={async () => {
                  try {
                    const res = await fetch("/api/v1/auth/sessions/revoke-others", {
                      method: "POST",
                      headers: getAuthHeaders(),
                    });
                    const d = await res.json();
                    if (d.success) {
                      notify({ type: "success", message: "Seluruh sesi di perangkat lain telah dicabut." });
                    }
                  } catch (e) {
                    notify({ type: "error", message: e.message || "Gagal mencabut sesi." });
                  }
                }}
                className="px-3.5 py-1.5 bg-neutral-800 hover:bg-neutral-700 text-xs font-semibold text-neutral-200 border border-neutral-700 rounded-lg transition"
              >
                Revoke Other Sessions
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 5: SUBSCRIPTION & ENTITLEMENTS                           */}
      {/* ============================================================== */}
      {activeTab === "subscription" && (
        <div className="space-y-6">
          <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-white/[0.08]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                  <CreditCard size={20} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-white">Paket Langganan Platform</h3>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        entitlements?.tier === "enterprise"
                          ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                          : entitlements?.tier === "pro"
                          ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                          : "bg-neutral-800 text-neutral-300 border border-white/10"
                      }`}
                    >
                      {entitlements?.tier || "FREE TIER"}
                    </span>
                    {hasNetworkingPlus && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        <Sparkles size={11} />
                        <span>NETWORKING++ AKTIF</span>
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-neutral-400 mt-0.5">
                    Entitlement menentukan kapasitas token bulanan serta akses ke otomasi & topologi jaringan.
                  </p>
                </div>
              </div>

              <button
                onClick={fetchEntitlements}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-xs text-neutral-300 border border-neutral-700 transition"
              >
                <RefreshCw size={12} />
                <span>Refresh Saldo</span>
              </button>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-neutral-400 font-medium">Pemakaian Kuota Periode Ini:</span>
                <span className="font-mono text-neutral-200">
                  <span className="text-cyan-400 font-semibold">{usedTokens.toLocaleString()}</span> /{" "}
                  {monthlyAllow.toLocaleString()} tokens ({usedPercent}%)
                </span>
              </div>

              <div className="w-full h-2 rounded-full bg-neutral-800 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    usedPercent > 85 ? "bg-rose-500" : usedPercent > 60 ? "bg-amber-500" : "bg-cyan-400"
                  }`}
                  style={{ width: `${usedPercent}%` }}
                />
              </div>

              <div className="flex items-center justify-between text-[11px] text-neutral-400 pt-1">
                <span>Sisa Saldo Tersedia: <strong className="text-white font-mono">{currentBal.toLocaleString()}</strong></span>
                {balance?.period_ends_at && (
                  <span>Reset Kuota: {new Date(balance.period_ends_at * 1000).toLocaleDateString()}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 6: TOKEN METERING & USAGE LEDGER                         */}
      {/* ============================================================== */}
      {activeTab === "token_usage" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-3">
              <h3 className="font-semibold text-white text-sm flex items-center gap-2">
                <Coins size={16} className="text-cyan-400" />
                <span>Konsumsi Token Sesi Ini</span>
              </h3>
              {usage ? (
                <div className="text-xs text-neutral-300 space-y-1.5 font-mono">
                  <div className="flex justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-neutral-400 font-sans">Total Sesi:</span>
                    <span className="font-bold text-white">{usage.session_total_tokens?.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-neutral-400 font-sans">Prompt Input:</span>
                    <span>{usage.session_prompt_tokens?.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-neutral-400 font-sans">Completion Output:</span>
                    <span>{usage.session_completion_tokens?.toLocaleString()}</span>
                  </div>
                </div>
              ) : (
                <p className="text-neutral-500 text-xs">Belum ada pemakaian token pada sesi ini.</p>
              )}
            </div>

            <div className="bg-gradient-to-br from-neutral-900/90 to-neutral-950/80 border border-white/[0.08] rounded-2xl p-5 shadow-xl space-y-3">
              <h3 className="font-semibold text-white text-sm flex items-center gap-2">
                <Sparkles size={16} className="text-purple-400" />
                <span>Saldo Provider Terintegrasi</span>
              </h3>
              {credits?.success ? (
                <div className="text-xs text-neutral-300 space-y-1.5 font-mono">
                  <div className="flex justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-neutral-400 font-sans">Total Kredit:</span>
                    <span className="font-bold text-white">{credits.total_credits}</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-white/[0.04]">
                    <span className="text-neutral-400 font-sans">Terpakai:</span>
                    <span>{credits.total_usage}</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-neutral-400 font-sans">Sisa Tersedia:</span>
                    <span className="text-emerald-400 font-bold">{credits.remaining}</span>
                  </div>
                </div>
              ) : (
                <p className="text-neutral-500 text-xs">
                  {credits?.error || "Provider aktif dikonfigurasi melalui engine lokal."}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 7: GENERAL & AUTONOMY POLICY PREFERENCES                 */}
      {/* ============================================================== */}
      {activeTab === "general" && (
        <div className="space-y-6">
          {/* Autonomy Policies */}
          <div className="bg-neutral-900/60 border border-white/[0.08] rounded-2xl p-5 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <ShieldCheck size={16} className="text-cyan-400" />
                <span>Kebijakan Persetujuan Otonomi (Risk Approval Engine)</span>
              </h3>
              <p className="text-xs text-neutral-400 mt-1">
                Tentukan kapan AIRA diizinkan menjalankan konfigurasi atau remediasi jaringan secara mandiri vs meminta persetujuan teknis.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {[
                {
                  id: "ALWAYS_ASK",
                  title: "Selalu Minta Izin (Strict)",
                  desc: "Minta persetujuan eksplisit untuk semua perubahan konfigurasi jaringan (Category B).",
                  icon: ShieldAlert,
                  color: "text-amber-400",
                },
                {
                  id: "ASK_HIGH_RISK",
                  title: "Standar (Recommended)",
                  desc: "Otomatis jalankan inspeksi & diagnostik (Cat A); minta izin untuk modifikasi rute/antarmuka (Cat B).",
                  icon: ShieldCheck,
                  color: "text-cyan-400",
                },
                {
                  id: "AUTO_APPROVE_LOW_RISK",
                  title: "Otonom Terkendali",
                  desc: "Izinkan auto-remediasi low-risk di dalam boundary terdaftar tanpa interupsi.",
                  icon: Sparkles,
                  color: "text-emerald-400",
                },
              ].map((opt) => {
                const Icon = opt.icon;
                const isSelected = (approvalPref?.mode || "ALWAYS_ASK") === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    disabled={savingPref}
                    onClick={() => handleUpdateApprovalMode(opt.id)}
                    className={`p-4 rounded-xl border text-left transition flex flex-col justify-between space-y-2 ${
                      isSelected
                        ? "bg-cyan-500/10 border-cyan-500/40 shadow-[0_0_15px_rgba(6,182,212,0.1)]"
                        : "bg-neutral-950/60 border-white/[0.06] hover:border-white/20"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Icon size={16} className={opt.color} />
                        <span className="text-xs font-semibold text-white">{opt.title}</span>
                      </div>
                      {isSelected && <CheckCircle2 size={14} className="text-cyan-400" />}
                    </div>
                    <p className="text-[11px] text-neutral-400 leading-relaxed">{opt.desc}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <GlobalSettingsPanel />
          </div>

          <div>
            <LocationPanel />
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* MODAL: ADD MEMORY                                             */}
      {/* ============================================================== */}
      {showAddMemoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-md bg-neutral-900 border border-white/[0.1] rounded-2xl p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Brain size={16} className="text-purple-400" />
                <span>Tambah Catatan Memori Personal</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowAddMemoryModal(false)}
                className="text-neutral-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleAddMemory} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">Isi Catatan Memori</label>
                <textarea
                  rows={3}
                  required
                  value={newMemoryContent}
                  onChange={(e) => setNewMemoryContent(e.target.value)}
                  placeholder="Contoh: Saya selalu menggunakan subnet 10.200.0.0/16 untuk segmen manajemen perangkat..."
                  className="w-full p-3 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">Kategori</label>
                  <select
                    value={newMemoryCategory}
                    onChange={(e) => setNewMemoryCategory(e.target.value)}
                    className="w-full p-2.5 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="general">General</option>
                    <option value="technical">Technical</option>
                    <option value="project">Project</option>
                    <option value="workflows">Workflows</option>
                    <option value="learning">Learning</option>
                    <option value="communication">Communication</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">Tingkat Penting (1-100)</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={newMemoryImportance}
                    onChange={(e) => setNewMemoryImportance(e.target.value)}
                    className="w-full p-2.5 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddMemoryModal(false)}
                  className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-xs font-semibold text-neutral-300 rounded-xl transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={savingMemory}
                  className="flex items-center gap-1.5 px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-neutral-950 text-xs font-semibold rounded-xl transition disabled:opacity-50"
                >
                  {savingMemory ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  <span>Simpan Memori</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* MODAL: CREATE CUSTOM PERSONA                                  */}
      {/* ============================================================== */}
      {showAddPersonaModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-neutral-900 border border-white/[0.1] rounded-2xl p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Sparkles size={16} className="text-cyan-400" />
                <span>Buat Persona Kustom Baru</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowAddPersonaModal(false)}
                className="text-neutral-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleCreateCustomPersona} className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">Nama Persona</label>
                <input
                  type="text"
                  required
                  placeholder="Misal: Senior Cisco Architect / SRE Tutor"
                  value={newPersonaName}
                  onChange={(e) => setNewPersonaName(e.target.value)}
                  className="w-full p-2.5 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">Gaya Respon</label>
                  <select
                    value={newPersonaStyle}
                    onChange={(e) => setNewPersonaStyle(e.target.value)}
                    className="w-full p-2 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="concise">Concise (Singkat padat)</option>
                    <option value="detailed">Detailed (Komprehensif)</option>
                    <option value="technical">Technical (Full CLI/Spesifikasi)</option>
                    <option value="instructive">Instructive (Pedagogis)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">Pendekatan Penjelasan</label>
                  <select
                    value={newPersonaPreference}
                    onChange={(e) => setNewPersonaPreference(e.target.value)}
                    className="w-full p-2 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="technical">Technical First</option>
                    <option value="visual">Visual & Topologi</option>
                    <option value="step-by-step">Step-by-step Guided</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">Bahasa</label>
                  <select
                    value={newPersonaLanguage}
                    onChange={(e) => setNewPersonaLanguage(e.target.value)}
                    className="w-full p-2 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="id">Bahasa Indonesia</option>
                    <option value="en">English</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-300 mb-1">Kedalaman Teknis ({newPersonaDepth}%)</label>
                  <input
                    type="range"
                    min={10}
                    max={100}
                    value={newPersonaDepth}
                    onChange={(e) => setNewPersonaDepth(e.target.value)}
                    className="w-full accent-cyan-400 mt-2"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">Instruksi Khusus Persona</label>
                <textarea
                  rows={3}
                  value={newPersonaInstructions}
                  onChange={(e) => setNewPersonaInstructions(e.target.value)}
                  placeholder="Instruksi tambahan yang mendefinisikan kepribadian atau batasan teknis..."
                  className="w-full p-2.5 bg-neutral-950 border border-white/[0.08] rounded-xl text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddPersonaModal(false)}
                  className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-xs font-semibold text-neutral-300 rounded-xl transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={savingPersona}
                  className="flex items-center gap-1.5 px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-neutral-950 text-xs font-semibold rounded-xl transition disabled:opacity-50"
                >
                  {savingPersona ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                  <span>Buat Persona</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* MODAL: PROMPT PREVIEW                                          */}
      {/* ============================================================== */}
      {previewPersonaText && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-lg bg-neutral-900 border border-white/[0.1] rounded-2xl p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Eye size={16} className="text-cyan-400" />
                <span>Preview Prompt Sistem Persona</span>
              </h3>
              <button
                type="button"
                onClick={() => setPreviewPersonaText(null)}
                className="text-neutral-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <pre className="p-4 bg-neutral-950 rounded-xl text-xs font-mono text-cyan-300 whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto border border-white/[0.06]">
              {previewPersonaText}
            </pre>

            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={() => setPreviewPersonaText(null)}
                className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-xs font-semibold text-neutral-200 rounded-xl transition"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* CONFIRMATION MODAL (DANGER ZONE)                              */}
      {/* ============================================================== */}
      {confirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-md bg-neutral-900 border border-rose-500/30 rounded-2xl p-5 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-rose-400">
              <ShieldAlert size={20} />
              <h3 className="text-sm font-bold">{confirmModal.title}</h3>
            </div>
            <p className="text-xs text-neutral-300 leading-relaxed">{confirmModal.description}</p>

            <div className="flex justify-end gap-2 pt-3 border-t border-white/[0.08]">
              <button
                type="button"
                disabled={actionInProgress}
                onClick={() => setConfirmModal(null)}
                className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 text-xs font-semibold text-neutral-300 rounded-xl transition"
              >
                Batal
              </button>
              <button
                type="button"
                disabled={actionInProgress}
                onClick={executeDangerousAction}
                className="flex items-center gap-1.5 px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-xl transition disabled:opacity-50"
              >
                {actionInProgress && <Loader2 size={13} className="animate-spin" />}
                <span>{confirmModal.confirmText}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
