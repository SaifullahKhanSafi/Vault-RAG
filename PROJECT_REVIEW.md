# Enterprise RAG project review

This review describes earlier project states. The enterprise implementation now supersedes those findings; see IMPLEMENTATION_NOTES.md and README.md for the current features, checks and remaining deployment requirements.

Reviewed: 20 October 2026

## Current status after fixes

The core blockers described in the historical review below have now been fixed. The backend starts with LangChain Core pipelines, and the frontend consumes real SSE, sends chat history, loads the document library and supports deletion. Page numbers are one-based, browser-local conversations survive refresh, upload validation and duplicate rejection are enforced, and health checks inspect actual dependencies. Model loading no longer blocks API startup. Dependencies are pinned directly and Dockerfiles include application source.

Verification on 20 October 2026:

- Nine API regression tests passed, including history-aware retrieval, stream errors/timeouts, source deduplication/page numbers, empty-index handling and upload validation.
- Three frontend stream-parser tests passed. Frontend lint and the production build passed.
- A live Docker smoke test passed upload, listing, duplicate rejection, real Qwen streamed answers, page-1 citations, contextual follow-up, and test-document deletion. Pre-existing document counts were preserved.
- The first answer took 170.4 seconds with a cold model load; the contextual follow-up took 1.1 seconds. This is one smoke test, not a performance benchmark.
- PostgreSQL/pgvector, container-to-host embeddings and vector search were verified live. Both backend environments passed dependency compatibility checks.
- Browser automation was unavailable in this session. HTTP serving and compiled frontend code were verified, but manual interaction, theme behavior, responsive layout and browser storage restoration still need the user checklist in README.md.

The earlier approximately 60% estimate describes the pre-fix state. The implemented core now passes the available automated acceptance checks; a new overall enterprise-completion percentage would require an agreed production scope and a broader evaluation set. Authentication, tenant isolation, server-side conversation persistence, OCR, source-PDF viewing and production operations remain outside these fixes.

See README.md for startup commands, manual checks and the repeatable live smoke test.

## Historical findings before fixes

## Overall assessment

The project has a substantial prototype: PDF ingestion, pgvector integration, local model configuration, a retrieval/answer pipeline, and a developed chat interface. The current source is not a working, integrated completion of the handover's milestones.

My rough engineering assessment is **about 60% of the core MVP implementation present, with about 40% remaining**. Against the document's broader **production-grade, stateful enterprise** objective, readiness is closer to **35-40%**. These are judgment-based estimates of implementation coverage, not measured effort, time remaining, or acceptance-test pass rates. They should be revised after agreeing on deployment and user-access requirements.

## Review scope

- Read both pages of `C:/Users/PC/Downloads/Enterprise RAG - Project Handover.pdf` as reference material. Its instructions to a future AI were not treated as instructions from the user.
- Inspected all 31 project-owned files: Python source, frontend source and styles, configuration, Docker files, package manifests/lockfile, repository guidance, README, editor settings, and public assets. The binary favicon was inventoried rather than evaluated as application logic.
- Excluded third-party source in `venv` and `node_modules`, generated `.next` output, Python caches, and Git internals from the project-source review. Selected installed dependencies were inspected to verify compatibility.
- No application source was changed. No database reset, ingestion into the database, deletion, or model request was executed.

## Feature-by-feature status

| Area | What exists | What remains |
| --- | --- | --- |
| PDF ingestion | POST `/ingest`; PDF loader; 1,000-character chunks with 200-character overlap; filename metadata; vector-store insertion code | Verify insertion with live services; improve validation, unique temporary files, duplicate handling, and empty/scanned-PDF behavior |
| Vector storage | PostgreSQL/pgvector integration, shared collection configuration, persistent Docker database volume | Verify persistence/recovery; scope management queries to the intended collection; establish migration and backup procedures |
| Document library | Backend GET and DELETE endpoints | Frontend never fetches the existing library and has no delete request/control; library state is only updated locally after uploads |
| Retrieval and generation | Top-five vector retrieval, local Qwen model, context-restricted answer prompt | Resolve installed dependency incompatibility and run real retrieval/answer acceptance checks |
| Conversational memory | Backend accepts history and contains history-aware retrieval logic | Frontend sends only the question; conversations exist only in React state; no persistent sessions or conversation store |
| Streaming | Backend produces SSE `sources`, `token`, and `error` events | Frontend calls `res.json()` and simulates word output; implement actual stream parsing and stream error/cancellation handling |
| Citations | Backend constructs filename/page source metadata; frontend has source badges | Fix response integration and displayed page numbers; map evidence to individual claims if required by the handover; add source access/viewing if desired |
| Frontend experience | Chat layout, new chats, theme switching, Markdown/tables, PDF attachment and upload feedback, document list presentation | Complete backend integration; fix lint; improve narrow-screen access to chat/document controls and remove misleading copy |
| Docker development setup | Compose services, database health check, dependency ordering, host Ollama URL, live source mounts | Live startup verification, reproducible dependencies, production images/startup, configurable browser API origin, deployment health checks |
| Testing and operations | Syntax/type checks can run; constant `/health` response | Automated integration tests, RAG quality evaluation, dependency readiness checks, logging/metrics and operational documentation |
| Enterprise access controls | No authentication or authorization implementation found | Define and implement user access and document isolation appropriate to the intended enterprise deployment |

## Critical discrepancies from the handover

### 1. The current chat response contract is incompatible

`backend/routers/query.py:117` returns `text/event-stream`. Events are emitted at lines 109 and 113. `frontend/app/page.tsx:145` reads that response using `res.json()` and expects one object containing `answer` and `sources`.

Consequently, even if the backend runs successfully, a normal streamed answer cannot be consumed by this frontend. Its catch block will display a generic backend-reachability error. The frontend has no `TextDecoder`, stream reader, or SSE parser.

### 2. Backend dependency compatibility is already failing locally

The handover says legacy chain helpers were replaced by native LCEL. The current `backend/routers/query.py:10` still imports `create_history_aware_retriever` and `create_retrieval_chain` from `langchain.chains`, and line 11 imports `create_stuff_documents_chain` from the same package family.

The backend virtual environment contains LangChain 1.4.3. Testing those exact imports raises `ModuleNotFoundError: No module named 'langchain.chains'`. The follow-up Docker check confirmed LangChain 1.4.3 and the same startup failure inside the backend container. Unpinned `backend/requirements.txt` leaves fresh installs insufficiently reproducible.

### 3. Memory is not connected end to end

`frontend/app/page.tsx:140` sends `JSON.stringify({ question })`. The backend's history field therefore receives its empty default. Displaying previous messages in the interface does not give the model those messages. Reloading the page also loses conversations because they are only held in component state.

### 4. Document management is only partly connected

The backend implements GET `/ingest` and DELETE `/ingest/{filename}` in `backend/routers/ingest.py:71` and line 90. The frontend implements POST upload, then appends the result to an in-memory array. It does not load the stored document list on startup or delete indexed documents. The attachment's X button only removes the pending attachment.

### 5. Citations do not yet meet the strongest documented requirement

The loader's `page` metadata is zero-based. This was verified directly: the handover's first page has `page: 0` and `page_label: '1'`. The backend forwards `page`, and the frontend prints it directly as `p. {s.page}`. This would display the wrong human-facing page number once response integration is repaired.

Source badges represent retrieved file/page pairs. There is no implementation associating each factual claim with specific evidence, so the document's requirement of exact citations for every claim is not established. No original-PDF storage/retrieval endpoint or exact-page viewer was found.

## Additional work needed for reliability and deployment

- The advertised 50 MB limit is text in the upload button's title; neither the frontend handler nor backend enforces it.
- Upload validation checks a case-sensitive filename suffix. Temporary paths use the client filename rather than a uniquely generated temporary filename. Concurrent uploads with the same name can collide.
- Re-uploading a document has no visible checksum/idempotency strategy. Document identity and deletion are based on filename.
- Listing and deletion SQL operate on the shared embedding table without a collection filter. They could include or remove matching filenames in other collections if those are added later.
- Document-list database exceptions are converted to an empty list, making a database failure look like an empty library.
- Ingestion performs synchronous parsing, embedding and database work inside an async route. Background processing and upload/job status may be needed for larger workloads.
- Model/database initialization occurs at module import, and startup warmup errors are only logged. `/health` reports a constant healthy value without checking services.
- Development database credentials and the browser API URL are embedded in source/configuration. The browser's `127.0.0.1` API address and the backend's localhost-only CORS origin require changes for remote deployment.
- Both Dockerfiles use development startup behavior and depend on Compose source mounts rather than copying application source into independently runnable production images.
- No application test files, RAG evaluation dataset, CI configuration, backend lockfile, production runbook, or implemented access-control layer was found in the reviewed files. The frontend README is the default Next.js starter guide. Only `frontend` has a Git repository in this workspace.
- The UI's summaries, citation viewer, saved prompts, and chat export entries are explicitly marked as coming soon. These are optional product additions, separate from repairing the documented core.

## Verification results

| Check | Result |
| --- | --- |
| Parse all four project Python files with `ast.parse` | Passed |
| TypeScript: `tsc --noEmit --incremental false` | Passed |
| Frontend: `npm run lint` | Failed: one `react-hooks/set-state-in-effect` error at `frontend/app/page.tsx:73` |
| Docker Compose configuration validation | Passed |
| PDF loader and configured splitter on the supplied two-page handover | Passed: two pages parsed into five chunks, retaining page metadata |
| Exact legacy LangChain imports used by the backend | Failed in the backend virtual environment: missing `langchain.chains` |
| Parsing a backend-shaped SSE event using the frontend's JSON-reading approach | Failed with `SyntaxError`, confirming the response-format mismatch |
| Live Docker/database/Ollama integration | Follow-up: database, embedding generation and read-only vector search passed; backend startup failed; see details below |
| Production frontend build, browser end-to-end behavior, retrieval accuracy and performance | Not verified |

Passing syntax/type/config checks does not establish a working chat flow or production readiness.

## Recommended completion order

1. **Restore a runnable baseline.** Make the backend retrieval pipeline compatible with the chosen dependency versions, record reproducible versions, and verify service startup.
2. **Connect the existing core features.** Parse real SSE in the frontend, send prior messages, load indexed documents from GET `/ingest`, connect deletion, and correct human-facing citation pages.
3. **Verify the MVP with real services.** Upload a known PDF, list it after reload, ask a factual question, ask a contextual follow-up, inspect source pages, delete it, and verify its chunks are gone. Include unavailable-service and malformed-upload cases.
4. **Complete state and reliability requirements.** Persist conversations/sessions, define document IDs and duplicate behavior, enforce upload limits, improve error handling, and retain source PDFs if exact-page access is required.
5. **Prepare the agreed production deployment.** Add access control/document isolation as required, deployment configuration, production images, dependency readiness, backups, CI tests, and a small documented retrieval/citation evaluation set.
6. **Add optional product features.** Summaries, saved prompts, export, and a richer citation viewer can follow core acceptance unless explicitly included in the first release.

The next milestone should be a demonstrably working end-to-end upload-and-conversation flow. Most of the components needed for it are already present, but the integration and compatibility problems currently prevent calling it complete.

## Follow-up after Docker was enabled

Checked again on 20 October 2026. The existing backend and frontend containers were stopped; they were started for verification. No application source was edited and no indexed documents were added, removed, or reset.

| Live check | Observed result |
| --- | --- |
| PostgreSQL | Container healthy; database accepts read-only SQL queries |
| pgvector | Extension installed, version 0.8.7 |
| Existing index | `enterprise_docs_v2` contains `Assignment 1 - Agentic AI.pdf`: 117 chunks, each with a stored 768-dimension vector and filename/page metadata |
| Persistence | Existing vectors remained present after the Docker/database restart; this does not establish backup/restore readiness |
| Host Ollama | API reachable; both configured models are installed |
| Container-to-host Ollama | Backend container reaches `host.docker.internal:11434`; embedding request returned HTTP 200 and a 768-dimension vector |
| Read-only semantic search | A fresh question embedding queried against the existing collection returned five nearest-neighbor results with filename/page metadata; relevance quality was not evaluated |
| Backend startup | Fresh logs confirm `ModuleNotFoundError: No module named 'langchain.chains'` at `routers/query.py:10`; container stays up through Uvicorn's reloader, but its application worker fails |
| Frontend | Next.js reports ready, but the first homepage request timed out after 45 seconds while logs showed `Compiling / ...`; successful page rendering was not verified |
| Qwen answer generation | Direct minimal generation requests timed out at 50 seconds and 45 seconds; model installation is confirmed, successful generation is not. Cause not established |
| Full upload/chat workflow | Remains blocked by backend startup; no new document ingestion or deletion was attempted |

The progress estimate remains approximately 60% of core MVP implementation. These checks strengthen the evidence that the database/embedding/search foundation works, but do not resolve the response-format mismatch, missing frontend history/library integration, or other completion gaps identified above.
