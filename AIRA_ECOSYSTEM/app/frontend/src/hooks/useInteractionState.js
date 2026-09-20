import { useCallback, useMemo, useState } from "react";

function flattenFields(schema) {
  const fields = [];
  (schema?.sections || []).forEach((section) => {
    (section.fields || []).forEach((field) => {
      fields.push(field);
    });
  });
  return fields;
}

function validateField(field, value) {
  const DISPLAY_ONLY = new Set(["info", "divider", "button", "image", "gallery", "progress", "svg"]);
  if (DISPLAY_ONLY.has(field.type)) {
    return null;
  }

  const isEmpty =
    value === undefined ||
    value === null ||
    (typeof value === "string" && value.trim() === "") ||
    (Array.isArray(value) && value.length === 0);

  if (field.required && isEmpty) {
    return field.error_required || "Wajib diisi.";
  }

  if (isEmpty) return null;

  if (field.type === "number" || field.type === "slider") {
    const num = Number(value);
    if (Number.isNaN(num)) return "Harus berupa angka.";
    if (typeof field.min === "number" && num < field.min) return `Minimal ${field.min}.`;
    if (typeof field.max === "number" && num > field.max) return `Maksimal ${field.max}.`;
  }

  if (typeof value === "string") {
    if (typeof field.min_length === "number" && value.length < field.min_length) {
      return `Minimal ${field.min_length} karakter.`;
    }
    if (typeof field.max_length === "number" && value.length > field.max_length) {
      return `Maksimal ${field.max_length} karakter.`;
    }
    if (field.pattern) {
      try {
        const re = new RegExp(field.pattern);
        if (!re.test(value)) return field.error_pattern || "Format tidak valid.";
      } catch {
        // pattern dari backend tidak valid sebagai regex - lewati validasi ini,
        // biar backend yang jadi validator utama (sesuai spec).
      }
    }
  }

  return null;
}

function defaultValues(schema) {
  const values = {};
  flattenFields(schema).forEach((field) => {
    if (field.default !== undefined) {
      values[field.id] = field.default;
    } else if (field.type === "checkbox" || field.type === "switch") {
      values[field.id] = field.options ? [] : false;
    } else if (field.type === "table") {
      values[field.id] = field.rows || [];
    } else {
      values[field.id] = "";
    }
  });
  return values;
}

/**
 * useInteractionState — state management untuk satu Interaction Schema
 * dari DIO. Murni React hook (bukan Redux), sesuai spec Sprint 03.5.
 *
 * State: values, errors, dirty, submitted
 * Method: setValue, validate, submit, reset
 */
export function useInteractionState(schema) {
  const [values, setValues] = useState(() => defaultValues(schema));
  const [errors, setErrors] = useState({});
  const [dirty, setDirty] = useState({});
  const [submitted, setSubmitted] = useState(false);

  const fields = useMemo(() => flattenFields(schema), [schema]);

  const setValue = useCallback((fieldId, value) => {
    setValues((prev) => ({ ...prev, [fieldId]: value }));
    setDirty((prev) => ({ ...prev, [fieldId]: true }));
  }, []);

  const validate = useCallback(() => {
    const nextErrors = {};
    fields.forEach((field) => {
      const message = validateField(field, values[field.id]);
      if (message) nextErrors[field.id] = message;
    });
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  }, [fields, values]);

  const reset = useCallback(() => {
    setValues(defaultValues(schema));
    setErrors({});
    setDirty({});
    setSubmitted(false);
  }, [schema]);

  const submit = useCallback(
    (onValid) => {
      const isValid = validate();
      setSubmitted(true);
      if (isValid) onValid?.(values);
      return isValid;
    },
    [validate, values]
  );

  return { values, errors, dirty, submitted, setValue, validate, submit, reset };
}