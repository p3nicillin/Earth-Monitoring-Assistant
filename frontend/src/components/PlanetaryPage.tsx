import { useQuery } from "@tanstack/react-query";
import {
  ArcType,
  Cartesian2,
  Cartesian3,
  Cartographic,
  ClockRange,
  Color,
  CustomDataSource,
  DistanceDisplayCondition,
  Ellipsoid,
  EllipsoidGeodesic,
  HorizontalOrigin,
  ImageryLayer,
  Ion,
  JulianDate,
  NearFarScalar,
  OpenStreetMapImageryProvider,
  PolygonHierarchy,
  Rectangle,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  SingleTileImageryProvider,
  Terrain,
  VerticalOrigin,
  Viewer,
  WebMapServiceImageryProvider,
  CallbackPositionProperty,
  PolylineGlowMaterialProperty,
  type Entity,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import {
  Activity,
  Clock3,
  CloudSun,
  Crosshair,
  Flame,
  Gauge,
  Globe2,
  Image as ImageIcon,
  Layers3,
  LocateFixed,
  Orbit,
  Play,
  Radar,
  Ruler,
  Satellite,
  Search,
  Waves,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { json2satrec, type SatRec } from "../lib/satellite";

import { api } from "../lib/api";
import { nextPass, orbitTrack, propagateState, type GroundPoint, type OrbitalState, type PassEstimate } from "../lib/orbits";
import type { EarthEvent, EarthquakeFeature, Project, SatelliteObservation, TrackedSatellite } from "../types";

interface PlanetaryPageProps {
  projectId?: string;
  projects: Project[];
}

interface LayerState {
  tracks: boolean;
  footprints: boolean;
  observations: boolean;
  earthquakes: boolean;
  earthEvents: boolean;
  trueColor: boolean;
  clouds: boolean;
  fires: boolean;
}

const EONET_COLORS: Record<string, string> = {
  wildfires: "#fb923c",
  volcanoes: "#f87171",
  severeStorms: "#38bdf8",
  seaLakeIce: "#a5f3fc",
  floods: "#60a5fa",
  earthquakes: "#facc15",
};

interface Telemetry {
  state: OrbitalState;
  pass: PassEstimate | null;
  time: Date;
}

interface GlobeProps {
  satellites: TrackedSatellite[];
  earthquakes: EarthquakeFeature[];
  earthEvents: EarthEvent[];
  observations: SatelliteObservation[];
  selectedId?: string;
  activeObservation?: SatelliteObservation;
  observer: GroundPoint;
  layers: LayerState;
  measureMode: boolean;
  onSelected: (satelliteId: string) => void;
  onTelemetry: (telemetry: Telemetry | null) => void;
  onMeasure: (distanceKm: number | null) => void;
}

interface SatelliteRuntime {
  satellite: TrackedSatellite;
  satrec: SatRec;
}

const GIBS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi";

const LIVE_LAYERS = [
  { key: "trueColor" as const, label: "VIIRS true color", icon: ImageIcon, layer: "VIIRS_SNPP_CorrectedReflectance_TrueColor", alpha: 0.9 },
  { key: "clouds" as const, label: "MODIS cloud fraction", icon: CloudSun, layer: "MODIS_Terra_Cloud_Fraction_Day", alpha: 0.48 },
  { key: "fires" as const, label: "VIIRS thermal anomalies", icon: Flame, layer: "VIIRS_SNPP_Thermal_Anomalies_375m_All", alpha: 0.88 },
];

// External feeds (STAC, EONET, USGS) occasionally carry longitudes outside
// [-180, 180] (antimeridian-crossing footprints, unwrapped bboxes). Cesium's
// Rectangle/Cartesian APIs throw a RangeError and halt the whole render loop
// on such values, so every raw coordinate is normalized before it reaches Cesium.
function normalizeLongitude(longitude: number): number {
  return ((longitude + 180) % 360 + 360) % 360 - 180;
}

function geometryPositions(geometry: GeoJSON.Geometry): number[][][] {
  if (geometry.type === "Polygon") return geometry.coordinates as number[][][];
  if (geometry.type === "MultiPolygon") return (geometry.coordinates as number[][][][]).flat();
  return [];
}

function geometryBounds(geometry: GeoJSON.Geometry): [number, number, number, number] | null {
  const points = geometryPositions(geometry).flat();
  if (points.length === 0) return null;
  const longitudes = points.map((point) => point[0]).filter((value): value is number => value !== undefined).map(normalizeLongitude);
  const latitudes = points.map((point) => point[1]).filter((value): value is number => value !== undefined);
  return [Math.min(...longitudes), Math.min(...latitudes), Math.max(...longitudes), Math.max(...latitudes)];
}

function PlanetaryGlobe({ satellites, earthquakes, earthEvents, observations, selectedId, activeObservation, observer, layers, measureMode, onSelected, onTelemetry, onMeasure }: GlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const runtimesRef = useRef(new Map<string, SatelliteRuntime>());
  const onSelectedRef = useRef(onSelected);
  const onTelemetryRef = useRef(onTelemetry);
  const onMeasureRef = useRef(onMeasure);
  const selectedRef = useRef(selectedId);
  const observerRef = useRef(observer);
  const satelliteSourceRef = useRef(new CustomDataSource("orbital-assets"));
  const trackSourceRef = useRef(new CustomDataSource("selected-orbit"));
  const footprintSourceRef = useRef(new CustomDataSource("sensor-footprints"));
  const observationSourceRef = useRef(new CustomDataSource("satellite-observations"));
  const earthquakeSourceRef = useRef(new CustomDataSource("earthquakes"));
  const earthEventSourceRef = useRef(new CustomDataSource("earth-events"));
  const measurementSourceRef = useRef(new CustomDataSource("measurements"));

  useEffect(() => { onSelectedRef.current = onSelected; }, [onSelected]);
  useEffect(() => { onTelemetryRef.current = onTelemetry; }, [onTelemetry]);
  useEffect(() => { onMeasureRef.current = onMeasure; }, [onMeasure]);
  useEffect(() => { selectedRef.current = selectedId; }, [selectedId]);
  useEffect(() => { observerRef.current = observer; }, [observer]);

  useEffect(() => {
    if (!containerRef.current) return;
    const token = import.meta.env.VITE_CESIUM_ION_TOKEN;
    if (token) Ion.defaultAccessToken = token;
    const baseLayer = new ImageryLayer(new OpenStreetMapImageryProvider({ url: "https://tile.openstreetmap.org/", maximumLevel: 18 }));
    const viewer = new Viewer(containerRef.current, {
      baseLayer,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      fullscreenButton: true,
      vrButton: true,
      infoBox: false,
      selectionIndicator: true,
      animation: true,
      timeline: true,
      scene3DOnly: true,
      shouldAnimate: false,
      targetFrameRate: 45,
      terrain: token ? Terrain.fromWorldTerrain({ requestVertexNormals: true, requestWaterMask: true }) : undefined,
    });
    viewer.scene.globe.enableLighting = true;
    viewer.scene.globe.dynamicAtmosphereLighting = true;
    viewer.scene.globe.dynamicAtmosphereLightingFromSun = true;
    viewer.scene.globe.showGroundAtmosphere = true;
    viewer.scene.globe.depthTestAgainstTerrain = true;
    viewer.scene.fog.enabled = true;
    viewer.scene.highDynamicRange = true;
    viewer.scene.postProcessStages.fxaa.enabled = true;
    const now = JulianDate.now();
    viewer.clock.startTime = JulianDate.addHours(now, -24, new JulianDate());
    viewer.clock.currentTime = JulianDate.clone(now);
    viewer.clock.stopTime = JulianDate.addHours(now, 24, new JulianDate());
    viewer.clock.clockRange = ClockRange.LOOP_STOP;
    viewer.clock.multiplier = 60;
    viewer.timeline.zoomTo(viewer.clock.startTime, viewer.clock.stopTime);
    viewer.camera.flyTo({ destination: Cartesian3.fromDegrees(-10, 25, 19_000_000), duration: 0 });
    for (const source of [satelliteSourceRef.current, trackSourceRef.current, footprintSourceRef.current, observationSourceRef.current, earthquakeSourceRef.current, earthEventSourceRef.current, measurementSourceRef.current]) {
      void viewer.dataSources.add(source);
    }
    const removeSelection = viewer.selectedEntityChanged.addEventListener((entity: Entity | undefined) => {
      if (!entity) return;
      const match = entity.id.match(/^(?:satellite|footprint):(.+)$/);
      if (match?.[1]) onSelectedRef.current(match[1]);
    });
    viewerRef.current = viewer;
    return () => {
      removeSelection();
      viewerRef.current = null;
      if (!viewer.isDestroyed()) viewer.destroy();
    };
  }, []);

  useEffect(() => {
    const source = satelliteSourceRef.current;
    const footprints = footprintSourceRef.current;
    source.entities.removeAll();
    footprints.entities.removeAll();
    runtimesRef.current.clear();
    for (const satellite of satellites) {
      let satrec: SatRec;
      try { satrec = json2satrec(satellite.omm); } catch { continue; }
      const color = Color.fromCssColorString(satellite.profile.color);
      const position = new CallbackPositionProperty((time) => {
        const state = propagateState(satrec, time ? JulianDate.toDate(time) : new Date());
        return state ? Cartesian3.fromDegrees(state.longitude, state.latitude, state.altitudeKm * 1000) : undefined;
      }, false);
      const groundPosition = new CallbackPositionProperty((time) => {
        const state = propagateState(satrec, time ? JulianDate.toDate(time) : new Date());
        return state ? Cartesian3.fromDegrees(state.longitude, state.latitude, 0) : undefined;
      }, false);
      source.entities.add({
        id: `satellite:${satellite.id}`,
        name: satellite.name,
        position,
        point: { pixelSize: 8, color, outlineColor: Color.WHITE.withAlpha(0.8), outlineWidth: 1.5, scaleByDistance: new NearFarScalar(1.5e6, 1.4, 4e7, 0.55), distanceDisplayCondition: new DistanceDisplayCondition(0, 5e7) },
        label: { text: satellite.name, font: "10px Inter, sans-serif", fillColor: Color.WHITE.withAlpha(0.9), showBackground: true, backgroundColor: Color.BLACK.withAlpha(0.55), verticalOrigin: VerticalOrigin.BOTTOM, horizontalOrigin: HorizontalOrigin.LEFT, pixelOffset: new Cartesian2(8, -8), distanceDisplayCondition: new DistanceDisplayCondition(0, 8e6), scaleByDistance: new NearFarScalar(1e6, 1, 8e6, 0.55) },
      });
      footprints.entities.add({
        id: `footprint:${satellite.id}`,
        position: groundPosition,
        ellipse: { semiMajorAxis: Math.min(satellite.profile.nominal_swath_km * 500, 3_000_000), semiMinorAxis: Math.min(satellite.profile.nominal_swath_km * 350, 2_000_000), material: color.withAlpha(0.055), outline: true, outlineColor: color.withAlpha(0.35), height: 0 },
      });
      runtimesRef.current.set(satellite.id, { satellite, satrec });
    }
  }, [satellites]);

  useEffect(() => {
    const source = trackSourceRef.current;
    source.entities.removeAll();
    if (!selectedId || !layers.tracks) return;
    const runtime = runtimesRef.current.get(selectedId);
    const viewer = viewerRef.current;
    if (!runtime || !viewer) return;
    const center = JulianDate.toDate(viewer.clock.currentTime);
    const states = orbitTrack(runtime.satrec, center, { minutesBefore: 50, minutesAfter: 100, stepMinutes: 2 });
    const positions = states.map((state) => Cartesian3.fromDegrees(state.longitude, state.latitude, state.altitudeKm * 1000));
    const ground = states.map((state) => Cartesian3.fromDegrees(state.longitude, state.latitude));
    const color = Color.fromCssColorString(runtime.satellite.profile.color);
    source.entities.add({ id: `track:${selectedId}`, polyline: { positions, width: 2.5, material: new PolylineGlowMaterialProperty({ color, glowPower: 0.18 }), arcType: ArcType.GEODESIC } });
    source.entities.add({ id: `swath:${selectedId}`, corridor: { positions: ground, width: Math.min(runtime.satellite.profile.nominal_swath_km * 1000, 3_000_000), material: color.withAlpha(0.055), outline: true, outlineColor: color.withAlpha(0.18) } });
  }, [selectedId, layers.tracks]);

  useEffect(() => {
    const source = observationSourceRef.current;
    source.entities.removeAll();
    for (const observation of observations) {
      for (const ring of geometryPositions(observation.footprint)) {
        const positions = ring.flatMap((point) => [normalizeLongitude(point[0] ?? 0), point[1] ?? 0]);
        source.entities.add({ id: `observation:${observation.id}:${source.entities.values.length}`, name: observation.source_item_id, polygon: { hierarchy: new PolygonHierarchy(Cartesian3.fromDegreesArray(positions)), material: Color.LIME.withAlpha(0.08), outline: true, outlineColor: Color.LIME.withAlpha(0.55) } });
      }
    }
  }, [observations]);

  useEffect(() => {
    const source = earthquakeSourceRef.current;
    source.entities.removeAll();
    for (const quake of earthquakes) {
      const magnitude = quake.magnitude ?? 0;
      source.entities.add({ id: `earthquake:${quake.id}`, name: quake.title, position: Cartesian3.fromDegrees(normalizeLongitude(quake.longitude), quake.latitude, Math.max(0, -quake.depth_km * 1000)), point: { pixelSize: Math.max(5, 5 + magnitude * 1.8), color: magnitude >= 6 ? Color.RED : magnitude >= 4 ? Color.ORANGE : Color.YELLOW.withAlpha(0.85), outlineColor: Color.BLACK, outlineWidth: 1, distanceDisplayCondition: new DistanceDisplayCondition(0, 2.8e7) } });
    }
  }, [earthquakes]);

  useEffect(() => {
    const source = earthEventSourceRef.current;
    source.entities.removeAll();
    for (const event of earthEvents) {
      if (event.longitude === null || event.latitude === null) continue;
      const color = Color.fromCssColorString(EONET_COLORS[event.category_id] ?? "#a3a3a3");
      source.entities.add({
        id: `earth-event:${event.id}`,
        name: event.title,
        position: Cartesian3.fromDegrees(normalizeLongitude(event.longitude), event.latitude, 0),
        point: { pixelSize: 7, color, outlineColor: Color.BLACK.withAlpha(0.7), outlineWidth: 1, distanceDisplayCondition: new DistanceDisplayCondition(0, 4e7) },
        label: { text: `${event.category_title}: ${event.title}`, font: "9px Inter, sans-serif", fillColor: color, showBackground: true, backgroundColor: Color.BLACK.withAlpha(0.6), verticalOrigin: VerticalOrigin.BOTTOM, horizontalOrigin: HorizontalOrigin.LEFT, pixelOffset: new Cartesian2(7, -7), distanceDisplayCondition: new DistanceDisplayCondition(0, 6.5e6) },
      });
    }
  }, [earthEvents]);

  useEffect(() => {
    footprintSourceRef.current.show = layers.footprints;
    observationSourceRef.current.show = layers.observations;
    earthquakeSourceRef.current.show = layers.earthquakes;
    earthEventSourceRef.current.show = layers.earthEvents;
    trackSourceRef.current.show = layers.tracks;
  }, [layers]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const added: ImageryLayer[] = [];
    const date = JulianDate.toDate(viewer.clock.currentTime).toISOString().slice(0, 10);
    for (const definition of LIVE_LAYERS) {
      if (!layers[definition.key]) continue;
      const provider = new WebMapServiceImageryProvider({ url: GIBS_URL, layers: definition.layer, parameters: { transparent: true, format: "image/png", time: date }, credit: "NASA EOSDIS GIBS" });
      const layer = viewer.imageryLayers.addImageryProvider(provider);
      layer.alpha = definition.alpha;
      added.push(layer);
    }
    return () => {
      if (viewer.isDestroyed()) return;
      for (const layer of added) viewer.imageryLayers.remove(layer, true);
    };
  }, [layers.trueColor, layers.clouds, layers.fires]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const href = activeObservation?.assets.rendered_preview?.href;
    const bounds = activeObservation ? geometryBounds(activeObservation.footprint) : null;
    if (!viewer || !href || !bounds) return;
    let layer: ImageryLayer | undefined;
    let cancelled = false;
    void SingleTileImageryProvider.fromUrl(href, { rectangle: Rectangle.fromDegrees(...bounds), credit: "Microsoft Planetary Computer" }).then((provider) => {
      if (cancelled || viewer.isDestroyed()) return;
      layer = viewer.imageryLayers.addImageryProvider(provider);
      layer.alpha = 0.72;
    });
    return () => { cancelled = true; if (layer && !viewer.isDestroyed()) viewer.imageryLayers.remove(layer, true); };
  }, [activeObservation]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const viewer = viewerRef.current;
      const runtime = selectedRef.current ? runtimesRef.current.get(selectedRef.current) : undefined;
      if (!viewer || !runtime) { onTelemetryRef.current(null); return; }
      const time = JulianDate.toDate(viewer.clock.currentTime);
      const state = propagateState(runtime.satrec, time);
      if (!state) { onTelemetryRef.current(null); return; }
      onTelemetryRef.current({ state, pass: nextPass(runtime.satrec, observerRef.current, time, { searchHours: 24 }), time });
    }, 1000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    const source = measurementSourceRef.current;
    source.entities.removeAll();
    onMeasureRef.current(null);
    if (!viewer || !measureMode) return;
    const handler = new ScreenSpaceEventHandler(viewer.canvas);
    const points: Cartesian3[] = [];
    handler.setInputAction((event: ScreenSpaceEventHandler.PositionedEvent) => {
      const point = viewer.camera.pickEllipsoid(event.position, Ellipsoid.WGS84);
      if (!point) return;
      if (points.length === 2) { points.length = 0; source.entities.removeAll(); onMeasureRef.current(null); }
      points.push(point);
      source.entities.add({ position: point, point: { pixelSize: 8, color: Color.CYAN, outlineColor: Color.BLACK, outlineWidth: 1 } });
      if (points.length === 2) {
        const geodesic = new EllipsoidGeodesic(Cartographic.fromCartesian(points[0]!), Cartographic.fromCartesian(points[1]!));
        const distanceKm = geodesic.surfaceDistance / 1000;
        source.entities.add({ polyline: { positions: points, width: 3, material: Color.CYAN }, position: points[1], label: { text: `${distanceKm.toFixed(1)} km`, font: "12px Inter", fillColor: Color.CYAN, showBackground: true, backgroundColor: Color.BLACK.withAlpha(0.75), pixelOffset: new Cartesian2(0, -18) } });
        onMeasureRef.current(distanceKm);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);
    return () => handler.destroy();
  }, [measureMode]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !selectedId) return;
    const entity = satelliteSourceRef.current.entities.getById(`satellite:${selectedId}`);
    if (entity) viewer.selectedEntity = entity;
  }, [selectedId]);

  return <div className="cesium-globe" ref={containerRef} />;
}

function watchAreaCenter(projectId: string | undefined, projects: Project[], areas: Awaited<ReturnType<typeof api.watchAreas>> | undefined): GroundPoint {
  const fallback = { longitude: -1.4, latitude: 52.3 };
  const targetProject = projectId ?? projects[0]?.id;
  const area = areas?.find((candidate) => candidate.project_id === targetProject) ?? areas?.[0];
  if (!area) return fallback;
  const bounds = geometryBounds(area.geometry);
  return bounds ? { longitude: (bounds[0] + bounds[2]) / 2, latitude: (bounds[1] + bounds[3]) / 2 } : fallback;
}

function formatDuration(start: Date, end: Date): string {
  const minutes = Math.max(0, Math.round((end.getTime() - start.getTime()) / 60_000));
  return `${minutes} min`;
}

export default function PlanetaryPage({ projectId, projects }: PlanetaryPageProps) {
  const [selectedId, setSelectedId] = useState<string>();
  const [search, setSearch] = useState("");
  const [family, setFamily] = useState("all");
  const [measureMode, setMeasureMode] = useState(false);
  const [measurement, setMeasurement] = useState<number | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [activeObservationId, setActiveObservationId] = useState<string>();
  const [layers, setLayers] = useState<LayerState>({ tracks: true, footprints: false, observations: true, earthquakes: true, earthEvents: true, trueColor: true, clouds: false, fires: false });
  const catalog = useQuery({ queryKey: ["satellite-catalog"], queryFn: api.satelliteCatalog, staleTime: 7_200_000, refetchInterval: 7_200_000 });
  const hazards = useQuery({ queryKey: ["earthquakes"], queryFn: api.earthquakes, staleTime: 60_000, refetchInterval: 60_000 });
  const earthEvents = useQuery({ queryKey: ["earth-events"], queryFn: api.earthEvents, staleTime: 300_000, refetchInterval: 300_000 });
  const observations = useQuery({ queryKey: ["observations", projectId], queryFn: () => api.observations(projectId), refetchInterval: 300_000 });
  const areaProjectIds = projectId ? [projectId] : projects.map((project) => project.id);
  const watchAreas = useQuery({ queryKey: ["planet-watch-areas", areaProjectIds], queryFn: async () => (await Promise.all(areaProjectIds.map(api.watchAreas))).flat(), enabled: areaProjectIds.length > 0 });
  const observer = watchAreaCenter(projectId, projects, watchAreas.data);
  const satellites = catalog.data?.satellites ?? [];
  const selected = satellites.find((satellite) => satellite.id === selectedId);
  const families = useMemo(() => [...new Set(satellites.map((satellite) => satellite.profile.family))].sort(), [satellites]);
  const filtered = useMemo(() => satellites.filter((satellite) => (family === "all" || satellite.profile.family === family) && `${satellite.name} ${satellite.profile.family} ${satellite.profile.operator}`.toLowerCase().includes(search.toLowerCase())), [satellites, family, search]);
  const relatedObservations = useMemo(() => {
    if (!selected) return [];
    const mission = selected.name.replace(/[^A-Z0-9]/gi, "").toUpperCase();
    return (observations.data ?? []).filter((item) => {
      const platform = String(item.metadata.platform ?? "").replace(/[^A-Z0-9]/gi, "").toUpperCase();
      return mission.includes(platform) || platform.includes(mission);
    });
  }, [selected, observations.data]);
  const activeObservation = observations.data?.find((item) => item.id === activeObservationId);

  useEffect(() => {
    if (!selectedId && satellites.length > 0) setSelectedId(satellites.find((satellite) => satellite.name === "SENTINEL-2A")?.id ?? satellites[0]?.id);
  }, [satellites, selectedId]);

  function toggleLayer(key: keyof LayerState) {
    setLayers((current) => ({ ...current, [key]: !current[key] }));
  }

  return (
    <section className="planetary-page">
      <header className="planetary-heading"><div><p className="eyebrow">PLANETARY OPERATIONS</p><h1>Live 3D Earth command</h1><span>SGP4-propagated public orbital elements, source-backed imagery, and near-real-time hazard feeds.</span></div><div className="planetary-source"><i /><span><strong>{catalog.data?.count ?? 0} spacecraft tracked</strong><small>{catalog.data ? `CelesTrak OMM · ${new Date(catalog.data.source_updated_at).toLocaleTimeString()}` : "Loading orbital catalogue…"}</small></span></div></header>
      <div className="planetary-stats"><article><Satellite /><span>Tracked assets<strong>{catalog.data?.count ?? "—"}</strong></span></article><article><Waves /><span>Live earthquakes<strong>{hazards.data?.count ?? "—"}</strong></span></article><article><ImageIcon /><span>Imagery records<strong>{observations.data?.length ?? "—"}</strong></span></article><article><LocateFixed /><span>Pass observer<strong>{observer.latitude.toFixed(2)}°, {observer.longitude.toFixed(2)}°</strong></span></article></div>
      <div className="planet-command-shell">
        <aside className="mission-browser">
          <div className="mission-search"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search missions…" /></div>
          <select value={family} onChange={(event) => setFamily(event.target.value)}><option value="all">All mission families</option>{families.map((item) => <option key={item}>{item}</option>)}</select>
          <div className="mission-list">{filtered.map((satellite) => <button className={selectedId === satellite.id ? "selected" : ""} key={satellite.id} onClick={() => setSelectedId(satellite.id)}><i style={{ background: satellite.profile.color }} /><span><strong>{satellite.name}</strong><small>{satellite.profile.family} · NORAD {satellite.norad_catalog_id}</small></span><Orbit size={14} /></button>)}</div>
        </aside>
        <div className="globe-stage">
          <PlanetaryGlobe satellites={satellites} earthquakes={hazards.data?.earthquakes ?? []} earthEvents={earthEvents.data?.events ?? []} observations={observations.data ?? []} selectedId={selectedId} activeObservation={activeObservation} observer={observer} layers={layers} measureMode={measureMode} onSelected={setSelectedId} onTelemetry={setTelemetry} onMeasure={setMeasurement} />
          <div className="globe-status"><span><i /> LIVE ORBIT PROPAGATION</span><span>{telemetry?.time.toLocaleString() ?? "Synchronizing clock…"}</span></div>
          <div className="globe-tools"><button className={measureMode ? "active" : ""} onClick={() => setMeasureMode((value) => !value)} title="Measure geodesic distance"><Ruler size={16} /></button><button onClick={() => setActiveObservationId(undefined)} title="Clear imagery overlay"><X size={16} /></button></div>
          {measureMode && <div className="measure-readout">{measurement == null ? "Click two globe positions" : `${measurement.toFixed(1)} km geodesic`}</div>}
        </div>
        <aside className="orbital-inspector">
          {selected ? <>
            <div className="inspector-title"><span style={{ color: selected.profile.color }}><Satellite size={20} /></span><div><small>{selected.profile.family}</small><h2>{selected.name}</h2><p>{selected.profile.operator}</p></div></div>
            <div className="telemetry-grid"><article><Gauge /><span>Altitude<strong>{telemetry ? `${telemetry.state.altitudeKm.toFixed(1)} km` : "—"}</strong></span></article><article><Zap /><span>Velocity<strong>{telemetry ? `${telemetry.state.velocityKmS.toFixed(3)} km/s` : "—"}</strong></span></article><article><Crosshair /><span>Heading<strong>{telemetry ? `${telemetry.state.heading.toFixed(1)}°` : "—"}</strong></span></article><article><Radar /><span>Nominal swath<strong>{selected.profile.nominal_swath_km.toLocaleString()} km</strong></span></article></div>
            <section className="inspector-section"><span>INSTRUMENTS</span><div className="instrument-list">{selected.profile.instruments.map((instrument) => <i key={instrument}>{instrument}</i>)}</div><p>{selected.profile.sensor_status}</p></section>
            <section className="inspector-section"><span>NEXT OVERPASS · WATCH AREA</span>{telemetry?.pass ? <div className="pass-card"><Clock3 /><div><strong>{telemetry.pass.rise.toLocaleString()}</strong><small>Peak {telemetry.pass.maxElevation.toFixed(1)}° · {formatDuration(telemetry.pass.rise, telemetry.pass.set)}</small></div></div> : <p>No pass above 10° in the next 24 hours at the selected watch area.</p>}</section>
            <section className="inspector-section"><span>ORBITAL ELEMENTS</span><dl><div><dt>Epoch</dt><dd>{new Date(selected.element_epoch).toLocaleString()}</dd></div><div><dt>Inclination</dt><dd>{Number(selected.omm.INCLINATION).toFixed(4)}°</dd></div><div><dt>Mean motion</dt><dd>{Number(selected.omm.MEAN_MOTION).toFixed(6)} rev/day</dd></div><div><dt>Orbit</dt><dd>{selected.profile.orbit_class}</dd></div><div><dt>Revisit</dt><dd>{selected.profile.nominal_revisit}</dd></div></dl></section>
            <section className="inspector-section"><span>AVAILABLE ACQUISITIONS</span>{relatedObservations.slice(0, 4).map((observation) => <button className={activeObservationId === observation.id ? "acquisition active" : "acquisition"} key={observation.id} onClick={() => setActiveObservationId(observation.id)}><Play size={12} /><span><strong>{new Date(observation.captured_at).toLocaleDateString()}</strong><small>{observation.cloud_cover?.toFixed(1) ?? "?"}% cloud · overlay preview</small></span></button>)}{relatedObservations.length === 0 && <p>No stored imagery currently matches this spacecraft.</p>}</section>
          </> : <div className="inspector-empty"><Globe2 size={28} /><h2>Select a spacecraft</h2><p>Inspect propagated state, instruments, swath, pass prediction, and matching acquisitions.</p></div>}
        </aside>
        <div className="layer-deck"><header><Layers3 size={15} />Operational layers</header><button className={layers.tracks ? "active" : ""} onClick={() => toggleLayer("tracks")}><Orbit />Orbit and swath</button><button className={layers.footprints ? "active" : ""} onClick={() => toggleLayer("footprints")}><Radar />Sensor footprints</button><button className={layers.observations ? "active" : ""} onClick={() => toggleLayer("observations")}><ImageIcon />STAC observations</button><button className={layers.earthquakes ? "active" : ""} onClick={() => toggleLayer("earthquakes")}><Activity />USGS earthquakes</button><button className={layers.earthEvents ? "active" : ""} onClick={() => toggleLayer("earthEvents")}><Flame />EONET natural events</button>{LIVE_LAYERS.map(({ key, label, icon: Icon }) => <button className={layers[key] ? "active" : ""} onClick={() => toggleLayer(key)} key={key}><Icon />{label}</button>)}</div>
      </div>
      {(catalog.isError || hazards.isError) && <div className="connection-error">One or more live planetary feeds are unavailable. Cached layers remain visible where available.</div>}
    </section>
  );
}
