import FileRow from "./FileRow.jsx";

export default function FileGrid({ entries, viewMode, selectedPath, onSelect, onOpen, onContextMenu, onCreateFolder }) {
  if (entries.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center py-16">
        <span className="text-5xl opacity-50">🌸</span>
        <p className="text-white/40 text-sm">No files yet</p>
        <button
          onClick={onCreateFolder}
          className="text-sm px-4 py-2 rounded-lg bg-pink-500/10 border border-pink-400/30 text-pink-200 hover:bg-pink-500/20 transition"
        >
          + Create Folder
        </button>
      </div>
    );
  }

  if (viewMode === "grid") {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3">
        {entries.map((entry) => (
          <FileRow
            key={entry.path}
            entry={entry}
            isGrid
            isSelected={selectedPath === entry.path}
            onSelect={onSelect}
            onOpen={onOpen}
            onContextMenu={onContextMenu}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      <div className="grid grid-cols-[1fr_100px_160px] gap-3 px-3 pb-2 text-[10px] uppercase tracking-wide text-white/30">
        <span>Name</span>
        <span>Size</span>
        <span>Modified</span>
      </div>
      {entries.map((entry) => (
        <FileRow
          key={entry.path}
          entry={entry}
          isGrid={false}
          isSelected={selectedPath === entry.path}
          onSelect={onSelect}
          onOpen={onOpen}
          onContextMenu={onContextMenu}
        />
      ))}
    </div>
  );
}