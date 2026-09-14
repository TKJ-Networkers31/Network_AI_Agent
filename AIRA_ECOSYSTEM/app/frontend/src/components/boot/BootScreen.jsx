export default function BootScreen({ label = "Menyiapkan AIRA..." }) {
  return (
    <div className="aira-boot">
      <div className="aira-boot__emblem-wrap">
        <img
          src="/assets/brand/boot-emblem.png"
          alt="AIRA"
          className="aira-boot__emblem"
        />
        <span className="aira-boot__glow" aria-hidden="true" />
      </div>
      <p className="aira-boot__label">{label}</p>
    </div>
  );
}