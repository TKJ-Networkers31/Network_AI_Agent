import { useModalDialog } from "../context/ModalDialogContext.jsx";
// src/pages/AdminPlatformPage.jsx
// AIRA OS — AIRA Control Plane (Admin Site)
// Phase F.1: Architecture Simplification, MikroTik-Style Group RBAC & User Activity Monitoring

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  Copy,
  Cpu,
  Database,
  Edit2,
  ExternalLink,
  Eye,
  FileText,
  Globe,
  Key,
  Layers,
  Lock,
  Network,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Server,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  Terminal,
  ToggleLeft,
  ToggleRight,
  Trash2,
  UserCheck,
  UserMinus,
  Users,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";
import { getAuthHeaders } from "../api.js";

const CONTROL_PLANE_MODULES = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "users", label: "User Management", icon: Users },
  { id: "groups", label: "Groups & Permissions", icon: ShieldCheck },
  { id: "ai_policy", label: "AI Operations Policy", icon: Sliders },
  { id: "activity", label: "Activity & Sessions", icon: Activity },
];

export default function AdminPlatformPage({ onOpenMenu }) {
  const { alert: modalAlert, confirm: modalConfirm, prompt: modalPrompt } = useModalDialog();

  const [activeModule, setActiveModule] = useState("overview");

  // Data states
  const [users, setUsers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activityEvents, setActivityEvents] = useState([]);
  const [deviceCount, setDeviceCount] = useState(0);
  const [loading, setLoading] = useState(false);

  // AI Operations Policy states (Phase G)
  const [policyData, setPolicyData] = useState({
    tenant_id: "tenant_internal",
    default_execution_mode: "SEMI_AUTONOMOUS",
    max_autonomous_risk_level: "LOW",
    require_human_approval_for_high_risk: true,
    require_human_approval_for_critical: true,
    enforce_rollback_plan: true,
    min_verification_checks: 1,
    audit_retention_days: 90,
    allowed_action_types_per_risk: {
      READ_ONLY: ["TELEMETRY_POLL", "ROUTE_PRINT", "PING_CHECK", "INTERFACE_STATUS"],
      LOW: ["INTERFACE_COMMENT", "NTP_UPDATE"],
      MEDIUM: ["DISABLE_UNUSED_PORT", "STATIC_ROUTE_ADD"],
      HIGH: ["INTERFACE_DOWN", "FIREWALL_RULE_CHANGE"],
      CRITICAL: ["REBOOT", "ROUTER_OS_UPGRADE", "FACTORY_RESET"]
    }
  });
  const [policyLoading, setPolicyLoading] = useState(false);
  const [policySaving, setPolicySaving] = useState(false);

  const fetchAiPolicy = useCallback(async () => {
    setPolicyLoading(true);
    try {
      const res = await fetch("/api/intelligence/actions/policy?tenant_id=tenant_internal", {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.policy) setPolicyData(data.policy);
      }
    } catch (err) {
      console.warn("Fetch policy error:", err);
    } finally {
      setPolicyLoading(false);
    }
  }, []);

  const handleSaveAiPolicy = async (e) => {
    if (e) e.preventDefault();
    setPolicySaving(true);
    try {
      const res = await fetch("/api/intelligence/actions/policy?tenant_id=tenant_internal", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify(policyData),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: "AI Operations Policy berhasil diperbarui." });
        if (data.policy) setPolicyData(data.policy);
      } else {
        notify({ type: "error", message: data.detail || "Gagal menyimpan AI policy." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setPolicySaving(false);
    }
  };

  // User Modals
  const [isCreateUserOpen, setIsCreateUserOpen] = useState(false);
  const [createUsername, setCreateUsername] = useState("");
  const [createDisplayName, setCreateDisplayName] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createGroup, setCreateGroup] = useState("NETWORK_ENGINEER");
  const [savingUser, setSavingUser] = useState(false);

  const [editUserTarget, setEditUserTarget] = useState(null);
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editGroup, setEditGroup] = useState("");
  const [editPassword, setEditPassword] = useState("");
  const [savingEditUser, setSavingEditUser] = useState(false);

  // Group Modals
  const [groupModalMode, setGroupModalMode] = useState(null); // 'create' | 'edit'
  const [activeGroupTarget, setActiveGroupTarget] = useState(null);
  const [groupName, setGroupName] = useState("");
  const [groupDesc, setGroupDesc] = useState("");
  const [groupPermMatrix, setGroupPermMatrix] = useState({}); // { permId: 'ALLOW' | 'DENY' }
  const [savingGroup, setSavingGroup] = useState(false);

  const { notify } = useToast();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = getAuthHeaders();
      const [uRes, gRes, pRes, sRes, actRes, devRes] = await Promise.all([
        fetch("/api/v1/admin/users", { headers }).then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/groups", { headers }).then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/permissions", { headers }).then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/sessions", { headers }).then((r) => r.json()).catch(() => ({})),
        fetch("/api/v1/admin/activity?limit=100", { headers }).then((r) => r.json()).catch(() => ({})),
        fetch("/api/devices", { headers }).then((r) => r.json()).catch(() => ({})),
      ]);

      if (uRes.users) setUsers(uRes.users);
      if (gRes.groups) setGroups(gRes.groups);
      if (pRes.permissions) setPermissions(pRes.permissions);
      if (sRes.sessions) setSessions(sRes.sessions);
      if (actRes.events) setActivityEvents(actRes.events);
      if (devRes && (devRes.count !== undefined || devRes.devices)) {
        setDeviceCount(devRes.count ?? devRes.devices?.length ?? 0);
      }
    } catch (err) {
      console.warn("Error loading admin data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    fetchAiPolicy();
  }, [loadData, fetchAiPolicy]);

  // Periodic heartbeat / session refresh
  useEffect(() => {
    const timer = setInterval(() => {
      if (activeModule === "activity" || activeModule === "users") {
        loadData();
      }
    }, 15000);
    return () => clearInterval(timer);
  }, [activeModule, loadData]);

  // --------------------------------------------------------------------------
  // User Actions
  // --------------------------------------------------------------------------
  async function handleCreateUser(e) {
    e.preventDefault();
    if (!createUsername.trim() || !createPassword.trim()) {
      notify({ type: "error", message: "Username dan password wajib diisi." });
      return;
    }
    setSavingUser(true);
    try {
      const res = await fetch("/api/v1/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          username: createUsername.trim(),
          display_name: createDisplayName.trim() || createUsername.trim(),
          password: createPassword,
          group_name: createGroup,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: `Pengguna '${data.username}' berhasil dibuat.` });
        setIsCreateUserOpen(false);
        setCreateUsername("");
        setCreateDisplayName("");
        setCreatePassword("");
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal membuat pengguna." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingUser(false);
    }
  }

  async function handleUpdateUser(e) {
    e.preventDefault();
    if (!editUserTarget) return;
    setSavingEditUser(true);
    try {
      const body = {
        display_name: editDisplayName.trim(),
        group: editGroup,
      };
      if (editPassword.trim()) {
        body.password = editPassword.trim();
      }
      const res = await fetch(`/api/v1/admin/users/${editUserTarget.user_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: `Profil '${data.username}' berhasil diperbarui.` });
        setEditUserTarget(null);
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal memperbarui pengguna." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingEditUser(false);
    }
  }

  async function handleToggleUserStatus(user) {
    const nextStatus = !user.account_enabled;
    const actionLabel = nextStatus ? "mengaktifkan" : "menonaktifkan";
    if (!nextStatus && !await modalConfirm({ message: `Yakin ingin ${actionLabel} akun ${user.username}? Semua sesi aktif akan langsung dicabut.`, isDestructive: true })) {
      return;
    }
    try {
      const res = await fetch(`/api/v1/admin/users/${user.user_id}/toggle-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ enabled: nextStatus }),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: data.message });
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal mengubah status akun." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleRevokeUserSessions(userId, username) {
    if (!await modalConfirm({ message: `Cabut seluruh sesi login aktif untuk user '${username}'?`, isDestructive: true })) return;
    try {
      const res = await fetch(`/api/v1/admin/users/${userId}/sessions`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: `${data.revoked_count} sesi untuk '${username}' berhasil dicabut.` });
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal mencabut sesi." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleRevokeSingleSession(sessionId) {
    if (!await modalConfirm({ message: "Cabut sesi ini sekarang?", isDestructive: true })) return;
    try {
      const res = await fetch(`/api/v1/admin/sessions/${sessionId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: "Sesi berhasil dicabut." });
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal mencabut sesi." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  // --------------------------------------------------------------------------
  // Group Actions (MikroTik Style)
  // --------------------------------------------------------------------------
  function openCreateGroupModal() {
    setGroupModalMode("create");
    setActiveGroupTarget(null);
    setGroupName("");
    setGroupDesc("");
    setGroupPermMatrix({});
  }

  async function openEditGroupModal(group) {
    setGroupModalMode("edit");
    setActiveGroupTarget(group);
    setGroupName(group.name);
    setGroupDesc(group.description || "");

    // Fetch full permission matrix for this group
    try {
      const res = await fetch(`/api/v1/admin/groups/${group.group_id}`, { headers: getAuthHeaders() });
      const data = await res.json();
      if (res.ok) {
        setGroupPermMatrix(data.permissions || {});
      }
    } catch {
      setGroupPermMatrix({});
    }
  }

  function handleSetPermEffect(permId, effect) {
    // effect: 'ALLOW' | 'DENY' | 'NONE'
    setGroupPermMatrix((prev) => {
      const copy = { ...prev };
      if (!effect || effect === "NONE") {
        delete copy[permId];
      } else {
        copy[permId] = effect;
      }
      return copy;
    });
  }

  async function handleSaveGroup(e) {
    e.preventDefault();
    if (!groupName.trim()) {
      notify({ type: "error", message: "Nama grup wajib diisi." });
      return;
    }
    setSavingGroup(true);
    try {
      const permList = Object.entries(groupPermMatrix).map(([pid, eff]) => ({
        permission_id: pid,
        effect: eff,
      }));

      let res;
      if (groupModalMode === "create") {
        res = await fetch("/api/v1/admin/groups", {
          method: "POST",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({
            name: groupName.trim(),
            description: groupDesc.trim(),
            permissions: permList,
          }),
        });
      } else {
        res = await fetch(`/api/v1/admin/groups/${activeGroupTarget.group_id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...getAuthHeaders() },
          body: JSON.stringify({
            name: groupName.trim(),
            description: groupDesc.trim(),
            permissions: permList,
          }),
        });
      }
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: `Grup '${data.name}' berhasil disimpan.` });
        setGroupModalMode(null);
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal menyimpan grup." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingGroup(false);
    }
  }

  async function handleDuplicateGroup(group) {
    const newName = await modalPrompt({ message: `Masukkan nama untuk duplikasi grup '${group.name}':`, defaultValue: `${group.name}_Copy` });
    if (!newName || !newName.trim()) return;

    try {
      const res = await fetch(`/api/v1/admin/groups/${group.group_id}/duplicate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ new_name: newName.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: `Grup duplikat '${data.name}' berhasil dibuat.` });
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal menduplikasi grup." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleDeleteGroup(group) {
    if (!await modalConfirm({ message: `Hapus grup '${group.name}'? Anggota grup akan kehilangan akses dari grup ini.`, isDestructive: true })) return;
    try {
      const res = await fetch(`/api/v1/admin/groups/${group.group_id}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      const data = await res.json();
      if (res.ok) {
        notify({ type: "success", message: `Grup '${group.name}' telah dihapus.` });
        loadData();
      } else {
        notify({ type: "error", message: data.detail || "Gagal menghapus grup." });
      }
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  // Group permissions by module
  const permissionsByModule = permissions.reduce((acc, p) => {
    const mod = p.module || "General";
    if (!acc[mod]) acc[mod] = [];
    acc[mod].push(p);
    return acc;
  }, {});

  // Online count
  const onlineCount = users.filter((u) => u.is_online).length;

  return (
    <div className="flex flex-col h-full bg-[#0d0d10] text-neutral-200">
      <TopBar onOpenMenu={onOpenMenu} title="AIRA Control Plane" />

      {/* Control Plane Horizontal Subnav */}
      <div className="flex items-center gap-1.5 px-6 py-2.5 border-b border-white/[0.08] bg-black/40 overflow-x-auto text-xs shrink-0">
        {CONTROL_PLANE_MODULES.map((m) => {
          const Icon = m.icon;
          const active = activeModule === m.id;
          return (
            <button
              key={m.id}
              onClick={() => setActiveModule(m.id)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-medium transition shrink-0 ${
                active
                  ? "bg-rose-500/15 text-rose-300 border border-rose-500/30 shadow-sm shadow-rose-950/30"
                  : "text-neutral-400 hover:text-white hover:bg-white/[0.04]"
              }`}
            >
              <Icon size={14} className={active ? "text-rose-400" : "text-neutral-400"} />
              <span>{m.label}</span>
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-2 pl-4">
          <button
            onClick={loadData}
            title="Refresh Data"
            className="p-1.5 rounded-lg bg-white/[0.04] text-neutral-400 hover:text-white transition"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Main Module Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* 1. OVERVIEW */}
        {activeModule === "overview" && (
          <div className="space-y-6">
            {/* KPI Cards Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div
                onClick={() => setActiveModule("users")}
                className="group p-4 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-white/5 hover:border-white/10 cursor-pointer transition space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="text-[11px] text-neutral-400 uppercase tracking-wider font-medium">Pengguna Terdaftar</div>
                  <Users size={16} className="text-neutral-500 group-hover:text-rose-400 transition" />
                </div>
                <div className="text-2xl font-bold text-white tracking-tight">{users.length}</div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-emerald-400 flex items-center gap-1 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    {onlineCount} Online Saat Ini
                  </span>
                  <span className="text-neutral-500 group-hover:text-neutral-300 flex items-center gap-0.5 text-[10px]">
                    Kelola <ChevronRight size={12} />
                  </span>
                </div>
              </div>

              <div
                onClick={() => setActiveModule("groups")}
                className="group p-4 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-white/5 hover:border-white/10 cursor-pointer transition space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="text-[11px] text-neutral-400 uppercase tracking-wider font-medium">Grup & Matriks Izin</div>
                  <ShieldCheck size={16} className="text-neutral-500 group-hover:text-rose-400 transition" />
                </div>
                <div className="text-2xl font-bold text-rose-400 tracking-tight">{groups.length}</div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-neutral-400">
                    {groups.filter((g) => g.is_system).length} Sistem + {groups.filter((g) => !g.is_system).length} Kustom
                  </span>
                  <span className="text-neutral-500 group-hover:text-neutral-300 flex items-center gap-0.5 text-[10px]">
                    Atur <ChevronRight size={12} />
                  </span>
                </div>
              </div>

              <div
                onClick={() => setActiveModule("activity")}
                className="group p-4 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-white/5 hover:border-white/10 cursor-pointer transition space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="text-[11px] text-neutral-400 uppercase tracking-wider font-medium">Sesi Login Aktif</div>
                  <Activity size={16} className="text-neutral-500 group-hover:text-cyan-400 transition" />
                </div>
                <div className="text-2xl font-bold text-cyan-400 tracking-tight">{sessions.length}</div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-cyan-300 flex items-center gap-1 font-medium">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                    Live Heartbeat
                  </span>
                  <span className="text-neutral-500 group-hover:text-neutral-300 flex items-center gap-0.5 text-[10px]">
                    Periksa <ChevronRight size={12} />
                  </span>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="text-[11px] text-neutral-400 uppercase tracking-wider font-medium">Node Jaringan</div>
                  <Network size={16} className="text-emerald-400" />
                </div>
                <div className="text-2xl font-bold text-emerald-400 tracking-tight">{deviceCount}</div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-emerald-400">Inventory Terpusat</span>
                  <span className="text-neutral-500 text-[10px]">Shared Infra</span>
                </div>
              </div>
            </div>

            {/* Subsystems & Quick Actions Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left (2 cols): Subsystems Health Cockpit */}
              <div className="lg:col-span-2 p-5 rounded-xl bg-black/40 border border-white/5 space-y-4">
                <div className="flex items-center justify-between border-b border-white/5 pb-3">
                  <div className="flex items-center gap-2">
                    <Cpu size={15} className="text-rose-400" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-300">
                      Subsystems Health & Security Status
                    </h3>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    ALL SYSTEMS NOMINAL
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-neutral-400 flex items-center gap-1.5">
                        <Server size={13} className="text-neutral-500" /> API Gateway Core
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        OPERATIONAL
                      </span>
                    </div>
                    <div className="text-[11px] text-neutral-300 font-medium">FastAPI Engine (Port 8000)</div>
                    <div className="text-[10px] text-neutral-500">Rest API, SSE Event Stream, Interceptors</div>
                  </div>

                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-neutral-400 flex items-center gap-1.5">
                        <Database size={13} className="text-neutral-500" /> Database Engine
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        WAL ACTIVE
                      </span>
                    </div>
                    <div className="text-[11px] text-neutral-300 font-medium">SQLite Write-Ahead Logging</div>
                    <div className="text-[10px] text-neutral-500">Single-writer, multi-reader concurrent pool</div>
                  </div>

                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-neutral-400 flex items-center gap-1.5">
                        <ShieldCheck size={13} className="text-neutral-500" /> AI Tool RBAC Barrier
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        STRICT
                      </span>
                    </div>
                    <div className="text-[11px] text-neutral-300 font-medium">MikroTik-Style Access Gate</div>
                    <div className="text-[10px] text-neutral-500">DENY overrides ALLOW, verified every tool invocation</div>
                  </div>

                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-neutral-400 flex items-center gap-1.5">
                        <Network size={13} className="text-neutral-500" /> Inventory & Topology
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        CONNECTED
                      </span>
                    </div>
                    <div className="text-[11px] text-neutral-300 font-medium">{deviceCount} Managed Network Nodes</div>
                    <div className="text-[10px] text-neutral-500">Shared topology discovery, SSH/API drivers</div>
                  </div>
                </div>

                <div className="pt-2 text-xs text-neutral-400 border-t border-white/5 flex items-center justify-between">
                  <span>Root Superadmin: <strong className="text-amber-300 font-mono">lingga_admin</strong> (Akses Penuh 56 Permissions)</span>
                  <span className="text-[10px] text-neutral-500">Platform ID: aira-core-v2</span>
                </div>
              </div>

              {/* Right (1 col): Quick Administrative Actions */}
              <div className="p-5 rounded-xl bg-black/40 border border-white/5 flex flex-col justify-between space-y-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Zap size={15} className="text-amber-400" />
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-300">
                      Pintasan Tindakan
                    </h3>
                  </div>
                  <p className="text-[11px] text-neutral-400">Aksi cepat manajemen platform dan operasional.</p>
                </div>

                <div className="space-y-2">
                  <button
                    onClick={() => setIsCreateUserOpen(true)}
                    className="w-full flex items-center justify-between p-2.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-300 text-xs font-medium transition"
                  >
                    <span className="flex items-center gap-2">
                      <Plus size={14} /> Tambah Pengguna Baru
                    </span>
                    <ChevronRight size={14} />
                  </button>

                  <button
                    onClick={openCreateGroupModal}
                    className="w-full flex items-center justify-between p-2.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 text-neutral-200 text-xs font-medium transition"
                  >
                    <span className="flex items-center gap-2">
                      <Shield size={14} className="text-amber-400" /> Buat Grup Hak Akses
                    </span>
                    <ChevronRight size={14} />
                  </button>

                  <button
                    onClick={() => setActiveModule("activity")}
                    className="w-full flex items-center justify-between p-2.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 text-neutral-200 text-xs font-medium transition"
                  >
                    <span className="flex items-center gap-2">
                      <Activity size={14} className="text-cyan-400" /> Periksa Sesi & Audit Trail
                    </span>
                    <ChevronRight size={14} />
                  </button>

                  <button
                    onClick={() => setActiveModule("users")}
                    className="w-full flex items-center justify-between p-2.5 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] border border-white/5 text-neutral-200 text-xs font-medium transition"
                  >
                    <span className="flex items-center gap-2">
                      <Users size={14} className="text-emerald-400" /> Kelola Direktori Akun
                    </span>
                    <ChevronRight size={14} />
                  </button>
                </div>

                <div className="p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/10 text-[11px] text-amber-300/80">
                  Semua akun terisolasi secara riwayat chat & persona, namun berbagi infrastruktur perangkat bersama.
                </div>
              </div>
            </div>

            {/* Recent Activity Audit Trail */}
            <div className="p-5 rounded-xl bg-black/40 border border-white/5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock size={15} className="text-neutral-400" />
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-300">
                    Audit Keamanan & Aktivitas Terkini
                  </h3>
                </div>
                <button
                  onClick={() => setActiveModule("activity")}
                  className="flex items-center gap-1 text-xs text-rose-400 hover:text-rose-300 font-medium transition"
                >
                  Lihat Semua ({activityEvents.length}) <ArrowRight size={12} />
                </button>
              </div>

              <div className="rounded-xl border border-white/5 bg-black/30 overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-white/[0.02] text-neutral-400 border-b border-white/5">
                    <tr>
                      <th className="py-2.5 px-4 font-medium">Waktu</th>
                      <th className="py-2.5 px-4 font-medium">Pengguna</th>
                      <th className="py-2.5 px-4 font-medium">Tipe Aktivitas</th>
                      <th className="py-2.5 px-4 font-medium">IP Address</th>
                      <th className="py-2.5 px-4 font-medium">Detail</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {activityEvents.slice(0, 6).map((evt) => (
                      <tr key={evt.event_id} className="hover:bg-white/[0.02]">
                        <td className="py-2.5 px-4 font-mono text-[11px] text-neutral-400">
                          {new Date(evt.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </td>
                        <td className="py-2.5 px-4 font-medium text-white flex items-center gap-1.5">
                          <span>{evt.username}</span>
                          {evt.username === "lingga_admin" && (
                            <span className="text-[9px] px-1 py-0.2 bg-amber-500/20 text-amber-300 rounded font-mono">
                              ROOT
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                              evt.event_type.includes("FAILED")
                                ? "bg-red-500/10 text-red-400 border-red-500/20"
                                : evt.event_type.includes("REVOKED") || evt.event_type.includes("DISABLED")
                                ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                                : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            }`}
                          >
                            {evt.event_type}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 text-neutral-400 font-mono text-[11px]">
                          {evt.ip_address || "127.0.0.1"}
                        </td>
                        <td className="py-2.5 px-4 font-mono text-[10px] text-neutral-400 truncate max-w-xs">
                          {JSON.stringify(evt.details || {})}
                        </td>
                      </tr>
                    ))}
                    {activityEvents.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-neutral-500">
                          Belum ada catatan aktivitas.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* 2. USER MANAGEMENT */}
        {activeModule === "users" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                User Directory ({users.length})
              </h3>
              <button
                onClick={() => setIsCreateUserOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 text-xs font-medium border border-rose-500/30 transition"
              >
                <Plus size={13} />
                <span>Tambah Pengguna</span>
              </button>
            </div>

            <div className="rounded-xl border border-white/5 bg-black/30 overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-white/[0.02] text-neutral-400 border-b border-white/5">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">Pengguna</th>
                    <th className="py-2.5 px-4 font-medium">Status Akun</th>
                    <th className="py-2.5 px-4 font-medium">Grup Akses</th>
                    <th className="py-2.5 px-4 font-medium">Aktivitas Terakhir</th>
                    <th className="py-2.5 px-4 font-medium">Login Terakhir</th>
                    <th className="py-2.5 px-4 font-medium text-right">Tindakan</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {users.map((u) => {
                    const isOnline = u.is_online;
                    const isDisabled = !u.account_enabled;

                    return (
                      <tr key={u.user_id} className="hover:bg-white/[0.02]">
                        <td className="py-3 px-4 font-medium text-white flex items-center gap-2">
                          <div
                            className={`w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold ${
                              isDisabled
                                ? "bg-red-500/20 text-red-400 border border-red-500/30"
                                : isOnline
                                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                : "bg-neutral-800 text-neutral-400 border border-neutral-700"
                            }`}
                          >
                            {u.username.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span>{u.username}</span>
                              {u.username === "lingga_admin" && (
                                <span className="text-[9px] px-1.5 py-0.2 bg-amber-500/20 text-amber-300 rounded font-mono">
                                  SUPERADMIN
                                </span>
                              )}
                            </div>
                            <div className="text-[10px] text-neutral-400">{u.display_name}</div>
                          </div>
                        </td>

                        <td className="py-3 px-4">
                          {isDisabled ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-red-500/10 text-red-400 border border-red-500/20">
                              <XCircle size={10} /> Disabled
                            </span>
                          ) : isOnline ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 animate-pulse">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Online
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-neutral-800 text-neutral-400 border border-neutral-700">
                              Offline
                            </span>
                          )}
                        </td>

                        <td className="py-3 px-4">
                          <div className="flex flex-wrap gap-1">
                            {(u.groups || []).map((g) => (
                              <span
                                key={g}
                                className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                                  g === "SUPER_ADMIN"
                                    ? "bg-amber-500/10 text-amber-300 border-amber-500/30"
                                    : g === "ADMIN"
                                    ? "bg-rose-500/10 text-rose-300 border-rose-500/30"
                                    : g === "NOC"
                                    ? "bg-blue-500/10 text-blue-300 border-blue-500/30"
                                    : g === "SOC"
                                    ? "bg-purple-500/10 text-purple-300 border-purple-500/30"
                                    : g === "NETWORK_ENGINEER"
                                    ? "bg-cyan-500/10 text-cyan-300 border-cyan-500/30"
                                    : "bg-white/5 text-neutral-400 border-white/10"
                                }`}
                              >
                                {g}
                              </span>
                            ))}
                          </div>
                        </td>

                        <td className="py-3 px-4 text-neutral-400 text-[11px]">
                          {u.last_activity_at ? new Date(u.last_activity_at).toLocaleString("id-ID") : "-"}
                        </td>

                        <td className="py-3 px-4 text-neutral-400 text-[11px]">
                          {u.last_login_at ? new Date(u.last_login_at).toLocaleString("id-ID") : "-"}
                        </td>

                        <td className="py-3 px-4 text-right space-x-2">
                          <button
                            onClick={() => {
                              setEditUserTarget(u);
                              setEditDisplayName(u.display_name || "");
                              setEditGroup(u.groups?.[0] || "READ_ONLY");
                              setEditPassword("");
                            }}
                            className="px-2.5 py-1 rounded bg-white/5 hover:bg-white/10 text-neutral-200 text-[11px] transition"
                          >
                            Edit
                          </button>

                          <button
                            onClick={() => handleRevokeUserSessions(u.user_id, u.username)}
                            title="Cabut seluruh sesi login user ini"
                            className="px-2.5 py-1 rounded bg-red-500/10 hover:bg-red-500/20 text-red-300 border border-red-500/20 text-[11px] transition"
                          >
                            Revoke Sesi
                          </button>

                          {u.username !== "lingga_admin" && (
                            <button
                              onClick={() => handleToggleUserStatus(u)}
                              className={`px-2.5 py-1 rounded text-[11px] border transition ${
                                u.account_enabled
                                  ? "bg-neutral-800 text-neutral-300 hover:bg-neutral-700 border-neutral-700"
                                  : "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border-emerald-500/30"
                              }`}
                            >
                              {u.account_enabled ? "Nonaktifkan" : "Aktifkan"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 3. GROUPS & PERMISSIONS (MikroTik Style) */}
        {activeModule === "groups" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                  Access Groups & Permission Matrix ({groups.length})
                </h3>
                <p className="text-[11px] text-neutral-400">
                  Manajemen izin modular seperti User Groups MikroTik RouterOS.
                </p>
              </div>
              <button
                onClick={openCreateGroupModal}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 text-xs font-medium border border-rose-500/30 transition"
              >
                <Plus size={13} />
                <span>Buat Grup Baru</span>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {groups.map((g) => (
                <div
                  key={g.group_id}
                  className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3 flex flex-col justify-between"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white text-sm flex items-center gap-1.5">
                        <Shield size={14} className={g.is_system ? "text-amber-400" : "text-rose-400"} />
                        {g.name}
                      </span>
                      {g.is_system ? (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                          SYSTEM
                        </span>
                      ) : (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-neutral-400 border border-white/10">
                          CUSTOM
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-neutral-400 line-clamp-2">{g.description || "Grup otorisasi sistem AIRA OS."}</p>
                  </div>

                  <div className="space-y-3 pt-2 border-t border-white/5 text-xs">
                    <div className="flex items-center justify-between text-neutral-400">
                      <span>Jumlah Anggota:</span>
                      <span className="font-semibold text-white">{g.member_count || 0} user</span>
                    </div>
                    <div className="flex items-center justify-between text-neutral-400">
                      <span>Izin Aktif:</span>
                      <span className="font-semibold text-emerald-400">{g.permission_count || 0} izin</span>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => openEditGroupModal(g)}
                        className="flex-1 py-1.5 rounded bg-white/5 hover:bg-white/10 text-neutral-200 text-center text-xs font-medium transition"
                      >
                        Edit Izin
                      </button>
                      <button
                        onClick={() => handleDuplicateGroup(g)}
                        title="Duplikasi Grup"
                        className="p-1.5 rounded bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white transition"
                      >
                        <Copy size={13} />
                      </button>
                      {!g.is_system && (
                        <button
                          onClick={() => handleDeleteGroup(g)}
                          title="Hapus Grup"
                          className="p-1.5 rounded bg-red-500/10 hover:bg-red-500/20 text-red-400 transition"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 4. ACTIVITY & SESSIONS */}
        {activeModule === "ai_policy" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-2xl bg-gradient-to-r from-neutral-900 via-neutral-900 to-rose-950/20 border border-white/10">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400">
                  <Sliders size={24} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white">AIRA Operations Policy Configuration</h3>
                  <p className="text-xs text-neutral-400">
                    Kebijakan tata kelola eksekusi otonom, approval matrix, validasi rollback, dan retensi audit log (Phase G).
                  </p>
                </div>
              </div>
              <button
                onClick={handleSaveAiPolicy}
                disabled={policySaving}
                className="px-4 py-2 rounded-xl bg-rose-500 hover:bg-rose-600 text-white text-xs font-semibold shadow-lg shadow-rose-500/20 transition flex items-center gap-1.5 disabled:opacity-50"
              >
                {policySaving ? <RefreshCw size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                <span>{policySaving ? "Menyimpan..." : "Simpan Perubahan Policy"}</span>
              </button>
            </div>

            <form onSubmit={handleSaveAiPolicy} className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Card 1: Execution Mode & Autonomous Threshold */}
              <div className="p-5 rounded-2xl bg-neutral-900/60 border border-white/10 space-y-4">
                <div className="flex items-center gap-2 pb-2 border-b border-white/5">
                  <Cpu size={16} className="text-rose-400" />
                  <h4 className="text-xs font-semibold text-white uppercase">Mode Eksekusi &amp; Batas Otonom</h4>
                </div>

                <div className="space-y-3 text-xs">
                  <div>
                    <label className="block text-neutral-400 mb-1">Default Execution Mode</label>
                    <select
                      value={policyData.default_execution_mode}
                      onChange={(e) => setPolicyData({ ...policyData, default_execution_mode: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white outline-none focus:border-rose-500"
                    >
                      <option value="RECOMMEND_ONLY">RECOMMEND_ONLY (Hanya rekomendasi &amp; analisis)</option>
                      <option value="SEMI_AUTONOMOUS">SEMI_AUTONOMOUS (Otonom untuk risiko rendah, approval untuk menengah ke atas)</option>
                      <option value="AUTONOMOUS">AUTONOMOUS (Otonom hingga batas ambang risiko)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-neutral-400 mb-1">Maximum Risk Level for Autonomous Execution</label>
                    <select
                      value={policyData.max_autonomous_risk_level}
                      onChange={(e) => setPolicyData({ ...policyData, max_autonomous_risk_level: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white outline-none focus:border-rose-500"
                    >
                      <option value="READ_ONLY">READ_ONLY (Hanya query &amp; telemetri)</option>
                      <option value="LOW">LOW (Tindakan berdampak minimal)</option>
                      <option value="MEDIUM">MEDIUM (Konfigurasi minor/rute)</option>
                    </select>
                    <p className="text-[10px] text-neutral-500 mt-1">
                      *Tindakan HIGH dan CRITICAL tidak pernah diizinkan dieksekusi secara otonom penuh tanpa persetujuan manusia.
                    </p>
                  </div>

                  <div>
                    <label className="block text-neutral-400 mb-1">Minimum Verification Checks Required</label>
                    <input
                      type="number"
                      min={1}
                      max={5}
                      value={policyData.min_verification_checks || 1}
                      onChange={(e) => setPolicyData({ ...policyData, min_verification_checks: parseInt(e.target.value) || 1 })}
                      className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white font-mono outline-none focus:border-rose-500"
                    />
                  </div>

                  <div>
                    <label className="block text-neutral-400 mb-1">Audit Log Retention Policy (Hari)</label>
                    <input
                      type="number"
                      min={30}
                      max={365}
                      value={policyData.audit_retention_days || 90}
                      onChange={(e) => setPolicyData({ ...policyData, audit_retention_days: parseInt(e.target.value) || 90 })}
                      className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white font-mono outline-none focus:border-rose-500"
                    />
                  </div>
                </div>
              </div>

              {/* Card 2: Mandatory Approvals & Rollback Enforcements */}
              <div className="p-5 rounded-2xl bg-neutral-900/60 border border-white/10 space-y-4">
                <div className="flex items-center gap-2 pb-2 border-b border-white/5">
                  <ShieldAlert size={16} className="text-amber-400" />
                  <h4 className="text-xs font-semibold text-white uppercase">Persetujuan Wajib &amp; Rollback Enforcement</h4>
                </div>

                <div className="space-y-3 text-xs">
                  {/* Non-Bypassable High Risk Approval */}
                  <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-amber-200">Mandatory Human Approval for HIGH Risk</div>
                      <div className="text-[11px] text-amber-300/70">Wajib persetujuan engineer sebelum eksekusi HIGH</div>
                    </div>
                    <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-mono font-bold">
                      LOCKED ON (NON-BYPASSABLE)
                    </span>
                  </div>

                  {/* Non-Bypassable Critical Risk Approval */}
                  <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-rose-200">Mandatory Human Approval for CRITICAL Risk</div>
                      <div className="text-[11px] text-rose-300/70">Reboot, firmware upgrade, router factory reset</div>
                    </div>
                    <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-mono font-bold">
                      LOCKED ON (NON-BYPASSABLE)
                    </span>
                  </div>

                  {/* Rollback Plan Enforcement */}
                  <div className="p-3 rounded-xl bg-white/5 border border-white/5 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-white">Rollback Plan Enforcement</div>
                      <div className="text-[11px] text-neutral-400">Tolak eksekusi mutasi jika tidak ada rencana rollback</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={!!policyData.enforce_rollback_plan}
                      onChange={(e) => setPolicyData({ ...policyData, enforce_rollback_plan: e.target.checked })}
                      className="w-4 h-4 rounded text-rose-500 focus:ring-rose-400"
                    />
                  </div>

                  {/* Tenant Scope Override */}
                  <div className="p-3 rounded-xl bg-white/5 border border-white/5 space-y-1">
                    <div className="font-semibold text-white">Tenant Policy Scope</div>
                    <div className="text-[11px] text-neutral-400 font-mono">
                      Current Target: {policyData.tenant_id} (Multi-Tenant Isolation)
                    </div>
                  </div>
                </div>
              </div>
            </form>
          </div>
        )}

        {activeModule === "activity" && (
          <div className="space-y-6">
            {/* Live Sessions */}
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                  Live Active Sessions ({sessions.length})
                </h3>
              </div>

              <div className="rounded-xl border border-white/5 bg-black/30 overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-white/[0.02] text-neutral-400 border-b border-white/5">
                    <tr>
                      <th className="py-2.5 px-4 font-medium">Session ID (Masked)</th>
                      <th className="py-2.5 px-4 font-medium">User</th>
                      <th className="py-2.5 px-4 font-medium">IP & User Agent</th>
                      <th className="py-2.5 px-4 font-medium">Aktivitas Terakhir</th>
                      <th className="py-2.5 px-4 font-medium">Status</th>
                      <th className="py-2.5 px-4 font-medium text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {sessions.map((s) => (
                      <tr key={s.session_id} className="hover:bg-white/[0.02]">
                        <td className="py-3 px-4 font-mono text-[11px] text-cyan-300">{s.masked_session_id}</td>
                        <td className="py-3 px-4 font-medium text-white">{s.username}</td>
                        <td className="py-3 px-4 text-neutral-400 text-[11px]">
                          <div>{s.ip_address || "127.0.0.1"}</div>
                          <div className="text-[10px] text-neutral-500 truncate max-w-xs">{s.user_agent || "Client Browser"}</div>
                        </td>
                        <td className="py-3 px-4 text-neutral-400 text-[11px]">
                          {s.last_activity_at ? new Date(s.last_activity_at).toLocaleString("id-ID") : "-"}
                        </td>
                        <td className="py-3 px-4">
                          {s.is_online ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 animate-pulse">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> ONLINE
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-neutral-800 text-neutral-400 border border-neutral-700">
                              IDLE / TIMEOUT
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleRevokeSingleSession(s.session_id)}
                            className="px-2.5 py-1 rounded bg-red-500/10 hover:bg-red-500/20 text-red-300 border border-red-500/20 text-[11px] transition"
                          >
                            Cabut Sesi
                          </button>
                        </td>
                      </tr>
                    ))}
                    {sessions.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-neutral-500">
                          Tidak ada sesi aktif saat ini.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Audit Log */}
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                Security & Activity Audit Log ({activityEvents.length})
              </h3>
              <div className="rounded-xl border border-white/5 bg-black/30 overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-white/[0.02] text-neutral-400 border-b border-white/5">
                    <tr>
                      <th className="py-2.5 px-4 font-medium">Waktu (UTC/WIB)</th>
                      <th className="py-2.5 px-4 font-medium">Username</th>
                      <th className="py-2.5 px-4 font-medium">Tipe Aktivitas</th>
                      <th className="py-2.5 px-4 font-medium">IP Address</th>
                      <th className="py-2.5 px-4 font-medium">Detail</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {activityEvents.map((evt) => (
                      <tr key={evt.event_id} className="hover:bg-white/[0.02]">
                        <td className="py-2.5 px-4 font-mono text-[11px] text-neutral-400">
                          {new Date(evt.created_at).toLocaleString("id-ID")}
                        </td>
                        <td className="py-2.5 px-4 font-medium text-white">{evt.username}</td>
                        <td className="py-2.5 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                              evt.event_type.includes("FAILED")
                                ? "bg-red-500/10 text-red-400 border-red-500/20"
                                : evt.event_type.includes("REVOKED") || evt.event_type.includes("DISABLED")
                                ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
                                : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            }`}
                          >
                            {evt.event_type}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 text-neutral-400 font-mono text-[11px]">
                          {evt.ip_address || "-"}
                        </td>
                        <td className="py-2.5 px-4 font-mono text-[10px] text-neutral-400 truncate max-w-xs">
                          {JSON.stringify(evt.details || {})}
                        </td>
                      </tr>
                    ))}
                    {activityEvents.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-neutral-500">
                          Belum ada catatan aktivitas.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* CREATE USER MODAL */}
      {isCreateUserOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-md rounded-2xl bg-neutral-900 border border-white/10 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Tambah Pengguna Baru</h3>
              <button onClick={() => setIsCreateUserOpen(false)} className="text-neutral-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateUser} className="space-y-3 text-xs">
              <div>
                <label className="block text-neutral-400 mb-1">Username *</label>
                <input
                  type="text"
                  required
                  value={createUsername}
                  onChange={(e) => setCreateUsername(e.target.value)}
                  placeholder="e.g. budi_noc"
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white placeholder-neutral-600 focus:outline-none focus:border-rose-500"
                />
              </div>
              <div>
                <label className="block text-neutral-400 mb-1">Nama Tampilan</label>
                <input
                  type="text"
                  value={createDisplayName}
                  onChange={(e) => setCreateDisplayName(e.target.value)}
                  placeholder="e.g. Budi Network Ops"
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white placeholder-neutral-600 focus:outline-none focus:border-rose-500"
                />
              </div>
              <div>
                <label className="block text-neutral-400 mb-1">Password *</label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={createPassword}
                  onChange={(e) => setCreatePassword(e.target.value)}
                  placeholder="Min. 6 karakter"
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white placeholder-neutral-600 focus:outline-none focus:border-rose-500"
                />
              </div>
              <div>
                <label className="block text-neutral-400 mb-1">Grup Akses Awal</label>
                <select
                  value={createGroup}
                  onChange={(e) => setCreateGroup(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-rose-500"
                >
                  {groups.map((g) => (
                    <option key={g.name} value={g.name}>
                      {g.name} — {g.description || "Grup Akses"}
                    </option>
                  ))}
                </select>
              </div>
              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsCreateUserOpen(false)}
                  className="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={savingUser}
                  className="px-4 py-2 rounded-lg bg-rose-500 hover:bg-rose-600 text-white font-medium disabled:opacity-50"
                >
                  {savingUser ? "Menyimpan..." : "Buat Pengguna"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT USER MODAL */}
      {editUserTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-md rounded-2xl bg-neutral-900 border border-white/10 p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Edit Pengguna: {editUserTarget.username}</h3>
              <button onClick={() => setEditUserTarget(null)} className="text-neutral-400 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleUpdateUser} className="space-y-3 text-xs">
              <div>
                <label className="block text-neutral-400 mb-1">Nama Tampilan</label>
                <input
                  type="text"
                  value={editDisplayName}
                  onChange={(e) => setEditDisplayName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-rose-500"
                />
              </div>
              <div>
                <label className="block text-neutral-400 mb-1">Grup Akses</label>
                <select
                  value={editGroup}
                  onChange={(e) => setEditGroup(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-rose-500"
                >
                  {groups.map((g) => (
                    <option key={g.name} value={g.name}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-neutral-400 mb-1">Reset Password (opsional)</label>
                <input
                  type="password"
                  value={editPassword}
                  onChange={(e) => setEditPassword(e.target.value)}
                  placeholder="Kosongkan jika tidak ingin mengubah password"
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white placeholder-neutral-600 focus:outline-none focus:border-rose-500"
                />
              </div>
              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditUserTarget(null)}
                  className="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={savingEditUser}
                  className="px-4 py-2 rounded-lg bg-rose-500 hover:bg-rose-600 text-white font-medium disabled:opacity-50"
                >
                  {savingEditUser ? "Menyimpan..." : "Simpan Perubahan"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CREATE / EDIT GROUP PERMISSION MATRIX MODAL (MikroTik Style) */}
      {groupModalMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
          <div className="w-full max-w-4xl max-h-[90vh] rounded-2xl bg-neutral-900 border border-white/10 p-6 flex flex-col shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-white/5 shrink-0">
              <div>
                <h3 className="text-sm font-semibold text-white">
                  {groupModalMode === "create" ? "Buat Grup Otorisasi Baru" : `Edit Izin Grup: ${activeGroupTarget?.name}`}
                </h3>
                <p className="text-[11px] text-neutral-400">
                  Matriks izin modular: ALLOW (izinkan), DENY (blokir mutlak), NONE (tidak diatur).
                </p>
              </div>
              <button onClick={() => setGroupModalMode(null)} className="text-neutral-400 hover:text-white">
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleSaveGroup} className="flex-1 flex flex-col overflow-hidden space-y-4">
              <div className="grid grid-cols-2 gap-3 shrink-0 text-xs">
                <div>
                  <label className="block text-neutral-400 mb-1">Nama Grup *</label>
                  <input
                    type="text"
                    required
                    disabled={activeGroupTarget?.name === "SUPER_ADMIN"}
                    value={groupName}
                    onChange={(e) => setGroupName(e.target.value)}
                    placeholder="e.g. TIER2_SUPPORT"
                    className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white placeholder-neutral-600 focus:outline-none focus:border-rose-500"
                  />
                </div>
                <div>
                  <label className="block text-neutral-400 mb-1">Deskripsi</label>
                  <input
                    type="text"
                    value={groupDesc}
                    onChange={(e) => setGroupDesc(e.target.value)}
                    placeholder="Deskripsi tugas dan tanggung jawab grup"
                    className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white placeholder-neutral-600 focus:outline-none focus:border-rose-500"
                  />
                </div>
              </div>

              {/* Permission Matrix Accordion / Table */}
              <div className="flex-1 overflow-y-auto pr-2 space-y-4">
                {Object.entries(permissionsByModule).map(([mod, perms]) => (
                  <div key={mod} className="rounded-xl border border-white/5 bg-black/30 overflow-hidden">
                    <div className="px-4 py-2 bg-white/[0.03] text-xs font-semibold text-neutral-300 border-b border-white/5 flex items-center justify-between">
                      <span>{mod}</span>
                      <span className="text-[10px] text-neutral-500 font-normal">{perms.length} izin</span>
                    </div>
                    <div className="divide-y divide-white/5 text-xs">
                      {perms.map((p) => {
                        const currentEffect = groupPermMatrix[p.permission_id] || "NONE";

                        return (
                          <div
                            key={p.permission_id}
                            className="px-4 py-2.5 flex items-center justify-between hover:bg-white/[0.01]"
                          >
                            <div className="pr-4">
                              <div className="font-mono text-[11px] text-white flex items-center gap-1.5">
                                <span>{p.permission_id}</span>
                              </div>
                              <div className="text-[10px] text-neutral-400">{p.description}</div>
                            </div>

                            <div className="flex items-center gap-1 shrink-0">
                              <button
                                type="button"
                                onClick={() => handleSetPermEffect(p.permission_id, "ALLOW")}
                                className={`px-2 py-0.5 rounded text-[10px] font-medium transition ${
                                  currentEffect === "ALLOW"
                                    ? "bg-emerald-500 text-white font-bold"
                                    : "bg-white/5 text-neutral-400 hover:text-emerald-300"
                                }`}
                              >
                                ALLOW
                              </button>
                              <button
                                type="button"
                                onClick={() => handleSetPermEffect(p.permission_id, "DENY")}
                                className={`px-2 py-0.5 rounded text-[10px] font-medium transition ${
                                  currentEffect === "DENY"
                                    ? "bg-red-500 text-white font-bold"
                                    : "bg-white/5 text-neutral-400 hover:text-red-300"
                                }`}
                              >
                                DENY
                              </button>
                              <button
                                type="button"
                                onClick={() => handleSetPermEffect(p.permission_id, "NONE")}
                                className={`px-2 py-0.5 rounded text-[10px] font-medium transition ${
                                  currentEffect === "NONE"
                                    ? "bg-neutral-700 text-white font-bold"
                                    : "bg-white/5 text-neutral-500 hover:text-neutral-300"
                                }`}
                              >
                                NONE
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-2 border-t border-white/5 flex items-center justify-between shrink-0">
                <div className="text-xs text-neutral-400">
                  Total izin ALLOW:{" "}
                  <strong className="text-emerald-400">
                    {Object.values(groupPermMatrix).filter((e) => e === "ALLOW").length}
                  </strong>{" "}
                  | DENY:{" "}
                  <strong className="text-red-400">
                    {Object.values(groupPermMatrix).filter((e) => e === "DENY").length}
                  </strong>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setGroupModalMode(null)}
                    className="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-300 text-xs"
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    disabled={savingGroup}
                    className="px-4 py-2 rounded-lg bg-rose-500 hover:bg-rose-600 text-white font-medium text-xs disabled:opacity-50"
                  >
                    {savingGroup ? "Menyimpan..." : "Simpan Matriks Izin"}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
