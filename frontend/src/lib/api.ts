import type {
  AssistantResult,
  DashboardSummary,
  EarthEventFeed,
  EarthquakeFeed,
  EventCollection,
  FeatureCollection,
  ForecastFeed,
  ImageryGallery,
  ImagerySourceStatus,
  LearningStatus,
  MetricBaseline,
  MonitoringEvent,
  MonitoringResult,
  Project,
  Report,
  SatelliteObservation,
  SatelliteCatalog,
  SolarSystemOverview,
  TokenResponse,
  User,
  WatchArea,
} from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "terralens-access-token";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = tokenStore.get();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        const validationMessages = body.detail
          .map((item) =>
            typeof item === "object" && item !== null && "msg" in item
              ? String(item.msg)
              : null,
          )
          .filter((item): item is string => item !== null);
        if (validationMessages.length > 0) message = validationMessages.join("; ");
      }
    } catch {
      // Preserve the status-based fallback for non-JSON gateway errors.
    }
    if (response.status === 401) tokenStore.clear();
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const body = new URLSearchParams({ username: email, password });
    return request<TokenResponse>("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  },
  // Local-appliance mode: the API issues a session for the auto-provisioned
  // operator without credentials. 404s when the deployment requires login.
  localSession: () => request<TokenResponse>("/auth/session", { method: "POST" }),
  me: () => request<User>("/auth/me"),
  projects: () => request<Project[]>("/projects"),
  createProject: (payload: { name: string; description: string; color: string }) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(payload) }),
  watchAreas: (projectId: string) =>
    request<WatchArea[]>(`/projects/${projectId}/watch-areas`),
  createWatchArea: (
    projectId: string,
    payload: {
      name: string;
      geometry: GeoJSON.Polygon;
      categories: string[];
      schedule: "manual" | "daily" | "weekly";
    },
  ) =>
    request<WatchArea>(`/projects/${projectId}/watch-areas`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  summary: (projectId?: string) =>
    request<DashboardSummary>(
      `/dashboard/summary${projectId ? `?project_id=${projectId}` : ""}`,
    ),
  events: (projectId?: string) =>
    request<EventCollection>(`/events${projectId ? `?project_id=${projectId}` : ""}`),
  eventGeoJSON: (projectId?: string) =>
    request<FeatureCollection>(`/events/geojson${projectId ? `?project_id=${projectId}` : ""}`),
  reviewEvent: (eventId: string, outcome: "confirmed" | "rejected" | "uncertain") =>
    request<MonitoringEvent>(`/events/${eventId}/review`, {
      method: "PATCH",
      body: JSON.stringify({ outcome, note: null }),
    }),
  observations: (projectId?: string) =>
    request<SatelliteObservation[]>(
      `/monitoring/observations${projectId ? `?project_id=${projectId}` : ""}`,
    ),
  runMonitoring: (watchAreaId: string, maxCloudCover: number) =>
    request<MonitoringResult>("/monitoring/runs", {
      method: "POST",
      body: JSON.stringify({
        watch_area_id: watchAreaId,
        provider: "planetary-computer",
        max_cloud_cover: maxCloudCover,
      }),
    }),
  reports: (projectId?: string) =>
    request<Report[]>(`/reports${projectId ? `?project_id=${projectId}` : ""}`),
  createReport: (
    projectId: string,
    reportType: "executive" | "environmental" | "disaster" | "agricultural",
    periodStart: string,
    periodEnd: string,
  ) =>
    request<Report>("/reports", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        report_type: reportType,
        period_start: periodStart,
        period_end: periodEnd,
      }),
    }),
  satelliteCatalog: () => request<SatelliteCatalog>("/planet/satellites"),
  earthquakes: () => request<EarthquakeFeed>("/planet/earthquakes"),
  solarOverview: () => request<SolarSystemOverview>("/solar-system/overview"),
  earthEvents: () => request<EarthEventFeed>("/solar-system/earth-events"),
  streamSolarOverview: async (
    onOverview: (overview: SolarSystemOverview) => void,
    signal: AbortSignal,
  ): Promise<void> => {
    const token = tokenStore.get();
    const headers = new Headers({ Accept: "text/event-stream" });
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${API_URL}/solar-system/stream`, { headers, signal });
    if (!response.ok || !response.body) {
      if (response.status === 401) tokenStore.clear();
      throw new ApiError(response.status, `Live stream failed (${response.status})`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let frameEnd = buffer.indexOf("\n\n");
      while (frameEnd >= 0) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6))
          .join("\n");
        if (data) {
          try {
            onOverview(JSON.parse(data) as SolarSystemOverview);
          } catch {
            // Skip malformed frames; the next snapshot replaces the state anyway.
          }
        }
        frameEnd = buffer.indexOf("\n\n");
      }
    }
  },
  ask: (question: string, projectId?: string) =>
    request<AssistantResult>("/assistant/query", {
      method: "POST",
      body: JSON.stringify({ question, project_id: projectId ?? null }),
    }),
  learningStatus: () => request<LearningStatus>("/insights/status"),
  learningBaselines: () => request<MetricBaseline[]>("/insights/baselines"),
  learningForecasts: () => request<ForecastFeed>("/insights/forecasts"),
  imagerySources: () => request<ImagerySourceStatus[]>("/imagery/sources"),
  imageryCaptures: (sourceKey?: string, limit = 60, offset = 0) =>
    request<ImageryGallery>(
      `/imagery/captures?limit=${limit}&offset=${offset}${sourceKey ? `&source_key=${encodeURIComponent(sourceKey)}` : ""}`,
    ),
  imageryFileUrl: (captureId: string) => `${API_URL}/imagery/captures/${captureId}/file`,
  globalSummary: () => request<DashboardSummary>("/global/summary"),
  globalEvents: () => request<EventCollection>("/global/events"),
  globalEventsGeoJSON: () => request<FeatureCollection>("/global/events/geojson"),
  streamGlobal: async (
    onSummary: (summary: DashboardSummary) => void,
    signal: AbortSignal,
  ): Promise<void> => {
    const token = tokenStore.get();
    const headers = new Headers({ Accept: "text/event-stream" });
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${API_URL}/global/stream`, { headers, signal });
    if (!response.ok || !response.body) {
      if (response.status === 401) tokenStore.clear();
      throw new ApiError(response.status, `Live stream failed (${response.status})`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let frameEnd = buffer.indexOf("\n\n");
      while (frameEnd >= 0) {
        const frame = buffer.slice(0, frameEnd);
        buffer = buffer.slice(frameEnd + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6))
          .join("\n");
        if (data) {
          try {
            onSummary(JSON.parse(data) as DashboardSummary);
          } catch {
            // Skip malformed frames; the next snapshot replaces the state anyway.
          }
        }
        frameEnd = buffer.indexOf("\n\n");
      }
    }
  },
};
