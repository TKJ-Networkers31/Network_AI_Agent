import { useState } from "react";

export default function TableField({ field, value, onChange }) {
  const rows = value && value.length ? value : field.rows || [];
  const [selected, setSelected] = useState([]);

  function updateCell(rowIndex, key, cellValue) {
    onChange(rows.map((row, i) => (i === rowIndex ? { ...row, [key]: cellValue } : row)));
  }

  function toggleSelect(rowIndex) {
    setSelected((prev) =>
      prev.includes(rowIndex) ? prev.filter((i) => i !== rowIndex) : [...prev, rowIndex]
    );
  }

  return (
    <div>
      {field.label && (
        <label className="text-xs font-medium text-white/70 mb-1.5 block">{field.label}</label>
      )}

      <div className="overflow-x-auto rounded-2xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-[#1F2937]">
            <tr>
              {field.selectable && <th className="w-8 px-3 py-2" />}
              {(field.columns || []).map((col) => (
                <th
                  key={col.key}
                  className="text-left px-3 py-2 text-xs font-semibold text-white/60 whitespace-nowrap"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-t border-white/10">
                {field.selectable && (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.includes(rowIndex)}
                      onChange={() => toggleSelect(rowIndex)}
                      className="accent-[#2563EB]"
                    />
                  </td>
                )}
                {(field.columns || []).map((col) => (
                  <td key={col.key} className="px-3 py-2 text-white/85">
                    {col.editable ? (
                      <input
                        type="text"
                        value={row[col.key] ?? ""}
                        onChange={(e) => updateCell(rowIndex, col.key, e.target.value)}
                        className="w-full bg-transparent border-b border-white/10 focus:border-[#2563EB] outline-none text-sm py-0.5"
                      />
                    ) : (
                      row[col.key]
                    )}
                  </td>
                ))}
              </tr>
            ))}

            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={(field.columns || []).length + (field.selectable ? 1 : 0)}
                  className="px-3 py-6 text-center text-white/30 text-xs"
                >
                  Tidak ada data.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}