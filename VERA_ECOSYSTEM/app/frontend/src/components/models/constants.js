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

export const PROVIDER_OPTIONS = [
  { value: "ollama", label: "Ollama (Lokal)" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "gemini", label: "Google Gemini" },
  { value: "nvidia", label: "NVIDIA NIM" },
];

export function formatContext(tokens) {
  if (!tokens || tokens <= 0) return "-";
  if (tokens >= 1000) return `${Math.round(tokens / 1000)}k`;
  return `${tokens}`;
}
