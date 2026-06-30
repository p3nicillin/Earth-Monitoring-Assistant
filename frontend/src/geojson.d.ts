declare namespace GeoJSON {
  type Position = number[];
  interface Geometry {
    type: string;
    coordinates: unknown;
  }
  interface Feature {
    type: "Feature";
    id?: string | number;
    geometry: Geometry;
    properties: Record<string, unknown> | null;
  }
}
