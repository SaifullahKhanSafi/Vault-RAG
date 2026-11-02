# Implementation record

Implemented on 20 October 2026, building on the repaired local MVP.

Delivery/UI follow-up on 21 October 2026: added feature-branch/PR CI with browser and release tests, synchronized application version `0.1.0`, allowlisted source/deploy archives, GHCR release publishing, manual environment-based SSH deployment, updated ignore rules and a GitHub-oriented README with public aggregate benchmark findings. Document indexing now uses accessible percentage bars and theme-aware cards/actions. See [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md). Remote workflow execution/publication/deployment remains dependent on the user's repository push and VPS configuration.

Completion review on 3 November 2026: refreshed security pins to Next.js 16.4.4 and pypdf 6.21.4, checked source-archive tamper detection and stricter SemVer, and completed 29 backend tests, 3 frontend tests, 5 browser tests, fresh-container integration and read-only production runtime probes. Runtime advisory audits pass; development-only lint findings remain documented. See [docs/DELIVERY_VALIDATION.md](docs/DELIVERY_VALIDATION.md) for the current results and reproducible checks. Earlier validation counts below are historical.

Follow-up on 21 October 2026: added self-service verification/recovery/invitations, optional Authlib/Keycloak SSO and provider MFA, PDF OCR and table extraction, document-level restrictive row policies with historical answer redaction, reviewed-document evaluation tools, incremental folder sync, OpenTelemetry/Jaeger and chat search/pinning/export. Full setup, limits and verification are in [OPEN_SOURCE_FEATURES.md](OPEN_SOURCE_FEATURES.md). Microsoft service integration remains unconfigured; the new local connector is folder-based. Earlier verification counts below describe the original implementation, not the full follow-up.

Benchmarking follow-up: added the four-configuration PDF benchmark, final-context diagnostics, ingestion extraction records (migration 007), ranking/citation/extraction metrics, private HTML/CSV reports, optional structured local judging, human-review calibration, paired comparisons and a real-generation capacity probe. The completed pilot and current validation are in [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md); repeat instructions are in [BENCHMARKING.md](BENCHMARKING.md). These replace the earlier narrow seed evaluation as the current synthetic baseline, while preserving its historical record below.

## Data preservation

A pre-change PostgreSQL dump and project-source archive were saved in backups/. Migration copied 117 legacy vectors into the application schema while preserving their original tables. The initial administrator/workspace was generated locally. Bootstrap passwords, database passwords, session signing material and metrics tokens are in ignored private environment files, not this document.

## Feature mapping

| Requested area | Implementation |
| --- | --- |
| Database ownership/migrations | Checksum-checked transactional SQL migrations, application tables and legacy import |
| Login and roles | Salted scrypt, opaque revocable HttpOnly sessions, CSRF and origin checks, admin/editor/reader memberships |
| Workspace isolation | Non-owner API database role, PostgreSQL row policies, scoped retrieval, authorized PDF downloads, private conversations |
| Durable document/version storage | Stable IDs, checksums, retained originals, version history, atomic active-version publication |
| Citation viewer | Stored excerpt and original PDF version/page, protected inline viewer; legacy missing originals explicitly flagged |
| Background ingestion | Persistent queue, SKIP LOCKED claims, fenced leases, heartbeats, automatic retries, manual retry, progress |
| Retrieval | Keyword/vector fusion, optional model reranking, filters, repeated-passage suppression |
| Conversation persistence | Server-owned history, messages, cancellation status, idempotent completed request replay |
| Evaluation | Synthetic 20-case seed set and report/gate CLI; does not substitute for representative domain evaluation |
| Capacity/performance | Shared model semaphore, rate/queue limits, load probe, cold-load handling and warmup CLI |
| Observability | Request IDs, structured HTTP logs, stage timings, feedback, audit and operations UI, protected metrics, alert rules |
| Recovery | Database/PDF backup with hashes, scratch-database restore/file-coverage verification |
| Deployment/CI | Non-root images, isolated production Compose/gateway, optional Prometheus, unit/build/integration workflow definitions |

## Validation

The checks below record the earlier implementation milestone. Delivery validation now includes Playwright browser automation, release-package tests and workflow lint; see the delivery completion record linked from README.md. CI definitions cannot be claimed to have run on GitHub without a connected remote workflow execution.

Completed checks:

- Nine backend security/storage unit tests and three frontend SSE parser tests passed.
- Frontend lint, TypeScript and the optimized production build passed, including the patched CSS-parser override.
- Full acceptance checks passed on the clean non-root API/worker images: separate users/workspaces, denied cross-workspace reads/downloads, reader write denial, CSRF/origin checks, queued ingestion, original PDFs, exact duplicate rejection, private server-side chats, completed-request replay without duplicate messages, real Qwen answers/follow-ups, shared administrator feedback counts, version publication, trash/restore, failed jobs/retry, protected metrics and audit events.
- Direct SQL under the restricted API role returned zero cross-workspace chunks and prevented reader document updates.
- All 20 synthetic evaluation cases passed with hybrid retrieval. Three reranking cases also passed. These narrow seed results are not a real-domain accuracy claim.
- The eight-request/four-client capacity probe returned six successes and two controlled 503 busy responses; its empty-workspace workload is not a generation throughput benchmark.
- An expired simulated worker lease was reclaimed, and the job completed at attempt two without duplicate publication.
- A database/original-file backup was restored into a scratch database and file coverage verified; live data was not overwritten.
- Both production images built. Temporary non-root probes passed standalone frontend HTTP serving and a read-only two-worker API's readiness/session flow; temporary containers were removed afterward.
- Retention ran in dry-run mode only; no retained user documents were purged.
- npm runtime audit reported zero vulnerabilities. One upstream development-only lint dependency chain remains flagged without a published patch; see deploy/SECURITY.md.
- Python runtime lockfile auditing reported zero known vulnerabilities. Reports are in output/python-audit.json.
- Final backup restore verified five accounts, 125 retained chunks across all workspaces (including isolated test records), all four migrations, and original-file coverage. The Initial workspace still has its original 117-chunk document.
- Local development uses Webpack after the final check exposed a Turbopack first-compile stall on the Windows bind mount. Production builds and standalone-image serving passed independently.

Original legacy tables still retain all 117 pre-existing vectors. Test workspaces/accounts and their audit records remain for inspection; their test PDFs were moved to trash by the test cleanup.

## Boundaries

This is an implemented, locally tested production foundation. Public TLS/hosting, secret-manager integration, outbound alert delivery, identity-provider configuration, additional OCR languages, representative enterprise quality targets and formal certification depend on additional environment/data choices. English PDF OCR and optional OIDC support were added after this earlier milestone. Original PDFs cannot be reconstructed from the legacy vector index; re-upload their originals as new versions.

Final local frontend check: HTTP 200 after the Webpack switch (14.6 seconds including its first compile). API health was healthy, worker heartbeat was present, and active pending/failed job metrics were zero.

An additional live adversarial-PDF check passed: a document containing an instruction to replace every answer with an override marker still produced the supported approval code and correct page citation. This is one regression case, not proof that prompt injection is eliminated.
