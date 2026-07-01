import { useMemo, useRef } from "react";
import Map, { Layer, NavigationControl, Source, type LayerProps, type MapRef } from "react-map-gl/maplibre";
import { Crosshair } from "lucide-react";

import type { FeatureCollection, MonitoringEvent } from "../types";

const mapStyle = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm", paint: { "raster-saturation": -0.68, "raster-brightness-max": 0.64 } }],
};

const fillLayer: LayerProps = {
  id: "event-fill",
  type: "fill",
  paint: {
    "fill-color": [
      "match",
      ["get", "severity"],
      "critical", "#fb7185",
      "high", "#f97316",
      "medium", "#facc15",
      "low", "#4ade80",
      "#67e8f9",
    ],
    "fill-opacity": 0.42,
  },
};

const lineLayer: LayerProps = {
  id: "event-line",
  type: "line",
  paint: {
    "line-color": ["match", ["get", "severity"], "critical", "#fda4af", "high", "#fb923c", "medium", "#fde047", "#86efac"],
    "line-width": 2,
    "line-opacity": 0.9,
  },
};

interface EventMapProps {
  data: FeatureCollection | undefined;
  selected: MonitoringEvent | null;
}

export function EventMap({ data, selected }: EventMapProps) {
  const mapRef = useRef<MapRef>(null);
  const collection = useMemo<FeatureCollection>(
    () => data ?? { type: "FeatureCollection", features: [] },
    [data],
  );
  return (
    <div className="map-wrap">
      <Map
        ref={mapRef}
        initialViewState={{ longitude: -1.4, latitude: 52.3, zoom: 5.4 }}
        mapStyle={mapStyle}
      >
        <NavigationControl position="bottom-right" showCompass={false} />
        <Source id="events" type="geojson" data={collection as never}>
          <Layer {...fillLayer} />
          <Layer {...lineLayer} />
        </Source>
      </Map>
      <div className="map-label"><span className="pulse-dot" /> REVIEWED DETECTION LAYER</div>
      <button
        className="map-tool"
        aria-label="Recenter map"
        onClick={() => mapRef.current?.flyTo({ center: [-1.4, 52.3], zoom: 5.4 })}
      ><Crosshair size={17} /></button>
      <div className="map-legend">
        {(["low", "medium", "high", "critical"] as const).map((severity) => (
          <span key={severity}><i className={`legend-${severity}`} />{severity}</span>
        ))}
      </div>
      {selected && (
        <aside className="map-callout">
          <div><span className={`severity severity-${selected.severity}`}>{selected.severity}</span><span>{Math.round(selected.confidence * 100)}% confidence</span></div>
          <strong>{selected.title}</strong>
          <p>{selected.summary}</p>
          <small>{selected.detector_name} · v{selected.detector_version}</small>
        </aside>
      )}
    </div>
  );
}
