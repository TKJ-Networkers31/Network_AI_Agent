import { useCallback, useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import WorkspaceSidebar from "../components/workspace/WorkspaceSidebar.jsx";
import WorkspaceToolbar from "../components/workspace/WorkspaceToolbar.jsx";
import FileGrid from "../components/workspace/FileGrid.jsx";
import PropertyPanel from "../components/workspace/PropertyPanel.jsx";
import ContextMenu from "../components/workspace/ContextMenu.jsx";
import { formatDate } from "../components/workspace/FileRow.jsx";

function parentOf(path) {
  const idx = (path || "").lastIndexOf("/");
  return idx === -1 ? "" : path.slice(0, idx);
}

export default function WorkspacePage({ onOpenMenu }) {
  const { notify } = useToast();

  const [hostInfo, setHostInfo] = useState(null);
  const [activeSection, setActiveSection] = useState("Projects");
  const [currentPath, setCurrentPath] = useState("Projects");
  const [entries, setEntries] = useState([]);
  const [trashEntries, setTrashEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState("grid");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);
  const [permissionRules, setPermissionRules] = useState({});

  useEffect(() => {
    api.host
      .info()
      .then(setHostInfo)
      .catch(() => {});

    api.workspace
      .permissions()
      .then((res) => setPermissionRules(res.rules || {}))
      .catch(() => {});
  }, []);

  const loadFolder = useCallback(
    (path) => {
      setLoading(true);
      setSelected(null);

      api.workspace
        .tree(path, 1)
        .then((node) => {
          setEntries(node.children.map((c) => c.entry));
          setCurrentPath(path);
        })
        .catch((err) => notify({ type: "error", message: err.message }))
        .finally(() => setLoading(false));
    },
    [notify]
  );

  const loadTrash = useCallback(() => {
    setLoading(true);
    setSelected(null);

    api.workspace
      .trashList()
      .then((res) => setTrashEntries(res.entries || []))
      .catch((err) => notify({ type: "error", message: err.message }))
      .finally(() => setLoading(false));
  }, [notify]);

  useEffect(() => {
    loadFolder("Projects");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSelectSection(section) {
    setActiveSection(section);
    setSearch("");

    if (section === "Trash") {
      loadTrash();
    } else {
      loadFolder(section);
    }
  }

  function handleBreadcrumbNavigate(path) {
    if (activeSection === "Trash") return;
    loadFolder(path || activeSection);
  }

  function handleOpen(entry) {
    if (entry.is_dir) loadFolder(entry.path);
  }

  function handleContextMenu(e, entry) {
    setSelected(entry);
    setContextMenu({ x: e.clientX, y: e.clientY, entry });
  }

  async function handleCreateFolder() {
    const name = window.prompt("Nama folder baru:");
    if (!name || !name.trim()) return;

    const path = currentPath ? `${currentPath}/${name.trim()}` : name.trim();

    try {
      await api.workspace.mkdir(path);
      notify({ type: "success", message: `Folder "${name}" dibuat.`, duration: 2500 });
      loadFolder(currentPath);
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleRename(entry) {
    const newName = window.prompt("Nama baru:", entry.name);
    if (!newName || !newName.trim() || newName.trim() === entry.name) return;

    const destination = `${parentOf(entry.path)}/${newName.trim()}`.replace(/^\//, "");

    try {
      await api.workspace.rename(entry.path, destination);
      notify({ type: "success", message: "Berhasil di-rename.", duration: 2500 });
      loadFolder(currentPath);
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleMove(entry) {
    const destination = window.prompt(
      "Path tujuan (relatif ke workspace root):",
      entry.path
    );
    if (!destination || !destination.trim() || destination.trim() === entry.path) return;

    try {
      await api.workspace.move(entry.path, destination.trim());
      notify({ type: "success", message: "Berhasil dipindahkan.", duration: 2500 });
      loadFolder(currentPath);
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleDelete(entry) {
    if (!window.confirm(`Hapus "${entry.name}"? Item akan dipindahkan ke Trash.`)) return;

    try {
      await api.workspace.delete(entry.path);
      notify({ type: "success", message: `"${entry.name}" dipindahkan ke Trash.`, duration: 2500 });
      loadFolder(currentPath);
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleRestore(trashEntry) {
    try {
      await api.workspace.restore(trashEntry.trash_id);
      notify({ type: "success", message: "Berhasil di-restore.", duration: 2500 });
      loadTrash();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  const filteredEntries = entries.filter((e) =>
    e.name.toLowerCase().includes(search.toLowerCase())
  );

  const isTrash = activeSection === "Trash";

  const contextMenuItems = contextMenu
    ? isTrash
      ? [
          {
            label: "Restore",
            icon: "♻️",
            onClick: () => handleRestore(contextMenu.entry),
          },
        ]
      : [
          ...(contextMenu.entry.is_dir
            ? [{ label: "Open", icon: "📂", onClick: () => handleOpen(contextMenu.entry) }]
            : []),
          { label: "Rename", icon: "✏️", onClick: () => handleRename(contextMenu.entry) },
          { label: "Move", icon: "📦", onClick: () => handleMove(contextMenu.entry) },
          { label: "Delete", icon: "🗑", danger: true, onClick: () => handleDelete(contextMenu.entry) },
        ]
    : [];

  return (
    <div className="flex flex-col min-h-0 h-full">
      <TopBar
        title="Workspace"
        subtitle="Antarmuka visual File System Engine AIRA"
        onMenuClick={onOpenMenu}
      />

      {hostInfo && (
        <div className="mb-4 text-xs text-white/40 bg-card border border-border rounded-xl2 px-4 py-2.5 flex items-center gap-2 flex-wrap">
          <span>💻 {hostInfo.os_name === "windows" ? "Windows" : "Linux"} ({hostInfo.architecture})</span>
          <span className="text-white/20">•</span>
          <span className="font-mono text-pink-200/80">{hostInfo.workspace_root}</span>
          <span className="text-white/20">•</span>
          <span>Storage: <span className="text-emerald-300">available</span></span>
        </div>
      )}

      <div className="flex-1 min-h-0 flex flex-col md:flex-row gap-4">
        <WorkspaceSidebar active={activeSection} onSelect={handleSelectSection} />

        <div className="flex-1 min-h-0 flex flex-col gap-3">
          {!isTrash && (
            <WorkspaceToolbar
              currentPath={currentPath}
              onNavigate={handleBreadcrumbNavigate}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              search={search}
              onSearchChange={setSearch}
              onCreateFolder={handleCreateFolder}
              showCreateFolder
            />
          )}

          <div className="flex-1 min-h-0 overflow-y-auto bg-card/50 border border-border rounded-xl2 p-4">
            {loading && <p className="text-white/30 text-sm text-center mt-10">Memuat...</p>}

            {!loading && isTrash && (
              <div className="space-y-1">
                {trashEntries.length === 0 && (
                  <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                    <span className="text-5xl opacity-50">🗑️</span>
                    <p className="text-white/40 text-sm">Trash kosong</p>
                  </div>
                )}

                {trashEntries.map((t) => (
                  <div
                    key={t.trash_id}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setContextMenu({ x: e.clientX, y: e.clientY, entry: t });
                    }}
                    className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg hover:bg-white/5 transition"
                  >
                    <div className="min-w-0">
                      <div className="text-sm text-white/85 truncate">{t.original_path}</div>
                      <div className="text-xs text-white/30">
                        Dihapus {formatDate(t.deleted_at)}
                      </div>
                    </div>
                    <button
                      onClick={() => handleRestore(t)}
                      className="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-pink-500/10 border border-pink-400/30 text-pink-200 hover:bg-pink-500/20 transition"
                    >
                      ♻️ Restore
                    </button>
                  </div>
                ))}
              </div>
            )}

            {!loading && !isTrash && (
              <FileGrid
                entries={filteredEntries}
                viewMode={viewMode}
                selectedPath={selected?.path}
                onSelect={setSelected}
                onOpen={handleOpen}
                onContextMenu={handleContextMenu}
                onCreateFolder={handleCreateFolder}
              />
            )}
          </div>
        </div>

        {selected && !isTrash && (
          <PropertyPanel
            entry={selected}
            permissionRules={permissionRules}
            onClose={() => setSelected(null)}
            onRename={handleRename}
            onMove={handleMove}
            onDelete={handleDelete}
          />
        )}
      </div>

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenuItems}
          onClose={() => setContextMenu(null)}
        />
      )}
    </div>
  );
}