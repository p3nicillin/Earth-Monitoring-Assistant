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

export interface PlanetState {
  name: string;
  body_class: string;
  x_au: number;
  y_au: number;
  z_au: number;
  ecliptic_longitude_deg: number;
  ecliptic_latitude_deg: number;
  distance_from_sun_au: number;
  distance_from_earth_au: number;
  elongation_deg: number;
  light_time_minutes: number;
  orbital_period_days: number;
  radius_km: number;
  display_color: string;
}

export interface EphemerisSnapshot {
  computed_at: string;
  source: string;
  valid_range: string;
  planets: PlanetState[];
}

export interface XrayFluxPoint {
  time_tag: string;
  flux_watts_m2: number;
}

export interface KpEntry {
  time_tag: string;
  kp: number;
}

export interface SolarWindPoint {
  time_tag: string;
  speed_km_s: number | null;
  density_p_cm3: number | null;
  bz_nt: number | null;
  bt_nt: number | null;
}

export interface FlareEvent {
  began_at: string | null;
  peaked_at: string | null;
  ended_at: string | null;
  max_class: string | null;
  in_progress: boolean;
}

export interface SpaceWeather {
  source: string;
  generated_at: string;
  cache_expires_at: string;
  xray_flux: XrayFluxPoint[];
  current_xray_class: string | null;
  latest_flare: FlareEvent | null;
  kp_index: KpEntry[];
  current_kp: number | null;
  solar_wind: SolarWindPoint[];
  current_solar_wind: SolarWindPoint | null;
  proton_flux_10mev_pfu: number | null;
}

export interface SolarImage {
  key: string;
  title: string;
  description: string;
  url: string;
  source: string;
}

export interface NeoApproach {
  designation: string;
  close_approach_at: string;
  distance_au: number;
  distance_lunar: number;
  velocity_km_s: number;
  absolute_magnitude_h: number | null;
  estimated_diameter_m: number | null;
}

export interface NeoFeed {
  source: string;
  generated_at: string;
  cache_expires_at: string;
  lookahead_days: number;
  count: number;
  approaches: NeoApproach[];
}

export interface EarthEvent {
  id: string;
  title: string;
  category_id: string;
  category_title: string;
  longitude: number | null;
  latitude: number | null;
  observed_at: string | null;
  magnitude_value: number | null;
  magnitude_unit: string | null;
  source_url: string | null;
}

export interface EarthEventFeed {
  source: string;
  generated_at: string;
  cache_expires_at: string;
  lookback_days: number;
  count: number;
  events: EarthEvent[];
}

export type DetectionSeverity = "info" | "watch" | "warning" | "critical";
export type DetectionBody = "sun" | "earth" | "interplanetary";

export interface SpotDetection {
  id: string;
  detector: string;
  detector_version: string;
  category: string;
  severity: DetectionSeverity;
  body: DetectionBody;
  title: string;
  summary: string;
  observed_at: string;
  source: string;
  source_url: string | null;
  longitude: number | null;
  latitude: number | null;
  metrics: Record<string, unknown>;
}

export interface DetectionFeed {
  generated_at: string;
  count: number;
  detections: SpotDetection[];
}

export interface FeedStatus {
  name: string;
  ok: boolean;
  detail: string | null;
}

export interface MetricBaseline {
  metric: string;
  title: string;
  unit: string;
  direction: "high" | "low";
  sample_count: number;
  window_days: number;
  first_sample_at: string | null;
  last_sample_at: string | null;
  mean: number | null;
  p50: number | null;
  p95: number | null;
  p99: number | null;
  observed_extreme: number | null;
  published_floor: number;
  adaptive_threshold: number | null;
  maturity: number;
}

export interface ForecastPoint {
  metric: string;
  model_name: string;
  model_version: string;
  made_at: string;
  target_time: string;
  horizon_minutes: number;
  predicted_value: number;
  actual_value: number | null;
  abs_error: number | null;
}

export interface ForecastSkill {
  metric: string;
  model_name: string;
  horizon_minutes: number;
  resolved_count: number;
  mean_abs_error: number;
  skill_vs_persistence: number | null;
}

export interface MetricArchiveStatus {
  metric: string;
  title: string;
  sample_count: number;
  first_sample_at: string | null;
  last_sample_at: string | null;
}

export interface LearningStatus {
  generated_at: string;
  learning_enabled: boolean;
  interval_seconds: number;
  baseline_window_days: number;
  min_baseline_samples: number;
  archive: MetricArchiveStatus[];
  total_samples: number;
  forecasts_pending: number;
  forecasts_resolved: number;
  skill: ForecastSkill[];
}

export interface ForecastFeed {
  generated_at: string;
  upcoming: ForecastPoint[];
  recent_resolved: ForecastPoint[];
}

export interface ImageryCapture {
  id: string;
  source_key: string;
  title: string;
  source: string;
  upstream_url: string;
  captured_at: string;
  content_hash: string;
  byte_size: number;
  content_type: string;
  metadata_json: Record<string, unknown>;
}

export interface ImagerySourceStatus {
  key: string;
  title: string;
  source: string;
  description: string;
  capture_count: number;
  latest_captured_at: string | null;
  latest_capture_id: string | null;
}

export interface ImageryGallery {
  generated_at: string;
  total: number;
  items: ImageryCapture[];
}

export interface SolarSystemOverview {
  generated_at: string;
  feed_status: FeedStatus[];
  space_weather: SpaceWeather | null;
  ephemeris: EphemerisSnapshot;
  neo: NeoFeed | null;
  earth_events: EarthEventFeed | null;
  solar_images: SolarImage[];
  detections: DetectionFeed;
}
