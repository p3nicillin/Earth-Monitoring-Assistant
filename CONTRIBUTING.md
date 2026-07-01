# Contributing

## Workflow

1. Open an issue describing the user outcome, scientific assumptions, and acceptance tests.
2. Keep changes inside an existing domain boundary or add an ADR when introducing a new one.
3. Add tests for authorization, geometry edge cases, evidence provenance, and failure behavior.
4. Run the backend and frontend verification commands from the README.
5. Keep pull requests small enough to review and include screenshots for interface changes.

## Engineering rules

- Never convert a source observation into an event without a named, versioned detector and evidence.
- Never accept a project-scoped identifier without resolving it through the authenticated owner.
- Never calculate metre-based measures directly in EPSG:4326 degrees.
- External downloads must have timeouts; processing jobs must be retry-safe and idempotent.
- Migrations are forward-only in production. Test downgrade logic for local use, but recover
  production data through a new corrective migration.
- Secrets, raw imagery, model artifacts, and generated reports do not belong in Git.

Commit messages should be imperative and scoped, for example:

```text
feat(monitoring): ingest cloud-filtered Sentinel-2 observations
fix(auth): scope watch area lookup through project owner
```
