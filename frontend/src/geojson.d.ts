declare namespace GeoJSON {
  type Position = number[];
  interface Geometry {
    type: string;
    coordinates: unknown;
  }
  interface Polygon extends Geometry {
    type: "Polygon";
    coordinates: Position[][];
  }
  interface Feature {
    type: "Feature";
    id?: string | number;
    geometry: Geometry;
    properties: Record<string, unknown> | null;
  }
}
