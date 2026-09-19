import { useInteractionState } from "../../hooks/useInteractionState.js";
import SectionRenderer from "./SectionRenderer.jsx";
import ActionBar from "./ActionBar.jsx";

/**
 * Renderer — Universal Interaction Renderer.
 *
 * TAMBAHAN (Worker 3 - Location): handleAction menerima parameter kedua
 * `extraValues` opsional - dipakai field yang mengurus alur async sendiri
 * (mis. LocationPermissionField yang baru dapat koordinat dari browser)
 * untuk menyisipkan data langsung ke payload submit TANPA bergantung pada
 * state `values` yang di-update lewat onChange (yang rawan race condition
 * kalau field langsung memanggil onAction pada callback async yang sama).
 */
export default function Renderer({ schema, onSubmitAction }) {
  const { values, errors, setValue, submit } = useInteractionState(schema);

  if (!schema) return null;

  function handleAction(actionId, extraValues) {
    const action = (schema.actions || []).find((a) => a.id === actionId);
    const needsValidation = !action || !["ghost", "secondary"].includes(action.style);

    if (needsValidation) {
      submit((finalValues) => onSubmitAction?.(actionId, { ...finalValues, ...extraValues }));
    } else {
      onSubmitAction?.(actionId, { ...values, ...extraValues });
    }
  }

  return (
    <div className="max-w-[720px] w-full bg-[#111827] border border-white/10 rounded-2xl p-4 sm:p-5 space-y-4 shadow-lg shadow-black/20">
      {(schema.title || schema.description) && (
        <div>
          {schema.title && <h3 className="text-base font-semibold text-white">{schema.title}</h3>}
          {schema.description && (
            <p className="text-sm text-white/50 mt-1">{schema.description}</p>
          )}
        </div>
      )}

      <div className="space-y-5">
        {(schema.sections || []).map((section, i) => (
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

      <ActionBar actions={schema.actions} onAction={handleAction} />
    </div>
  );
}