export type TaskLabel =
  | "general" | "reasoning" | "coding" | "networking"
  | "vision" | "voice" | "retrieval" | "automation";

export type Provider = "ollama" | "openrouter" | "gemini";

export interface ModelRecord {
  id: string;
  provider: Provider;
  model_id: string;
  display_name: string;
  label: TaskLabel;
  context_window: number; // 0 = tidak diketahui
  enabled: boolean;
  created_at: string;
}

export interface ModelInput {
  provider: Provider;
  model_id: string;
  display_name: string;
  label: TaskLabel;
  context_window: number;
  enabled: boolean;
}

export type RoutingMap = Record<TaskLabel, string | null>;

export interface ModelPolicy {
  fallback_model_id: string | null;
  retry_provider: number; // 0..5
}

export interface RoutingResponse {
  routing: RoutingMap;
  policy: ModelPolicy;
  labels: TaskLabel[];
}

export interface TaskClassification {
  primary_label: TaskLabel;
  confidence: number;
  requires_tools: boolean;
  requires_vision: boolean;
  requires_voice: boolean;
}

export interface SelectedModel {
  id: string;
  display_name: string;
  provider: Provider;
  model_id: string;
  label: TaskLabel;
  context_window: number;
  fallback_from: string | null;
}

export interface RoutePreview {
  classification: TaskClassification;
  selected: SelectedModel | null;
}