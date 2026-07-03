import { useQuery } from "@tanstack/react-query";
import { Archive, Brain, Gauge, Target, TrendingUp } from "lucide-react";

import { api } from "../lib/api";
import type { ForecastPoint, ForecastSkill } from "../types";
import { PageHeading } from "./WorkspacePages";

const REFRESH_MS = 60_000;

function formatValue(value: number | null | undefined, unit?: string) {
  if (value == null) return "—";
  const text = Math.abs(value) >= 0.01 || value === 0 ? value.toFixed(2) : value.toExponential(1);
  return unit ? `${text} ${unit}` : text;
}

function horizonLabel(minutes: number) {
  return minutes % 60 === 0 ? `${minutes / 60}h` : `${minutes}m`;
}

function archiveSpanDays(first: string | null, last: string | null) {
  if (!first || !last) return 0;
  return Math.max(0, (new Date(last).getTime() - new Date(first).getTime()) / 86_400_000);
}

function SkillTable({ skill }: { skill: ForecastSkill[] }) {
  const learned = skill.filter((item) => item.model_name !== "persistence");
  if (learned.length === 0) {
    return <div className="empty-state-large"><Target /><p>No forecasts have matured yet. Skill scores appear once predictions can be compared with what actually happened.</p></div>;
  }
  return (
    <div className="data-table skill-table">
      <div className="table-row table-head"><span>Metric</span><span>Model</span><span>Horizon</span><span>Scored</span><span>Vs persistence</span></div>
      {learned.map((item) => (
        <div className="table-row" key={`${item.metric}-${item.model_name}-${item.horizon_minutes}`}>
          <span><strong>{item.metric}</strong></span>
          <span>{item.model_name}</span>
          <span>{horizonLabel(item.horizon_minutes)}</span>
          <span>{item.resolved_count} · MAE {formatValue(item.mean_abs_error)}</span>
          <span>
            {item.skill_vs_persistence == null
              ? "no control yet"
              : <strong className={item.skill_vs_persistence < 1 ? "skill-good" : "skill-flat"}>{`${(item.skill_vs_persistence * 100).toFixed(0)}% of naive error`}</strong>}
          </span>
        </div>
      ))}
    </div>
  );
}

function ForecastTable({ points, resolved }: { points: ForecastPoint[]; resolved?: boolean }) {
  if (points.length === 0) {
    return <div className="empty-state-large"><TrendingUp /><p>{resolved ? "No resolved forecasts yet." : "No open forecasts. The scheduler issues a fresh set every hour."}</p></div>;
  }
  return (
    <div className="data-table skill-table">
      <div className="table-row table-head"><span>Metric</span><span>Model</span><span>Target (UTC)</span><span>Predicted</span><span>{resolved ? "Actual / error" : "Horizon"}</span></div>
      {points.slice(0, 12).map((point) => (
        <div className="table-row" key={`${point.metric}-${point.model_name}-${point.target_time}`}>
          <span><strong>{point.metric}</strong></span>
          <span>{point.model_name}</span>
          <span>{new Date(point.target_time).toISOString().slice(5, 16).replace("T", " ")}</span>
          <span>{formatValue(point.predicted_value)}</span>
          <span>{resolved ? `${formatValue(point.actual_value)} · Δ ${formatValue(point.abs_error)}` : horizonLabel(point.horizon_minutes)}</span>
        </div>
      ))}
    </div>
  );
}

export default function InsightsPage() {
  const status = useQuery({ queryKey: ["learning-status"], queryFn: api.learningStatus, refetchInterval: REFRESH_MS });
  const baselines = useQuery({ queryKey: ["learning-baselines"], queryFn: api.learningBaselines, refetchInterval: REFRESH_MS * 5 });
  const forecasts = useQuery({ queryKey: ["learning-forecasts"], queryFn: api.learningForecasts, refetchInterval: REFRESH_MS });

  const spanDays = Math.max(
    0,
    ...(status.data?.archive.map((item) => archiveSpanDays(item.first_sample_at, item.last_sample_at)) ?? [0]),
  );
  const adaptiveActive = baselines.data?.filter((item) => item.adaptive_threshold != null).length ?? 0;

  return (
    <section className="page-shell">
      <PageHeading
        eyebrow="ADAPTIVE INTELLIGENCE"
        title="Learning and prediction"
        copy="The platform archives every live space-weather reading, learns local climatology from its own history, forecasts ahead, and scores those forecasts against what actually happened. All improvement is measured, never asserted."
      />
      <div className="mini-stat-grid insights-stats">
        <article><Archive /><span>SAMPLES ARCHIVED<strong>{status.data?.total_samples.toLocaleString() ?? "—"}</strong></span></article>
        <article><Brain /><span>ARCHIVE DEPTH<strong>{spanDays >= 1 ? `${spanDays.toFixed(1)} days` : "building"}</strong></span></article>
        <article><Gauge /><span>ADAPTIVE THRESHOLDS<strong>{adaptiveActive} / {baselines.data?.length ?? 0} active</strong></span></article>
        <article><Target /><span>FORECASTS SCORED<strong>{status.data?.forecasts_resolved ?? 0} · {status.data?.forecasts_pending ?? 0} open</strong></span></article>
      </div>

      <section className="section-block">
        <div className="section-title"><div><span>LEARNED CLIMATOLOGY · LAST {status.data?.baseline_window_days ?? 60} DAYS</span><h2>Adaptive baselines</h2></div></div>
        <div className="data-table baseline-table">
          <div className="table-row table-head"><span>Metric</span><span>Samples</span><span>Maturity</span><span>p50 / p95 / p99</span><span>Learned threshold</span><span>Published floor</span></div>
          {(baselines.data ?? []).map((baseline) => (
            <div className="table-row" key={baseline.metric}>
              <span><strong>{baseline.title}</strong><small>{baseline.metric}</small></span>
              <span>{baseline.sample_count.toLocaleString()}</span>
              <span><i className="maturity-bar"><b style={{ width: `${Math.round(baseline.maturity * 100)}%` }} /></i>{Math.round(baseline.maturity * 100)}%</span>
              <span>{formatValue(baseline.p50)} / {formatValue(baseline.p95)} / {formatValue(baseline.p99)}</span>
              <span>{baseline.adaptive_threshold == null ? <small>needs {status.data?.min_baseline_samples ?? "more"} samples</small> : <strong>{formatValue(baseline.adaptive_threshold, baseline.unit)}</strong>}</span>
              <span>{formatValue(baseline.published_floor, baseline.unit)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="section-block">
        <div className="section-title"><div><span>SELF-SCORED PREDICTION</span><h2>Forecast skill</h2></div><strong>damped-trend model vs naive persistence control</strong></div>
        <SkillTable skill={status.data?.skill ?? []} />
      </section>

      <div className="split-columns">
        <section className="section-block">
          <div className="section-title"><div><span>OPEN PREDICTIONS</span><h2>Upcoming forecasts</h2></div></div>
          <ForecastTable points={forecasts.data?.upcoming ?? []} />
        </section>
        <section className="section-block">
          <div className="section-title"><div><span>VERIFIED OUTCOMES</span><h2>Recently resolved</h2></div></div>
          <ForecastTable points={forecasts.data?.recent_resolved ?? []} resolved />
        </section>
      </div>
    </section>
  );
}
