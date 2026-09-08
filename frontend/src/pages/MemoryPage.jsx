import { useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";

export default function MemoryPage() {
  const [facts, setFacts] = useState([]);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [error, setError] = useState(null);

  function loadFacts() {
    api
      .facts()
      .then((res) => setFacts(res.facts))
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    loadFacts();
  }, []);

  async function handleAdd(e) {
    e.preventDefault();
    if (!newKey.trim() || !newValue.trim()) return;

    try {
      await api.addFact(newKey.trim(), newValue.trim());
      setNewKey("");
      setNewValue("");
      loadFacts();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(key) {
    try {
      await api.deleteFact(key);
      loadFacts();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <TopBar
        title="Memory"
        subtitle="Fakta jangka-panjang yang diingat agent lintas sesi"
      />

      <form
        onSubmit={handleAdd}
        className="bg-card border border-border rounded-xl2 p-4 mb-6 flex flex-col sm:flex-row gap-3"
      >
        <input
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          placeholder="key (mis. threshold_cpu_r1)"
          className="flex-1 bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <input
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          placeholder="value"
          className="flex-1 bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
        />
        <button
          type="submit"
          className="bg-accent-gradient text-white text-sm font-semibold px-4 py-2 rounded-lg"
        >
          + Tambah
        </button>
      </form>

      {error && (
        <div className="text-sm mb-4 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300">
          {error}
        </div>
      )}

      <div className="space-y-2">
        {facts.map((f) => (
          <div
            key={f.key}
            className="flex items-center justify-between bg-card border border-border rounded-xl2 px-4 py-3"
          >
            <div className="min-w-0">
              <div className="text-xs text-accent-light font-mono">{f.key}</div>
              <div className="text-sm text-white/80 truncate">{f.value}</div>
            </div>
            <button
              onClick={() => handleDelete(f.key)}
              className="shrink-0 text-xs text-red-300 hover:text-red-200 border border-red-500/20 hover:bg-red-500/10 rounded-lg px-3 py-1.5 ml-3"
            >
              Hapus
            </button>
          </div>
        ))}

        {facts.length === 0 && (
          <p className="text-white/40 text-sm">
            Belum ada fakta tersimpan. Agent akan otomatis menyimpan hal
            penting saat kamu chat.
          </p>
        )}
      </div>
    </div>
  );
}
