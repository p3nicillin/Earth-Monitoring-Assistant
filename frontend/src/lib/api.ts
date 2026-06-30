import type {
  AssistantResult,
  DashboardSummary,
  EventCollection,
  FeatureCollection,
  Project,
  TokenResponse,
  User,
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
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
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
  me: () => request<User>("/auth/me"),
  projects: () => request<Project[]>("/projects"),
  summary: (projectId?: string) =>
    request<DashboardSummary>(
      `/dashboard/summary${projectId ? `?project_id=${projectId}` : ""}`,
    ),
  events: (projectId?: string) =>
    request<EventCollection>(`/events${projectId ? `?project_id=${projectId}` : ""}`),
  eventGeoJSON: (projectId?: string) =>
    request<FeatureCollection>(`/events/geojson${projectId ? `?project_id=${projectId}` : ""}`),
  ask: (question: string, projectId?: string) =>
    request<AssistantResult>("/assistant/query", {
      method: "POST",
      body: JSON.stringify({ question, project_id: projectId ?? null }),
    }),
};
