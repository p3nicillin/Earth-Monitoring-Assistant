# ULTIMATE_EARTH_MONITOR_BUILD

## Executive assessment

TerraLens is a sound audit-first vertical slice: ownership is enforced in queries, source
observations are separated from detections, geospatial objects retain provenance, and the React
console consumes typed APIs. It is not yet a planetary-scale processing platform. The present
implementation is a synchronous modular monolith with one live STAC provider, one relational
transaction boundary, no raster worker plane, no object store, no durable orchestration, and no
validated detector.

This document records the complete repository review and the first integrated production
evolution. Performance numbers below are acceptance targets or qualitative effects unless marked
as measured; they are not invented benchmark results.

## Current system mental model

```text
Browser / React / MapLibre
        |
        | JWT + JSON + GeoJSON
        v
FastAPI modular monolith
  |-- authentication and owner-scoped dependencies
  |-- projects / watch areas / observations / events / reports
  |-- deterministic natural-language event filtering
  `-- synchronous monitoring service
             |
             v
    Microsoft Planetary Computer STAC
        |
        v
PostgreSQL + PostGIS
```

The frontend is a client-rendered console with React Query caching. The API owns authorization and
domain orchestration. Monitoring searches STAC, normalizes and validates features, then stores
observations before any possible event. Events are absent until a validated detector is installed.
Docker Compose is the supported full-stack deployment; SQLite is a local-development compatibility
path only.

## Weakness register

| Priority | Weakness | Impact | Effort | Required control |
| --- | --- | --- | --- | --- |
| P0 | No durable job/run state or queue | Requests cannot survive process loss or long raster work | L | Transactional run table, outbox, queue workers |
| P0 | No operational pixel detector | No scientifically defensible change events | XL | Choose one phenomenon; validate end-to-end |
| P0 | No raw/derived object store | Assets cannot be checksummed, retained, tiled, or reproduced | L | Versioned S3-compatible storage and lifecycle policy |
| P0 | Shared HS256 signing boundary | Unsafe across independently deployed services | M | OIDC/asymmetric JWTs with rotation and JWKS |
| P1 | Synchronous external acquisition | Provider latency consumes API capacity | M | Queue search jobs and return `202` run resources |
| P1 | Single metadata provider | Provider outage or coverage gap stops acquisition | M | Adapter conformance suite and registry-driven providers |
| P1 | No provider credential abstraction | Restricted providers cannot be onboarded safely | M | Secret references, scoped credentials, rotation |
| P1 | No COG/Zarr processing plane | Multi-scene analysis is memory/node constrained | XL | Xarray/Dask chunk contract and object-store execution |
| P1 | No cloud/shadow/quality-mask pipeline | Optical analytics would be scientifically invalid | L | Sensor-specific QA/SCL masking with coverage metrics |
| P1 | No co-registration/reprojection service | Pixel differencing would create false change | L | Grid policy, reprojection, alignment residual checks |
| P1 | No immutable evidence manifest | Reproduction and chain of custody remain incomplete | M | Content-addressed manifests and append-only audit log |
| P1 | No PostGIS integration tests before this pass | Migration/spatial failures could escape CI | S | Live PostGIS migration and query tests |
| P2 | In-process rate limiting | Multi-replica limits are inconsistent | S | Gateway/Redis token bucket |
| P2 | No distributed tracing | Cross-service latency/failures will be opaque | M | OpenTelemetry traces and correlation propagation |
| P2 | No raster/vector tile service | Browser cannot explore large outputs efficiently | M | TiTiler/pg_tileserv or equivalent bounded tile APIs |
| P2 | No model registry/model cards | Detector promotion and rollback are uncontrolled | M | Signed artifacts, approval states, evaluation registry |
| P2 | No organization/team model | Roles do not express collaboration boundaries | M | Organization membership and project grants |
| P2 | No alert delivery/outbox | Notifications cannot be reliable or idempotent | M | Policy engine, outbox, delivery receipts |
| P2 | No quota/cost controls | Planet-scale queries can create unbounded spend | M | Area/time/provider quotas and budget telemetry |
| P3 | Large frontend map bundle | Slower first interactive map on weak clients | S | Route-level and vendor chunking, tile-first rendering |
| P3 | No accessibility/browser matrix | UI regressions may exclude users | M | WCAG audit and Playwright matrix |
| P3 | No benchmark suite | Optimization claims cannot be substantiated | M | Representative COG/Zarr and API benchmark corpus |

## Engineering iterations implemented

### Iteration 1

- **Primary Focus:** architectural truth and source-only operation.
- **Reasoning:** catalogue metadata must never be presented as a scientific detection.
- **Changes Implemented:** removed non-source providers and generated events; exposed live
  observations, working workspace pages, STAC provenance, and rendered source previews.
- **Expected Performance Gain:** no processing-throughput claim; fewer invalid downstream records.
- **Scalability Impact:** clean observation/detection boundary permits independent worker scaling.
- **Reliability Impact:** idempotent source storage avoids duplicate acquisition records.
- **Scientific Benefit:** prevents metadata-only false positives.
- **Trade-offs:** event, report, and assistant results remain empty until a detector passes its gate.

### Iteration 2

- **Primary Focus:** resilient acquisition and hexagonal provider boundary.
- **Reasoning:** provider payloads and networks fail independently of the domain service.
- **Changes Implemented:** provider-neutral search/item contracts; registry/factory selection;
  transient HTTP retry with exponential backoff; WGS84 geometry, temporal, cloud, item and asset
  validation; invalid-feature isolation; safe asset schemes; provider-scoped deduplication; SHA-256
  canonical provenance checksums; bounded search size.
- **Expected Performance Gain:** retry avoids repeated manual runs; search limits bound response
  memory. Throughput must be benchmarked under provider quotas.
- **Scalability Impact:** adapters can be added without changing monitoring persistence.
- **Reliability Impact:** transient 408/425/429/5xx and network errors receive bounded retry;
  malformed items cannot poison a full response when valid items remain.
- **Scientific Benefit:** source geometry, capture time, assets, and collection provenance are
  validated before persistence.
- **Trade-offs:** exponential retry increases tail latency; the synchronous API still waits for it.

### Iteration 3

- **Primary Focus:** scientific primitives and raster correctness.
- **Reasoning:** most false change maps begin with misalignment, nodata leakage, or undocumented
  formulas rather than model choice.
- **Changes Implemented:** 15 vectorized index implementations; named band registry; deterministic
  missing-band failures; finite/nodata-safe division; dNBR; same-shape enforcement; CRS, affine,
  size, dtype and nodata grid validation; literature, assumptions and limitations documentation.
- **Expected Performance Gain:** `O(N)` vectorized NumPy reference path; no distributed speedup is
  claimed until benchmarked.
- **Scalability Impact:** pure formulas are compatible with future Dask/Xarray/CuPy block adapters.
- **Reliability Impact:** invalid alignment and singular transforms fail before pixel arithmetic.
- **Scientific Benefit:** formulas and their sensor/preprocessing assumptions are reviewable.
- **Trade-offs:** arrays are currently in memory; accepted formulas are not detectors by themselves.

### Iteration 4

- **Primary Focus:** API, container, and delivery hardening.
- **Reasoning:** scientific integrity is irrelevant if identity, host routing, request bounds, or
  migrations are weak.
- **Changes Implemented:** JWT issuer/audience/JTI validation; explicit required claims; trusted
  hosts; one-megabyte default request bound; CSP/frame protections; bounded rate-limit client
  cleanup; loopback-only Compose ports; read-only API container; no-new-privileges; CI PostGIS
  migration execution; provider/schema migration.
- **Expected Performance Gain:** bounded request and limiter memory; no latency claim.
- **Scalability Impact:** safer baseline for gateway deployment and migration automation.
- **Reliability Impact:** CI now detects migration and PostGIS compatibility failures.
- **Scientific Benefit:** provenance and processing records receive stronger access boundaries.
- **Trade-offs:** host/CSP configuration must be explicitly extended for each deployment domain.

## Proposed production architecture

```text
                           +-------------------------+
                           | OIDC / JWKS / Policy    |
                           +------------+------------+
                                        |
Users -> CDN/WAF -> Web/API Gateway -> Control-plane API -> PostGIS metadata
                    |                   |      |             |
                    |                   |      |             +-> pg_tileserv
                    |                   |      +-> transactional outbox
                    |                   +-> run state / quotas / audit log
                    |
                    +-> TiTiler / signed COG and Zarr access

Provider adapters -> acquisition queue -> normalization workers -> object store
 STAC / CMR /        (Kafka/SQS/PubSub)      |                   (versioned)
 EarthData / USGS                            +-> checksum/evidence manifests
 Copernicus / Planet                         |
                                              v
                                  workflow orchestrator
                                  |       |        |
                              Dask CPU  Ray/GPU  Spark batch
                                  |       |        |
                                  +--- detector plugins ---+
                                                        |
                                               model registry/cards
                                                        |
                                               reviewable events

All components -> OpenTelemetry -> metrics/logs/traces -> SLOs and cost telemetry
```

### Plane boundaries

- **Control plane:** identity, ownership, projects, watch areas, run policy, budgets, review.
- **Acquisition plane:** provider adapters, credentials, retry, normalization, checksum manifests.
- **Data plane:** immutable source/derived objects, STAC catalogue, PostGIS metadata, tiles.
- **Compute plane:** queue-driven preprocessing and detector plugins with explicit resource classes.
- **Evidence plane:** model cards, manifests, uncertainty, audit decisions, signed exports.

## Migration roadmap

### Phase 1 — Durable execution

Add monitoring-run/job/attempt tables, transactional outbox, idempotency keys, and a queue worker.
Acceptance gate: kill API and worker processes during every state transition; a run resumes or
fails terminally without duplicate observations.

### Phase 2 — Cloud-native source storage

Stream assets into versioned object storage, verify size/checksum/media type, create STAC Items and
COG/Zarr derivatives, and issue short-lived signed URLs. Acceptance gate: every API observation can
be reconstructed from an immutable manifest after provider URLs expire.

### Phase 3 — One validated detector

Select one bounded product, such as Sentinel-1 flood extent or Sentinel-2 burn severity. Implement
quality masks, co-registration, uncertainty, independent geographic/seasonal validation, model
card, and analyst review. Acceptance gate: published benchmark, calibrated thresholds, traceable
false-positive/negative analysis, and reproducible evidence bundle.

### Phase 4 — Distributed processing

Introduce Xarray/Rioxarray with documented chunk layouts, Dask for COG/Zarr block graphs, and
resource-aware scheduling. Add CuPy/Numba only where profiling proves kernel pressure; use Ray for
stateful model serving only where Dask is unsuitable. Acceptance gate: numerical parity with the
NumPy reference, bounded worker memory, retry-safe tasks, and benchmarked cost per square kilometre.

### Phase 5 — Multi-provider and multi-sensor fusion

Add adapters in this order: NASA CMR/Earthaccess, Copernicus Data Space, USGS Landsat, Sentinel-1,
MODIS/VIIRS, DEM and reanalysis. Commercial providers require license-aware access controls.
Acceptance gate: provider conformance tests cover missing scenes, corrupted metadata, rate limits,
auth expiry, temporal gaps, CRS differences and duplicate identities.

### Phase 6 — Enterprise operations

Deploy Kubernetes operators/workers, autoscaling, OIDC, asymmetric signing, organization grants,
Redis/gateway limits, OpenTelemetry, SLOs, alert outbox, disaster recovery, SBOM/signing and policy
controls across AWS/Azure/GCP. Edge packages should contain explicitly versioned, offline-capable
models and synchronization policies rather than a second architecture.

## Performance and reliability acceptance targets

| Area | Target before production claim |
| --- | --- |
| Catalogue API | p95 under 2 s excluding provider delay; bounded three-attempt retry |
| Idempotency | zero duplicate observations across 10,000 replayed messages |
| Raster worker | peak memory below 2.5 times configured chunk working set |
| Numerical parity | distributed versus reference absolute error below method tolerance |
| Availability | 99.9% control-plane SLO with provider degradation isolated |
| Recovery | worker interruption resumes without partial event publication |
| Provenance | 100% detections resolve to checksummed sources, code/model version and parameters |
| Security | no critical/high findings in released images; tested key/credential rotation |

## Engineering saturation assessment

Saturation has not been reached, and claiming otherwise would be technically and scientifically
false. Material work remains in durable orchestration, object storage, cloud masking,
co-registration, independent detector validation, distributed execution, model governance,
multi-tenant authorization, observability, cost controls, disaster recovery, and measured
benchmarks. The repository now has a stronger integrated foundation for that work; the phase gates
above define how progress can be demonstrated rather than asserted.
