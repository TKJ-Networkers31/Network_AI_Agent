import { useModalDialog } from "../context/ModalDialogContext.jsx";
// src/pages/TopologyPage.jsx
// AIRA OS Topology Fabric V2: Evidence-Based Discovery, ISP Boundary Detection,
// Device Ownership Governance & Physical-Link Confidence Canvas.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { useToast } from "../components/Toast.jsx";
import { inventoryApi } from "../inventoryApi.js";
import TopologyNodeInspector from "../components/topology/TopologyNodeInspector.jsx";
import TopologyEdgeInspector from "../components/topology/TopologyEdgeInspector.jsx";
import SnmpSetupWizardModal from "../components/nms/SnmpSetupWizardModal.jsx";
import DeviceDetailModal from "../components/nms/DeviceDetailModal.jsx";
import {
  PolicySettingsModal,
  ReviewQueueModal,
  TopologyLegendOverlay,
} from "../components/topology/TopologyGovernanceModals.jsx";
import {
  API_BASE,
  CONFIDENCE_TIERS,
  DEVICE_COLORS,
  DEVICE_ICONS,
  DISCOVERY_MODES,
  FRESHNESS_BADGES,
  OWNERSHIP_BADGES,
  RELATIONSHIP_CLASSES,
  SCOPE_LABELS,
  STATUS_CONFIG,
  VIEW_MODES,
  computeCurvedEdgePath,
  formatRelativeTime,
  getLinkVisualConfig,
  getMultiLayerEdgeVisualConfig,
  normalizeEdge,
} from "../components/topology/topologyConstants.js";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Eye,
  GitBranch,
  History,
  Layers,
  Link2,
  Loader2,
  Network,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Sliders,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import TopologyHistoryModal from "../components/topology/TopologyHistoryModal.jsx";
import { getSnapshot } from "../components/topology/topologyHistoryApi.js";
import RouteHistoryModal from "../components/topology/RouteHistoryModal.jsx";
import MultiDeviceRouteInspector from "../components/topology/MultiDeviceRouteInspector.jsx";
import {
  fetchTopologyRouteOverlay,
  getOverlaySegmentVisualStyle,
} from "../components/topology/routeOverlayApi.js";

export default function TopologyPage({ onOpenMenu }) {
  const { alert: modalAlert, confirm: modalConfirm, prompt: modalPrompt } = useModalDialog();

  const { pushToast, notify } = useToast();
  const showToast = useCallback((msg, type = "info") => {
    if (typeof pushToast === "function") pushToast(msg, type);
    else if (typeof notify === "function") notify(msg, type);
  }, [pushToast, notify]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [refreshingStatus, setRefreshingStatus] = useState(false);
  const [data, setData] = useState({ nodes: [], links: [], stats: {}, policy: null, last_job: null });
  const [inventoryDevices, setInventoryDevices] = useState([]);

  // Discovery & View Governance Controls
  const [viewMode, setViewMode] = useState("internal_and_edge");
  const [discoveryMode, setDiscoveryMode] = useState("seed_only");
  const [seedDeviceName, setSeedDeviceName] = useState("");
  const policyInitRef = useRef(false);

  // Canvas & Filter States
  const [selectedNode, setSelectedNode] = useState(null);
  const [filterType, setFilterType] = useState("all");
  const [search, setSearch] = useState("");
  const [zoom, setZoom] = useState(1);
  const [legendOpen, setLegendOpen] = useState(false);

  // Phase 4.5: Multi-Layer Topology States
  const [layerFilters, setLayerFilters] = useState({
    physical: true,
    layer2: true,
    layer3: true,
    logical: true,
  });
  const [operStatusFilter, setOperStatusFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState("all");
  const [selectedEdge, setSelectedEdge] = useState(null);

  // Modals
  const [historyModalOpen, setHistoryModalOpen] = useState(false);
  const [routeHistoryModalOpen, setRouteHistoryModalOpen] = useState(false);
  const [activeSnapshotView, setActiveSnapshotView] = useState(null);
  const activeSnapshotViewRef = useRef(activeSnapshotView);
  activeSnapshotViewRef.current = activeSnapshotView;

  // WP 4.6.5: Non-Destructive Multi-Device Route Overlay States
  const [routeOverlayOpen, setRouteOverlayOpen] = useState(false);
  const [routeOverlaySource, setRouteOverlaySource] = useState("");
  const [routeOverlayDest, setRouteOverlayDest] = useState("");
  const [routeOverlayTable, setRouteOverlayTable] = useState("main");
  const [routeOverlayLoading, setRouteOverlayLoading] = useState(false);
  const [routeOverlayData, setRouteOverlayData] = useState(null);
  const [selectedRouteSegment, setSelectedRouteSegment] = useState(null);
  const routeOverlayReqRef = useRef(0);

  const handleLoadRouteOverlay = useCallback(async (overrideParams = {}) => {
    const reqId = ++routeOverlayReqRef.current;
    setRouteOverlayLoading(true);
    try {
      const payload = await fetchTopologyRouteOverlay({
        sourceDevice: overrideParams.sourceDevice ?? routeOverlaySource,
        destination: overrideParams.destination ?? routeOverlayDest,
        routingTable: overrideParams.routingTable ?? routeOverlayTable,
      });
      if (reqId !== routeOverlayReqRef.current) return;
      setRouteOverlayData(payload);
      const segs = payload?.overlay?.segments || [];
      setSelectedRouteSegment(segs.length > 0 ? segs[0] : null);
    } catch (err) {
      if (reqId === routeOverlayReqRef.current) {
        showToast(err.message || "Gagal memuat analisis jalur rute lintas-router.", "error");
      }
    } finally {
      if (reqId === routeOverlayReqRef.current) {
        setRouteOverlayLoading(false);
      }
    }
  }, [routeOverlaySource, routeOverlayDest, routeOverlayTable, showToast]);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [troubleshootModal, setTroubleshootModal] = useState(null);
  const [troubleshooting, setTroubleshooting] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [addNodeModal, setAddNodeModal] = useState(false);
  const [addLinkModal, setAddLinkModal] = useState(false);
  const [editNodeModal, setEditNodeModal] = useState(null);
  const [nmsDetailDeviceId, setNmsDetailDeviceId] = useState(null);
  const [nmsWizardDevice, setNmsWizardDevice] = useState(null);

  // Dragging node state
  const [draggingNodeId, setDraggingNodeId] = useState(null);
  const dragOffset = useRef({ x: 0, y: 0 });
  const canvasRef = useRef(null);

  const [newNodeForm, setNewNodeForm] = useState({
    name: "",
    identity: "",
    ip: "",
    mac: "",
    device_type: "router",
    status: "online",
    ownership_status: "owned",
    topology_scope: "enterprise_internal",
    register_inventory: true,
    port: 22,
    username: "admin",
    password: "",
    snmp_community: "",
    snmp_port: 161,
  });

  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [showAdvancedMgmt, setShowAdvancedMgmt] = useState(false);

  const [newLinkForm, setNewLinkForm] = useState({
    source_id: "",
    target_id: "",
    source_port: "ether1",
    target_port: "ether1",
    link_type: "ethernet",
    bandwidth: "1 Gbps",
  });

  // Load authorized inventory devices for Seed Router selector
  useEffect(() => {
    inventoryApi.devices
      .list()
      .then((res) => {
        if (res?.devices) {
          setInventoryDevices(res.devices.filter((d) => d.enabled !== false));
        }
      })
      .catch(() => {});
  }, []);

  const fetchTopology = useCallback(
    async (silent = false, overrideView = null) => {
      // Historical Snapshot Mode Isolation: Silent background polling must never overwrite snapshot canvas
      if (activeSnapshotViewRef.current && silent) {
        return;
      }
      if (!silent) setLoading(true);
      const vm = overrideView || viewMode;
      try {
        const res = await fetch(`${API_BASE}?view_mode=${encodeURIComponent(vm)}`);
        const json = await res.json();
        if (json.success) {
          setData(json);
          if (!policyInitRef.current && json.policy) {
            policyInitRef.current = true;
            if (json.policy.discovery_mode) setDiscoveryMode(json.policy.discovery_mode);
            if (json.policy.seed_device_id) setSeedDeviceName(json.policy.seed_device_id);
          }

          // Fokus otomatis jika dinavigasi dari halaman NMS
          try {
            const focusId = sessionStorage.getItem("aira_focus_topology_node");
            if (focusId && json.nodes) {
              const match = json.nodes.find((n) => n.id === focusId || n.name === focusId || n.ip === focusId);
              if (match) {
                setSelectedNode(match);
                sessionStorage.removeItem("aira_focus_topology_node");
              }
            }
          } catch {}
        }
      } catch {
        if (!silent) pushToast("Gagal memuat topologi jaringan.", "error");
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [viewMode, pushToast]
  );

  // Dragging ref agar draggingNodeId tidak me-remount effect polling dan memicu loading spinner
  const draggingRef = useRef(draggingNodeId);
  draggingRef.current = draggingNodeId;

  // Lightweight 30s single-flight status refresh
  useEffect(() => {
    let mounted = true;
    let timer = null;
    let inFlight = false;

    // Load awal saat mode tampilan berubah
    fetchTopology(false, viewMode);

    async function scheduleNext() {
      if (!mounted) return;
      if (!document.hidden && !draggingRef.current && !inFlight && !activeSnapshotViewRef.current) {
        inFlight = true;
        try {
          await fetchTopology(true, viewMode);
        } finally {
          inFlight = false;
        }
      }
      if (mounted) {
        timer = setTimeout(scheduleNext, 30000);
      }
    }

    timer = setTimeout(scheduleNext, 30000);

    function onVisibility() {
      if (!document.hidden && mounted && !draggingRef.current) {
        if (timer) clearTimeout(timer);
        scheduleNext();
      }
    }
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      mounted = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [fetchTopology, viewMode]);

  // Keep selectedNode synchronized with fresh server state
  useEffect(() => {
    if (!selectedNode) return;
    const updated = data.nodes.find((n) => n.id === selectedNode.id);
    if (updated) setSelectedNode(updated);
  }, [data.nodes]);

  const handleRefreshStatuses = async () => {
    if (activeSnapshotViewRef.current) {
      showToast("Refresh status dinonaktifkan dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    setRefreshingStatus(true);
    try {
      await fetch(`${API_BASE}/refresh-status`, { method: "POST" });
      await fetchTopology(true);
      pushToast("Kesegaran observasi & status perangkat diperbarui.", "success");
    } catch {
      pushToast("Gagal menyegarkan status.", "error");
    } finally {
      setRefreshingStatus(false);
    }
  };

  const handleClearTopology = async () => {
    if (activeSnapshotViewRef.current) {
      showToast("Topologi tidak dapat dikosongkan dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    if (!await modalConfirm({ message: "Kosongkan seluruh peta topologi, bukti observasi, dan antrean konflik?", isDestructive: true })) return;
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/clear?confirm=true`, { method: "DELETE" });
      const json = await res.json();
      if (res.ok && json.success) {
        pushToast("Topologi berhasil dikosongkan.", "success");
        setSelectedNode(null);
        fetchTopology();
      } else {
        pushToast(json.detail || "Gagal mengosongkan topologi.", "error");
      }
    } catch {
      pushToast("Gagal mengosongkan topologi.", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleSeedDemo = async () => {
    if (activeSnapshotViewRef.current) {
      showToast("Seed demo tidak dapat dimuat dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/seed-demo`, { method: "POST" });
      const json = await res.json();
      if (json.success) {
        pushToast("Sampel topologi V2 berhasil dimuat!", "success");
        fetchTopology();
      }
    } catch {
      pushToast("Gagal generate sampel topologi.", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDiscover = async () => {
    if (activeSnapshotViewRef.current) {
      showToast("Auto Discover dinonaktifkan dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    setDiscovering(true);
    try {
      const payload = { mode: discoveryMode };
      if (seedDeviceName) payload.device_name = seedDeviceName;

      const res = await fetch(`${API_BASE}/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (res.ok && json.success) {
        const limCount = json.limitations?.length || 0;
        pushToast(
          limCount > 0
            ? `${json.message} (${limCount} catatan batas visibilitas)`
            : json.message || "Evidence-based discovery selesai!",
          "success"
        );
        fetchTopology();
      } else {
        pushToast(json.detail || json.error || "Discovery gagal.", res.status === 409 ? "warning" : "error");
      }
    } catch {
      pushToast("Gagal memicu discovery (pastikan router resmi terdaftar di Devices).", "error");
    } finally {
      setDiscovering(false);
    }
  };

  const handleTestConnection = async () => {
    if (!newNodeForm.ip) {
      pushToast("Isi IP address terlebih dahulu untuk melakukan test koneksi.", "warning");
      return;
    }
    setTestingConnection(true);
    setTestResult(null);
    try {
      const res = await fetch(`${API_BASE}/nodes/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          host: newNodeForm.ip,
          port: parseInt(newNodeForm.port, 10) || 22,
          username: newNodeForm.username || "admin",
          password: newNodeForm.password || null,
          device_type: newNodeForm.device_type,
          snmp_community: newNodeForm.snmp_community || null,
          snmp_port: parseInt(newNodeForm.snmp_port, 10) || 161,
        }),
      });
      const data = await res.json();
      setTestResult(data);
      if (data.reachable) {
        if (data.authenticated) {
          pushToast(`Koneksi & Auth Berhasil! (${data.latency_ms} ms)`, "success");
          if (data.identity && !newNodeForm.identity) {
            setNewNodeForm((prev) => ({ ...prev, identity: data.identity }));
          }
        } else {
          pushToast(`Host terjangkau (${data.latency_ms} ms): ${data.message}`, "info");
        }
      } else {
        pushToast(`Perangkat tidak terjangkau: ${data.message}`, "error");
      }
    } catch (err) {
      pushToast("Gagal melakukan tes koneksi: " + (err?.message || err), "error");
    } finally {
      setTestingConnection(false);
    }
  };

  const handleCreateNode = async (e) => {
    e.preventDefault();
    if (activeSnapshotViewRef.current) {
      showToast("Tidak dapat menambahkan node dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    if (!newNodeForm.name) {
      pushToast("Nama perangkat wajib diisi.", "warning");
      return;
    }
    const id = `node_${Date.now()}`;
    try {
      const res = await fetch(`${API_BASE}/nodes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id,
          ...newNodeForm,
          port: parseInt(newNodeForm.port, 10) || 22,
          snmp_port: parseInt(newNodeForm.snmp_port, 10) || 161,
          pos_x: Math.round(400 + Math.random() * 90),
          pos_y: Math.round(240 + Math.random() * 90),
        }),
      });
      const json = await res.json();
      if (json.success) {
        pushToast(`Perangkat ${newNodeForm.name} ditambahkan & didaftarkan ke Inventory.`, "success");
        setAddNodeModal(false);
        setTestResult(null);
        setNewNodeForm({
          name: "",
          identity: "",
          ip: "",
          mac: "",
          device_type: "router",
          status: "online",
          ownership_status: "owned",
          topology_scope: "enterprise_internal",
          register_inventory: true,
          port: 22,
          username: "admin",
          password: "",
          snmp_community: "",
          snmp_port: 161,
        });
        fetchTopology();
      }
    } catch {
      pushToast("Gagal menambahkan perangkat.", "error");
    }
  };

  const handleCreateLink = async (e) => {
    e.preventDefault();
    if (activeSnapshotViewRef.current) {
      showToast("Tidak dapat menambah link dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    if (!newLinkForm.source_id || !newLinkForm.target_id) {
      pushToast("Pilih perangkat asal dan tujuan kabel.", "warning");
      return;
    }
    if (newLinkForm.source_id === newLinkForm.target_id) {
      pushToast("Perangkat asal dan tujuan tidak boleh sama.", "warning");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/links`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newLinkForm),
      });
      const json = await res.json();
      if (json.success) {
        pushToast("Wiring manual tersimpan & dilindungi dari penimpaan scan.", "success");
        setAddLinkModal(false);
        fetchTopology();
      }
    } catch {
      pushToast("Gagal menghubungkan kabel.", "error");
    }
  };

  const handleDeleteLink = async (linkId) => {
    if (activeSnapshotViewRef.current) {
      showToast("Tidak dapat menghapus link dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    if (!await modalConfirm({ message: "Putuskan link interkoneksi ini?", isDestructive: true })) return;
    try {
      const res = await fetch(`${API_BASE}/links?link_id=${encodeURIComponent(linkId)}`, {
        method: "DELETE",
      });
      const json = await res.json();
      if (json.success) {
        pushToast("Link berhasil dihapus.", "success");
        if (selectedEdge?.id === linkId) setSelectedEdge(null);
        fetchTopology();
      }
    } catch {
      pushToast("Gagal menghapus link.", "error");
    }
  };

  const handleDeleteNode = async (nodeId) => {
    if (activeSnapshotViewRef.current) {
      showToast("Tidak dapat menghapus node dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    if (!await modalConfirm({ message: "Hapus perangkat ini beserta link terhubung dari topologi?", isDestructive: true })) return;
    try {
      const res = await fetch(`${API_BASE}/nodes/${encodeURIComponent(nodeId)}`, { method: "DELETE" });
      const json = await res.json();
      if (json.success) {
        pushToast("Perangkat dihapus dari topologi.", "success");
        setSelectedNode(null);
        fetchTopology();
      }
    } catch {
      pushToast("Gagal menghapus perangkat.", "error");
    }
  };

  const handleSaveNodeEdit = async (e) => {
    e.preventDefault();
    if (activeSnapshotViewRef.current) {
      showToast("Tidak dapat mengedit node dalam mode riwayat snapshot (Read-only).", "warning");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/nodes/${encodeURIComponent(editNodeModal.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editNodeModal),
      });
      const json = await res.json();
      if (json.success) {
        pushToast("Koreksi perangkat tersimpan (Protected Override).", "success");
        setEditNodeModal(null);
        fetchTopology();
      }
    } catch {
      pushToast("Gagal menyimpan koreksi.", "error");
    }
  };

  const handleNodeMouseDown = (e, node) => {
    e.stopPropagation();
    setDraggingNodeId(node.id);
    setSelectedNode(node);
    dragOffset.current = {
      x: e.clientX / zoom - node.pos_x,
      y: e.clientY / zoom - node.pos_y,
    };
  };

  const handleCanvasMouseMove = (e) => {
    if (!draggingNodeId) return;
    const newX = Math.round(e.clientX / zoom - dragOffset.current.x);
    const newY = Math.round(e.clientY / zoom - dragOffset.current.y);
    setData((prev) => ({
      ...prev,
      nodes: prev.nodes.map((n) => (n.id === draggingNodeId ? { ...n, pos_x: newX, pos_y: newY } : n)),
    }));
  };

  const handleCanvasMouseUp = async () => {
    if (!draggingNodeId) return;
    const movedNode = data.nodes.find((n) => n.id === draggingNodeId);
    setDraggingNodeId(null);
    // In historical snapshot mode, dragging only updates local visual coordinates and does not mutate live positions
    if (movedNode && !activeSnapshotViewRef.current) {
      try {
        await fetch(`${API_BASE}/nodes/${encodeURIComponent(movedNode.id)}/position`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pos_x: movedNode.pos_x, pos_y: movedNode.pos_y }),
        });
      } catch {
        // silent fail
      }
    }
  };

  const handlePingNode = async (nodeId) => {
    setPinging(true);
    try {
      const res = await fetch(`${API_BASE}/nodes/${encodeURIComponent(nodeId)}/ping`, { method: "POST" });
      const json = await res.json();
      if (res.status === 429 || json.rate_limited) {
        pushToast(json.error || "Probe dibatasi cooldown rate-limit.", "warning");
      } else if (json.success) {
        pushToast(
          json.alive
            ? `Reachable via ICMP (${json.latency_ms} ms) — Ownership tidak berubah.`
            : "ICMP tidak merespons (Unreachable). Node tetap dipertahankan.",
          json.alive ? "success" : "warning"
        );
        fetchTopology(true);
      } else {
        pushToast(json.error || json.detail || "Gagal melakukan ping.", "error");
      }
    } catch {
      pushToast("Koneksi probe terputus.", "error");
    } finally {
      setPinging(false);
    }
  };

  const handleTroubleshoot = async (node) => {
    setTroubleshooting(true);
    setTroubleshootModal({ loading: true, node });
    try {
      const res = await fetch(`${API_BASE}/nodes/${encodeURIComponent(node.id)}/troubleshoot`);
      const json = await res.json();
      if (json.success) {
        setTroubleshootModal({ loading: false, node, ...json });
      } else {
        pushToast(json.detail || "Gagal melakukan troubleshooting.", "error");
        setTroubleshootModal(null);
      }
    } catch {
      pushToast("Gagal menganalisis jalur troubleshooting.", "error");
      setTroubleshootModal(null);
    } finally {
      setTroubleshooting(false);
    }
  };

  const handleLoadSnapshotOntoCanvas = async (snapshotId) => {
    try {
      const res = await getSnapshot(snapshotId, { include_graph: true });
      if (res.success && res.snapshot && res.snapshot.graph) {
        const graph = res.snapshot.graph;
        setData((prev) => ({
          ...prev,
          nodes: graph.nodes || [],
          links: graph.edges || [],
          edges: graph.edges || [],
          historicalEvidence: graph.evidence || [],
        }));
        const snapView = {
          snapshot_id: res.snapshot.snapshot_id,
          description: res.snapshot.description,
          created_at: res.snapshot.created_at,
        };
        activeSnapshotViewRef.current = snapView;
        setActiveSnapshotView(snapView);
        setSelectedNode(null);
        setSelectedEdge(null);
        setHistoryModalOpen(false);
        showToast(`Menampilkan snapshot ${snapshotId} di kanvas (Read-only).`, "info");
      }
    } catch (err) {
      showToast(`Gagal memuat snapshot ke kanvas: ${err.message}`, "error");
    }
  };

  const handleReturnToLiveTopology = async () => {
    activeSnapshotViewRef.current = null;
    setActiveSnapshotView(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    await fetchTopology(false);
    showToast("Kembali ke topologi jaringan aktif (live).", "success");
  };

  const filteredNodes = useMemo(() => {
    return data.nodes.filter((n) => {
      const matchType = filterType === "all" || n.device_type === filterType;
      const q = search.trim().toLowerCase();
      const matchSearch =
        !q ||
        n.name.toLowerCase().includes(q) ||
        (n.ip && n.ip.toLowerCase().includes(q)) ||
        (n.mac && n.mac.toLowerCase().includes(q)) ||
        (n.identity && n.identity.toLowerCase().includes(q));
      return matchType && matchSearch;
    });
  }, [data.nodes, filterType, search]);

  const nodesMap = useMemo(() => {
    const map = {};
    filteredNodes.forEach((n) => {
      map[n.id] = n;
    });
    return map;
  }, [filteredNodes]);

  // Multi-Layer Normalized Edges (Phase 4.5)
  const allNormalizedEdges = useMemo(() => {
    const rawList = data.edges && data.edges.length > 0 ? data.edges : data.links || [];
    const normalized = [];
    const seenIds = new Set();

    for (const item of rawList) {
      const norm = normalizeEdge(item);
      if (!norm || !norm.id) continue;
      if (!seenIds.has(norm.id)) {
        seenIds.add(norm.id);
        normalized.push(norm);
      }
    }

    if (data.links && data.edges && data.edges.length > 0) {
      for (const item of data.links) {
        const norm = normalizeEdge(item);
        if (!norm || !norm.id) continue;
        if (!seenIds.has(norm.id)) {
          seenIds.add(norm.id);
          normalized.push(norm);
        }
      }
    }

    return normalized;
  }, [data.edges, data.links]);

  // Layer Edge Counters for Control Badges
  const layerCounts = useMemo(() => {
    const counts = { physical: 0, layer2: 0, layer3: 0, logical: 0, total: 0 };
    for (const edge of allNormalizedEdges) {
      const srcId = edge.source_node_id || edge.source;
      const dstId = edge.target_node_id || edge.target;
      if (!nodesMap[srcId] || !nodesMap[dstId]) continue;
      const c = edge.relationship_class || RELATIONSHIP_CLASSES.PHYSICAL;
      if (counts[c] !== undefined) counts[c]++;
      counts.total++;
    }
    return counts;
  }, [allNormalizedEdges, nodesMap]);

  // Filtered Edges based on Layer, Operational Status, and Confidence Filters
  const visibleEdges = useMemo(() => {
    return allNormalizedEdges.filter((edge) => {
      const srcId = edge.source_node_id || edge.source;
      const dstId = edge.target_node_id || edge.target;
      if (!nodesMap[srcId] || !nodesMap[dstId]) return false;

      const relClass = edge.relationship_class || RELATIONSHIP_CLASSES.PHYSICAL;
      if (layerFilters[relClass] === false) return false;

      if (operStatusFilter !== "all") {
        const op = (edge.operational_status || edge.oper_status || edge.status || "up").toLowerCase();
        if (operStatusFilter === "up" && op !== "up") return false;
        if (operStatusFilter === "down" && op !== "down") return false;
        if (operStatusFilter === "degraded" && op !== "degraded" && op !== "warning") return false;
      }

      if (confidenceFilter !== "all") {
        const tier = (edge.confidence_tier || "medium").toLowerCase();
        if (confidenceFilter === "confirmed" && tier !== "confirmed") return false;
        if (confidenceFilter === "high" && tier !== "high") return false;
        if (confidenceFilter === "medium" && tier !== "medium") return false;
        if (confidenceFilter === "low_inferred" && tier !== "low" && tier !== "inferred") return false;
      }

      return true;
    });
  }, [allNormalizedEdges, nodesMap, layerFilters, operStatusFilter, confidenceFilter]);

  // Parallel Multi-Layer Edge Bundles for Non-Overlapping Bezier Curves
  const bundledEdges = useMemo(() => {
    const groups = new Map();
    for (const edge of visibleEdges) {
      const srcId = edge.source_node_id || edge.source;
      const dstId = edge.target_node_id || edge.target;
      const pairKey = [srcId, dstId].sort().join("---");
      if (!groups.has(pairKey)) {
        groups.set(pairKey, []);
      }
      groups.get(pairKey).push(edge);
    }

    const result = [];
    for (const [, edges] of groups.entries()) {
      const bundleSize = edges.length;
      edges.forEach((edge, bundleIndex) => {
        result.push({
          edge,
          bundleIndex,
          bundleSize,
        });
      });
    }
    return result;
  }, [visibleEdges]);

  const reviewBadgeCount =
    (data.stats?.pending_review_nodes || 0) + (data.stats?.open_conflicts || 0);

  const ownStats = data.stats?.ownership || {};
  const lvStats = data.stats?.link_verification || {};

  return (
    <div className="flex flex-col h-full bg-black text-text-primary overflow-hidden select-none">
      <TopBar
        title="Topology Fabric V2"
        subtitle="Evidence-Based Enterprise Discovery, ISP Boundary & Wiring Confidence"
        onOpenMenu={onOpenMenu}
        actions={
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Seed Router Picker */}
            <select
              value={seedDeviceName}
              onChange={(e) => setSeedDeviceName(e.target.value)}
              className="text-[11px] bg-white/5 border border-white/10 rounded-pill px-2.5 py-1.5 text-text-primary outline-none focus:border-sky-500/40 hidden lg:block"
              title="Pilih Seed Router resmi dari Inventory"
            >
              <option value="">Seed: Auto Inventory</option>
              {inventoryDevices.map((d) => (
                <option key={d.name} value={d.name}>
                  Seed: {d.name} ({d.host})
                </option>
              ))}
            </select>

            {/* Discovery Mode Picker */}
            <select
              value={discoveryMode}
              onChange={(e) => setDiscoveryMode(e.target.value)}
              className="text-[11px] bg-white/5 border border-white/10 rounded-pill px-2.5 py-1.5 text-sky-300 outline-none focus:border-sky-500/40 hidden md:block"
              title="Mode kedalaman dan batas ekspansi discovery"
            >
              {DISCOVERY_MODES.map((m) => (
                <option key={m.value} value={m.value} className="bg-black text-white">
                  {m.label}
                </option>
              ))}
            </select>

            <button
              onClick={handleDiscover}
              disabled={discovering || !!activeSnapshotView}
              className="text-xs font-medium px-3 py-1.5 rounded-pill bg-sky-500/15 text-sky-300 border border-sky-500/30 hover:bg-sky-500/25 hover:shadow-glow-cyan transition flex items-center gap-1.5 disabled:opacity-40"
              title={
                activeSnapshotView
                  ? "Tidak tersedia dalam mode riwayat snapshot (Read-only)"
                  : "Jalankan interogasi read-only berbasis bukti dari Seed Router"
              }
            >
              <RefreshCw className={`w-3.5 h-3.5 ${discovering ? "animate-spin" : ""}`} />
              <span className="hidden sm:inline">{discovering ? "Scanning..." : "Auto Discover"}</span>
            </button>

            <button
              onClick={() => setReviewModalOpen(true)}
              className="text-xs font-medium px-2.5 py-1.5 rounded-pill bg-amber-500/10 text-amber-300 border border-amber-500/25 hover:bg-amber-500/20 transition flex items-center gap-1.5"
              title="Tinjau perangkat Unknown, link belum terverifikasi, dan konflik"
            >
              <Shield className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Review</span>
              {reviewBadgeCount > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-amber-400 text-black text-[10px] font-bold">
                  {reviewBadgeCount}
                </span>
              )}
            </button>

            <button
              onClick={() => setHistoryModalOpen(true)}
              className="text-xs font-medium px-2.5 py-1.5 rounded-pill bg-purple-500/10 text-purple-300 border border-purple-500/25 hover:bg-purple-500/20 transition flex items-center gap-1.5"
              title="Buka Timeline Snapshot & Semantic Graph Diff"
            >
              <History className="w-3.5 h-3.5 text-purple-400" />
              <span className="hidden sm:inline">History</span>
            </button>

            <button
              onClick={() => setPolicyModalOpen(true)}
              className="text-xs font-medium px-2.5 py-1.5 rounded-pill bg-white/5 text-text-primary border border-white/10 hover:bg-white/10 transition flex items-center gap-1.5"
              title="Atur ISP Boundary, Subnet Internal, dan Kebijakan Discovery"
            >
              <Sliders className="w-3.5 h-3.5 text-sky-400" />
              <span className="hidden xl:inline">Policy</span>
            </button>

            <button
              onClick={() => setAddNodeModal(true)}
              disabled={!!activeSnapshotView}
              className="text-xs font-medium px-2.5 py-1.5 rounded-pill bg-white/5 text-text-primary border border-white/10 hover:bg-white/10 transition flex items-center gap-1 disabled:opacity-40"
              title={
                activeSnapshotView
                  ? "Tidak tersedia dalam mode riwayat snapshot (Read-only)"
                  : "Tambah perangkat secara manual"
              }
            >
              <Plus className="w-3.5 h-3.5 text-sky-400" />
              <span className="hidden xl:inline">Node</span>
            </button>

            <button
              onClick={() => {
                if (activeSnapshotView) return;
                if (data.nodes.length < 2) {
                  pushToast("Dibutuhkan minimal 2 perangkat untuk wiring manual.", "warning");
                  return;
                }
                setNewLinkForm((prev) => ({
                  ...prev,
                  source_id: data.nodes[0]?.id || "",
                  target_id: data.nodes[1]?.id || "",
                }));
                setAddLinkModal(true);
              }}
              disabled={!!activeSnapshotView}
              className="text-xs font-medium px-2.5 py-1.5 rounded-pill bg-white/5 text-text-primary border border-white/10 hover:bg-white/10 transition flex items-center gap-1 disabled:opacity-40"
              title={
                activeSnapshotView
                  ? "Tidak tersedia dalam mode riwayat snapshot (Read-only)"
                  : "Hubungkan kabel fisik secara manual"
              }
            >
              <Link2 className="w-3.5 h-3.5 text-purple-400" />
              <span className="hidden xl:inline">Wiring</span>
            </button>

            {data.nodes.length > 0 ? (
              <button
                onClick={handleClearTopology}
                disabled={!!activeSnapshotView}
                className="text-xs font-medium px-2.5 py-1.5 rounded-pill bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition flex items-center gap-1 disabled:opacity-40"
                title={
                  activeSnapshotView
                    ? "Tidak tersedia dalam mode riwayat snapshot (Read-only)"
                    : "Kosongkan seluruh peta topologi (memerlukan konfirmasi)"
                }
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                onClick={handleSeedDemo}
                disabled={!!activeSnapshotView}
                className="text-xs font-medium px-3 py-1.5 rounded-pill bg-purple-500/10 text-purple-300 border border-purple-500/25 hover:bg-purple-500/20 transition flex items-center gap-1.5 disabled:opacity-40"
                title={
                  activeSnapshotView
                    ? "Tidak tersedia dalam mode riwayat snapshot (Read-only)"
                    : "Muat sampel demo"
                }
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Demo V2</span>
              </button>
            )}
          </div>
        }
      />

      {/* READ-ONLY HISTORICAL SNAPSHOT BANNER */}
      {activeSnapshotView && (
        <div className="flex items-center justify-between px-4 py-2 bg-purple-950/40 border-b border-purple-500/30 text-xs text-purple-200 shrink-0">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-purple-400 shrink-0" />
            <span>
              Menampilkan Titik Waktu Snapshot: <strong className="font-mono text-purple-300">{activeSnapshotView.snapshot_id}</strong> ({activeSnapshotView.description}) — Mode Read-Only
            </span>
          </div>
          <button
            onClick={handleReturnToLiveTopology}
            className="px-2.5 py-1 rounded-pill bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/40 text-white font-medium transition shrink-0"
          >
            Kembali ke Topologi Live
          </button>
        </div>
      )}

      {/* GOVERNANCE & TELEMETRY CONTROL BAR */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-white/[0.08] bg-black/75 backdrop-blur-md overflow-x-auto text-[11px] shrink-0">
        {/* View Scope Switcher */}
        <div className="flex rounded-pill bg-white/5 border border-white/10 p-0.5 shrink-0">
          {VIEW_MODES.map((vm) => (
            <button
              key={vm.value}
              onClick={() => setViewMode(vm.value)}
              className={`px-2.5 py-0.5 rounded-pill font-medium transition ${
                viewMode === vm.value
                  ? "bg-sky-500 text-black font-semibold"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {vm.label}
            </button>
          ))}
        </div>

        {/* Ownership Counters */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 shrink-0">
          <CheckCircle2 className="w-3 h-3" />
          <span>Owned:</span>
          <span className="font-bold">{ownStats.owned || 0}</span>
        </div>

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-cyan-500/10 border border-cyan-400/25 text-cyan-200 shrink-0">
          <span>ISP/3rd:</span>
          <span className="font-bold">{(ownStats.third_party || 0) + (ownStats.managed_external || 0)}</span>
        </div>

        {(ownStats.unknown || 0) > 0 && (
          <button
            onClick={() => setReviewModalOpen(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 shrink-0"
          >
            <AlertTriangle className="w-3 h-3" />
            <span>Unknown:</span>
            <span className="font-bold">{ownStats.unknown}</span>
          </button>
        )}

        {/* Link Confidence Counters */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-white/5 border border-white/10 text-text-secondary shrink-0">
          <span>Links:</span>
          <span className="text-emerald-300 font-mono">✓{(lvStats.confirmed || 0) + (lvStats.manual || 0)}</span>
          <span>/</span>
          <span className="text-sky-300 font-mono">Obs:{lvStats.observed || 0}</span>
          <span>/</span>
          <span className="text-slate-300 font-mono">Inf:{lvStats.inferred || 0}</span>
          {(lvStats.conflicting || 0) > 0 && (
            <span className="text-rose-400 font-bold ml-1">⚠{lvStats.conflicting}</span>
          )}
        </div>

        {/* Last Scan Telemetry + Lightweight Refresh */}
        <button
          onClick={handleRefreshStatuses}
          disabled={refreshingStatus}
          className="flex items-center gap-1 px-2.5 py-1 rounded-pill bg-white/5 hover:bg-white/10 border border-white/10 text-text-secondary hover:text-text-primary shrink-0"
          title="Evaluasi ulang kesegaran observasi (Fresh / Stale) tanpa membuka koneksi SSH"
        >
          <Activity className={`w-3 h-3 text-sky-400 ${refreshingStatus ? "animate-spin" : ""}`} />
          <span>
            {data.last_job
              ? `Scan ${formatRelativeTime(data.last_job.finished_at || data.last_job.started_at)}`
              : "Refresh Status"}
          </span>
        </button>

        {/* Search & Type Filter */}
        <div className="ml-auto flex items-center gap-2 shrink-0">
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2.5 top-2 text-text-secondary/50" />
            <input
              type="text"
              placeholder="Cari IP / MAC / Nama..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-pill pl-7 pr-3 py-1 text-[11px] text-text-primary focus:border-sky-500/50 outline-none w-36 sm:w-44 transition"
            />
          </div>

          <div className="flex rounded-pill bg-white/5 border border-white/10 p-0.5">
            {["all", "router", "switch", "access_point", "server", "wan", "client"].map((type) => (
              <button
                key={type}
                onClick={() => setFilterType(type)}
                className={`px-2 py-0.5 text-[10px] rounded-pill font-medium capitalize transition ${
                  filterType === type
                    ? "bg-sky-500 text-black font-semibold"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {type === "access_point" ? "AP" : type === "wan" ? "ISP/WAN" : type}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* MULTI-LAYER TAXONOMY & RELATIONSHIP CONTROL BAR (PHASE 4.5) */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-white/[0.06] bg-black/60 backdrop-blur-sm overflow-x-auto text-[11px] shrink-0 gap-3">
        {/* Layer Filters */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] uppercase font-bold tracking-wider text-text-secondary mr-1 flex items-center gap-1">
            <Layers className="w-3 h-3 text-sky-400" /> Layers:
          </span>

          <button
            onClick={() => {
              const allActive = Object.values(layerFilters).every(Boolean);
              setLayerFilters({
                physical: !allActive,
                layer2: !allActive,
                layer3: !allActive,
                logical: !allActive,
              });
            }}
            className={`px-2 py-0.5 rounded-pill text-[10px] font-medium border transition ${
              Object.values(layerFilters).every(Boolean)
                ? "bg-white/15 text-white border-white/20"
                : "bg-white/5 text-text-secondary border-white/10 hover:text-text-primary"
            }`}
          >
            All ({layerCounts.total})
          </button>

          <button
            onClick={() => setLayerFilters((prev) => ({ ...prev, physical: !prev.physical }))}
            className={`px-2 py-0.5 rounded-pill text-[10px] font-medium border transition flex items-center gap-1 ${
              layerFilters.physical
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-semibold"
                : "bg-white/5 text-text-secondary/60 border-white/5 hover:text-text-secondary line-through"
            }`}
            title="Kabel Fisik Terkonfirmasi (Copper/Fiber)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
            Physical ({layerCounts.physical})
          </button>

          <button
            onClick={() => setLayerFilters((prev) => ({ ...prev, layer2: !prev.layer2 }))}
            className={`px-2 py-0.5 rounded-pill text-[10px] font-medium border transition flex items-center gap-1 ${
              layerFilters.layer2
                ? "bg-sky-500/20 text-sky-300 border-sky-500/40 font-semibold"
                : "bg-white/5 text-text-secondary/60 border-white/5 hover:text-text-secondary line-through"
            }`}
            title="Layer 2 Adjacency (Bridge / VLAN / Switch-port)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 inline-block" />
            Layer 2 ({layerCounts.layer2})
          </button>

          <button
            onClick={() => setLayerFilters((prev) => ({ ...prev, layer3: !prev.layer3 }))}
            className={`px-2 py-0.5 rounded-pill text-[10px] font-medium border transition flex items-center gap-1 ${
              layerFilters.layer3
                ? "bg-purple-500/20 text-purple-300 border-purple-500/40 font-semibold"
                : "bg-white/5 text-text-secondary/60 border-white/5 hover:text-text-secondary line-through"
            }`}
            title="Layer 3 Reachability (Routed Next-Hop / Gateway)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400 inline-block" />
            Layer 3 ({layerCounts.layer3})
          </button>

          <button
            onClick={() => setLayerFilters((prev) => ({ ...prev, logical: !prev.logical }))}
            className={`px-2 py-0.5 rounded-pill text-[10px] font-medium border transition flex items-center gap-1 ${
              layerFilters.logical
                ? "bg-amber-500/20 text-amber-300 border-amber-500/40 font-semibold"
                : "bg-white/5 text-text-secondary/60 border-white/5 hover:text-text-secondary line-through"
            }`}
            title="Logical Relationship (VPN / Overlay Tunnel / VRRP)"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
            Logical ({layerCounts.logical})
          </button>
        </div>

        {/* Operational Status & Confidence Dropdown / Toggles */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-text-secondary">Status:</span>
            <select
              value={operStatusFilter}
              onChange={(e) => setOperStatusFilter(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-pill px-2 py-0.5 text-[10px] text-text-primary outline-none focus:border-sky-500/40"
            >
              <option value="all">Semua Status</option>
              <option value="up">Up Saja</option>
              <option value="down">Down (Error)</option>
              <option value="degraded">Degraded / Warning</option>
            </select>
          </div>

          <div className="flex items-center gap-1">
            <span className="text-[10px] text-text-secondary">Confidence:</span>
            <select
              value={confidenceFilter}
              onChange={(e) => setConfidenceFilter(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-pill px-2 py-0.5 text-[10px] text-text-primary outline-none focus:border-sky-500/40"
            >
              <option value="all">Semua Confidence</option>
              <option value="confirmed">Confirmed Only</option>
              <option value="high">High (&gt;=85%)</option>
              <option value="medium">Medium (&gt;=65%)</option>
              <option value="low_inferred">Low / Inferred</option>
            </select>
          </div>

          {/* Toggle Route Overlay (WP 4.6.5) */}
          <button
            onClick={() => {
              const nextOpen = !routeOverlayOpen;
              setRouteOverlayOpen(nextOpen);
              if (nextOpen && !routeOverlayData) {
                handleLoadRouteOverlay();
              }
            }}
            className={`px-2.5 py-0.5 rounded-pill text-[10px] font-medium border transition flex items-center gap-1 ${
              routeOverlayOpen
                ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 font-semibold"
                : "bg-white/5 text-text-secondary border-white/10 hover:text-text-primary"
            }`}
            title="Tampilkan Overlay Jalur Rute Lintas-Router (Tanpa Mengubah Kabel Fisik)"
          >
            <GitBranch className="w-3 h-3" />
            <span>Route Overlay</span>
          </button>

          {/* Open Route History Modal (WP 4.6.4) */}
          <button
            onClick={() => setRouteHistoryModalOpen(true)}
            className="px-2.5 py-0.5 rounded-pill text-[10px] font-medium border bg-white/5 text-text-secondary border-white/10 hover:text-text-primary transition flex items-center gap-1"
            title="Riwayat Snapshot & Perubahan Tabel Routing"
          >
            <History className="w-3 h-3 text-purple-400" />
            <span>Route History</span>
          </button>

          {/* Toggle Legend */}
          <button
            onClick={() => setLegendOpen((v) => !v)}
            className={`px-2.5 py-0.5 rounded-pill text-[10px] font-medium border transition flex items-center gap-1 ${
              legendOpen
                ? "bg-sky-500/20 text-sky-300 border-sky-500/40"
                : "bg-white/5 text-text-secondary border-white/10 hover:text-text-primary"
            }`}
            title="Tampilkan Legend Simbol Multi-Layer"
          >
            <Eye className="w-3 h-3" />
            <span>Legend</span>
          </button>
        </div>
      </div>

      {/* FOCUSED ROUTE OVERLAY QUERY BAR (WP 4.6.5) */}
      {routeOverlayOpen && (
        <div className="flex flex-wrap items-center gap-2 px-4 py-1.5 border-b border-cyan-500/20 bg-cyan-950/20 text-[11px] shrink-0">
          <span className="font-semibold text-cyan-300 flex items-center gap-1">
            <GitBranch className="w-3.5 h-3.5" /> Cross-Device Route Path:
          </span>
          <select
            value={routeOverlaySource}
            onChange={(e) => setRouteOverlaySource(e.target.value)}
            className="bg-black/60 border border-white/15 rounded-pill px-2.5 py-0.5 text-[10px] text-white outline-none"
          >
            <option value="">Semua Router (Summary)</option>
            {data.nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name || n.id} ({n.ip || "no-ip"})
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Destination IP/Prefix (mis. 8.8.8.8 atau 10.20.0.0/24)"
            value={routeOverlayDest}
            onChange={(e) => setRouteOverlayDest(e.target.value)}
            className="bg-black/60 border border-white/15 rounded-pill px-3 py-0.5 text-[10px] text-white w-56 outline-none focus:border-cyan-400/50"
          />
          <input
            type="text"
            placeholder="VRF / Table (main)"
            value={routeOverlayTable}
            onChange={(e) => setRouteOverlayTable(e.target.value)}
            className="bg-black/60 border border-white/15 rounded-pill px-2.5 py-0.5 text-[10px] text-white w-28 outline-none"
          />
          <button
            onClick={() => handleLoadRouteOverlay()}
            disabled={routeOverlayLoading}
            className="px-3 py-0.5 rounded-pill bg-cyan-500/25 hover:bg-cyan-500/35 border border-cyan-400/40 text-cyan-200 font-semibold text-[10px] flex items-center gap-1 transition"
          >
            {routeOverlayLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <ArrowRight className="w-3 h-3" />}
            <span>Evaluasi Jalur</span>
          </button>
          {routeOverlayData && (
            <span className="text-[10px] font-mono text-cyan-200/80 ml-1">
              State: <strong>{routeOverlayData?.overlay?.path_state}</strong> · Segments:{" "}
              {routeOverlayData?.overlay?.segments_count ?? 0} · Inconsistencies:{" "}
              {routeOverlayData?.inconsistencies?.length ?? 0}
            </span>
          )}
          <button
            onClick={() => {
              setRouteOverlayData(null);
              setSelectedRouteSegment(null);
              setRouteOverlayOpen(false);
            }}
            className="ml-auto text-[10px] text-text-secondary hover:text-white px-2 py-0.5"
          >
            Tutup Overlay
          </button>
        </div>
      )}

      {/* MAIN INTERACTIVE CANVAS */}
      <div
        ref={canvasRef}
        className="relative flex-1 bg-black overflow-hidden cursor-grab active:cursor-grabbing"
        onMouseMove={handleCanvasMouseMove}
        onMouseUp={handleCanvasMouseUp}
        onClick={() => {
          setSelectedNode(null);
          setSelectedEdge(null);
          setSelectedRouteSegment(null);
        }}
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.06) 1px, transparent 0)",
          backgroundSize: "28px 28px",
        }}
      >
        {/* SVG MULTI-LAYER LINKS & EDGES */}
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          style={{ transform: `scale(${zoom})`, transformOrigin: "0 0" }}
        >
          <defs>
            <linearGradient id="link-gradient-up" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#34d399" stopOpacity="0.85" />
            </linearGradient>
            <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="glow-edge-selected" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            {/* Arrow marker for Layer 3 (purple) */}
            <marker
              id="arrow-layer3"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#8b5cf6" />
            </marker>
            {/* Arrow marker for Logical overlay (amber) */}
            <marker
              id="arrow-logical"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#f59e0b" />
            </marker>
            {/* Arrow markers for Ephemeral Route Path Overlay (WP 4.6.5) */}
            <marker
              id="arrow-route-inferred"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#22d3ee" />
            </marker>
            <marker
              id="arrow-route-recursive"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#c084fc" />
            </marker>
            <marker
              id="arrow-route-uncertain"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#fbbf24" />
            </marker>
          </defs>

          {bundledEdges.map(({ edge, bundleIndex, bundleSize }) => {
            const srcId = edge.source_node_id || edge.source;
            const dstId = edge.target_node_id || edge.target;
            const src = nodesMap[srcId];
            const dst = nodesMap[dstId];
            if (!src || !dst) return null;

            const x1 = src.pos_x + 92;
            const y1 = src.pos_y + 42;
            const x2 = dst.pos_x + 92;
            const y2 = dst.pos_y + 42;

            const isSelected = selectedEdge?.id === edge.id;
            const vis = getMultiLayerEdgeVisualConfig(edge, src, dst, isSelected);
            const curved = computeCurvedEdgePath(x1, y1, x2, y2, bundleIndex, bundleSize);

            const showRemoteQuestion =
              !edge.target_interface_name &&
              !edge.target_port &&
              (edge.relationship_class === RELATIONSHIP_CLASSES.PHYSICAL ||
                edge.relationship_class === RELATIONSHIP_CLASSES.LAYER2);

            const localPortLabel = edge.source_interface_name || edge.source_port;
            const remotePortLabel = edge.target_interface_name || edge.target_port;

            return (
              <g key={edge.id} className="transition-all duration-300">
                {/* Visual Stroke Path */}
                <path
                  d={curved.pathD}
                  stroke={vis.stroke}
                  strokeWidth={vis.strokeWidth}
                  strokeDasharray={vis.strokeDasharray}
                  strokeOpacity={vis.opacity}
                  fill="none"
                  markerEnd={vis.markerEnd}
                  filter={isSelected ? "url(#glow-edge-selected)" : (vis.glow ? "url(#glow-cyan)" : undefined)}
                />

                {/* Wide transparent click hitbox for smooth selection */}
                <path
                  d={curved.pathD}
                  stroke="transparent"
                  strokeWidth={20}
                  fill="none"
                  className="pointer-events-auto cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedEdge(edge);
                    setSelectedNode(null);
                  }}
                >
                  <title>{`${vis.label}: ${src.name} ➔ ${dst.name} (${edge.bandwidth || "1 Gbps"})`}</title>
                </path>

                {/* Midpoint Verification & Layer Pill Badge */}
                <g
                  className="pointer-events-auto cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedEdge(edge);
                    setSelectedNode(null);
                  }}
                >
                  <rect
                    x={curved.labelX - 32}
                    y={curved.labelY - 8}
                    width="64"
                    height="16"
                    rx="8"
                    fill="#050810"
                    stroke={isSelected ? "#38bdf8" : vis.dotColor}
                    strokeOpacity={isSelected ? 0.9 : 0.6}
                    strokeWidth={isSelected ? 1.5 : 1}
                  />
                  <text
                    x={curved.labelX}
                    y={curved.labelY + 3.5}
                    fill={isSelected ? "#38bdf8" : vis.dotColor}
                    fontSize="8"
                    fontFamily="monospace"
                    fontWeight="bold"
                    textAnchor="middle"
                  >
                    {vis.badge}
                  </text>
                </g>

                {/* Honest Port Labels (Never invent port names when absent) */}
                {localPortLabel && (
                  <text
                    x={(x1 * 2 + curved.labelX) / 3}
                    y={(y1 * 2 + curved.labelY) / 3 - 6}
                    fill="#38bdf8"
                    fontSize="9"
                    fontFamily="monospace"
                    textAnchor="middle"
                  >
                    {localPortLabel}
                  </text>
                )}
                {(remotePortLabel || showRemoteQuestion) && (
                  <text
                    x={(curved.labelX + x2 * 2) / 3}
                    y={(curved.labelY + y2 * 2) / 3 - 6}
                    fill={remotePortLabel ? "#c084fc" : "#fbbf24"}
                    fontSize="9"
                    fontFamily="monospace"
                    textAnchor="middle"
                  >
                    {remotePortLabel || "?"}
                  </text>
                )}
              </g>
            );
          })}

          {/* EPHEMERAL MULTI-DEVICE ROUTE PATH OVERLAY (WP 4.6.5 — NON-DESTRUCTIVE) */}
          {routeOverlayOpen &&
            (routeOverlayData?.overlay?.segments || []).map((seg, idx) => {
              const src = nodesMap[seg.source_device_id];
              const dst = seg.target_device_id ? nodesMap[seg.target_device_id] : null;
              if (!src || !dst) return null;

              const x1 = src.pos_x + 92;
              const y1 = src.pos_y + 42;
              const x2 = dst.pos_x + 92;
              const y2 = dst.pos_y + 42;
              const isSegSelected = selectedRouteSegment?.segment_id === seg.segment_id;
              const styleCfg = getOverlaySegmentVisualStyle(seg, isSegSelected);
              // Offset curve slightly from physical edges so both remain clearly visible
              const curved = computeCurvedEdgePath(x1, y1, x2, y2, 1, 2);

              return (
                <g key={`route_ov_${seg.segment_id}_${idx}`}>
                  <path
                    d={curved.pathD}
                    stroke={styleCfg.stroke}
                    strokeWidth={styleCfg.strokeWidth}
                    strokeDasharray={styleCfg.strokeDasharray}
                    strokeOpacity={styleCfg.opacity}
                    fill="none"
                    markerEnd={styleCfg.markerEnd}
                    filter={isSegSelected ? "url(#glow-edge-selected)" : "url(#glow-cyan)"}
                  />
                  <path
                    d={curved.pathD}
                    stroke="transparent"
                    strokeWidth={18}
                    fill="none"
                    className="pointer-events-auto cursor-pointer"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedRouteSegment(seg);
                      setSelectedEdge(null);
                      setSelectedNode(null);
                    }}
                  >
                    <title>{`${styleCfg.label}: ${seg.source_device_id} → ${seg.next_device_hypothesis} (${seg.destination_prefix})`}</title>
                  </path>
                  <g
                    className="pointer-events-auto cursor-pointer"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedRouteSegment(seg);
                      setSelectedEdge(null);
                      setSelectedNode(null);
                    }}
                  >
                    <rect
                      x={curved.labelX - 42}
                      y={curved.labelY - 22}
                      width="84"
                      height="15"
                      rx="7"
                      fill="#041019"
                      stroke={styleCfg.dotColor}
                      strokeOpacity={0.85}
                      strokeWidth={isSegSelected ? 1.5 : 1}
                    />
                    <text
                      x={curved.labelX}
                      y={curved.labelY - 12}
                      fill={styleCfg.dotColor}
                      fontSize="7.5"
                      fontFamily="monospace"
                      fontWeight="bold"
                      textAnchor="middle"
                    >
                      {styleCfg.badge}
                    </text>
                  </g>
                </g>
              );
            })}
        </svg>

        {/* NODES LAYER */}
        <div className="absolute inset-0" style={{ transform: `scale(${zoom})`, transformOrigin: "0 0" }}>
          {filteredNodes.map((node) => {
            const Icon = DEVICE_ICONS[node.device_type] || Network;
            const colors = DEVICE_COLORS[node.device_type] || DEVICE_COLORS.unknown;
            const statusCfg = STATUS_CONFIG[node.status] || STATUS_CONFIG.warning;
            const ownCfg = OWNERSHIP_BADGES[node.ownership_status] || OWNERSHIP_BADGES.unknown;
            const freshCfg = FRESHNESS_BADGES[node.observation_freshness] || FRESHNESS_BADGES.unknown;
            const isSelected = selectedNode?.id === node.id;
            const isBoundary =
              node.topology_scope === "isp_upstream" ||
              node.topology_scope === "external" ||
              node.metadata?.is_isp_boundary;

            return (
              <div
                key={node.id}
                onMouseDown={(e) => handleNodeMouseDown(e, node)}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedNode(node);
                }}
                style={{ transform: `translate(${node.pos_x}px, ${node.pos_y}px)` }}
                className={`absolute w-48 rounded-2xl p-2.5 cursor-pointer select-none transition-shadow duration-200 border bg-black/90 backdrop-blur-xl ${
                  isBoundary ? "border-dashed border-cyan-400/55" : colors.border
                } ${colors.glow} ${
                  isSelected
                    ? "ring-2 ring-sky-400 shadow-[0_0_25px_rgba(56,189,248,0.5)] z-30"
                    : "z-10 hover:z-20"
                }`}
              >
                {/* Top Ownership + Scope Strip */}
                <div className="flex items-center justify-between mb-1.5 gap-1">
                  <span className={`px-1.5 py-0.2 rounded text-[8px] font-bold border ${ownCfg.className}`}>
                    {ownCfg.short}
                  </span>
                  <span className="text-[9px] text-text-secondary truncate">
                    {SCOPE_LABELS[node.topology_scope] || node.topology_scope || "Unclassified"}
                  </span>
                  <div
                    className={`w-2.5 h-2.5 rounded-full shrink-0 ${statusCfg.dot}`}
                    title={`${node.reachability_status || node.status} (${node.observation_freshness || "unknown"})`}
                  />
                </div>

                {/* Device Icon + Name + IP */}
                <div className="flex items-center gap-2 mb-1.5">
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${colors.badge} border border-white/5`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="text-xs font-semibold text-text-primary truncate" title={node.name}>
                      {node.name}
                    </h4>
                    <p className="text-[10px] text-text-secondary/75 font-mono truncate" title={node.ip || node.mac || "No IP"}>
                      {node.ip || node.mac || "No IP"}
                    </p>
                  </div>
                </div>

                {/* Footer: Reachability, Freshness & Observability */}
                <div className="flex items-center justify-between pt-1 border-t border-white/[0.06] text-[9px]">
                  <span className={`font-mono ${freshCfg.className}`}>
                    {node.reachability_status === "reachable"
                      ? "Reachable"
                      : node.reachability_status === "unreachable"
                      ? "Unreachable"
                      : "Unverified"}{" "}
                    • {freshCfg.label}
                  </span>

                  <span className="font-mono text-text-secondary/80 flex items-center gap-1">
                    {node.observability &&
                      node.observability !== "fully_observable" &&
                      ["router", "switch", "access_point"].includes(node.device_type) && (
                        <Eye className="w-2.5 h-2.5 text-amber-400" title={node.observability_reason} />
                      )}
                    {node.latency_ms > 0 ? `${node.latency_ms}ms` : ""}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* EMPTY STATE */}
        {data.nodes.length === 0 && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center">
            <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-sky-400 mb-4 shadow-glow-cyan">
              <Network className="w-8 h-8" />
            </div>
            <h3 className="text-base font-semibold text-text-primary mb-1">Topology Fabric V2 Siap Digunakan</h3>
            <p className="text-xs text-text-secondary max-w-md mb-4">
              Jalankan <strong>Auto Discover</strong> dari seed router resmi di tab Devices. Tetangga ISP/eksternal dan
              perangkat belum terverifikasi otomatis dipisahkan dari aset internal perusahaan.
            </p>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <button
                onClick={handleDiscover}
                disabled={discovering || !!activeSnapshotView}
                className="text-xs px-4 py-2 rounded-pill bg-sky-500 text-black font-semibold shadow-glow-cyan hover:bg-sky-400 transition flex items-center gap-1.5 disabled:opacity-40"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${discovering ? "animate-spin" : ""}`} />
                <span>{discovering ? "Memindai..." : "Auto Discover (Evidence-Based)"}</span>
              </button>
              <button
                onClick={() => setPolicyModalOpen(true)}
                className="text-xs px-4 py-2 rounded-pill bg-white/5 text-text-primary border border-white/10 font-medium hover:bg-white/10 transition flex items-center gap-1.5"
              >
                <Sliders className="w-3.5 h-3.5 text-sky-400" />
                <span>Atur ISP Boundary & Subnet</span>
              </button>
              <button
                onClick={handleSeedDemo}
                disabled={!!activeSnapshotView}
                className="text-xs px-4 py-2 rounded-pill bg-purple-500/15 text-purple-300 border border-purple-500/30 font-medium hover:bg-purple-500/25 transition flex items-center gap-1.5 disabled:opacity-40"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Muat Sampel Demo V2</span>
              </button>
            </div>
          </div>
        )}

        {/* ZOOM CONTROLS */}
        <div className="absolute bottom-4 left-4 flex items-center gap-1.5 bg-black/85 backdrop-blur-xl border border-white/10 rounded-pill p-1 shadow-lg z-20">
          <button
            onClick={() => setZoom((z) => Math.min(z + 0.15, 2))}
            className="w-7 h-7 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition text-sm font-bold"
          >
            +
          </button>
          <span className="text-[10px] font-mono text-text-secondary px-1.5">{Math.round(zoom * 100)}%</span>
          <button
            onClick={() => setZoom((z) => Math.max(z - 0.15, 0.5))}
            className="w-7 h-7 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition text-sm font-bold"
          >
            -
          </button>
          <div className="w-px h-4 bg-white/10 my-auto" />
          <button
            onClick={() => setZoom(1)}
            className="text-[10px] px-2.5 py-1 rounded-pill text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
          >
            Reset
          </button>
        </div>

        {/* TOGGLEABLE ACCESSIBLE LEGEND */}
        <TopologyLegendOverlay open={legendOpen} onToggle={() => setLegendOpen((v) => !v)} />
      </div>

      {/* EVIDENCE-BASED NODE INSPECTOR */}
      <TopologyNodeInspector
        node={selectedNode}
        links={data.links}
        nodesMap={nodesMap}
        onClose={() => setSelectedNode(null)}
        onSelectNode={(node) => {
          setSelectedNode(node);
          setSelectedEdge(null);
        }}
        onSelectEdge={(edge) => {
          setSelectedEdge(edge);
          setSelectedNode(null);
        }}
        onEditNode={setEditNodeModal}
        onDeleteNode={handleDeleteNode}
        onOpenAddLink={() => {
          if (!selectedNode) return;
          setNewLinkForm((prev) => ({
            ...prev,
            source_id: selectedNode.id,
            target_id: data.nodes.find((n) => n.id !== selectedNode.id)?.id || "",
          }));
          setAddLinkModal(true);
        }}
        onDeleteLink={handleDeleteLink}
        onPingNode={handlePingNode}
        onTroubleshoot={handleTroubleshoot}
        onRefreshTopology={() => fetchTopology(true)}
        onOpenNmsDetail={(id) => setNmsDetailDeviceId(id)}
        onOpenSnmpWizard={(dev) => setNmsWizardDevice(dev)}
        pinging={pinging}
        troubleshooting={troubleshooting}
        pushToast={pushToast}
        readOnly={!!activeSnapshotView}
      />

      {/* MULTI-LAYER EDGE & EVIDENCE INSPECTOR (PHASE 4.5) */}
      {selectedEdge && (
        <TopologyEdgeInspector
          edge={selectedEdge}
          nodesMap={nodesMap}
          onClose={() => setSelectedEdge(null)}
          onSelectNode={(node) => {
            setSelectedNode(node);
            setSelectedEdge(null);
          }}
          onDeleteEdge={(edgeId) => {
            handleDeleteLink(edgeId);
            setSelectedEdge(null);
          }}
          onTroubleshoot={handleTroubleshoot}
          onRefreshTopology={() => fetchTopology(true)}
          pushToast={pushToast}
          readOnly={!!activeSnapshotView}
          historicalEvidence={data.historicalEvidence || []}
        />
      )}

      {/* MULTI-DEVICE ROUTE OVERLAY SEGMENT INSPECTOR (WP 4.6.5) */}
      {routeOverlayOpen && selectedRouteSegment && (
        <MultiDeviceRouteInspector
          segment={selectedRouteSegment}
          overlayPayload={routeOverlayData}
          nodesMap={nodesMap}
          onClose={() => setSelectedRouteSegment(null)}
          onSelectSegment={(seg) => setSelectedRouteSegment(seg)}
        />
      )}

      {/* GOVERNANCE MODALS */}
      <PolicySettingsModal
        open={policyModalOpen}
        policy={data.policy}
        inventoryDevices={inventoryDevices}
        onClose={() => setPolicyModalOpen(false)}
        onSaved={(newPol) => {
          if (newPol?.discovery_mode) setDiscoveryMode(newPol.discovery_mode);
          if (newPol?.seed_device_id !== undefined) setSeedDeviceName(newPol.seed_device_id);
          fetchTopology(true);
        }}
        pushToast={pushToast}
      />

      <ReviewQueueModal
        open={reviewModalOpen}
        onClose={() => setReviewModalOpen(false)}
        onUpdated={() => fetchTopology(true)}
        pushToast={pushToast}
      />

      {/* MODAL: ADD MANUAL NODE */}
      {addNodeModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-black border border-white/10 rounded-3xl p-6 max-w-md w-full shadow-2xl relative">
            <button
              onClick={() => setAddNodeModal(false)}
              className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
            >
              <X className="w-4 h-4" />
            </button>
            <h3 className="text-sm font-bold text-text-primary mb-1">Tambah Perangkat Manual</h3>
            <p className="text-[11px] text-text-secondary mb-4">
              Perangkat manual disimpan sebagai <code>user_managed</code> dan tidak akan ditimpa oleh scan otomatis.
            </p>
            <form onSubmit={handleCreateNode} className="space-y-3 text-xs">
              <div>
                <label className="text-text-secondary block mb-1">Nama Perangkat *</label>
                <input
                  type="text"
                  required
                  placeholder="Mis. Core-Router-Pusat"
                  value={newNodeForm.name}
                  onChange={(e) => setNewNodeForm({ ...newNodeForm, name: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary outline-none focus:border-sky-500/50"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-text-secondary block mb-1">IP Address</label>
                  <input
                    type="text"
                    placeholder="10.0.0.1"
                    value={newNodeForm.ip}
                    onChange={(e) => setNewNodeForm({ ...newNodeForm, ip: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary font-mono outline-none focus:border-sky-500/50"
                  />
                </div>
                <div>
                  <label className="text-text-secondary block mb-1">MAC Address</label>
                  <input
                    type="text"
                    placeholder="48:8F:5A:00:00:01"
                    value={newNodeForm.mac}
                    onChange={(e) => setNewNodeForm({ ...newNodeForm, mac: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary font-mono outline-none focus:border-sky-500/50"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-text-secondary block mb-1">Tipe Perangkat</label>
                  <select
                    value={newNodeForm.device_type}
                    onChange={(e) => setNewNodeForm({ ...newNodeForm, device_type: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none"
                  >
                    <option value="router">Router / Core</option>
                    <option value="switch">Switch</option>
                    <option value="access_point">Access Point</option>
                    <option value="server">Server</option>
                    <option value="wan">ISP / WAN Gateway</option>
                    <option value="client">Client / Host</option>
                  </select>
                </div>
                <div>
                  <label className="text-text-secondary block mb-1">Kepemilikan (Ownership)</label>
                  <select
                    value={newNodeForm.ownership_status}
                    onChange={(e) =>
                      setNewNodeForm({
                        ...newNodeForm,
                        ownership_status: e.target.value,
                        topology_scope: e.target.value === "third_party" ? "isp_upstream" : "enterprise_internal",
                      })
                    }
                    className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none"
                  >
                    <option value="owned">Company Owned</option>
                    <option value="managed_external">Managed External</option>
                    <option value="third_party">Third-Party / ISP</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </div>
              </div>

              {/* Management & Inventory Registration */}
              <div className="p-3 rounded-2xl bg-white/[0.03] border border-white/10 space-y-2.5">
                <label className="flex items-center gap-2 cursor-pointer text-text-primary select-none">
                  <input
                    type="checkbox"
                    checked={newNodeForm.register_inventory}
                    onChange={(e) => setNewNodeForm({ ...newNodeForm, register_inventory: e.target.checked })}
                    className="rounded border-white/20 text-sky-500 focus:ring-0 bg-black/40"
                  />
                  <span className="font-semibold text-sky-300">Daftarkan ke Inventory & Monitoring</span>
                </label>

                {newNodeForm.register_inventory && (
                  <div className="space-y-2 pt-1 border-t border-white/5">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="text-text-secondary block mb-1">Port SSH</label>
                        <input
                          type="number"
                          value={newNodeForm.port}
                          onChange={(e) => setNewNodeForm({ ...newNodeForm, port: e.target.value })}
                          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-text-primary font-mono outline-none focus:border-sky-500/50"
                        />
                      </div>
                      <div>
                        <label className="text-text-secondary block mb-1">Username SSH</label>
                        <input
                          type="text"
                          value={newNodeForm.username}
                          onChange={(e) => setNewNodeForm({ ...newNodeForm, username: e.target.value })}
                          className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-text-primary outline-none focus:border-sky-500/50"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-text-secondary block mb-1">Password SSH (Opsional)</label>
                      <input
                        type="password"
                        placeholder="••••••••"
                        value={newNodeForm.password}
                        onChange={(e) => setNewNodeForm({ ...newNodeForm, password: e.target.value })}
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-text-primary font-mono outline-none focus:border-sky-500/50"
                      />
                    </div>

                    <div className="pt-1">
                      <button
                        type="button"
                        onClick={() => setShowAdvancedMgmt((v) => !v)}
                        className="text-[11px] text-white/50 hover:text-white flex items-center gap-1 transition"
                      >
                        {showAdvancedMgmt ? "Sembunyikan Opsi SNMP ▲" : "Tampilkan Opsi SNMP ▼"}
                      </button>
                      {showAdvancedMgmt && (
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          <div>
                            <label className="text-text-secondary block mb-1">SNMP Community</label>
                            <input
                              type="text"
                              placeholder="public"
                              value={newNodeForm.snmp_community}
                              onChange={(e) => setNewNodeForm({ ...newNodeForm, snmp_community: e.target.value })}
                              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-text-primary font-mono outline-none"
                            />
                          </div>
                          <div>
                            <label className="text-text-secondary block mb-1">Port SNMP</label>
                            <input
                              type="number"
                              value={newNodeForm.snmp_port}
                              onChange={(e) => setNewNodeForm({ ...newNodeForm, snmp_port: e.target.value })}
                              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-text-primary font-mono outline-none"
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Test Connection Button & Result Indicator */}
              <div className="flex items-center justify-between gap-2 pt-1">
                <button
                  type="button"
                  disabled={testingConnection || !newNodeForm.ip}
                  onClick={handleTestConnection}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-sky-500/30 bg-sky-500/10 hover:bg-sky-500/20 text-sky-300 font-medium transition disabled:opacity-40"
                >
                  {testingConnection ? <Loader2 size={13} className="animate-spin" /> : <Activity size={13} />}
                  <span>{testingConnection ? "Menguji..." : "Test Koneksi"}</span>
                </button>

                {testResult && (
                  <div className="text-[11px] font-mono flex items-center gap-1">
                    {testResult.reachable ? (
                      <span className="text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={13} />
                        {testResult.authenticated ? "Auth OK" : "Reachable"} ({testResult.latency_ms} ms)
                      </span>
                    ) : (
                      <span className="text-red-400 flex items-center gap-1" title={testResult.message}>
                        <AlertTriangle size={13} />
                        Unreachable
                      </span>
                    )}
                  </div>
                )}
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setAddNodeModal(false)}
                  className="px-4 py-2 rounded-pill bg-white/5 hover:bg-white/10 text-text-secondary transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-pill bg-sakura-gradient text-white font-semibold shadow-sakura-glow hover:brightness-110 transition"
                >
                  Simpan Perangkat
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: MANUAL LINK WIRING */}
      {addLinkModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-black border border-white/10 rounded-3xl p-6 max-w-md w-full shadow-2xl relative">
            <button
              onClick={() => setAddLinkModal(false)}
              className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
            >
              <X className="w-4 h-4" />
            </button>
            <h3 className="text-sm font-bold text-text-primary mb-1">Hubungkan Kabel (Manual Verified Link)</h3>
            <p className="text-[11px] text-text-secondary mb-4">
              Kabel manual ditandai <code>verification_status=manual</code> dan tidak ditimpa saat rediscovery.
            </p>
            <form onSubmit={handleCreateLink} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-text-secondary block mb-1">Perangkat Asal</label>
                  <select
                    value={newLinkForm.source_id}
                    onChange={(e) => setNewLinkForm({ ...newLinkForm, source_id: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none"
                  >
                    {data.nodes.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-text-secondary block mb-1">Port Asal</label>
                  <input
                    type="text"
                    placeholder="ether1 / sfp1"
                    value={newLinkForm.source_port}
                    onChange={(e) => setNewLinkForm({ ...newLinkForm, source_port: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary font-mono outline-none"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-text-secondary block mb-1">Perangkat Tujuan</label>
                  <select
                    value={newLinkForm.target_id}
                    onChange={(e) => setNewLinkForm({ ...newLinkForm, target_id: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none"
                  >
                    {data.nodes.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-text-secondary block mb-1">Port Tujuan</label>
                  <input
                    type="text"
                    placeholder="ether24 / sfp1"
                    value={newLinkForm.target_port}
                    onChange={(e) => setNewLinkForm({ ...newLinkForm, target_port: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary font-mono outline-none"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-text-secondary block mb-1">Tipe Link</label>
                  <select
                    value={newLinkForm.link_type}
                    onChange={(e) => setNewLinkForm({ ...newLinkForm, link_type: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none"
                  >
                    <option value="physical">Physical (Ethernet / Fiber)</option>
                    <option value="wireless">Wireless Bridge</option>
                    <option value="vpn">VPN Tunnel</option>
                    <option value="routed">Routed Next-Hop</option>
                  </select>
                </div>
                <div>
                  <label className="text-text-secondary block mb-1">Kapasitas</label>
                  <input
                    type="text"
                    placeholder="1 Gbps / 10 Gbps"
                    value={newLinkForm.bandwidth}
                    onChange={(e) => setNewLinkForm({ ...newLinkForm, bandwidth: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary outline-none"
                  />
                </div>
              </div>
              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setAddLinkModal(false)}
                  className="px-4 py-2 rounded-pill bg-white/5 hover:bg-white/10 text-text-secondary transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-pill bg-sakura-gradient text-white font-semibold shadow-sakura-glow hover:brightness-110 transition"
                >
                  Hubungkan Kabel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: EDIT NODE DETAILS */}
      {editNodeModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-black border border-white/10 rounded-3xl p-6 max-w-md w-full shadow-2xl relative">
            <button
              onClick={() => setEditNodeModal(null)}
              className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
            >
              <X className="w-4 h-4" />
            </button>
            <h3 className="text-sm font-bold text-text-primary mb-1">Koreksi Data Perangkat</h3>
            <p className="text-[11px] text-text-secondary mb-4">
              Perubahan nama, tipe, dan ownership dikunci sebagai override pengguna agar bertahan melewati scan ulang.
            </p>
            <form onSubmit={handleSaveNodeEdit} className="space-y-3 text-xs">
              <div>
                <label className="text-text-secondary block mb-1">Nama Tampilan</label>
                <input
                  type="text"
                  required
                  value={editNodeModal.name}
                  onChange={(e) => setEditNodeModal({ ...editNodeModal, name: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary outline-none"
                />
              </div>
              <div>
                <label className="text-text-secondary block mb-1">IP Address</label>
                <input
                  type="text"
                  value={editNodeModal.ip || ""}
                  onChange={(e) => setEditNodeModal({ ...editNodeModal, ip: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-text-primary font-mono outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-text-secondary block mb-1">Tipe Perangkat</label>
                  <select
                    value={editNodeModal.device_type}
                    onChange={(e) => setEditNodeModal({ ...editNodeModal, device_type: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none"
                  >
                    <option value="router">Router / Core</option>
                    <option value="switch">Switch</option>
                    <option value="access_point">Access Point</option>
                    <option value="server">Server</option>
                    <option value="wan">ISP / WAN Gateway</option>
                    <option value="client">Client / Host</option>
                  </select>
                </div>
                <div>
                  <label className="text-text-secondary block mb-1">Ownership</label>
                  <select
                    value={editNodeModal.ownership_status || "unknown"}
                    onChange={(e) => setEditNodeModal({ ...editNodeModal, ownership_status: e.target.value })}
                    className="w-full bg-black border border-white/10 rounded-xl px-2.5 py-2 text-text-primary outline-none"
                  >
                    <option value="owned">owned</option>
                    <option value="managed_external">managed_external</option>
                    <option value="third_party">third_party</option>
                    <option value="unknown">unknown</option>
                  </select>
                </div>
              </div>
              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditNodeModal(null)}
                  className="px-4 py-2 rounded-pill bg-white/5 hover:bg-white/10 text-text-secondary transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-pill bg-sakura-gradient text-white font-semibold shadow-sakura-glow hover:brightness-110 transition"
                >
                  Simpan Koreksi
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ROOT CAUSE ANALYSIS (RCA) MODAL */}
      {troubleshootModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-black border border-white/10 rounded-3xl p-6 max-w-lg w-full shadow-2xl relative">
            <button
              onClick={() => setTroubleshootModal(null)}
              className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-white/10 transition"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-2 mb-3">
              <div className="w-8 h-8 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <ShieldAlert className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-text-primary">Autonomous Troubleshooting RCA</h3>
                <p className="text-[11px] text-text-secondary">Path Tracing, Ownership Boundary & Failure Inference</p>
              </div>
            </div>

            {troubleshootModal.loading ? (
              <div className="py-12 flex flex-col items-center justify-center gap-3">
                <RefreshCw className="w-6 h-6 text-sky-400 animate-spin" />
                <p className="text-xs text-text-secondary">Menganalisis graf interkoneksi dan batas jaringan...</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div
                  className={`p-3.5 rounded-2xl border text-xs leading-relaxed ${
                    troubleshootModal.root_cause_node
                      ? "bg-red-500/10 border-red-500/20 text-red-300"
                      : "bg-sky-500/10 border-sky-500/20 text-sky-300"
                  }`}
                >
                  {troubleshootModal.diagnosis}
                </div>

                {troubleshootModal.path && troubleshootModal.path.length > 0 && (
                  <div>
                    <span className="text-[10px] font-semibold uppercase text-text-secondary tracking-wider block mb-2">
                      Jalur Transmisi ({troubleshootModal.path.length} Hops):
                    </span>
                    <div className="flex items-center gap-2 overflow-x-auto py-2">
                      {troubleshootModal.path.map((hop, idx) => (
                        <div key={hop.id} className="flex items-center gap-1.5 shrink-0">
                          <div
                            className={`p-2 rounded-xl border text-center ${
                              hop.status === "offline"
                                ? "bg-red-500/20 border-red-500/40 text-red-300"
                                : hop.status === "warning"
                                ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
                                : "bg-white/5 border-white/10 text-text-primary"
                            }`}
                          >
                            <span className="text-[9px] text-text-secondary block font-mono">
                              Hop {idx + 1} • {hop.ownership_status || "unknown"}
                            </span>
                            <span className="text-xs font-semibold block">{hop.name}</span>
                            <span className="text-[10px] text-text-secondary font-mono">{hop.ip || "no-ip"}</span>
                          </div>
                          {idx < troubleshootModal.path.length - 1 && (
                            <ArrowRight className="w-3.5 h-3.5 text-text-secondary/40 shrink-0" />
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="pt-2 flex justify-end">
                  <button
                    onClick={() => setTroubleshootModal(null)}
                    className="px-4 py-1.5 rounded-pill bg-white/10 hover:bg-white/20 text-xs font-medium text-text-primary transition"
                  >
                    Tutup
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      {/* NMS DEVICE TELEMETRY DETAIL MODAL */}
      {nmsDetailDeviceId && (
        <DeviceDetailModal
          deviceId={nmsDetailDeviceId}
          onClose={() => setNmsDetailDeviceId(null)}
          onOpenWizard={(dev) => setNmsWizardDevice(dev)}
          pushToast={pushToast}
        />
      )}

      {/* NMS SNMP SETUP WIZARD MODAL */}
      {nmsWizardDevice && (
        <SnmpSetupWizardModal
          device={nmsWizardDevice}
          onClose={() => setNmsWizardDevice(null)}
          onSuccess={() => {
            setNmsWizardDevice(null);
            fetchTopology(true);
          }}
          pushToast={pushToast}
        />
      )}

      {/* HISTORICAL TOPOLOGY & CHANGE DETECTION MODAL */}
      <TopologyHistoryModal
        open={historyModalOpen}
        onClose={() => setHistoryModalOpen(false)}
        onLoadOntoCanvas={handleLoadSnapshotOntoCanvas}
        pushToast={showToast}
      />

      {/* HISTORICAL ROUTE ANALYTICS MODAL (WP 4.6.4) */}
      <RouteHistoryModal
        open={routeHistoryModalOpen}
        onClose={() => setRouteHistoryModalOpen(false)}
        pushToast={showToast}
      />
    </div>
  );
}
