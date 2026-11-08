import React, { useMemo } from "react";
import { useInteractionState } from "../../hooks/useInteractionState.js";
import SectionRenderer from "./SectionRenderer.jsx";
import ActionBar from "./ActionBar.jsx";

/**
 * Renderer — Universal Interaction Renderer.
 *
 * Normalizes both nested section schemas (sections[].fields[])
 * and flat schemas (fields[] + submit/actions) with full resilience.
 */
export default function Renderer({ schema, onSubmitAction }) {
  const normalizedSchema = useMemo(() => {
    if (!schema) return null;
    const s = { ...schema };

    // 1. Normalize flat fields into sections
    if ((!s.sections || s.sections.length === 0) && Array.isArray(s.fields)) {
      s.sections = [
        {
          id: s.form_id || "form",
          title: s.title || null,
          columns: s.fields.length > 2 ? 2 : 1,
          fields: s.fields.map((f) => ({ ...f, id: f.id || f.name })),
        },
      ];
    } else if (Array.isArray(s.sections)) {
      s.sections = s.sections.map((sec) => ({
        ...sec,
        fields: (sec.fields || []).map((f) => ({ ...f, id: f.id || f.name })),
      }));
    }

    // 2. Normalize actions / submit button
    if (!s.actions || s.actions.length === 0) {
      if (s.submit) {
        s.actions = [
          { id: "cancel", label: "Batal", style: "ghost" },
          { id: "submit", label: s.submit.label || "Submit", style: "primary" },
        ];
      } else {
        s.actions = [
          { id: "cancel", label: "Batal", style: "ghost" },
          { id: "submit", label: "Simpan", style: "primary" },
        ];
      }
    }

    return s;
  }, [schema]);

  const { values, errors, setValue, submit } = useInteractionState(normalizedSchema);

  if (!normalizedSchema) return null;

  function handleAction(actionId, extraValues) {
    const action = (normalizedSchema.actions || []).find((a) => a.id === actionId);
    const needsValidation = !action || !["ghost", "secondary"].includes(action.style);

    if (needsValidation) {
      submit((finalValues) => onSubmitAction?.(actionId, { ...finalValues, ...extraValues }));
    } else {
      onSubmitAction?.(actionId, { ...values, ...extraValues });
    }
  }

  const sections = normalizedSchema.sections || [];

  return (
    <div className="max-w-[720px] w-full bg-[#111827] border border-white/10 rounded-2xl p-4 sm:p-5 space-y-4 shadow-lg shadow-black/20">
      {(normalizedSchema.title || normalizedSchema.description) && (
        <div>
          {normalizedSchema.title && <h3 className="text-base font-semibold text-white">{normalizedSchema.title}</h3>}
          {normalizedSchema.description && (
            <p className="text-sm text-white/50 mt-1">{normalizedSchema.description}</p>
          )}
        </div>
      )}

      {sections.length === 0 ? (
        <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300 text-xs">
          Tidak ada elemen interaktif yang dapat ditampilkan pada schema ini.
        </div>
      ) : (
        <div className="space-y-5">
          {sections.map((section, i) => (
            <SectionRenderer
              key={section.id || i}
              section={section}
              values={values}
              errors={errors}
              onChange={setValue}
              onAction={handleAction}
            />
          ))}
        </div>
      )}

      <ActionBar actions={normalizedSchema.actions} onAction={handleAction} />
    </div>
  );
}