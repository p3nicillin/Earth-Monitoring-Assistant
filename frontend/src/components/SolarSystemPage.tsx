import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CircleAlert,
  Flame,
  Gauge,
  Globe2,
  Orbit,
  Radio,
  Rocket,
  Sun,
  Waves,
  Wind,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../lib/api";
import {
  BODY_LABELS,
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
} from "../lib/solar";
import type { DetectionBody, PlanetState, SolarSystemOverview, SpotDetection } from "../types";

const ORRERY_SIZE = 720;
const ORRERY_CENTER = ORRERY_SIZE / 2;
const ORRERY_MAX_RADIUS = 330;
const STREAM_RETRY_MS = 15_000;

const CATEGORY_ICONS: Record<string, typeof Flame> = {
  solar_flare: Sun,
  geomagnetic_storm: Zap,
  solar_wind: Wind,
  radiation_storm: Radio,
  earthquake: Activity,
  neo_approach: Rocket,
  wildfires: Flame,
  volcanoes: Flame,
  severeStorms: Waves,
  floods: Waves,
};

function Orrery({
  planets,
  selected,
  onSelect,
}: {
  planets: PlanetState[];
  selected: string;
  onSelect: (name: string) => void;
}) {
  return (
    <svg
      className="orrery"
      viewBox={`0 0 ${ORRERY_SIZE} ${ORRERY_SIZE}`}
      role="img"
      aria-label="Live positions of the planets around the Sun"
    >
      <defs>
        <radialGradient id="sun-glow">
          <stop offset="0%" stopColor="#fde68a" />
          <stop offset="45%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="rgba(245,158,11,0)" />
        </radialGradient>
      </defs>
      {planets.map((planet) => (
        <circle
          key={`orbit:${planet.name}`}
          cx={ORRERY_CENTER}
          cy={ORRERY_CENTER}
          r={orbitRadius(planet.distance_from_sun_au, ORRERY_MAX_RADIUS)}
          className="orrery-orbit"
        />
      ))}
      <circle cx={ORRERY_CENTER} cy={ORRERY_CENTER} r={26} fill="url(#sun-glow)" />
      <circle cx={ORRERY_CENTER} cy={ORRERY_CENTER} r={9} fill="#fbbf24" />
      {planets.map((planet) => {
        const { x, y } = orreryPosition(planet, ORRERY_CENTER, ORRERY_MAX_RADIUS);
        const isSelected = selected === planet.name;
        const isEarth = planet.name === "earth";
        const radius = isEarth ? 7 : 5.5;
        return (
          <g
            key={planet.name}
            className={`orrery-planet ${isSelected ? "selected" : ""}`}
            onClick={() => onSelect(planet.name)}
          >
            {isSelected && (
              <circle cx={x} cy={y} r={radius + 6} fill="none" stroke={planet.display_color} strokeDasharray="3 3" />
            )}
            <circle cx={x} cy={y} r={radius} fill={planet.display_color} stroke="rgba(255,255,255,.65)" strokeWidth={isEarth ? 1.4 : 0.8} />
            <text x={x + radius + 4} y={y + 3}>{planetDisplayName(planet.name)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function DetectionRow({ detection }: { detection: SpotDetection }) {
  const meta = SEVERITY_META[detection.severity];
  const Icon = CATEGORY_ICONS[detection.category] ?? CircleAlert;
  return (
    <article className="detection-row">
      <span className="detection-icon" style={{ color: meta.color }}><Icon size={15} /></span>
      <div>
        <strong>{detection.title}</strong>
        <p>{detection.summary}</p>
        <small>
          {BODY_LABELS[detection.body]} · {detection.source} · {formatRelativeTime(detection.observed_at)}
        </small>
      </div>
      <i className="detection-severity" style={{ background: meta.color }} title={meta.label} />
    </article>
  );
}

export default function SolarSystemPage() {
  const [live, setLive] = useState<SolarSystemOverview | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [selectedPlanet, setSelectedPlanet] = useState("earth");
  const [bodyFilter, setBodyFilter] = useState<DetectionBody | "all">("all");
  const [imageKey, setImageKey] = useState("aia-193");
  const fallback = useQuery({
    queryKey: ["solar-overview"],
    queryFn: api.solarOverview,
    refetchInterval: streaming ? false : 60_000,
    staleTime: 30_000,
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    async function run() {
      while (!cancelled) {
        try {
          await api.streamSolarOverview((snapshot) => {
            setLive(snapshot);
            setStreaming(true);
          }, controller.signal);
        } catch {
          // Stream unavailable; the react-query poll below keeps data flowing.
        }
        setStreaming(false);
        if (cancelled) return;
        await new Promise((resolve) => setTimeout(resolve, STREAM_RETRY_MS));
      }
    }
    void run();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  const overview = live ?? fallback.data;
  const weather = overview?.space_weather ?? null;
  const planets = useMemo(() => overview?.ephemeris.planets ?? [], [overview]);
  const planet = planets.find((item) => item.name === selectedPlanet);
  const detections = useMemo(() => {
    const all = overview?.detections.detections ?? [];
    return bodyFilter === "all" ? all : all.filter((item) => item.body === bodyFilter);
  }, [overview, bodyFilter]);
  const failedFeeds = (overview?.feed_status ?? []).filter((status) => !status.ok);
  const solarImage =
    overview?.solar_images.find((image) => image.key === imageKey) ?? overview?.solar_images[0];
  const cacheKey = imageCacheKey();

  const xrayData = useMemo(
    () =>
      (weather?.xray_flux ?? []).map((point) => ({
        time: new Date(point.time_tag).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        flux: point.flux_watts_m2,
      })),
    [weather],
  );
  const kpData = useMemo(
    () =>
      (weather?.kp_index ?? []).slice(-24).map((entry) => ({
        time: new Date(entry.time_tag).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        kp: entry.kp,
      })),
    [weather],
  );
  const windData = useMemo(
    () =>
      (weather?.solar_wind ?? [])
        .filter((point) => point.speed_km_s !== null)
        .map((point) => ({
          time: new Date(point.time_tag).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          speed: point.speed_km_s,
        })),
    [weather],
  );

  const criticalCount = detections.filter((item) => item.severity === "critical").length;

  return (
    <section className="solar-page">
      <header className="planetary-heading">
        <div>
          <p className="eyebrow">SOLAR SYSTEM OPERATIONS</p>
          <h1>Live heliosphere and near-Earth command</h1>
          <span>
            Keyless public feeds: NOAA SWPC, USGS, NASA EONET, JPL close approaches, SDO/SOHO
            imagery, and an on-board planetary ephemeris.
          </span>
        </div>
        <div className="planetary-source">
          <i className={streaming ? "" : "polling"} />
          <span>
            <strong>{streaming ? "LIVE STREAM" : "POLLING"} · {overview?.detections.count ?? 0} active detections</strong>
            <small>
              {overview
                ? `Snapshot ${new Date(overview.generated_at).toLocaleTimeString()}`
                : "Connecting to live feeds…"}
            </small>
          </span>
        </div>
      </header>

      {failedFeeds.length > 0 && (
        <div className="connection-error">
          Degraded: {failedFeeds.map((status) => status.name).join(", ")} temporarily unavailable.
          Remaining feeds stay live.
        </div>
      )}
      {fallback.isError && !overview && (
        <div className="connection-error">Unable to reach the solar-system API.</div>
      )}

      <div className="planetary-stats solar-stats">
        <article>
          <Sun />
          <span>X-ray flux<strong style={{ color: xrayClassColor(weather?.current_xray_class ?? null) }}>{weather?.current_xray_class ?? "—"}</strong></span>
        </article>
        <article>
          <Zap />
          <span>Planetary Kp<strong style={{ color: weather?.current_kp != null ? kpColor(weather.current_kp) : undefined }}>{weather?.current_kp?.toFixed(1) ?? "—"}</strong></span>
        </article>
        <article>
          <Wind />
          <span>Solar wind<strong>{weather?.current_solar_wind?.speed_km_s != null ? `${weather.current_solar_wind.speed_km_s.toFixed(0)} km/s` : "—"}</strong></span>
        </article>
        <article>
          <Rocket />
          <span>NEO passes · {overview?.neo?.lookahead_days ?? 7}d<strong>{overview?.neo?.count ?? "—"}</strong></span>
        </article>
        <article>
          <CircleAlert />
          <span>Critical detections<strong style={{ color: criticalCount > 0 ? "#f87171" : undefined }}>{criticalCount}</strong></span>
        </article>
      </div>

      <div className="solar-grid">
        <article className="panel orrery-panel">
          <header>
            <div><span>PLANETARY EPHEMERIS</span><h2>Solar system now</h2></div>
            <small>{overview ? new Date(overview.ephemeris.computed_at).toUTCString() : ""}</small>
          </header>
          <div className="orrery-stage">
            <Orrery planets={planets} selected={selectedPlanet} onSelect={setSelectedPlanet} />
            {planet && (
              <aside className="planet-inspector">
                <h3 style={{ color: planet.display_color }}><Globe2 size={15} /> {planetDisplayName(planet.name)}</h3>
                <small>{planet.body_class}</small>
                <dl>
                  <div><dt>From Sun</dt><dd>{formatAu(planet.distance_from_sun_au)}</dd></div>
                  <div><dt>From Earth</dt><dd>{planet.name === "earth" ? "—" : formatAu(planet.distance_from_earth_au)}</dd></div>
                  <div><dt>Light time</dt><dd>{planet.name === "earth" ? "—" : `${planet.light_time_minutes.toFixed(1)} min`}</dd></div>
                  <div><dt>Elongation</dt><dd>{planet.name === "earth" ? "—" : `${planet.elongation_deg.toFixed(1)}°`}</dd></div>
                  <div><dt>Ecliptic lon</dt><dd>{planet.ecliptic_longitude_deg.toFixed(2)}°</dd></div>
                  <div><dt>Period</dt><dd>{planet.orbital_period_days < 1000 ? `${planet.orbital_period_days.toFixed(0)} d` : `${(planet.orbital_period_days / 365.25).toFixed(1)} yr`}</dd></div>
                </dl>
              </aside>
            )}
          </div>
        </article>

        <article className="panel sun-panel">
          <header>
            <div><span>SOLAR IMAGERY · LIVE</span><h2>{solarImage?.title ?? "The Sun"}</h2></div>
            <small>{solarImage?.source}</small>
          </header>
          <div className="sun-image-wrap">
            {solarImage && (
              <img
                src={`${solarImage.url}?t=${cacheKey}`}
                alt={solarImage.description}
                loading="lazy"
              />
            )}
          </div>
          <p className="sun-caption">{solarImage?.description}</p>
          <div className="sun-tabs">
            {(overview?.solar_images ?? []).map((image) => (
              <button
                key={image.key}
                className={image.key === (solarImage?.key ?? "") ? "active" : ""}
                onClick={() => setImageKey(image.key)}
              >
                {image.title}
              </button>
            ))}
          </div>
        </article>

        <article className="panel detections-panel">
          <header>
            <div><span>SPOT DETECTIONS · RULE ENGINE v{overview?.detections.detections[0]?.detector_version ?? "1.0.0"}</span><h2>Live detections</h2></div>
            <div className="body-filter">
              {(["all", "sun", "earth", "interplanetary"] as const).map((body) => (
                <button
                  key={body}
                  className={bodyFilter === body ? "active" : ""}
                  onClick={() => setBodyFilter(body)}
                >
                  {body === "all" ? "All" : BODY_LABELS[body]}
                </button>
              ))}
            </div>
          </header>
          <div className="detection-list">
            {detections.map((detection) => (
              <DetectionRow key={detection.id} detection={detection} />
            ))}
            {overview && detections.length === 0 && (
              <div className="empty-state">No detections match this filter — quiet skies.</div>
            )}
            {!overview && <div className="empty-state">Waiting for the first live snapshot…</div>}
          </div>
        </article>

        <article className="panel chart-panel">
          <header><div><span>GOES X-RAY FLUX · 6H</span><h2>Flare activity</h2></div><Gauge size={15} /></header>
          <ResponsiveContainer width="100%" height={170}>
            <LineChart data={xrayData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <XAxis dataKey="time" tick={{ fontSize: 9 }} minTickGap={40} />
              <YAxis
                scale="log"
                domain={[1e-9, 1e-3]}
                tick={{ fontSize: 9 }}
                tickFormatter={(value: number) => `1e${Math.round(Math.log10(value))}`}
                width={44}
              />
              <Tooltip formatter={(value) => formatFlux(Number(value))} />
              <Line type="monotone" dataKey="flux" stroke="#facc15" dot={false} strokeWidth={1.6} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </article>

        <article className="panel chart-panel">
          <header><div><span>PLANETARY K-INDEX · 72H</span><h2>Geomagnetic activity</h2></div><Zap size={15} /></header>
          <ResponsiveContainer width="100%" height={170}>
            <BarChart data={kpData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <XAxis dataKey="time" tick={{ fontSize: 9 }} minTickGap={40} />
              <YAxis domain={[0, 9]} tick={{ fontSize: 9 }} width={24} />
              <Tooltip />
              <Bar dataKey="kp" isAnimationActive={false}>
                {kpData.map((entry, index) => (
                  <Cell key={index} fill={kpColor(entry.kp)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </article>

        <article className="panel chart-panel">
          <header><div><span>L1 SOLAR WIND · 24H</span><h2>Wind speed</h2></div><Wind size={15} /></header>
          <ResponsiveContainer width="100%" height={170}>
            <AreaChart data={windData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <XAxis dataKey="time" tick={{ fontSize: 9 }} minTickGap={40} />
              <YAxis tick={{ fontSize: 9 }} width={34} unit="" domain={["auto", "auto"]} />
              <Tooltip formatter={(value) => `${Number(value).toFixed(0)} km/s`} />
              <Area type="monotone" dataKey="speed" stroke="#38bdf8" fill="rgba(56,189,248,.15)" dot={false} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </article>

        <article className="panel neo-panel">
          <header>
            <div><span>NEAR-EARTH OBJECTS · NEXT {overview?.neo?.lookahead_days ?? 7} DAYS</span><h2>Close approaches</h2></div>
            <Orbit size={15} />
          </header>
          <div className="neo-table-wrap">
            <table className="neo-table">
              <thead>
                <tr><th>Object</th><th>Closest</th><th>Miss distance</th><th>Speed</th><th>Est. size</th></tr>
              </thead>
              <tbody>
                {(overview?.neo?.approaches ?? []).slice(0, 10).map((approach) => (
                  <tr key={`${approach.designation}-${approach.close_approach_at}`} className={approach.distance_lunar <= 5 ? "close" : ""}>
                    <td>{approach.designation}</td>
                    <td>{formatRelativeTime(approach.close_approach_at)}</td>
                    <td>{approach.distance_lunar.toFixed(2)} LD</td>
                    <td>{approach.velocity_km_s.toFixed(1)} km/s</td>
                    <td>{approach.estimated_diameter_m != null ? `~${approach.estimated_diameter_m.toFixed(0)} m` : "unknown"}</td>
                  </tr>
                ))}
                {overview?.neo && overview.neo.count === 0 && (
                  <tr><td colSpan={5}>No close approaches inside 0.05 au this week.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="panel earth-events-panel">
          <header>
            <div><span>EARTH · NASA EONET OPEN EVENTS</span><h2>Natural events under watch</h2></div>
            <a href="#planet" className="globe-link"><Globe2 size={14} /> View on 3D globe</a>
          </header>
          <div className="earth-event-groups">
            {Object.entries(
              (overview?.earth_events?.events ?? []).reduce<Record<string, number>>(
                (accumulator, event) => {
                  accumulator[event.category_title] = (accumulator[event.category_title] ?? 0) + 1;
                  return accumulator;
                },
                {},
              ),
            ).map(([category, count]) => (
              <div key={category}><strong>{count}</strong><span>{category}</span></div>
            ))}
            {overview?.earth_events && overview.earth_events.count === 0 && (
              <div className="empty-state">EONET reports no open events for this window.</div>
            )}
          </div>
        </article>
      </div>
    </section>
  );
}
