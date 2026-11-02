# Open-source features and verification

The application changes use open-source libraries and local services. SharePoint and OneDrive are proprietary hosted products; this change does not connect to a Microsoft tenant. An operator-run folder connector is included as a local alternative. No paid API is required for the local features. Hosting, SMTP delivery and organizational identity-provider setup are separate operational choices.

## Start and open the services

```powershell
cd D:\RAG
python tools/setup_env.py
docker compose up -d --build
docker compose ps
```

Docker starts the web app, API, ingestion worker, database, mail dispatcher, Mailpit and Jaeger. No separate `npm run dev` is needed. Keep Ollama running with the configured models installed.

| Service | Address | Purpose |
| --- | --- | --- |
| Application | http://localhost:3000 | Accounts, documents, chat and settings |
| Mailpit | http://localhost:8025 | Local inbox for verification, recovery and invitation messages |
| Jaeger | http://localhost:16686 | API/retrieval/worker traces |
| API health | http://localhost:8000/health | Database, model and worker readiness |
| Optional Keycloak | http://localhost:8081 | Organization identity provider and authenticator-app MFA |

The local inbox captures messages instead of delivering to real email addresses. Its contents contain account action links; keep it bound to localhost. Production uses explicitly configured SMTP with STARTTLS and credentials. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD` and the actual `PUBLIC_ORIGIN` before enabling public registration. Mail failures retry through the database outbox, up to eight attempts.

## Verify accounts, recover passwords, and invite a team

1. Create an account. Sign-in is blocked until verification.
2. Open Mailpit, choose the verification message, and open its link. Click **Confirm**, then sign in.
3. To recover a password, enter the account email on the sign-in form and choose **Forgot password?**. Open the recovery email, set a new password, and confirm. Existing application sessions are revoked.
4. **Resend verification** issues a replacement link. Verification and recovery links expire after 30 minutes, are stored as hashes, and can be used once.
5. As a workspace administrator, open Settings and use **Invite by email**, selecting reader or editor. Invitations expire after 48 hours. Recipients register/verify if needed, sign in with the matching email, then open and confirm the invitation link.

Pre-existing accounts remain approved during migration. Administrator-provisioned accounts are explicitly approved by their administrator and retain the existing workflow. Self-registration always requires verification. An email invitation never silently upgrades an existing membership and cannot be accepted by another email address. MFA is provided by optional Keycloak, not by the password-only local form.

## Document permissions

An administrator can choose **Manage access** on a document and restrict it to selected workspace members. Administrators and the original uploader retain access; removal from the workspace removes that user's document access as well. This is a read-access restriction: an allowed reader remains a reader and cannot edit/upload.

Check in separate browser profiles: grant a reader access, open the PDF, revoke access, then refresh. The document should disappear from its library/jobs/search and its file/version endpoints should deny access. PostgreSQL restrictive row policies cover documents, versions, chunks and jobs. Saved answers citing revoked/deleted documents are redacted when fetched/exported and excluded from model history/replay. Data already downloaded or displayed before revocation cannot be recalled; an answer already streaming is not retroactively erased.

## OCR, tables, and retrieval tuning

Upload an image-only scanned PDF with readable English text. The worker renders only pages needing OCR and runs Tesseract. Original physical page numbers are retained in citations. PDFs with ruled text tables also include rows with cell boundaries in the indexed text.

- Default OCR limit: 50 raster pages per document. Change `OCR_MAX_PAGES` if your hardware allows it.
- `OCR_ENABLED=false` disables fallback; additional OCR languages require their Tesseract language packages in the image.
- Per-page render/recognition timeouts and existing size/text/page limits bound the work.
- `CHUNK_SIZE` defaults to 1000 characters; `CHUNK_OVERLAP` defaults to 200. Changes affect newly indexed versions. Evaluate before reindexing existing documents.

This parser supports PDFs. It does not claim general handwriting recognition, perfect table understanding, or DOCX/PPTX ingestion. pdfplumber/Tesseract are used instead of adding a second large model runtime.

## Evaluate your own documents

Copy `evals/real-documents.example.json` to your own dataset and replace the placeholders with human-reviewed questions, expected filenames, physical pages and facts from your documents. Include unsupported questions. Find the workspace UUID through `/workspaces` in the API docs after signing in via the app, or through the browser Network tab's workspace requests.

```powershell
.\backend\venv\Scripts\python.exe tools/evaluate_documents.py --dataset evals/real-documents.example.json --validate-only
.\backend\venv\Scripts\python.exe tools/evaluate_documents.py --workspace YOUR_WORKSPACE_UUID --dataset evals/your-reviewed-dataset.json
```

Compare `--method vector`, the default hybrid method, and `--rerank`. Add `--judge` for an advisory local Ollama groundedness check. Output includes retrieval recall against expected pages, citation recall, expected-fact checks, abstention, timings and optional unsupported-claim judgments. Default gate: 90 percent of cases pass; set a threshold appropriate to your domain. Phrase/reference checks and an LLM judge do not prove factual correctness. No human-reviewed business benchmark can be fabricated from repository fixtures.

The existing `tools/evaluate.py` remains the synthetic seed evaluation. Ragas informed the metric categories; the runner uses the project's local APIs/Ollama and does not install Ragas or call a paid evaluator.

## Local folder connector

Create a dedicated workspace for the source folder and restrict its memberships appropriately. The selected directory's top-level PDF files are uploaded incrementally; content hashes detect changes. Checkpoints live in `storage/connectors/`. Re-running queues new versions for changed files and skips unchanged files.

```powershell
.\backend\venv\Scripts\python.exe tools/sync_folder.py --folder D:\RAG\imports --workspace YOUR_WORKSPACE_UUID
```

The directory must exist. Only connector-managed documents can be trashed by adding `--apply-deletions`; deletion propagation is opt-in. The script queues at most eight changed files per run to respect the API budget. Run it again after a minute for another batch. To schedule it, use Windows Task Scheduler after checking a manual run. Use `--email` with `RAG_SYNC_PASSWORD` for another workspace administrator; otherwise it reads the private local bootstrap test configuration. Source filesystem permissions are not copied, so this is not a SharePoint permission synchronization service. Do not run overlapping syncs for the same folder/workspace. Reverting to an older already-uploaded checksum requires an explicit document-version restore workflow; it is not silently treated as a new upload.

## SSO and authenticator-app MFA with Keycloak

The provider is optional because it consumes additional memory. For local testing:

```powershell
docker compose --profile sso up -d keycloak
```

Open http://localhost:8081 and sign into its administrator console with username `admin` and `KEYCLOAK_ADMIN_PASSWORD` from your private `.env`. In realm **rag**, create a test user, set its password, populate its email/name, and explicitly verify/approve the email through your identity-provider process. The imported realm requests authenticator-app setup. Do not use the initial application's administrator email for the new SSO test account.

Add these values to `.env`, then recreate the backend:

```dotenv
OIDC_ISSUER=http://localhost:8081/realms/rag
OIDC_INTERNAL_ISSUER=http://keycloak:8080/realms/rag
OIDC_CLIENT_ID=rag-web
COMPOSE_PROFILES=sso
```

```powershell
docker compose up -d backend
```

The login page now offers **Continue with organization SSO**. Sign in and complete the provider's authenticator setup. OIDC uses authorization code + PKCE with state, nonce, signature, issuer and audience validation. Identities bind to issuer/subject; a matching email never silently merges with an existing local account. Existing local accounts keep their original sign-in method. Local app logout ends its session; global provider logout and provider-side user disable/session events are separate from the app's eight-hour session lifecycle. Production needs a supported HTTPS identity-provider deployment, its own client, approved redirect URI and MFA policy; the bundled development realm is not a public production deployment.

SSO-created accounts cannot use the local password login or local recovery path, so email recovery cannot bypass provider MFA. Recover those accounts through the organization identity provider.

Remove the OIDC values and recreate the backend to disable the button. Stop the optional provider with `docker compose --profile sso stop keycloak` when unused.

## Traces, service objectives, and chat tools

In Jaeger choose `rag-api` or `rag-worker`. API responses include `X-Trace-ID`; traces include request correlation and retrieval/ingestion spans without document bodies or passwords. The local trace store is in-memory and resets on restart. Production can set `OTEL_EXPORTER_OTLP_ENDPOINT` to its collector. Prometheus rules include proposed HTTP availability and first-token latency targets; these are configurable proposals, not measured guarantees. Existing alerts still require an alert delivery destination.

Upload trace context is persisted with the ingestion job. The worker continues that trace and attaches `job.id`, so the API upload and background ingestion appear together. This cross-process link was checked against the collected Jaeger trace.

Use **Search chats, then Enter** to search your titles and questions. Star a conversation to pin it. Open a chat and choose **Export** for Markdown or **Print / PDF** for the browser's Save as PDF flow. Exports remain private to the conversation author and recheck cited document access.

## Automated checks

```powershell
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\venv\Scripts\python.exe tools/test_registration.py
.\backend\venv\Scripts\python.exe tools/test_enterprise_features.py
.\backend\venv\Scripts\python.exe backend/smoke_test.py --no-generation
```

Live tests create isolated test accounts/workspaces and fixture documents. They preserve existing application content. The enterprise test uses local Mailpit and Windows Arial to generate an image-only fixture. Run the registration/account tests sequentially to respect shared rate limits.

If rapid reruns receive HTTP 429, wait one minute before retrying. The tests exercise the normal rate limits rather than disabling them.

Validated locally: 13 backend unit tests, 3 frontend stream tests, lint/type checks, optimized frontend image, existing smoke checks, registration and enterprise-feature live checks, folder sync, browser verification/panel/mobile checks, the Keycloak authenticator flow and invalid-state rejection, and the adversarial PDF check. The two-case fixture evaluation also passed; it is not a business accuracy benchmark. The pinned Python lock-file audit reported no known vulnerabilities. Optional Keycloak was stopped after its checks; enable it using the steps above. CI definitions were extended with local mail/registration coverage but have not been run on GitHub from this workspace.

## Components and sources

| Component | Open-source license | Use |
| --- | --- | --- |
| [Mailpit](https://github.com/axllent/mailpit/blob/develop/LICENSE) | MIT | Local mail capture |
| [Authlib](https://github.com/authlib/authlib/blob/main/LICENSE) | BSD-3-Clause | OIDC client validation |
| [Keycloak](https://github.com/keycloak/keycloak/blob/main/LICENSE.txt) | Apache-2.0 | Optional identity provider/MFA |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | OCR |
| [pdfplumber](https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt) | MIT | Structured text/table extraction |
| [Poppler](https://poppler.freedesktop.org/) | GPL-2.0-or-later | PDF page rendering |
| [OpenTelemetry](https://github.com/open-telemetry/opentelemetry-python/blob/main/LICENSE) | Apache-2.0 | Trace SDK/export |
| [Jaeger](https://github.com/jaegertracing/jaeger/blob/main/LICENSE) | Apache-2.0 | Local trace viewer |

Package/image versions are pinned in requirements and Compose. Component license notices remain in their distributions. This work does not assign a new license to your own application source. [Microsoft Graph delta queries](https://learn.microsoft.com/graph/delta-query-overview) remain a future proprietary-service connector option requiring tenant consent and source-permission handling.
