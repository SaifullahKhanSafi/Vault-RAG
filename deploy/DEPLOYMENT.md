# Docker VPS deployment

The project implements continuous delivery with manual SSH promotion. Feature branches receive CI checks and preview packages. A version tag reachable from the repository's default branch runs the full CI suite, publishes GHCR application images and creates a GitHub release. The Deploy workflow promotes an existing release to a configured `staging` or `production` environment.

No repository remote, VPS, DNS, TLS certificate or GitHub environment has been configured locally. Push the feature branch yourself, open a PR and configure the settings below. Workflows can be reviewed before any deployment credentials are supplied.

## Pipeline and branch policy

| Event | Result |
| --- | --- |
| Push to any branch, including `feature/*` | Version checks, unit/browser tests, runtime dependency audits, fresh-database integration, container builds and preview archives |
| Pull request | Same checks, read-only repository token, no deployment secrets |
| Push `vVERSION` tag | Requires matching versions/changelog and default-branch ancestry; reruns CI, then publishes images and release archives |
| Manual Deploy from default branch | Downloads a published release, verifies hashes/commit/image references and deploys over SSH using environment secrets |

In repository rules, require the **Required checks** job before merging the default branch. Protect `v*` release tags, disallow force pushes and require PR review for workflow/deployment changes. Configure environment branch restrictions to the default branch and reviewers where your GitHub plan supports them. See [GitHub environment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

GitHub only offers manual workflow dispatch once the workflow exists on the default branch. Your first feature push still starts CI automatically. Feature branches do not publish application images or deploy to the VPS.

## Versioning and publishing

`VERSION` is authoritative. `backend/VERSION`, frontend package metadata/lockfile and the API version must match it. SQL migration numbers are independent.

```powershell
python tools/version.py --check
python tools/version.py --set 0.2.0
# Add a matching CHANGELOG.md entry, then commit the changed version files.
```

After the feature PR is merged and checks pass on the default branch:

```powershell
git tag -a v0.2.0 -m "Enterprise RAG 0.2.0"
git push origin v0.2.0
```

Use the actual value in `VERSION`; the initial packaging baseline is `0.1.0`. Semantic prereleases such as `0.2.0-rc.1` produce prereleases in GitHub. Build metadata `+...` is mapped to `_...` only in Docker tags. Existing releases should never be rewritten; publish another version.

The Release workflow publishes:

- `ghcr.io/<owner>/<repository>/backend:<version>` for API, migrator, ingestion worker and mailer.
- `ghcr.io/<owner>/<repository>/frontend:<version>` with the browser API URL built as `/api`.
- Commit SHA tags plus BuildKit provenance and SBOM attestations in GHCR.
- `enterprise-rag-<version>-source.tar.gz`, an allowlisted source archive.
- `enterprise-rag-<version>-deploy.tar.gz`, configuration/operator tools with immutable application image digests.
- `release.json` with version, source commit, architecture and image references, plus `SHA256SUMS`.

Application images currently target **Linux amd64**. The backend includes English Tesseract OCR and Poppler. Models, user PDFs, database contents, credentials and private benchmark output are excluded. Database/gateway/monitoring images retain the tags in Compose; digest pinning here covers the published application images.

GHCR publishing uses the workflow's `GITHUB_TOKEN` with `packages: write`. Allow GitHub Actions to publish repository-linked packages and check package access settings. A private registry requires a read-only package token on the VPS, configured with `docker login ghcr.io`; the workflow does not send registry credentials over SSH. [GitHub's publishing guide](https://docs.github.com/en/actions/use-cases-and-examples/publishing-packages/publishing-docker-images) describes registry permissions.

## Prepare the VPS once

Use a Linux amd64 host with Docker Engine, the Compose plugin, Python 3, Bash, `flock`, GNU tar/coreutils and outbound GHCR access. The SSH account needs access to Docker and ownership of the application directory. Docker access grants broad host privileges; use a dedicated deployment account and key.

1. Install Ollama or configure an accessible private model server. Pull `qwen2.5:7b-instruct` and `nomic-embed-text`. For host Ollama on Linux, make it reachable from the Docker bridge, set `OLLAMA_BASE_URL` accordingly, and firewall it from the public Internet. `host.docker.internal` is mapped to the host gateway in Compose; an Ollama listener restricted to host loopback is not reachable through that address.
2. Prepare `/opt/enterprise-rag-staging` or `/opt/enterprise-rag-production`, owned by the deployment account. Use separate directories, Compose projects and gateway ports if both environments share a host.
3. Download the published deployment archive and its checksum manifest, verify its SHA256 and unpack it into a temporary `bootstrap/` directory inside the application directory. Review its `release.json` and `deploy/compose.release.yaml`.
4. In the application directory, copy `bootstrap/tools/setup_env.py` to `tools/setup_env.py`, and `bootstrap/deploy/production.env.example` to `.env.production` for a **new installation only**. Run `python3 tools/setup_env.py --production`. This creates credentials and `.secrets.production/metrics_token` without printing secrets.
5. Edit `.env.production`: set the real HTTPS `PUBLIC_ORIGIN`, administrator email, model URL and SMTP/OIDC settings as needed. Use `GATEWAY_PORT=8081` for staging if production uses the default port 8080 on the same host. Retain existing credentials on upgrades.
6. Configure an HTTPS ingress on the host to proxy your domain to `127.0.0.1:<GATEWAY_PORT>`. Secure browser cookies are enabled. Public traffic must use the configured HTTPS origin.
7. If images are private, authenticate Docker to GHCR using a token limited to reading the required packages. Keep this credential on the host.

The Compose stack binds its gateway to localhost. PostgreSQL, the API and model services must not be directly exposed publicly. Production self-registration defaults to disabled; enable it deliberately after SMTP verification/recovery mail is working. OIDC MFA is enforced by your configured identity provider.

## GitHub environment settings

Create `staging` and `production` under repository **Settings → Environments** as needed. Configure these environment secrets, rather than placing credentials in the repository:

| Secret | Value |
| --- | --- |
| `SSH_HOST` | VPS DNS name or IPv4 address |
| `SSH_USER` | Dedicated Linux deployment username |
| `SSH_PRIVATE_KEY` | Matching OpenSSH private key, with permission to access the host |
| `SSH_KNOWN_HOSTS` | Trusted OpenSSH known-hosts entry; verify the fingerprint through the VPS console or another trusted channel |

Optional environment variables:

| Variable | Default |
| --- | --- |
| `SSH_PORT` | `22` |
| `DEPLOY_PATH` | `/opt/enterprise-rag-<environment>`; must be a canonical path under `/opt/` or `/srv/` |

The deployment workflow pins the SSH host key and fails if it changes. For a nonstandard port the known-hosts entry must match `[host]:port`. It currently accepts DNS names/IPv4 addresses; use a DNS name for an IPv6-only host.

## Deploy and verify

After Release succeeds, open **Actions → Deploy → Run workflow**, choose the default branch, enter `vVERSION` and select the environment.

The job verifies the downloaded bundle against its external/internal checksums and checks its source commit, version, archive paths and digest-pinned image references. On the host it:

1. Acquires a deployment lock and verifies the transferred archive hash.
2. Retains the release in `releases/<version>/`, then pulls images before stopping application services.
3. Stops application writers and saves paired database/original-file backups under `backups/` with SHA256 checksums.
4. Runs Compose; successful migrations are required before API/worker startup.
5. Checks frontend HTTP serving, gateway API version and readiness for database, worker and installed models.
6. Updates `current` only after verification passes. Previous releases and backups remain available.

Deployment has a brief maintenance window; it is not a zero-downtime blue/green rollout. Default model concurrency is one. Readiness checks model installation/reachability, not the quality of generated answers or a guaranteed warm model. Run a permitted document question after deployment and inspect its citation.

No live deployment is complete until the actual VPS workflow and public HTTPS login have passed. Application logs, environment secrets and backup contents should remain on the host rather than being pasted into public CI logs.

## Failure recovery and rollback

Image-pull failure occurs before application shutdown. After shutdown, a migration/startup/readiness failure leaves the deployment failed and preserves backups and release files; the script does not automatically reverse database migrations or restart an older application against an unknown schema. Inspect the host with the release's Compose configuration and private environment files.

For an application rollback, verify that the previous release is compatible with the current database schema, then run Deploy with its existing tag. A database rollback requires a reviewed restore of **both** the paired database dump and originals into a recovery environment first. Never restore blindly over a live database or delete Compose volumes as a restart procedure.

Backups are `database.dump` (PostgreSQL custom format), `originals.tar.gz` and `SHA256SUMS`. They are retained locally, not encrypted/uploaded off-host by this workflow. Configure encrypted off-host storage, retention and restore drills for your environment. The earlier `tools/ops.py` backup format and these deployment backups are separate formats; follow the corresponding recovery procedure.

## Packaging locally

Install backend dependencies into your local virtual environment, then:

```powershell
.\backend\venv\Scripts\python.exe tools/package_release.py --output dist/preview
.\backend\venv\Scripts\python.exe tools/verify_release.py dist/preview
```

Add `--check-compose` to validate the packaged Compose configuration with its credential-free template. This check requires the Docker Compose CLI and does not read your private environment files or start containers.

A local/feature preview has `deployable: false`. Only a release bundle supplied with both image digests passes `--require-deployable`. Package creation uses an explicit source allowlist rather than archiving your working directory, and never reads `.env`. Existing packages are preserved. Identical inputs with the same `SOURCE_DATE_EPOCH` produce identical source/deploy archive bytes.
