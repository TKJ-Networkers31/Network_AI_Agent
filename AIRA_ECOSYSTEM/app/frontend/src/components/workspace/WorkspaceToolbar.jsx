import Breadcrumb from "./Breadcrumb.jsx";

export default function WorkspaceToolbar({
  currentPath,
  onNavigate,
  viewMode,
  onViewModeChange,
  search,
  onSearchChange,
  onCreateFolder,
  showCreateFolder,
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 bg-card border border-border rounded-xl2 px-4 py-3">
      <div className="flex-1 min-w-0">
        <Breadcrumb path={currentPath} onNavigate={onNavigate} />
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search file..."
          className="bg-white/5 border border-border rounded-lg px-3 py-1.5 text-sm outline-none focus:border-pink-400/50 w-40"
        />

        <div className="flex items-center bg-white/5 border border-border rounded-lg overflow-hidden">
          <button
            onClick={() => onViewModeChange("grid")}
            className={`px-2.5 py-1.5 text-sm transition ${
              viewMode === "grid" ? "bg-pink-500/20 text-pink-200" : "text-white/50 hover:text-white"
            }`}
            title="Grid view"
          >
            ▦
          </button>
          <button
            onClick={() => onViewModeChange("list")}
            className={`px-2.5 py-1.5 text-sm transition ${
              viewMode === "list" ? "bg-pink-500/20 text-pink-200" : "text-white/50 hover:text-white"
            }`}
            title="List view"
          >
            ☰
          </button>
        </div>

        {showCreateFolder && (
          <button
            onClick={onCreateFolder}
            className="text-sm px-3 py-1.5 rounded-lg bg-accent-gradient text-white font-medium whitespace-nowrap"
          >
            + Folder
          </button>
        )}
      </div>
    </div>
  );
}