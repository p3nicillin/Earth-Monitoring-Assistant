import type { OMMJsonObject } from "./lib/satellite";

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

export interface WatchArea {
  id: string;
  project_id: string;
  name: string;
  geometry: GeoJSON.Polygon;
  categories: EventCategory[];
  schedule: "manual" | "daily" | "weekly";
  is_active: boolean;
  last_checked_at: string | null;
  created_at: string;
}

export interface SatelliteObservation {
  id: string;
  project_id: string;
  watch_area_id: string;
  watch_area_name: string;
  source: string;
  source_item_id: string;
  captured_at: string;
  cloud_cover: number | null;
  footprint: GeoJSON.Geometry;
  assets: Record<string, { href?: string; type?: string }>;
  metadata: {
    platform?: string;
    constellation?: string;
    stac_collection?: string;
    stac_item_url?: string;
  };
  provenance_checksum: string | null;
  status: string;
  created_at: string;
}

export interface MonitoringResult {
  run_id: string;
  source_items: number;
  observations_created: number;
  events_created: number;
  status: "completed" | "no_imagery";
  message: string;
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

export interface Report {
  id: string;
  project_id: string;
  title: string;
  report_type: string;
  period_start: string;
  period_end: string;
  content: {
    summary?: string;
    event_count?: number;
    reviewed_count?: number;
    mean_confidence?: number | null;
    categories?: Record<string, number>;
    severities?: Record<string, number>;
    methodology?: string;
  };
  status: string;
  created_at: string;
}

export interface MissionProfile {
  family: string;
  operator: string;
  instruments: string[];
  nominal_swath_km: number;
  nominal_revisit: string;
  orbit_class: string;
  color: string;
  sensor_status: string;
}

export interface TrackedSatellite {
  id: string;
  name: string;
  international_designator: string;
  norad_catalog_id: number;
  element_epoch: string;
  profile: MissionProfile;
  omm: OMMJsonObject;
}

export interface SatelliteCatalog {
  source: string;
  source_updated_at: string;
  cache_expires_at: string;
  count: number;
  satellites: TrackedSatellite[];
}

export interface EarthquakeFeature {
  id: string;
  title: string;
  magnitude: number | null;
  occurred_at: string;
  longitude: number;
  latitude: number;
  depth_km: number;
  detail_url: string | null;
  tsunami: boolean;
  place: string | null;
}

export interface EarthquakeFeed {
  source: string;
  generated_at: string;
  cache_expires_at: string;
  count: number;
  earthquakes: EarthquakeFeature[];
}
