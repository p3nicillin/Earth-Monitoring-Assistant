# Security policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Contact the repository owner privately
through the security reporting channel configured on GitHub. Include the affected endpoint or
commit, reproduction steps, impact, and any safe mitigation you have identified.

## Deployment checklist

Before exposing this service beyond a local machine:

- Generate a unique high-entropy `SECRET_KEY`; rotate all demo/database credentials and disable
  demo seeding and public registration.
- Serve only through TLS, validate allowed hosts at ingress, restrict CORS to exact origins, and set
  request/body size limits.
- Keep Postgres private, enforce encrypted connections, use least-privilege roles, and enable
  encrypted backups with tested restore procedures.
- Restrict `/metrics` and API documentation to trusted networks when they expose operational detail.
- Enforce distributed rate limits and abuse controls at the gateway for multi-replica deployments.
- Pin and scan container images; apply dependency updates after CI and smoke testing.
- Store satellite/provider credentials and signing keys in a managed secret store.
- Define retention and deletion policy for watch areas, reports, user data, and audit events.
- Complete a threat model before adding uploads, public share links, webhooks, or LLM retrieval.

JWTs currently use a shared HS256 secret. That is suitable for a single service boundary. If several
independently deployed services validate tokens, migrate to short-lived asymmetric signing with a
published key set and planned rotation.
