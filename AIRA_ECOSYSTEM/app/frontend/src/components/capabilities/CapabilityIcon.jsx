// src/components/capabilities/CapabilityIcon.jsx
//
// SPRINT 2.7 - W8 (Dynamic Capability UI)
//
// Registry ikon generik, dipetakan dari string `capability.icon` yang
// dikirim backend. Ini BUKAN daftar kapabilitas - hanya tabel visual kecil
// (nama -> path SVG) supaya kapabilitas apa pun yang backend kirim dapat
// dirender dengan ikon yang masuk akal. Nama yang tidak dikenal jatuh ke
// ikon titik generik ("dot"), jadi backend selalu aman menambah kapabilitas
// baru tanpa menunggu rilis frontend.

const ICONS = {
  spark: ["M12 2 13.6 8.4 20 10 13.6 11.6 12 18 10.4 11.6 4 10 10.4 8.4 12 2Z"],
  translate: [
    "M4 5h7M7.5 3v2",
    "M6 9c1 2.5 3 4.3 5.5 5.3",
    "M11 5c-1.2 3.8-3.6 6.8-7 8.6",
    "M13 20l3.5-8 3.5 8M14.6 17h3.8",
  ],
  image: ["M4 5h16v14H4z", "M8 12l3-3 3 3 3-4 2 3"],
  tool: ["M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 1 5.4-5.4l-2.6 2.6-2-2 2.6-2.6Z"],
  link: ["M9 15l6-6", "M8 12l-2.5 2.5a3 3 0 0 0 4.2 4.2L12 16", "M12 8l2.3-2.3a3 3 0 0 1 4.2 4.2L16 12"],
  location: ["M12 21s-7-6.1-7-11a7 7 0 0 1 14 0c0 4.9-7 11-7 11Z", "M12 12.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"],
  folder: ["M4 6h5l2 2h9v11H4Z"],
  chat: ["M4 5h16v10H8l-4 4Z"],
  attachment: ["M17 8v8a4 4 0 0 1-8 0V6a2.5 2.5 0 0 1 5 0v9a1 1 0 0 1-2 0V8"],
  trash: ["M5 7h14", "M9 7V5h6v2", "M7 7l1 13h8l1-13"],
  copy: ["M9 9h9v9H9z", "M6 15V6h9"],
  dot: ["M12 12m-2 0a2 2 0 1 0 4 0 2 2 0 1 0-4 0"],
};

export default function CapabilityIcon({ name, className = "w-3.5 h-3.5" }) {
  const paths = ICONS[name] || ICONS.dot;

  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      {paths.map((d, i) => (
        <path
          key={i}
          d={d}
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </svg>
  );
}
