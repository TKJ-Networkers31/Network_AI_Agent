export default function BootScreen({ label = "Menyiapkan AIRA..." }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 text-white/60 min-h-[60vh]">
      <div
        className="w-10 h-10 rounded-full border-2 border-accent-light/30 border-t-accent-light spin-ring"
        aria-hidden="true"
      />
      <p className="text-sm">{label}</p>
    </div>
  );
}