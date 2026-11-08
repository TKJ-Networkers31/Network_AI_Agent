export default function DividerField({ field }) {
  if (!field.label) {
    return <hr className="border-white/10" />;
  }

  return (
    <div className="flex items-center gap-3">
      <hr className="flex-1 border-white/10" />
      <span className="text-[11px] uppercase tracking-wide text-white/30">{field.label}</span>
      <hr className="flex-1 border-white/10" />
    </div>
  );
}