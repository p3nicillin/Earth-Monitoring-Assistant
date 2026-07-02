import { describe, expect, it } from "vitest";

import {
  SEVERITY_META,
  formatAu,
  formatFlux,
  formatRelativeTime,
  imageCacheKey,
  kpColor,
  orbitRadius,
  orreryPosition,
  planetDisplayName,
  xrayClassColor,
} from "./solar";

describe("orbitRadius", () => {
  it("is monotonic with distance and bounded by the max radius", () => {
    const distances = [0.39, 0.72, 1.0, 1.52, 5.2, 9.5, 19.2, 30.1, 39.5];
    const radii = distances.map((au) => orbitRadius(au, 300));
    for (let index = 1; index < radii.length; index += 1) {
      expect(radii[index]!).toBeGreaterThan(radii[index - 1]!);
    }
    expect(radii.at(-1)!).toBeLessThanOrEqual(300);
    expect(radii[0]!).toBeGreaterThan(20);
  });
});

describe("orreryPosition", () => {
  it("places zero longitude on the +x axis and 90 degrees up", () => {
    const east = orreryPosition(
      { distance_from_sun_au: 1, ecliptic_longitude_deg: 0 },
      360,
      300,
    );
    expect(east.x).toBeGreaterThan(360);
    expect(east.y).toBeCloseTo(360, 6);
    const north = orreryPosition(
      { distance_from_sun_au: 1, ecliptic_longitude_deg: 90 },
      360,
      300,
    );
    expect(north.x).toBeCloseTo(360, 6);
    expect(north.y).toBeLessThan(360);
  });
});

describe("formatters", () => {
  it("formats distances in au and kilometres", () => {
    expect(formatAu(1.2345)).toBe("1.234 au");
    expect(formatAu(19.19)).toBe("19.19 au");
    expect(formatAu(0.00256955529)).toBe("384400 km");
  });

  it("formats x-ray flux in scientific notation", () => {
    expect(formatFlux(5.2e-5)).toBe("5.2e-5 W/m²");
    expect(formatFlux(1.0e-6)).toBe("1.0e-6 W/m²");
  });

  it("renders relative times in both directions", () => {
    const now = new Date("2026-07-02T12:00:00Z");
    expect(formatRelativeTime("2026-07-02T11:59:40Z", now)).toBe("just now");
    expect(formatRelativeTime("2026-07-02T11:30:00Z", now)).toBe("30m ago");
    expect(formatRelativeTime("2026-07-02T09:00:00Z", now)).toBe("3h ago");
    expect(formatRelativeTime("2026-07-04T18:00:00Z", now)).toBe("in 2d");
  });

  it("capitalizes planet names", () => {
    expect(planetDisplayName("mercury")).toBe("Mercury");
  });

  it("buckets image cache keys to five minutes", () => {
    const first = imageCacheKey(new Date("2026-07-02T12:00:01Z"));
    const second = imageCacheKey(new Date("2026-07-02T12:04:59Z"));
    const third = imageCacheKey(new Date("2026-07-02T12:05:01Z"));
    expect(first).toBe(second);
    expect(third).toBe(first + 1);
  });
});

describe("colors", () => {
  it("maps x-ray classes to escalating colors", () => {
    expect(xrayClassColor("X1.2")).toBe("#f87171");
    expect(xrayClassColor("M5.0")).toBe("#fb923c");
    expect(xrayClassColor("C2.0")).toBe("#facc15");
    expect(xrayClassColor("B7.1")).toBe("#a3e635");
    expect(xrayClassColor(null)).toBe("#4ade80");
  });

  it("maps kp to storm colors", () => {
    expect(kpColor(2)).toBe("#4ade80");
    expect(kpColor(4.3)).toBe("#facc15");
    expect(kpColor(5.7)).toBe("#fb923c");
    expect(kpColor(8)).toBe("#f87171");
  });

  it("ranks severities from critical to info", () => {
    const ranks = ["critical", "warning", "watch", "info"].map(
      (severity) => SEVERITY_META[severity as keyof typeof SEVERITY_META].rank,
    );
    expect(ranks).toEqual([0, 1, 2, 3]);
  });
});
