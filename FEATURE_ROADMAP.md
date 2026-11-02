# Recommended next improvements

Delivery follow-up: feature-branch CI, package/version checks, browser regressions, GHCR releases and a manual Docker VPS promotion workflow are implemented in `.github/workflows/`. See [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md) for the repository/environment setup still required before remote execution.

Local completion was reviewed on 3 November 2026; see [docs/DELIVERY_VALIDATION.md](docs/DELIVERY_VALIDATION.md) for verified results, current dependency findings and how to repeat the checks. The research list below records earlier priorities; identity, English OCR, document permissions and tracing have since been implemented as described in `OPEN_SOURCE_FEATURES.md`.

Research checked on 21 October 2026. This file preserves the original priorities. Implemented follow-up work and exact verification steps are now in [OPEN_SOURCE_FEATURES.md](OPEN_SOURCE_FEATURES.md): verification/recovery/invitations, optional Keycloak SSO/MFA, real-document evaluation tooling, OCR/tables, document ACLs, a local folder connector, tracing and chat tools. Microsoft source synchronization, a human-reviewed business dataset, and a dedicated cross-encoder benchmark remain future work. Keep PostgreSQL/pgvector and the current hybrid retrieval until representative measurements justify a change.

Benchmarking follow-up: [BENCHMARKING.md](BENCHMARKING.md) now covers four retrieval configurations, actual post-rerank context metrics, citations, OCR/tables, real-generation load, optional local claim judging and human calibration. [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) records the completed forty-question synthetic pilot. A representative human-reviewed business dataset remains necessary.

## Current changes

- Public local registration with validation, salted password hashes, per-address registration limits, duplicate handling and an atomic private-workspace creation transaction.
- Existing reader/editor accounts can sign in; membership controls what they can access. New accounts administer their own workspace only and do not join any existing workspace automatically.
- Redesigned responsive sign-in/sign-up page with password visibility and clear success/error feedback. Chat code is loaded separately after sign-in.
- Desktop sidebars support pointer dragging, keyboard resizing, collapse/expand, reset and per-account browser preferences. Mobile retains its existing document overlay.
- Production registration defaults to disabled. New self-registered accounts now require an email verification link; local mail is captured by Mailpit.

## Recommended order

| Priority | Feature | Value for this project | Acceptance check |
| --- | --- | --- | --- |
| 1 | Verified email, invitation links, password reset, then OIDC SSO/MFA | Completes account onboarding and recovery; reduces reliance on administrators distributing passwords | Single-use expiring tokens; replay denied; verified ownership before joining a team; old sessions revoked after reset |
| 2 | Real-document evaluation and evidence checks | Extends the existing synthetic evaluation with realistic retrieval and answer quality measurements | Human-reviewed questions, unanswerable cases, citation correctness and groundedness; compare retrieval quality and latency before release |
| 3 | OCR and structured document parsing | Handles scanned PDFs, tables and multi-column pages missed by basic text extraction; later add DOCX/PPTX | Evaluate page/table extraction on representative fixtures; preserve page references and original files; keep OCR inside the background worker |
| 4 | Document-level permissions and adversarial ingestion tests | Extends workspace isolation where teams need restricted documents; increases coverage of poisoned source content | Permission filters applied before retrieval, cache lookup, excerpts and file downloads; test revoked access and injected instructions |
| 5 | SharePoint/OneDrive connector, then other sources | Replaces repeated manual uploading with incremental document updates | Track create/update/delete and permission changes; retry safely; remove stale searchable content; keep source provenance |
| 6 | Distributed traces and service objectives | Explains whether delays come from retrieval, Ollama, the queue or the network | Correlate request/job IDs across services; monitor first-token latency, job age and failure rates without recording secrets or document bodies |
| 7 | Measured search tuning and user workflow improvements | Builds on current hybrid retrieval and reranking | Compare chunk boundaries and a dedicated reranker on the real evaluation set; add search-in-chat, pinned chats and Markdown/PDF exports based on usage |

## Sources and implications

1. [OWASP email validation and verification](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html) distinguishes syntactic validation from proving control of an address. Our current registration only performs the former. [OWASP MFA guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html) informs the later identity work.
2. [Ragas evaluation metrics](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/) separates retrieval precision/recall from answer faithfulness. Use these as evaluation dimensions alongside human review, not as a claim of production accuracy.
3. [Docling technical report](https://arxiv.org/abs/2501.17887) describes layout and table structure extraction. Its [OCR/table CLI options](https://docling-project.github.io/docling/reference/cli/) provide a concrete candidate to benchmark locally. Benchmark resource use before adoption.
4. [OWASP RAG Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html) covers threats across ingestion, retrieval and generation. Expand the existing injection and isolation tests rather than assuming prompts alone are sufficient.
5. [Microsoft Graph delta queries](https://learn.microsoft.com/graph/delta-query-overview) support incremental create/update/delete synchronization. Connector implementation must also preserve source permissions and handle expired sync state.
6. [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/) covers traces, metrics and logs. Tracing would complement the existing metrics and request logging.

## Verification of this change

Run backend unit tests and `tools/test_registration.py` against the live stack. The registration script creates isolated test accounts/workspaces and checks duplicate rejection, password length, private workspace isolation, reader login and denied administration. It leaves its generated test records for inspection.

Frontend checks: lint, TypeScript, stream parser tests and optimized Docker build. Browser verification covers form registration/sign-in, both pointer drag handles, keyboard collapse, expand, reload persistence and mobile overflow. These checks do not certify overall enterprise readiness or a complete accessibility audit.
