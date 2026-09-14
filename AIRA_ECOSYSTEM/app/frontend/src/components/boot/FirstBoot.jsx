export default function FirstBoot({ onDone }) {
  return (
    <div className="aira-firstboot">
      <img
        src="/assets/brand/first-boot.png"
        alt="Selamat datang di AIRA"
        className="aira-firstboot__image"
      />
      <div className="aira-firstboot__content">
        <h1>Selamat datang di AIRA</h1>
        <p>
          Adaptive Intelligent Reasoning Assistant siap membantu monitoring
          dan manajemen jaringanmu.
        </p>
        <button onClick={onDone} className="aira-firstboot__button">
          Mulai
        </button>
      </div>
    </div>
  );
}