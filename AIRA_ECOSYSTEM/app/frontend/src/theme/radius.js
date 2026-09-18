/**
 * theme/radius.js — corner radius scale.
 * Cards use "card" (20px). DIO interactive components (inputs, selects,
 * buttons, sliders) use "control" (16px) per the redesign spec.
 */

export const radius = {
  sm: "0.5rem",    // 8px  — chips, tags
  md: "0.75rem",   // 12px — inline elements
  control: "1rem", // 16px — DIO form components
  card: "1.25rem", // 20px — cards, panels, modals
  pill: "999px",   // capsule buttons, avatars
};

export default radius;
