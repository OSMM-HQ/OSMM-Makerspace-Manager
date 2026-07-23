#!/usr/bin/env bash
# Apply the newest fully-published Space Works release to a production Compose stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.prod.yml)
LOCK_DIR="$ROOT/.spaceworks-update.lock"
VERSION_FILE="$ROOT/.spaceworks-version"
RELEASE_API="https://api.github.com/repos/SpaceWorks-HQ/SpaceWorks/releases/latest"

say() { printf '[Space Works updater] %s\n' "$*"; }
die() { printf '[Space Works updater] ERROR: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is not installed."
command -v curl >/dev/null 2>&1 || die "curl is required to check GitHub releases."

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  sleep 1
  lock_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ "$lock_pid" =~ ^[0-9]+$ ]] && kill -0 "$lock_pid" 2>/dev/null; then
    say "Another update is already running; skipping."
    exit 0
  fi
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || die "Could not clear a stale update lock."
  mkdir "$LOCK_DIR"
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
trap 'rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

release_json="$(curl --fail --silent --show-error --location \
  --header 'Accept: application/vnd.github+json' \
  --header 'User-Agent: spaceworks-self-host-updater' \
  "$RELEASE_API")"
tag="$(printf '%s' "$release_json" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
version="${tag#v}"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-main\.[0-9]+\.[0-9a-f]{12}$ ]]; then
  die "GitHub latest release returned an unexpected tag: ${tag:-<empty>}"
fi

current=""
if [[ -f "$VERSION_FILE" ]]; then
  current="$(tr -d '[:space:]' < "$VERSION_FILE")"
fi
if [[ "$current" == "$version" ]]; then
  say "$version is already installed."
  exit 0
fi

say "Updating ${current:-untracked installation} to $version."
export MAKERSPACE_IMAGE_TAG="$version"

mkdir -p "$ROOT/backups"
"${COMPOSE[@]}" up -d --wait db
backup_name="pre-update-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
say "Creating database backup backups/$backup_name."
"${COMPOSE[@]}" exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip -c > "/backups/'"$backup_name"'"'
"${COMPOSE[@]}" exec -T db test -s "/backups/$backup_name" \
  || die "Database backup was not created; update cancelled."

say "Pulling immutable release images."
"${COMPOSE[@]}" pull migrate backend worker beat frontend

say "Running migrations and replacing application containers."
"${COMPOSE[@]}" up -d

ready=0
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T backend python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/readiness/', timeout=3).read()" \
    >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 3
done
[[ "$ready" == 1 ]] || die "Release $version did not become ready. The backup is backups/$backup_name."

printf '%s\n' "$version" > "$VERSION_FILE"
find "$ROOT/backups" -maxdepth 1 -type f -name 'pre-update-*.sql.gz' -mtime +14 -delete
say "Update complete: $version."
