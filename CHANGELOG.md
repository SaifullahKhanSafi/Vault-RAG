# Changelog

Changes follow Semantic Versioning. `VERSION` is the application release version; SQL migrations retain their own ordered numbers.

## [0.1.0] - 2026-11-03

First versioned packaging baseline for the existing application. Earlier internal API/package labels were not published releases.

### Added

- Local PDF RAG with PostgreSQL/pgvector, hybrid search, page citations and persistent private conversations.
- Verified local registration/recovery/invitations, role and document access controls, optional OIDC identity-provider MFA.
- Durable versioned originals, background indexing, English scan OCR, table extraction and ingestion diagnostics.
- Forty-question synthetic benchmarking across four retrieval configurations, extraction/security checks, optional local judging, human review and capacity probes.
- Feature-branch/PR CI, browser regressions, fresh-database integration, version checks and container/package validation.
- Version-tagged GHCR images with build provenance/SBOM, checksummed source/deployment archives and manual SSH deployment for Docker VPS environments.

### Changed

- Document cards use theme-aware text/action colors and accessible indexing percentage bars, including queued, processing, failed and ready states.
- Retried ingestion resets progress when a new attempt starts.
- README and operator/deployment instructions distinguish measured results from deployment prerequisites and remaining evaluation work.

### Known limitations

- The synthetic pilot is not human-reviewed enterprise accuracy. Two hybrid answers lacked required evidence citations.
- The current optional model reranker fell back on 12/40 pilot cases; hybrid without reranking remains the default.
- Default model concurrency is one; excess concurrent generation receives HTTP 503.
- Public hosting, TLS, SMTP, OIDC provider setup and representative quality targets require operator configuration.

### Fixed

- Upgraded pypdf to 6.21.4 after refreshed CI audits identified parser advisories in the earlier pins.
- Upgraded Next.js and its lint configuration to 16.4.4 after the runtime audit flagged the previous 16.3.8 pin.
