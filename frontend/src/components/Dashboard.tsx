import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Bell,
  Bot,
  ChevronDown,
  CircleHelp,
  CloudSun,
  FolderKanban,
  Globe2,
  Layers3,
  LogOut,
  Map as MapIcon,
  Menu,
  Radar,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { api, tokenStore } from "../lib/api";
import type { MonitoringEvent, User } from "../types";
import { AssistantPanel } from "./AssistantPanel";
import { EventMap } from "./EventMap";

interface DashboardProps {
  user: User;
  onLogout: () => void;
}

const categoryColors: Record<string, string> = {
  environment: "#4ade80",
  agriculture: "#a3e635",
  urban: "#67e8f9",
  infrastructure: "#a78bfa",
  disaster: "#fb7185",
  maritime: "#38bdf8",
};

function timeAgo(value: string) {
  const hours = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 3_600_000));
  return hours < 24 ? `${hours}h ago` : `${Math.round(hours / 24)}d ago`;
}

export function Dashboard({ user, onLogout }: DashboardProps) {
  const [projectId, setProjectId] = useState<string>();
  const [selected, setSelected] = useState<MonitoringEvent | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const summary = useQuery({
    queryKey: ["summary", projectId],
    queryFn: () => api.summary(projectId),
  });
  const events = useQuery({ queryKey: ["events", projectId], queryFn: () => api.events(projectId) });
  const geojson = useQuery({ queryKey: ["geojson", projectId], queryFn: () => api.eventGeoJSON(projectId) });

  const chartData = useMemo(
    () => Object.entries(summary.data?.category_counts ?? {}).map(([name, value]) => ({ name, value })),
    [summary.data],
  );
  const currentProject = projects.data?.find((project) => project.id === projectId);

  function logout() {
    tokenStore.clear();
    onLogout();
  }

  const failed = projects.isError || summary.isError || events.isError || geojson.isError;
  return (
    <div className="app-shell">
      {mobileNav && <button className="sidebar-backdrop" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}
      <aside className={`sidebar ${mobileNav ? "sidebar-mobile-open" : ""}`}>
        <div className="brand-lockup sidebar-brand"><span className="brand-mark"><Globe2 size={20} /></span><span>TerraLens</span></div>
        <nav>
          <p>WORKSPACE</p>
          <a className="active"><MapIcon size={18} />Overview</a>
          <a><Radar size={18} />Monitoring<span className="nav-badge">3</span></a>
          <a><TriangleAlert size={18} />Events</a>
          <a><FolderKanban size={18} />Projects</a>
          <p>ANALYSIS</p>
          <a><Layers3 size={18} />Imagery</a>
          <a><Activity size={18} />Reports</a>
          <a><Bot size={18} />Assistant</a>
        </nav>
        <div className="sidebar-bottom">
          <a><CircleHelp size={17} />Documentation</a>
          <a><Settings size={17} />Settings</a>
          <button onClick={logout}><span>{user.display_name.slice(0, 2).toUpperCase()}</span><div><strong>{user.display_name}</strong><small>{user.role}</small></div><LogOut size={15} /></button>
        </div>
      </aside>

      <main className="dashboard-main">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMobileNav((value) => !value)}><Menu size={20} /></button>
          <div className="project-switcher">
            <span style={{ backgroundColor: currentProject?.color ?? "#4ade80" }} />
            <select value={projectId ?? ""} onChange={(event) => setProjectId(event.target.value || undefined)}>
              <option value="">All projects</option>
              {projects.data?.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}
            </select>
            <ChevronDown size={15} />
          </div>
          <div className="topbar-actions">
            <div className="system-status"><span /> SYSTEM OPERATIONAL</div>
            <button aria-label="Search"><Search size={18} /></button>
            <button className="notification" aria-label="Notifications"><Bell size={18} /><i /></button>
          </div>
        </header>

        <div className="dashboard-content">
          <section className="dashboard-heading">
            <div><p className="eyebrow">MONITORING OVERVIEW</p><h1>Good morning, {user.display_name.split(" ")[0]}.</h1><span>Here’s what Earth observation has surfaced across your watch areas.</span></div>
            <div className="weather-chip"><CloudSun size={22} /><div><strong>12°C</strong><small>London · Clear</small></div></div>
          </section>

          {failed && <div className="connection-error"><TriangleAlert size={18} /><span><strong>Unable to reach the API.</strong> Confirm the backend and database containers are healthy, then refresh.</span></div>}

          <section className="stat-grid">
            <article><div className="stat-icon green"><Radar size={18} /></div><span>EVENTS · 24H</span><strong>{summary.data?.events_24h ?? "—"}</strong><small><i className="up">↗ 18%</i> vs previous period</small></article>
            <article><div className="stat-icon cyan"><MapIcon size={18} /></div><span>WATCH AREAS</span><strong>{summary.data?.watch_areas ?? "—"}</strong><small>{summary.data?.active_projects ?? 0} active projects</small></article>
            <article><div className="stat-icon red"><TriangleAlert size={18} /></div><span>CRITICAL EVENTS</span><strong>{summary.data?.critical_events ?? "—"}</strong><small>Require immediate review</small></article>
            <article><div className="stat-icon purple"><ShieldCheck size={18} /></div><span>REVIEWED</span><strong>{summary.data?.reviewed_percentage ?? "—"}<sup>%</sup></strong><small>Human verification coverage</small></article>
          </section>

          <section className="workspace-grid">
            <article className="map-card panel">
              <header><div><span>ACTIVE DETECTIONS</span><h2>Change event map</h2></div><div className="time-filter">Last 30 days <ChevronDown size={14} /></div></header>
              <EventMap data={geojson.data} selected={selected} />
            </article>

            <article className="events-card panel">
              <header><div><span>INTELLIGENCE FEED</span><h2>Recent events</h2></div><button>View all</button></header>
              <div className="event-list">
                {events.isLoading && [1, 2, 3].map((item) => <div className="event-skeleton" key={item} />)}
                {events.data?.items.slice(0, 5).map((event) => (
                  <button className={selected?.id === event.id ? "selected" : ""} key={event.id} onClick={() => setSelected(event)}>
                    <span className={`event-symbol symbol-${event.category}`}><TriangleAlert size={16} /></span>
                    <div><strong>{event.title}</strong><span>{event.category} · {event.area_sq_km ? `${event.area_sq_km} km²` : "extent pending"}</span><small>{timeAgo(event.detected_at)} · {Math.round(event.confidence * 100)}% confidence</small></div>
                    <i className={`severity-dot dot-${event.severity}`} />
                  </button>
                ))}
                {events.data?.items.length === 0 && <div className="empty-state">No detections match this project.</div>}
              </div>
            </article>
          </section>

          <section className="lower-grid">
            <article className="panel distribution-card">
              <header><div><span>LAST 30 DAYS</span><h2>Events by domain</h2></div></header>
              <div className="chart-body">
                <div className="donut-wrap"><ResponsiveContainer width="100%" height={150}><PieChart><Pie data={chartData} innerRadius={46} outerRadius={68} dataKey="value" stroke="none">{chartData.map((entry) => <Cell key={entry.name} fill={categoryColors[entry.name] ?? "#94a3b8"} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer><span><strong>{events.data?.total ?? 0}</strong>TOTAL</span></div>
                <div className="chart-legend">{chartData.map((item) => <div key={item.name}><i style={{ background: categoryColors[item.name] }} /><span>{item.name}</span><strong>{item.value}</strong></div>)}</div>
              </div>
            </article>
            <article className="panel assistant-teaser">
              <div className="assistant-orb"><Sparkles size={23} /></div>
              <div><span>AI ANALYSIS</span><h2>Ask the planet a question.</h2><p>Turn plain language into scoped searches across your authorised events and watch areas.</p></div>
              <button onClick={() => setAssistantOpen(true)}>Open assistant <Sparkles size={15} /></button>
            </article>
          </section>
        </div>
      </main>
      <AssistantPanel projectId={projectId} open={assistantOpen} onClose={() => setAssistantOpen(false)} />
    </div>
  );
}
