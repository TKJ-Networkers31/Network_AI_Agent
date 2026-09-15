import FieldRenderer from "./FieldRenderer.jsx";

export default function SectionRenderer({ section, values, errors, onChange, onAction }) {
  const columns = section.columns === 2 ? 2 : 1;

  return (
    <div className="space-y-3">
      {(section.title || section.description) && (
        <div>
          {section.title && <h4 className="text-sm font-semibold text-white">{section.title}</h4>}
          {section.description && (
            <p className="text-xs text-white/40 mt-0.5">{section.description}</p>
          )}
        </div>
      )}

      <div className={`grid gap-3 ${columns === 2 ? "sm:grid-cols-2" : "grid-cols-1"}`}>
        {(section.fields || []).map((field, i) => {
          const isFull =
            field.span === "full" ||
            field.type === "table" ||
            field.type === "info" ||
            field.type === "divider";

          return (
            <div key={field.id || `${field.type}-${i}`} className={isFull ? "sm:col-span-2" : ""}>
              <FieldRenderer
                field={field}
                value={values[field.id]}
                error={errors[field.id]}
                onChange={onChange}
                onAction={onAction}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}