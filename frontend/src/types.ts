export type EventCategory =
  | "environment"
  | "agriculture"
  | "urban"
  | "infrastructure"
  | "disaster"
  | "maritime";

export type Severity = "low" | "medium" | "high" | "critical";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: "viewer" | "analyst" | "admin";
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: User;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  color: string;
  is_archived: boolean;
  created_at: string;
  watch_area_count: number;
  event_count: number;
}

export interface MonitoringEvent {
  id: string;
  project_id: string;
  title: string;
  summary: string;
  event_type: string;
  category: EventCategory;
  severity: Severity;
  confidence: number;
  geometry: GeoJSON.Geometry;
  area_sq_km: number | null;
  detected_at: string;
  detector_name: string;
  detector_version: string;
  evidence: Record<string, unknown>;
  is_reviewed: boolean;
  review_outcome: "unreviewed" | "confirmed" | "rejected" | "uncertain";
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  review_note: string | null;
}

export interface EventCollection {
  items: MonitoringEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface DashboardSummary {
  active_projects: number;
  watch_areas: number;
  events_24h: number;
  critical_events: number;
  reviewed_percentage: number;
  category_counts: Record<string, number>;
  severity_counts: Record<string, number>;
  processing_status: "operational" | "degraded";
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: GeoJSON.Feature[];
}

export interface AssistantResult {
  answer: string;
  interpreted_filters: Record<string, unknown>;
  result_count: number;
  features: FeatureCollection;
  suggestions: string[];
}
