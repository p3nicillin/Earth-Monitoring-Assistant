import {
  degreesLat,
  degreesLong,
  ecfToLookAngles,
  eciToEcf,
  eciToGeodetic,
  gstime,
  propagate,
  radiansLat,
  radiansLong,
  type SatRec,
} from "./satellite";

export interface OrbitalState {
  longitude: number;
  latitude: number;
  altitudeKm: number;
  velocityKmS: number;
  heading: number;
}

export interface GroundPoint {
  longitude: number;
  latitude: number;
}

export interface PassEstimate {
  rise: Date;
  peak: Date;
  set: Date;
  maxElevation: number;
}

function bearing(from: GroundPoint, to: GroundPoint): number {
  const lat1 = radiansLat(from.latitude);
  const lat2 = radiansLat(to.latitude);
  // to.longitude - from.longitude is an angular delta, not a longitude itself, and can
  // exceed +-180 when the ground track crosses the antimeridian between samples. Wrap it
  // into (-180, 180] before converting to radians instead of feeding it through radiansLong,
  // which validates its input as a real longitude and throws outside that range.
  const wrappedDeltaDegrees = ((to.longitude - from.longitude + 540) % 360) - 180;
  const deltaLongitude = (wrappedDeltaDegrees * Math.PI) / 180;
  const y = Math.sin(deltaLongitude) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLongitude);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

export function propagateState(satrec: SatRec, date: Date): OrbitalState | null {
  const state = propagate(satrec, date);
  if (!state?.position || !state.velocity) return null;
  const gmst = gstime(date);
  const geodetic = eciToGeodetic(state.position, gmst);
  const future = propagate(satrec, new Date(date.getTime() + 10_000));
  const futureGeodetic = future?.position ? eciToGeodetic(future.position, gstime(new Date(date.getTime() + 10_000))) : geodetic;
  const currentPoint = { longitude: degreesLong(geodetic.longitude), latitude: degreesLat(geodetic.latitude) };
  const futurePoint = { longitude: degreesLong(futureGeodetic.longitude), latitude: degreesLat(futureGeodetic.latitude) };
  return {
    ...currentPoint,
    altitudeKm: geodetic.height,
    velocityKmS: Math.hypot(state.velocity.x, state.velocity.y, state.velocity.z),
    heading: bearing(currentPoint, futurePoint),
  };
}

export function orbitTrack(
  satrec: SatRec,
  center: Date,
  options: { minutesBefore?: number; minutesAfter?: number; stepMinutes?: number } = {},
): OrbitalState[] {
  const { minutesBefore = 45, minutesAfter = 90, stepMinutes = 2 } = options;
  const states: OrbitalState[] = [];
  for (let minute = -minutesBefore; minute <= minutesAfter; minute += stepMinutes) {
    const state = propagateState(satrec, new Date(center.getTime() + minute * 60_000));
    if (state) states.push(state);
  }
  return states;
}

export function nextPass(
  satrec: SatRec,
  observer: GroundPoint,
  start: Date,
  options: { searchHours?: number; minimumElevationDegrees?: number } = {},
): PassEstimate | null {
  const { searchHours = 24, minimumElevationDegrees = 10 } = options;
  const observerGeodetic = {
    longitude: radiansLong(observer.longitude),
    latitude: radiansLat(observer.latitude),
    height: 0,
  };
  let rise: Date | null = null;
  let peak: Date | null = null;
  let set: Date | null = null;
  let maxElevation = -90;
  const stepMs = 60_000;
  for (let elapsed = 0; elapsed <= searchHours * 3_600_000; elapsed += stepMs) {
    const date = new Date(start.getTime() + elapsed);
    const state = propagate(satrec, date);
    if (!state?.position) continue;
    const look = ecfToLookAngles(observerGeodetic, eciToEcf(state.position, gstime(date)));
    const elevation = look.elevation * 180 / Math.PI;
    if (elevation >= minimumElevationDegrees && rise === null) rise = date;
    if (rise !== null && elevation > maxElevation) {
      maxElevation = elevation;
      peak = date;
    }
    if (rise !== null && elevation < minimumElevationDegrees) {
      set = date;
      break;
    }
  }
  return rise && peak && set ? { rise, peak, set, maxElevation } : null;
}
