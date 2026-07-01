import { describe, expect, it } from "vitest";
import { json2satrec } from "./satellite";

import { nextPass, orbitTrack, propagateState } from "./orbits";

const OMM = {
  OBJECT_NAME: "SENTINEL-2A",
  OBJECT_ID: "2015-028A",
  EPOCH: "2026-07-01T03:08:19.35312",
  MEAN_MOTION: 14.30818234,
  ECCENTRICITY: 0.0001199,
  INCLINATION: 98.5688,
  RA_OF_ASC_NODE: 256.7842,
  ARG_OF_PERICENTER: 95.242,
  MEAN_ANOMALY: 264.89,
  EPHEMERIS_TYPE: 0 as const,
  CLASSIFICATION_TYPE: "U" as const,
  NORAD_CAT_ID: 40697,
  ELEMENT_SET_NO: 999,
  REV_AT_EPOCH: 57572,
  BSTAR: -3.4166e-5,
  MEAN_MOTION_DOT: -1.33e-6,
  MEAN_MOTION_DDOT: 0,
};

describe("orbital propagation", () => {
  const satrec = json2satrec(OMM);
  const date = new Date("2026-07-01T10:00:00Z");

  it("produces finite position, velocity, and heading", () => {
    const state = propagateState(satrec, date);
    expect(state).not.toBeNull();
    expect(state?.longitude).toBeGreaterThanOrEqual(-180);
    expect(state?.longitude).toBeLessThanOrEqual(180);
    expect(state?.altitudeKm).toBeGreaterThan(600);
    expect(state?.velocityKmS).toBeGreaterThan(7);
    expect(state?.heading).toBeGreaterThanOrEqual(0);
  });

  it("generates an ordered orbital track", () => {
    const track = orbitTrack(satrec, date, { minutesBefore: 10, minutesAfter: 10, stepMinutes: 2 });
    expect(track).toHaveLength(11);
    expect(track.every((state) => Number.isFinite(state.latitude))).toBe(true);
  });

  it("returns either a bounded pass estimate or no pass in the search window", () => {
    const pass = nextPass(satrec, { longitude: -1.4, latitude: 52.3 }, date, { searchHours: 24 });
    if (pass) {
      expect(pass.rise.getTime()).toBeLessThan(pass.peak.getTime());
      expect(pass.peak.getTime()).toBeLessThan(pass.set.getTime());
      expect(pass.maxElevation).toBeGreaterThanOrEqual(10);
    }
  });
});
