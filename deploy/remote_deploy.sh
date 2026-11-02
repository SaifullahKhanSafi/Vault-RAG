#!/usr/bin/env bash
# Runs on a provisioned Linux Docker host over authenticated SSH. No credentials in argv.
set -Eeuo pipefail
umask 077

root=${1:?deployment directory required}
version=${2:?version required}
expected_sha=${3:?archive checksum required}
environment=${4:?staging or production required}
[[ "$root" =~ ^/(opt|srv)/[A-Za-z0-9_/-]+$ && "$root" != *'/../'* && "$root" != */.. ]] || { echo 'Unsafe deployment directory'; exit 2; }
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([+-][0-9A-Za-z.+-]+)?$ ]] || { echo 'Invalid version'; exit 2; }
[[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || { echo 'Invalid checksum'; exit 2; }
[[ "$environment" == staging || "$environment" == production ]] || { echo 'Invalid environment'; exit 2; }
if [[ "${5:-}" == --dry-run ]]; then
  echo "Plan: verify $root/incoming/$version.tar.gz; preserve backups; deploy rag-$environment; require readiness and version $version."
  exit 0
fi
[[ "$(realpath -m "$root")" == "$root" ]] || { echo 'Deployment directory must be canonical without symlinks'; exit 2; }
[[ -f "$root/.env.production" ]] || { echo 'Provision .env.production first; see deploy/DEPLOYMENT.md'; exit 2; }
[[ ! -e "$root/current" || -L "$root/current" ]] || { echo 'current must be a release symlink'; exit 2; }
chmod 600 "$root/.env.production"
exec 9>"$root/deploy.lock"
flock -n 9 || { echo 'Another deployment is running'; exit 2; }
archive="$root/incoming/$version.tar.gz"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == "$expected_sha" ]] || { echo 'Uploaded archive checksum mismatch'; exit 2; }
release="$root/releases/$version"
mkdir -p "$root/releases" "$root/backups"
chmod 700 "$root/backups"
if [[ -e "$release" ]]; then
  [[ -d "$release" && ! -L "$release" && -f "$release/.archive.sha256" && "$(cat "$release/.archive.sha256")" == "$expected_sha" ]] || { echo 'Existing release differs; refusing overwrite'; exit 2; }
else
  mkdir "$release"
  tar -xzf "$archive" -C "$release" --strip-components=1 --no-same-owner
  printf '%s\n' "$expected_sha" > "$release/.archive.sha256"
fi
export RAG_SECRETS_DIR="$root/.secrets.production"
compose=(docker compose --env-file "$root/.env.production" --env-file "$release/release.env" -p "rag-$environment" -f "$release/deploy/compose.release.yaml")
"${compose[@]}" config --quiet
"${compose[@]}" pull db gateway migrate backend worker mailer frontend
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 db

# Quiesce writes before taking a paired DB/original-file backup. Retain all backups/releases.
"${compose[@]}" stop gateway frontend backend worker mailer
backup="$root/backups/pre-$version-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir "$backup"
trap 'echo "Deployment stopped. Backups and release files retained. Inspect the host before retrying; no database rollback was attempted." >&2' ERR
"${compose[@]}" exec -T db pg_dump -U rag_owner -d rag_db --format=custom > "$backup/database.dump"
"${compose[@]}" run --rm --no-deps -T --entrypoint tar backend -czf - -C /data . > "$backup/originals.tar.gz"
sha256sum "$backup/database.dump" "$backup/originals.tar.gz" > "$backup/SHA256SUMS"

# Compose runs the migrator to completion before API/worker startup. Migration failure blocks rollout.
"${compose[@]}" up -d --no-build --wait --wait-timeout 300
"${compose[@]}" exec -T backend python - "$version" <<'PY'
import json,sys,time,urllib.request
for attempt in range(30):
    try:
        live=json.load(urllib.request.urlopen('http://gateway/api/health/live',timeout=10))
        ready=json.load(urllib.request.urlopen('http://gateway/api/health/ready',timeout=10))
        web=urllib.request.urlopen('http://gateway/',timeout=10)
        assert live['version']==sys.argv[1] and ready['status']=='healthy' and web.status==200
        print('Gateway, frontend, database, worker, installed models and API version verified.')
        break
    except Exception:
        if attempt==29:raise SystemExit('Readiness/version verification failed; inspect the host.')
        time.sleep(3)
PY
link="$root/.current-$$"
ln -s "$release" "$link"
mv -Tf "$link" "$root/current"
trap - ERR
echo "Deployed Enterprise RAG $version to $environment. Previous releases and pre-deploy backups retained."
