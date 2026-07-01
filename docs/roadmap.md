# Product roadmap

The original vision is decomposed into evidence-producing vertical slices. Each milestone has a
testable exit condition; “supports AI” is not an exit condition.

## Milestone 1 — Auditable platform foundation (current)

Delivered: typed web/API contracts, authentication and ownership, projects/watch areas,
PostGIS events, live Sentinel-2 STAC catalogue ingestion, source-safe monitoring, map/dashboard,
assistant filters, reports, containers, migration, metrics, tests, and CI.

Exit criteria still to close: PostGIS integration tests in CI, browser end-to-end tests, WCAG audit,
and a deployment runbook for the first chosen cloud.

## Milestone 2 — Real environmental change pipeline

- Durable run/job tables and queue-backed workers
- S3-compatible raw/processed/artifact storage with checksums and lifecycle rules
- Sentinel-2 COG access, scene classification/cloud masks, reprojection, and co-registration
- Validated NDVI/NDWI/NBR differencing with minimum mapping units and uncertainty
- Flood, burn-severity, and vegetation-loss plugins with benchmark datasets
- Analyst review UI, labels, false-positive reasons, and model cards

Exit: a held-out geographic benchmark meets agreed precision/recall/IoU thresholds, every event is
reproducible from checksummed inputs, and a human can approve/reject it.

## Milestone 3 — Operations, alerts, and exports

- Scheduled watch-area runs with backfill and idempotency
- Rule-based alert policies, quiet periods, escalation, and delivery ledger
- Email and webhook first; SMS/Slack/Teams/Discord as separate adapters
- GeoJSON, GeoPackage, CSV, COG, and signed download exports
- PDF report rendering and scheduled daily/weekly/monthly reports
- Audit-log search, retention, backup restore drill, and SLO dashboards

Exit: notification retries are observable and duplicate-safe, exports round-trip through common GIS
tools, and a backup restore is timed and documented.

## Milestone 4 — Teams and global map performance

- Organizations, project membership, invitations, RBAC policies, and API keys
- Vector/raster tile service, overview pyramids, CDN caching, and time slider
- Event/observation table partitioning and materialized dashboard summaries
- Address/geocoding integration, measurements, saved views, and share links
- Usage metering, quotas, and per-tenant cost attribution

Exit: authorization has an explicit policy matrix and cross-tenant tests; representative map tiles
meet the latency SLO under expected concurrency.

## Milestone 5 — Domain packs

Agriculture, urban development, infrastructure, disaster response, and maritime monitoring ship as
independently versioned packs. Each has domain-specific inputs, taxonomies, models, evaluation,
thresholds, and human review. Shared platform services remain ingestion, identity, storage, jobs,
maps, reporting, and notifications.

Exit: each advertised detector has a model card, geographic/seasonal evaluation, drift indicators,
and a named operational owner.

## Milestone 6 — Geospatial RAG and multimodal reasoning

- Curated retrieval over event evidence, model cards, reports, and metadata
- Geometry/time-aware retrieval and query plans displayed to users
- Citation links back to observations and source assets
- Prompt-injection isolation for untrusted metadata/documents
- Evaluation set for factuality, spatial/temporal constraint adherence, and abstention

Exit: assistant answers are citation-backed, tenant-scoped, regression-tested, and abstain when the
stored evidence does not support an answer.
