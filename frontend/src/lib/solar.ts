import type { DetectionBody, DetectionSeverity, PlanetState } from "../types";

export interface SeverityMeta {
  label: string;
  color: string;
  rank: number;
}

export const SEVERITY_META: Record<DetectionSeverity, SeverityMeta> = {
  critical: { label: "CRITICAL", color: "#f87171", rank: 0 },
  warning: { label: "WARNING", color: "#fb923c", rank: 1 },
  watch: { label: "WATCH", color: "#facc15", rank: 2 },
  info: { label: "INFO", color: "#38bdf8", rank: 3 },
};

export const BODY_LABELS: Record<DetectionBody, string> = {
  sun: "Sun",
  earth: "Earth",
  interplanetary: "Deep space",
};

/** Log-compressed orbit radius so Mercury..Pluto all fit one orrery view. */
export function orbitRadius(distanceAu: number, maxRadiusPx: number): number {
  const compress = (au: number) => Math.log10(1 + 24 * Math.max(au, 0));
  return (compress(distanceAu) / compress(41)) * maxRadiusPx;
}

/** Heliocentric ecliptic longitude to SVG position (ecliptic north up, CCW). */
export function orreryPosition(
  planet: Pick<PlanetState, "distance_from_sun_au" | "ecliptic_longitude_deg">,
  center: number,
  maxRadiusPx: number,
): { x: number; y: number; r: number } {
  const r = orbitRadius(planet.distance_from_sun_au, maxRadiusPx);
  const angle = (planet.ecliptic_longitude_deg * Math.PI) / 180;
  return { x: center + r * Math.cos(angle), y: center - r * Math.sin(angle), r };
}

export function formatAu(value: number): string {
  if (value < 0.01) return `${(value * 149_597_870.7).toFixed(0)} km`;
  return `${value.toFixed(value < 10 ? 3 : 2)} au`;
}

export function formatFlux(fluxWattsM2: number): string {
  const exponent = Math.floor(Math.log10(fluxWattsM2));
  const mantissa = fluxWattsM2 / 10 ** exponent;
  return `${mantissa.toFixed(1)}e${exponent} W/m²`;
}

export function xrayClassColor(xrayClass: string | null): string {
  switch (xrayClass?.[0]?.toUpperCase()) {
    case "X":
      return "#f87171";
    case "M":
      return "#fb923c";
    case "C":
      return "#facc15";
    case "B":
      return "#a3e635";
    default:
      return "#4ade80";
  }
}

export function kpColor(kp: number): string {
  if (kp >= 7) return "#f87171";
  if (kp >= 5) return "#fb923c";
  if (kp >= 4) return "#facc15";
  return "#4ade80";
}

export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const deltaMs = now.getTime() - new Date(iso).getTime();
  const future = deltaMs < 0;
  const minutes = Math.round(Math.abs(deltaMs) / 60_000);
  const format = (value: number, unit: string) =>
    future ? `in ${value}${unit}` : `${value}${unit} ago`;
  if (minutes < 1) return future ? "imminent" : "just now";
  if (minutes < 60) return format(minutes, "m");
  const hours = Math.round(minutes / 60);
  if (hours < 48) return format(hours, "h");
  return format(Math.round(hours / 24), "d");
}

export function planetDisplayName(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** Cache-busting timestamp bucketed to five minutes so images refetch politely. */
export function imageCacheKey(now: Date = new Date()): number {
  return Math.floor(now.getTime() / 300_000);
}
