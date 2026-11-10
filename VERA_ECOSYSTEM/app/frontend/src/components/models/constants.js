// src/components/models/constants.js
export const LABEL_OPTIONS = [
  { value: "general", label: "General" },
  { value: "reasoning", label: "Reasoning" },
  { value: "coding", label: "Coding" },
  { value: "networking", label: "Networking" },
  { value: "vision", label: "Vision" },
  { value: "voice", label: "Voice" },
  { value: "retrieval", label: "Retrieval" },
  { value: "automation", label: "Automation" },
];

export const CAPABILITY_OPTIONS = [
  { value: "all", label: "All Capabilities" },
  { value: "tool_calling", label: "Tool Calling" },
  { value: "streaming", label: "Streaming" },
  { value: "vision", label: "Vision / Multimodal" },
  { value: "structured_output", label: "Structured Output (JSON)" },
  { value: "audio", label: "Audio / Voice" },
];

export const LIFECYCLE_OPTIONS = [
  { value: "all", label: "All Lifecycles" },
  { value: "ACTIVE", label: "Active" },
  { value: "EXPERIMENTAL", label: "Experimental" },
  { value: "DEPRECATED_PENDING", label: "Deprecated (Pending)" },
  { value: "DEPRECATED", label: "Deprecated" },
];

export const PROVIDER_OPTIONS = [
  { value: "nvidia", label: "NVIDIA NIM (integrate.api.nvidia.com)" },
  { value: "openrouter", label: "OpenRouter (openrouter.ai)" },
  { value: "gemini", label: "Google Gemini (generativelanguage.googleapis.com)" },
];

export function formatContext(tokens) {
  if (!tokens || tokens <= 0) return "-";
  if (tokens >= 1000) return `${Math.round(tokens / 1000)}k`;
  return `${tokens}`;
}
