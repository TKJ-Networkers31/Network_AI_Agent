import { useCallback, useEffect, useState } from "react";
import TopBar from "../components/TopBar.jsx";
import { api } from "../api.js";
import { useToast } from "../components/Toast.jsx";
import BehaviorSlider from "../components/persona/BehaviorSlider.jsx";
import PresetCard from "../components/persona/PresetCard.jsx";

const BEHAVIOR_FIELDS = [
  { key: "professionalism", label: "Professionalism", low: "Casual", high: "Professional mentor" },
  { key: "friendliness", label: "Friendliness", low: "Formal", high: "Warm companion" },
  { key: "playfulness", label: "Playfulness", low: "Serious", high: "Light teasing" },
  { key: "verbosity", label: "Verbosity", low: "Short", high: "Very detailed" },
  { key: "empathy", label: "Empathy", low: "Objective", high: "Emotionally supportive" },
  { key: "teaching_depth", label: "Teaching Depth", low: "Quick answer", high: "Beginner → Expert" },
];

export default function PersonaPage({ onOpenMenu }) {
  const [profile, setProfile] = useState(null);
  const [behavior, setBehavior] = useState(null);
  const [presets, setPresets] = useState([]);
  const [preview, setPreview] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const { notify } = useToast();

  const loadAll = useCallback(() => {
    setLoading(true);
    Promise.all([api.persona.get(), api.persona.presets()])
      .then(([state, presetRes]) => {
        setProfile(state.profile);
        setBehavior(state.behavior);
        setPresets(presetRes.presets);
      })
      .catch((e) => notify({ type: "error", message: e.message }))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadPreview = useCallback(() => {
    setPreviewLoading(true);
    api.persona
      .preview()
      .then((res) => setPreview(res.system_prompt))
      .catch((e) => notify({ type: "error", message: e.message }))
      .finally(() => setPreviewLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!loading) loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  function handleProfileField(field, value) {
    setProfile((prev) => ({ ...prev, [field]: value }));
  }

  async function saveProfile() {
    setSavingProfile(true);
    try {
      const res = await api.persona.updateProfile({
        assistant_name: profile.assistant_name,
        user_name: profile.user_name,
        language: profile.language,
        timezone: profile.timezone,
        greeting: profile.greeting,
      });
      setProfile(res.profile);
      notify({ type: "success", message: "Identity tersimpan.", duration: 2500 });
      loadPreview();
    } catch (err) {
      notify({ type: "error", message: err.message });
    } finally {
      setSavingProfile(false);
    }
  }

  function handleSliderChange(key, value) {
    setBehavior((prev) => ({ ...prev, [key]: value }));
  }

  async function commitSlider(key, value) {
    try {
      const res = await api.persona.updateBehavior({ [key]: value });
      setBehavior(res.behavior);
      loadPreview();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleApplyPreset(presetId) {
    try {
      const res = await api.persona.applyPreset(presetId);
      setProfile(res.state.profile);
      setBehavior(res.state.behavior);
      loadAll();
      loadPreview();
      notify({ type: "success", message: `Preset "${presetId}" diterapkan.`, duration: 2500 });
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  async function handleDuplicatePreset(presetId, currentName) {
    const newName = window.prompt("Nama preset baru:", `${currentName} Copy`);
    if (!newName || !newName.trim()) return;

    try {
      await api.persona.clonePreset(presetId, newName.trim());
      notify({ type: "success", message: `Preset "${newName}" dibuat.`, duration: 2500 });
      loadAll();
    } catch (err) {
      notify({ type: "error", message: err.message });
    }
  }

  if (loading || !profile || !behavior) {
    return (
      <div>
        <TopBar title="Persona" subtitle="Dynamic Persona Engine" onMenuClick={onOpenMenu} />
        <p className="text-white/40 text-sm">Memuat persona...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <TopBar
        title="Persona"
        subtitle="Kepribadian AIRA - terpisah dari model LLM yang dipakai"
        onMenuClick={onOpenMenu}
      />

      {/* Section 1 — Identity */}
      <section className="bg-card border border-border rounded-xl2 p-5">
        <h3 className="font-semibold text-white mb-4">Identity</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-white/50 block mb-1">Assistant Name</label>
            <input
              value={profile.assistant_name || ""}
              onChange={(e) => handleProfileField("assistant_name", e.target.value)}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </div>

          <div>
            <label className="text-xs text-white/50 block mb-1">User Name</label>
            <input
              value={profile.user_name || ""}
              onChange={(e) => handleProfileField("user_name", e.target.value)}
              placeholder="opsional"
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </div>

          <div>
            <label className="text-xs text-white/50 block mb-1">Language</label>
            <input
              value={profile.language || ""}
              onChange={(e) => handleProfileField("language", e.target.value)}
              placeholder="id"
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </div>

          <div>
            <label className="text-xs text-white/50 block mb-1">Timezone</label>
            <input
              value={profile.timezone || ""}
              onChange={(e) => handleProfileField("timezone", e.target.value)}
              placeholder="Asia/Jakarta"
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            />
          </div>

          <div className="sm:col-span-2">
            <label className="text-xs text-white/50 block mb-1">Greeting</label>
            <textarea
              value={profile.greeting || ""}
              onChange={(e) => handleProfileField("greeting", e.target.value)}
              rows={2}
              className="w-full bg-white/5 border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent resize-none"
            />
          </div>
        </div>

        <button
          onClick={saveProfile}
          disabled={savingProfile}
          className="mt-4 bg-accent-gradient text-white text-sm font-semibold px-4 py-2 rounded-lg disabled:opacity-50"
        >
          {savingProfile ? "Menyimpan..." : "Simpan Identity"}
        </button>
      </section>

      {/* Section 2 — Behavior */}
      <section className="bg-card border border-border rounded-xl2 p-5">
        <h3 className="font-semibold text-white mb-4">Behavior</h3>

        <div className="space-y-5">
          {BEHAVIOR_FIELDS.map((field) => (
            <BehaviorSlider
              key={field.key}
              label={field.label}
              value={behavior[field.key]}
              lowLabel={field.low}
              highLabel={field.high}
              onChange={(v) => handleSliderChange(field.key, v)}
              onCommit={(v) => commitSlider(field.key, v)}
            />
          ))}
        </div>
      </section>

      {/* Section 3 — Presets */}
      <section className="bg-card border border-border rounded-xl2 p-5">
        <h3 className="font-semibold text-white mb-4">Presets</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {presets.map((p) => (
            <PresetCard
              key={p.id}
              preset={p}
              onApply={() => handleApplyPreset(p.id)}
              onDuplicate={() => handleDuplicatePreset(p.id, p.name)}
            />
          ))}
        </div>
      </section>

      {/* Section 4 — Live Preview */}
      <section className="bg-card border border-border rounded-xl2 p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-white">Live Preview</h3>
          <button
            onClick={loadPreview}
            disabled={previewLoading}
            className="text-xs px-3 py-1.5 rounded-lg bg-white/5 text-white/70 hover:text-white disabled:opacity-50"
          >
            {previewLoading ? "Memuat..." : "⟳ Refresh"}
          </button>
        </div>

        <textarea
          readOnly
          value={preview}
          rows={16}
          className="w-full bg-black/30 border border-border rounded-lg px-3 py-2 text-xs font-mono text-white/70 outline-none resize-y"
        />
      </section>
    </div>
  );
}