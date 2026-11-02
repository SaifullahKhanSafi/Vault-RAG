# Delivery completion record

Reviewed on **3 November 2026**, application version **0.1.0**. This records the CI/CD, packaging, documentation and indexing UI work. The October quality benchmark remains a historical engine baseline; these delivery checks do not rerun or replace it.

## Implemented

| Area | Result |
| --- | --- |
| Feature branches and PRs | CI checks versions, backend/frontend/browser tests, runtime advisories, fresh-database integration, workflow/shell lint, container boundaries and preview packages. `Required checks` aggregates the jobs. |
| Release | Matching `vVERSION` tags reachable from the default branch rerun CI, publish Linux amd64 GHCR images with provenance/SBOM and create checked GitHub release archives. |
| VPS delivery | Manual staging/production promotion uses pinned SSH host keys, application image digests, retained releases, paired pre-migration backups and readiness/version checks. |
| Packaging/versioning | Synchronized version files, changelog checks, deterministic allowlisted source/deployment archives, external/internal SHA256 manifests, tamper/path checks and a preview deployment gate. |
| UI | Accessible indexing bars with real percentages, queue/failure/completion states, contrast-checked light/dark filenames, version/passages metadata and grouped document actions. |
| Documentation | README purpose, architecture, tools, measured benchmark findings/limits, setup, testing, file structure and delivery instructions; public demonstration screenshots and aggregate benchmark data. |
| Repository hygiene | Git and Docker exclusions cover credentials, user PDFs, originals, backups, caches, environments, local reports and generated packages. Lockfiles, migrations, templates and public evidence remain source files. |

The refreshed audits required Next.js/eslint-config-next **16.4.4**, pypdf **6.21.4**, and a compatible transitive Zod update. Runtime audits pass; sixteen moderate development-only lint findings remain tracked in [SECURITY.md](../deploy/SECURITY.md).

## Local validation results

| Check | Result |
| --- | --- |
| Backend units | **29 passed**, including six release/version/package integrity tests; the final stricter SemVer cases also passed the focused release suite. |
| Frontend units | **3 passed** for streamed event parsing, errors and truncated streams. |
| Browser | **5 passed** against the production build: light/dark progress/actions/contrast, queue/failure states, mobile/reader controls and login controls. |
| Static/build | ESLint, TypeScript, optimized frontend build, actionlint and ShellCheck passed. |
| Fresh integration | Smoke, registration and enterprise suites passed against disposable PostgreSQL, API, worker, OCR, SMTP capture and tracing services, using the rebuilt pypdf 6.21.4 image. Existing user data was not used. |
| Production runtime | Both Docker images built; temporary read-only probes passed standalone web HTTP 200 as UID 1000 and two-worker API health/session login as UID 10001. |
| Advisory audits | Python lockfile and npm production graph: zero known findings at validation time. Complete npm graph: sixteen moderate development-only lint findings. |
| Repository hygiene | Eleven private/generated paths ignored and eight required source paths retained in a disposable Git check. Twelve configured secret values were absent from the 136 allowlisted source files. No secret values were printed. |
| Documentation | README preview inspected visually; public Markdown relative file links resolved. |

The live local API was refreshed and returned version 0.1.0 with healthy database, worker and installed models. Checks do not certify enterprise accuracy, eliminate prompt injection, prove sustained load capacity or validate an unconfigured VPS.

## Reproduce the checks

From the project root in VS Code PowerShell, with Python 3.12 and the backend virtual environment installed:

```powershell
.\backend\venv\Scripts\python.exe tools/version.py --check
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\backend\venv\Scripts\python.exe -m pip install pip-audit==2.10.1
.\backend\venv\Scripts\python.exe -m pip_audit -r backend/requirements.lock

cd frontend
npm.cmd ci
npm.cmd run lint
npm.cmd test
npm.cmd audit --omit=dev --audit-level=high
npm.cmd run build
npm.cmd run typecheck
npx.cmd playwright install chromium
npm.cmd run test:e2e
cd ..

# Choose a new output directory for each preview; existing bundles are preserved.
.\backend\venv\Scripts\python.exe tools/package_release.py --output dist/my-review
.\backend\venv\Scripts\python.exe tools/verify_release.py dist/my-review --check-compose
```

The CI integration job uses fresh PostgreSQL, Mailpit, Jaeger and an Ollama protocol double, and runs the smoke, registration and enterprise suites. Its OCR test processes a real raster-only PDF. It checks application behavior and isolation, not language-model quality. To test against your running development stack instead, follow the live integration commands and rate-window cooldown in [README.md](../README.md#testing).

For a manual UI check, open `http://localhost:3000`, sign in, and upload a PDF. Watch the indexing bar move from preparation to completion. Check the filename, version/passages and View PDF / Manage access / Upload new version actions in both themes. A replacement version keeps the ready original searchable until publication. Reader accounts do not receive editor/admin actions.

## External activation still required

No GitHub run, GHCR publication or VPS deployment is claimed by local validation. The user will push a feature branch manually; no repository was initialized and no code was pushed here. Configure repository rules and the GitHub `staging`/`production` environments, SSH secrets, private server environment, model access and HTTPS as described in [DEPLOYMENT.md](../deploy/DEPLOYMENT.md).

The first feature push runs CI. After review/merge, push the matching version tag to publish a release, then use **Actions → Deploy → Run workflow** from the default branch to promote it. The remote run and HTTPS login must pass before the hosted deployment can be considered complete.
