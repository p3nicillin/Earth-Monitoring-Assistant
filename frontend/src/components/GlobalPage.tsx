import { useQuery } from "@tanstack/react-query";
import { Globe2, Radio, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatRelativeTime } from "../lib/solar";
import type { DashboardSummary, MonitoringEvent } from "../types";
import { EventMap } from "./EventMap";
import { PageHeading } from "./WorkspacePages";

const STREAM_RETRY_MS = 15_000;

export default function GlobalPage() {
  const [live, setLive] = useState<DashboardSummary | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [selected, setSelected] = useState<MonitoringEvent | null>(null);

  const summaryFallback = useQuery({
    queryKey: ["global-summary"],
    queryFn: api.globalSummary,
    refetchInterval: streaming ? false : 60_000,
    staleTime: 30_000,
  });
  const events = useQuery({
    queryKey: ["global-events"],
    queryFn: api.globalEvents,
    refetchInterval: 60_000,
  });
  const geojson = useQuery({
    queryKey: ["global-geojson"],
    queryFn: api.globalEventsGeoJSON,
    refetchInterval: 60_000,
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    async function run() {
      while (!cancelled) {
        try {
          await api.streamGlobal((snapshot) => {
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

  const summary = live ?? summaryFallback.data;
  const failed = summaryFallback.isError || events.isError || geojson.isError;

  return (
    <section className="page-shell">
      <PageHeading
        eyebrow="WHOLE-PLANET MONITORING"
        title="Global live feed"
        copy="Continent-scale Sentinel-2 coverage, shared across every workspace, updated automatically as new imagery is checked."
      />

      <div className="truth-banner">
        <Radio size={19} />
        <span>
          <strong>{streaming ? "Live." : "Live (polling)."}</strong> New Sentinel-2 imagery is
          checked automatically across six continent-scale regions; typical satellite revisit is
          roughly 5 days per location. This is continuous automated monitoring, not real-time
          video.
        </span>
      </div>

      {failed && (
        <div className="connection-error">
          <TriangleAlert size={18} />
          <span>
            <strong>Unable to reach the global feed.</strong> Confirm the backend is healthy, then
            refresh.
          </span>
        </div>
      )}

      <section className="stat-grid">
        <article>
          <div className="stat-icon cyan">
            <Globe2 size={18} />
          </div>
          <span>WATCH AREAS</span>
          <strong>{summary?.watch_areas ?? "—"}</strong>
          <small>Continent-scale coverage regions</small>
        </article>
        <article>
          <div className="stat-icon red">
            <TriangleAlert size={18} />
          </div>
          <span>EVENTS · 24H</span>
          <strong>{summary?.events_24h ?? "—"}</strong>
          <small>Real detector outputs, planet-wide</small>
        </article>
        <article>
          <div className="stat-icon purple">
            <ShieldCheck size={18} />
          </div>
          <span>CRITICAL</span>
          <strong>{summary?.critical_events ?? "—"}</strong>
          <small>Highest-severity active detections</small>
        </article>
        <article>
          <div className="stat-icon green">
            <Radio size={18} />
          </div>
          <span>REVIEWED</span>
          <strong>
            {summary?.reviewed_percentage ?? "—"}
            <sup>%</sup>
          </strong>
          <small>Human verification coverage</small>
        </article>
      </section>

      <div className="split-page">
        <article className="panel page-map">
          <header>
            <div>
              <span>PLANET-WIDE DETECTIONS</span>
              <h2>Global event map</h2>
            </div>
          </header>
          <EventMap data={geojson.data} selected={selected} />
        </article>
        <div className="event-review-list">
          {events.data?.items.map((event) => (
            <article
              className={`review-card ${selected?.id === event.id ? "selected" : ""}`}
              key={event.id}
              onClick={() => setSelected(event)}
            >
              <div>
                <span className={`status-pill severity-${event.severity}`}>{event.severity}</span>
                <small>{formatRelativeTime(event.detected_at)}</small>
              </div>
              <h2>{event.title}</h2>
              <p>{event.summary}</p>
              <footer>
                <span>
                  {event.detector_name} · {Math.round(event.confidence * 100)}%
                </span>
                <span>{event.category}</span>
              </footer>
            </article>
          ))}
          {!events.isLoading && events.data?.items.length === 0 && (
            <div className="empty-state-large">
              <ShieldCheck />
              <p>
                No global detections yet. The scheduler checks each continent-scale region
                automatically as new Sentinel-2 imagery becomes available.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
