import { useCallback, useEffect, useRef, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";

const LEVEL_STYLES = {
  DEBUG: "text-white/40 border-white/10 bg-white/5",
  INFO: "text-sky-300 border-sky-500/20 bg-sky-500/10",
  WARNING: "text-amber-300 border-amber-500/20 bg-amber-500/10",
  ERROR: "text-red-300 border-red-500/20 bg-red-500/10",
  CRITICAL: "text-white border-red-500/60 bg-red-600/40",
};

const LEVELS = ["all", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
const AUTO_REFRESH_MS = 5000;

function formatTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleString("id-ID", { hour12: false });
}

function LogRow({ log }) {
  const [open, setOpen] = useState(false);
  const style = LEVEL_STYLES[log.level] || LEVEL_STYLES.INFO;
  const hasContext = log.context && Object.keys(log.context).length > 0;

  return (
    <div className="border border-border rounded-lg bg-card/60 overflow-hidden">
      <button
        type="button"
        onClick={() => hasContext && setOpen((v) => !v)}
        className={`w-full text-left px-3 py-2 flex items-start gap-2 ${hasContext ? "cursor-pointer hover:bg-white/5" : "cursor-default"}`}
      >
        <span className={`shrink-0 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${style}`}>
          {log.level}
        </span>
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-accent-light bg-accent/10 px-2 py-0.5 rounded-full mt-0">
          {log.category}
        </span>
        <span className="flex-1 min-w-0 text-sm text-white/80 truncate">
          {log.message}
        </span>
        {typeof log.duration_ms === "number" && (
          <span className="shrink-0 text-[10px] text-white/30">{log.duration_ms.toFixed(0)}ms</span>
        )}
        {log.success === false && <span className="shrink-0 text-[10px] text-red-300">✗</span>}
        {log.success === true && <span className="shrink-0 text-[10px] text-emerald-300">✓</span>}
        <span className="shrink-0 text-[10px] text-white/30 font-mono">{formatTime(log.created_at)}</span>
      </button>

      {open && hasContext && (
        <pre className="text-[11px] text-white/60 bg-black/30 px-3 py-2 overflow-x-auto border-t border-border">
          {JSON.stringify(log.context, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function LogsPage({ onOpenMenu }) {
  const [logs, setLogs] = useState([]);
  const [categories, setCategories] = useState([]);
  const [total, setTotal] = useState(0);
  const [category, setCategory] = useState("all");
  const [level, setLevel] = useState("all");
  const [search, setSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(false);
  const { notify } = useToast();

  const searchRef = useRef(search);
  searchRef.current = search;

  const loadCategories = useCallback(() => {
    api.logs
      .categories()
      .then((res) => setCategories(res.categories))
      .catch(() => {});
  }, []);

  const loadLogs = useCallback(
    (silent = false) => {
      if (!silent) setLoading(true);

      api.logs
        .list({
          category: category === "all" ? undefined : category,
          level: level === "all" ? undefined : level,
          search: searchRef.current || undefined,
          limit: 150,
        })
        .then((res) => {
          setLogs(res.logs);
          setTotal(res.total);
        })
        .catch((e) => notify({ type: "error", message: e.message }))
        .finally(() => setLoading(false));
    },
    [category, level, notify]
  );

  useEffect(() => {
    loadCategories();
  }, [loadCategories]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  useEffect(() => {
    if (!autoRefresh) return undefined;

    const timer = setInterval(() => {
      loadLogs(true);
      loadCategories();
    }, AUTO_REFRESH_MS);

    return () => clearInterval(timer);
  }, [autoRefresh, loadLogs, loadCategories]);

  function handleSearchSubmit(e) {
    e.preventDefault();
    loadLogs();
  }

  async function handleClear() {
    const label = category === "all" ? "SEMUA kategori" : `kategori "${category}"`;
    if (!window.confirm(`Hapus log ${label}? Tindakan ini tidak bisa dibatalkan.`)) return;

    try {
      const res = await api.logs.clear(category === "all" ? undefined : category);
      notify({ type: "success", message: `${res.deleted} log dihapus.`, duration: 2500 });
      loadLogs();
      loadCategories();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  return (
    <div className="flex flex-col min-h-0 h-full">
      <TopBar title="Logs" subtitle={`${total} entri · kategori & level bisa difilter`} onMenuClick={onOpenMenu} />

      <div className="bg-card border border-border rounded-xl2 p-4 mb-4 space-y-3 shrink-0">
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setCategory("all")}
            className={`text-xs px-3 py-1.5 rounded-full border transition ${
              category === "all" ? "bg-accent-gradient text-white border-transparent" : "border-border text-white/50 hover:text-white"
            }`}
          >
            Semua ({categories.reduce((s, c) => s + c.count, 0)})
          </button>
          {categories.map((c) => (
            <button
              key={c.category}
              onClick={() => setCategory(c.category)}
              className={`text-xs px-3 py-1.5 rounded-full border transition ${
                category === c.category ? "bg-accent-gradient text-white border-transparent" : "border-border text-white/50 hover:text-white"
              }`}
            >
              {c.category} ({c.count})
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="bg-white/5 border border-border rounded-lg px-2 py-1.5 text-xs text-white/80 outline-none"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l === "all" ? "Semua level" : l}</option>
            ))}
          </select>

          <form onSubmit={handleSearchSubmit} className="flex-1 min-w-[160px] flex gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cari pesan/context..."
              className="flex-1 bg-white/5 border border-border rounded-lg px-3 py-1.5 text-xs outline-none focus:border-accent"
            />
            <button type="submit" className="text-xs px-3 py-1.5 rounded-lg bg-white/10 text-white/70 hover:text-white">
              Cari
            </button>
          </form>

          <label className="flex items-center gap-1.5 text-xs text-white/50 select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-accent"
            />
            Auto-refresh 5s
          </label>

          <button
            onClick={() => loadLogs()}
            className="text-xs px-3 py-1.5 rounded-lg bg-white/10 text-white/70 hover:text-white"
          >
            ⟳ Refresh
          </button>

          <button
            onClick={handleClear}
            className="text-xs px-3 py-1.5 rounded-lg bg-red-500/10 text-red-300 hover:bg-red-500/20 border border-red-500/20"
          >
            Hapus
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 space-y-1.5 pr-1">
        {loading && logs.length === 0 && (
          <p className="text-white/30 text-sm text-center mt-10">Memuat log...</p>
        )}

        {!loading && logs.length === 0 && (
          <p className="text-white/30 text-sm text-center mt-10">Tidak ada log untuk filter ini.</p>
        )}

        {logs.map((log) => (
          <LogRow key={log.id} log={log} />
        ))}
      </div>
    </div>
  );
}