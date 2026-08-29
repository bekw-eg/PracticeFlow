#!/usr/bin/env sh
set -eu

# Backward-compatible entrypoint: the historical "backup-postgres" command now
# creates a complete PracticeFlow backup bundle (PostgreSQL + backend_storage).
output_directory="${1:-./backups}"
compose_file="${COMPOSE_FILE:-docker-compose.prod.yml}"
env_file="${ENV_FILE:-.env.production}"
project_name="${COMPOSE_PROJECT_NAME:-}"

if [ ! -f "$compose_file" ]; then
  echo "Compose file does not exist: $compose_file" >&2
  exit 1
fi

compose() {
  if [ -n "$project_name" ] && [ -f "$env_file" ]; then
    docker compose --project-name "$project_name" --env-file "$env_file" -f "$compose_file" "$@"
  elif [ -n "$project_name" ]; then
    docker compose --project-name "$project_name" -f "$compose_file" "$@"
  elif [ -f "$env_file" ]; then
    docker compose --env-file "$env_file" -f "$compose_file" "$@"
  else
    docker compose -f "$compose_file" "$@"
  fi
}

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

mkdir -p "$output_directory"
resolved_output="$(cd "$output_directory" && pwd)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
bundle_name="practiceflow-backup-$stamp"
staging_directory="$resolved_output/.${bundle_name}.incomplete"
bundle_directory="$resolved_output/$bundle_name"
database_file="database.dump"
storage_file="backend-storage.tar.gz"
manifest_file="manifest.json"
database_container_path="/tmp/$database_file"
helper_id=""
backend_was_running=false
completed=false

cleanup() {
  if [ -n "$helper_id" ]; then
    docker rm -f "$helper_id" >/dev/null 2>&1 || true
  fi
  if [ "$backend_was_running" = true ]; then
    compose up -d backend >/dev/null || echo "WARNING: backup succeeded but backend restart failed; start it manually." >&2
  fi
  if [ "$completed" = false ] && [ -d "$staging_directory" ]; then
    echo "Backup did not complete. Preserving diagnostic artifacts in $staging_directory" >&2
  fi
}
trap cleanup EXIT INT TERM

if [ -e "$staging_directory" ] || [ -e "$bundle_directory" ]; then
  echo "Backup destination already exists: $bundle_directory" >&2
  exit 1
fi
mkdir "$staging_directory"

backend_id="$(compose ps -q backend || true)"
if [ -n "$backend_id" ] && [ "$(docker inspect -f '{{.State.Running}}' "$backend_id")" = "true" ]; then
  backend_was_running=true
  echo "Stopping backend briefly to create a consistent database + file-storage snapshot..."
  compose stop backend
fi

echo "Creating PostgreSQL dump..."
compose exec -T postgres sh -eu -c 'exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --compress=9 --file=/tmp/database.dump'
compose cp "postgres:$database_container_path" "$staging_directory/$database_file"
test -s "$staging_directory/$database_file"

echo "Archiving persistent backend storage..."
helper_id="$(compose run -d --no-deps --entrypoint sh backend -c 'sleep 300')"
docker exec "$helper_id" sh -eu -c "tar -C /app/storage_data --numeric-owner -czf /tmp/$storage_file ."
docker cp "$helper_id:/tmp/$storage_file" "$staging_directory/$storage_file"
test -s "$staging_directory/$storage_file"

database_sha256="$(sha256 "$staging_directory/$database_file")"
storage_sha256="$(sha256 "$staging_directory/$storage_file")"
database_size="$(wc -c < "$staging_directory/$database_file" | tr -d '[:space:]')"
storage_size="$(wc -c < "$staging_directory/$storage_file" | tr -d '[:space:]')"

cat > "$staging_directory/$manifest_file" <<EOF
{
  "format_version": 1,
  "created_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "consistency": "backend service was stopped while PostgreSQL and backend_storage artifacts were captured",
  "artifacts": [
    {"name": "$database_file", "sha256": "$database_sha256", "size_bytes": $database_size},
    {"name": "$storage_file", "sha256": "$storage_sha256", "size_bytes": $storage_size}
  ]
}
EOF

manifest_sha256="$(sha256 "$staging_directory/$manifest_file")"
printf '%s  %s\n' "$manifest_sha256" "$manifest_file" > "$staging_directory/manifest.sha256"

mv "$staging_directory" "$bundle_directory"
completed=true
printf 'Complete backup bundle written to %s\n' "$bundle_directory"
