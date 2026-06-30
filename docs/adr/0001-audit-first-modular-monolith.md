# ADR 0001: Audit-first modular monolith

- Status: accepted
- Date: 2026-06-30

## Context

The product vision includes many sensors, phenomena, models, delivery channels, and worldwide
scale. Starting with microservices would distribute incomplete domain assumptions across network
boundaries. At the same time, scientific inference needs stronger provenance than an ordinary CRUD
dashboard.

## Decision

Start with a modular FastAPI application and one PostGIS transaction boundary. Keep provider,
detector, reporting, and query use cases behind explicit modules and typed contracts. Persist the
source observation before any derived event. Every event records detector identity/version,
confidence, evidence, geometry, and review state.

Demo inference is a distinct provider/detector path. Live catalogue ingestion cannot silently call
the demo detector.

## Consequences

- Local development and transactions remain simple.
- Domain boundaries can be tested before they become service APIs.
- Raster/GPU workloads will move behind a durable queue when implemented.
- Independent scaling is deferred, but extraction points are clear.
- The schema and UI carry provenance from the first release rather than adding it after users depend
  on opaque scores.
