import { useQuery } from "@tanstack/react-query";
import { Camera, Database, Orbit, Sun } from "lucide-react";
import { useState } from "react";

import { api } from "../lib/api";
import { PageHeading } from "./WorkspacePages";

const REFRESH_MS = 120_000;

function formatBytes(bytes: number) {
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export default function GalleryPage() {
  const [sourceKey, setSourceKey] = useState<string>();
  const sources = useQuery({ queryKey: ["imagery-sources"], queryFn: api.imagerySources, refetchInterval: REFRESH_MS });
  const gallery = useQuery({
    queryKey: ["imagery-captures", sourceKey],
    queryFn: () => api.imageryCaptures(sourceKey, 48),
    refetchInterval: REFRESH_MS,
  });

  const totalFrames = sources.data?.reduce((sum, item) => sum + item.capture_count, 0) ?? 0;
  const activeSources = sources.data?.filter((item) => item.capture_count > 0).length ?? 0;

  return (
    <section className="page-shell">
      <PageHeading
        eyebrow="AUTONOMOUS SPACE IMAGERY"
        title="Live capture archive"
        copy="The scheduler continuously watches SDO, SOHO, GOES SUVI, and DSCOVR EPIC, archiving each genuinely new frame to local storage with provenance. Unchanged upstream frames are deduplicated by content hash, so the archive grows exactly as fast as the Sun and Earth actually change."
      />
      <div className="mini-stat-grid">
        <article><Camera /><span>FRAMES ARCHIVED<strong>{totalFrames.toLocaleString()}</strong></span></article>
        <article><Sun /><span>LIVE SOURCES<strong>{activeSources} of {sources.data?.length ?? 0} capturing</strong></span></article>
        <article><Database /><span>STORAGE<strong>Local · content-hash deduplicated</strong></span></article>
      </div>
      <div className="gallery-filters">
        <button className={sourceKey ? "" : "active"} onClick={() => setSourceKey(undefined)}>All sources</button>
        {sources.data?.map((source) => (
          <button
            key={source.key}
            className={sourceKey === source.key ? "active" : ""}
            onClick={() => setSourceKey(source.key)}
            title={source.description}
          >
            {source.title}
            <em>{source.capture_count}</em>
          </button>
        ))}
      </div>
      <div className="imagery-gallery space-gallery">
        {gallery.data?.items.map((capture) => (
          <article key={capture.id}>
            <a href={api.imageryFileUrl(capture.id)} target="_blank" rel="noreferrer">
              <img src={api.imageryFileUrl(capture.id)} alt={`${capture.title}, captured ${capture.captured_at}`} loading="lazy" />
            </a>
            <div>
              <span>{capture.source.toUpperCase()}</span>
              <h2>{capture.title}</h2>
              <p>{new Date(capture.captured_at).toUTCString().replace("GMT", "UTC")} · {formatBytes(capture.byte_size)}</p>
            </div>
          </article>
        ))}
      </div>
      {!gallery.isLoading && gallery.data?.items.length === 0 && (
        <div className="empty-state-large">
          <Orbit />
          <p>No frames captured yet. The imagery harvester runs automatically every few minutes after startup; the first sweep populates this gallery.</p>
        </div>
      )}
    </section>
  );
}
