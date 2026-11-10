import React from "react";

export default function UnknownBlockFallback({ block }) {
  const originalType = block?.data?.originalType || block?.type || "unknown";
  const message =
    block?.data?.message ||
    `Komponen tipe '${originalType}' belum terdaftar pada VAE registry.`;

  const children = [
    React.createElement(
      "div",
      { key: "header", className: "flex items-center gap-1.5 font-medium" },
      React.createElement("span", null, "⚠"),
      React.createElement("span", null, message)
    ),
  ];

  if (block?.data?.originalData && Object.keys(block.data.originalData).length > 0) {
    children.push(
      React.createElement(
        "pre",
        {
          key: "raw",
          className: "mt-1 p-2 bg-black/40 rounded text-[11px] text-white/70 overflow-x-auto",
        },
        React.createElement("code", null, JSON.stringify(block.data.originalData, null, 2))
      )
    );
  }

  return React.createElement(
    "div",
    {
      className: "my-2 p-3 rounded-xl border border-amber-500/20 bg-amber-500/10 text-amber-300 text-xs flex flex-col gap-1",
    },
    children
  );
}
