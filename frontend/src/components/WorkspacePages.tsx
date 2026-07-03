import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  Cloud,
  Database,
  FilePlus2,
  FolderKanban,
  Layers3,
  LoaderCircle,
  MapPin,
  Play,
  Plus,
  Radar,
  Satellite,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { api } from "../lib/api";
import type { MonitoringEvent, Project, SatelliteObservation, WatchArea } from "../types";
import { EventMap } from "./EventMap";

interface PageProps {
  projectId?: string;
  projects: Project[];
}

export function PageHeading({ eyebrow, title, copy }: { eyebrow: string; title: string; copy: string }) {
  return (
    <header className="page-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <span>{copy}</span>
    </header>
  );
}

function useWatchAreas(projects: Project[], projectId?: string) {
  const selectedProjects = projectId
    ? projects.filter((project) => project.id === projectId)
    : projects;
  return useQuery({
    queryKey: ["watch-areas", projectId, selectedProjects.map((project) => project.id)],
    queryFn: async () =>
      (await Promise.all(selectedProjects.map((project) => api.watchAreas(project.id)))).flat(),
    enabled: selectedProjects.length > 0,
  });
}

export function MonitoringPage({ projectId, projects }: PageProps) {
  const queryClient = useQueryClient();
  const areas = useWatchAreas(projects, projectId);
  const observations = useQuery({
    queryKey: ["observations", projectId],
    queryFn: () => api.observations(projectId),
  });
  const [cloudCover, setCloudCover] = useState(30);
  const run = useMutation({
    mutationFn: (areaId: string) => api.runMonitoring(areaId, cloudCover),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["observations"] });
      await queryClient.invalidateQueries({ queryKey: ["watch-areas"] });
    },
  });

  return (
    <section className="page-shell">
      <PageHeading
        eyebrow="SATELLITE MONITORING"
        title="Sentinel-2 acquisition search"
        copy="Query the live Microsoft Planetary Computer catalogue for recent imagery over each authorised watch area."
      />
      <div className="truth-banner">
        <Satellite size={19} />
        <span><strong>Live catalogue data only.</strong> Observations are real Sentinel-2 records. No change event is created unless a validated detector is installed.</span>
      </div>
      <div className="page-toolbar">
        <label>Maximum cloud cover <strong>{cloudCover}%</strong></label>
        <input type="range" min="0" max="100" value={cloudCover} onChange={(event) => setCloudCover(Number(event.target.value))} />
      </div>
      {run.data && (
        <div className="success-banner"><CheckCircle2 size={17} />Found {run.data.source_items} source items; stored {run.data.observations_created} new observations.</div>
      )}
      {run.isError && <div className="connection-error"><TriangleAlert size={17} />{run.error.message}</div>}
      <div className="data-grid">
        {areas.data?.map((area) => (
          <article className="data-card" key={area.id}>
            <div className="data-card-icon"><MapPin size={19} /></div>
            <div className="data-card-main">
              <span>WATCH AREA</span><h2>{area.name}</h2>
              <p>{area.categories.join(" · ")}</p>
              <small>{area.last_checked_at ? `Last searched ${new Date(area.last_checked_at).toLocaleString()}` : "Not searched yet"}</small>
            </div>
            <button className="action-button" onClick={() => run.mutate(area.id)} disabled={run.isPending}>
              {run.isPending && run.variables === area.id ? <LoaderCircle className="spin" size={16} /> : <Play size={15} />}
              Search live catalogue
            </button>
          </article>
        ))}
        {!areas.isLoading && areas.data?.length === 0 && <EmptyState icon={<MapPin />} text="No watch areas exist for this project." />}
      </div>
      <section className="section-block">
        <div className="section-title"><div><span>CATALOGUE STATUS</span><h2>Recent satellite observations</h2></div><strong>{observations.data?.length ?? 0} stored</strong></div>
        <ObservationTable observations={(observations.data ?? []).slice(0, 8)} />
      </section>
    </section>
  );
}

function ObservationTable({ observations }: { observations: SatelliteObservation[] }) {
  if (observations.length === 0) return <EmptyState icon={<Satellite />} text="Run a live catalogue search to ingest Sentinel-2 observations." />;
  return (
    <div className="data-table observation-table">
      <div className="table-row table-head"><span>Acquisition</span><span>Watch area</span><span>Platform</span><span>Cloud</span><span>Provenance</span></div>
      {observations.map((observation) => (
        <div className="table-row" key={observation.id}>
          <span><strong>{new Date(observation.captured_at).toLocaleString()}</strong><small>{observation.source_item_id}{observation.provenance_checksum ? ` · SHA-256 ${observation.provenance_checksum.slice(0, 10)}…` : ""}</small></span>
          <span>{observation.watch_area_name}</span>
          <span className="capitalize">{observation.metadata.platform ?? observation.source}</span>
          <span><Cloud size={14} /> {observation.cloud_cover == null ? "Unknown" : `${observation.cloud_cover.toFixed(1)}%`}</span>
          <span>{observation.metadata.stac_item_url ? <a href={observation.metadata.stac_item_url} target="_blank" rel="noreferrer">Open STAC record <ArrowUpRight size={13} /></a> : "Stored locally"}</span>
        </div>
      ))}
    </div>
  );
}

export function EventsPage({ projectId }: PageProps) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<MonitoringEvent | null>(null);
  const events = useQuery({ queryKey: ["events", projectId], queryFn: () => api.events(projectId) });
  const geojson = useQuery({ queryKey: ["geojson", projectId], queryFn: () => api.eventGeoJSON(projectId) });
  const review = useMutation({
    mutationFn: ({ eventId, outcome }: { eventId: string; outcome: "confirmed" | "rejected" | "uncertain" }) => api.reviewEvent(eventId, outcome),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["events"] });
      await queryClient.invalidateQueries({ queryKey: ["summary"] });
    },
  });
  return (
    <section className="page-shell">
      <PageHeading eyebrow="DETECTION REVIEW" title="Evidence-backed events" copy="Only outputs from configured detectors appear here. Satellite catalogue records alone are never promoted to detections." />
      <div className="split-page">
        <article className="panel page-map"><header><div><span>DETECTION FOOTPRINTS</span><h2>Event map</h2></div></header><EventMap data={geojson.data} selected={selected} /></article>
        <div className="event-review-list">
          {events.data?.items.map((event) => (
            <article className={`review-card ${selected?.id === event.id ? "selected" : ""}`} key={event.id} onClick={() => setSelected(event)}>
              <div><span className={`status-pill severity-${event.severity}`}>{event.severity}</span><small>{new Date(event.detected_at).toLocaleString()}</small></div>
              <h2>{event.title}</h2><p>{event.summary}</p>
              <footer><span>{event.detector_name} · {Math.round(event.confidence * 100)}%</span>{event.is_reviewed ? <strong>{event.review_outcome}</strong> : <div className="review-actions"><button onClick={(click) => { click.stopPropagation(); review.mutate({ eventId: event.id, outcome: "confirmed" }); }}>Confirm</button><button onClick={(click) => { click.stopPropagation(); review.mutate({ eventId: event.id, outcome: "rejected" }); }}>Reject</button></div>}</footer>
            </article>
          ))}
          {!events.isLoading && events.data?.items.length === 0 && <EmptyState icon={<ShieldCheck />} text="No validated detector events exist. Live satellite observations remain available under Imagery." />}
        </div>
      </div>
    </section>
  );
}

export function ProjectsPage({ projectId, projects }: PageProps) {
  const queryClient = useQueryClient();
  const areas = useWatchAreas(projects, projectId);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useMutation({
    mutationFn: () => api.createProject({ name: name.trim(), description: description.trim(), color: "#4ade80" }),
    onSuccess: async () => {
      setName(""); setDescription("");
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
  function submit(event: FormEvent) { event.preventDefault(); if (name.trim().length >= 2) create.mutate(); }
  return (
    <section className="page-shell">
      <PageHeading eyebrow="WORKSPACE CONFIGURATION" title="Projects and watch areas" copy="Projects scope access and organise the geographic areas queried against the satellite catalogue." />
      <form className="inline-form" onSubmit={submit}>
        <div><label>Project name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="North Sea monitoring" minLength={2} required /></label><label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Purpose and operating scope" /></label></div>
        <button className="action-button" disabled={create.isPending}><Plus size={16} />Create project</button>
      </form>
      <div className="data-grid project-grid">
        {projects.map((project) => <article className="data-card" key={project.id}><div className="project-color" style={{ background: project.color }} /><div className="data-card-main"><span>PROJECT</span><h2>{project.name}</h2><p>{project.description || "No description"}</p><small>{project.watch_area_count} watch areas · {project.event_count} detections</small></div></article>)}
      </div>
      <section className="section-block"><div className="section-title"><div><span>GEOGRAPHIC SCOPE</span><h2>Watch areas</h2></div></div><div className="data-grid">{areas.data?.map((area: WatchArea) => <article className="compact-card" key={area.id}><MapPin size={18} /><div><strong>{area.name}</strong><span>{area.schedule} · {area.categories.join(", ")}</span></div><i className={area.is_active ? "online" : ""} /></article>)}</div></section>
    </section>
  );
}

export function ImageryPage({ projectId }: PageProps) {
  const observations = useQuery({ queryKey: ["observations", projectId], queryFn: () => api.observations(projectId) });
  const collectionCount = useMemo(() => new Set(observations.data?.map((item) => item.source)).size, [observations.data]);
  const previewItems = (observations.data ?? []).filter(
    (observation) => Boolean(observation.assets.rendered_preview?.href),
  );
  return (
    <section className="page-shell">
      <PageHeading eyebrow="LIVE SATELLITE CATALOGUE" title="Imagery observations" copy="Immutable Sentinel-2 acquisition metadata and source provenance returned by the Planetary Computer STAC API." />
      <div className="mini-stat-grid"><article><Satellite /><span>OBSERVATIONS<strong>{observations.data?.length ?? 0}</strong></span></article><article><Layers3 /><span>COLLECTIONS<strong>{collectionCount}</strong></span></article><article><Database /><span>SOURCE<strong>Planetary Computer</strong></span></article></div>
      <div className="imagery-gallery">
        {previewItems.slice(0, 6).map((observation) => (
          <article key={observation.id}>
            <img src={observation.assets.rendered_preview?.href} alt={`Sentinel-2 acquisition ${observation.source_item_id}`} loading="lazy" />
            <div><span>LIVE SENTINEL-2</span><h2>{observation.watch_area_name}</h2><p>{new Date(observation.captured_at).toLocaleString()} · {observation.cloud_cover?.toFixed(1) ?? "Unknown"}% cloud</p></div>
          </article>
        ))}
      </div>
      <ObservationTable observations={observations.data ?? []} />
    </section>
  );
}

export function ReportsPage({ projectId, projects }: PageProps) {
  const queryClient = useQueryClient();
  const reports = useQuery({ queryKey: ["reports", projectId], queryFn: () => api.reports(projectId) });
  const targetProject = projectId ?? projects[0]?.id;
  const create = useMutation({
    mutationFn: () => {
      if (!targetProject) throw new Error("Create a project before generating a report.");
      const end = new Date(); const start = new Date(end.getTime() - 30 * 86_400_000);
      return api.createReport(targetProject, "executive", start.toISOString(), end.toISOString());
    },
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["reports"] }),
  });
  return (
    <section className="page-shell">
      <PageHeading eyebrow="AUDITABLE OUTPUTS" title="Monitoring reports" copy="Generate evidence summaries from validated events in the selected project and time period." />
      <div className="page-toolbar report-toolbar"><span>Reports never infer events from catalogue metadata.</span><button className="action-button" onClick={() => create.mutate()} disabled={!targetProject || create.isPending}><FilePlus2 size={16} />Generate 30-day report</button></div>
      <div className="report-list">{reports.data?.map((report) => <article className="report-card" key={report.id}><div><Activity size={20} /><span className="status-pill">{report.status}</span></div><h2>{report.title}</h2><p>{report.content.summary}</p><footer><span>{new Date(report.period_start).toLocaleDateString()} — {new Date(report.period_end).toLocaleDateString()}</span><strong>{report.content.event_count ?? 0} events</strong></footer></article>)}{!reports.isLoading && reports.data?.length === 0 && <EmptyState icon={<FilePlus2 />} text="No reports have been generated." />}</div>
    </section>
  );
}

export function AssistantPage({ projectId }: PageProps) {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Array<{ question: string; answer: string; count: number }>>([]);
  const ask = useMutation({ mutationFn: (text: string) => api.ask(text, projectId), onSuccess: (result, text) => { setExchanges((items) => [...items, { question: text, answer: result.answer, count: result.result_count }]); setQuestion(""); } });
  function submit(event: FormEvent) { event.preventDefault(); const value = question.trim(); if (value) ask.mutate(value); }
  return (
    <section className="page-shell assistant-page-shell">
      <PageHeading eyebrow="GROUNDED QUERY" title="Earth observation assistant" copy="Translate plain-language questions into filters over your authorised, validated event catalogue." />
      <div className="assistant-page"><div className="assistant-page-thread">{exchanges.length === 0 && <div className="assistant-page-welcome"><Bot size={30} /><h2>Ask about recorded detections</h2><p>The assistant searches stored events only. It does not invent satellite findings.</p></div>}{exchanges.map((item, index) => <div className="exchange" key={`${item.question}-${index}`}><p className="user-message">{item.question}</p><div className="assistant-message"><Sparkles size={14} /><p>{item.answer}<small>{item.count} matching events</small></p></div></div>)}</div><form className="assistant-page-input" onSubmit={submit}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about validated events…" /><button disabled={!question.trim() || ask.isPending}><Sparkles size={16} />Ask</button></form></div>
    </section>
  );
}

export function DocumentationPage() {
  return <section className="page-shell"><PageHeading eyebrow="SYSTEM GUIDE" title="How TerraLens handles satellite data" copy="The boundary between an observation and a detection is deliberate." /><div className="documentation-grid"><article><Satellite /><h2>1. Live observation</h2><p>A Sentinel-2 STAC record is retrieved with acquisition time, footprint, cloud cover, assets, and source provenance.</p></article><article><Radar /><h2>2. Validated detector</h2><p>A detector must process pixels, masks, alignment, and thresholds before it may produce an evidence-backed detection.</p></article><article><ShieldCheck /><h2>3. Human review</h2><p>Analysts confirm, reject, or mark detections uncertain. Catalogue metadata is never silently presented as environmental change.</p></article></div></section>;
}

export function SettingsPage() {
  return <section className="page-shell"><PageHeading eyebrow="RUNTIME CONFIGURATION" title="Data and integrity settings" copy="Current local workspace capabilities and active data sources." /><div className="settings-list"><article><div><Satellite /><span><strong>Satellite catalogue</strong><small>Microsoft Planetary Computer · Sentinel-2 L2A</small></span></div><span className="status-pill online-pill">CONNECTED</span></article><article><div><Radar /><span><strong>Pixel-level detector</strong><small>No validated detector is installed</small></span></div><span className="status-pill warning-pill">NOT CONFIGURED</span></article><article><div><ShieldCheck /><span><strong>Observation policy</strong><small>Only source-backed catalogue records are stored</small></span></div><span className="status-pill">ENFORCED</span></article></div></section>;
}

function EmptyState({ icon, text }: { icon: ReactNode; text: string }) {
  return <div className="empty-state-large">{icon}<p>{text}</p></div>;
}
