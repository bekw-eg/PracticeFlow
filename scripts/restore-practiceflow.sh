#!/usr/bin/env sh
set -eu

usage() {
  cat >&2 <<'EOF'
Usage: ./scripts/restore-practiceflow.sh <backup-bundle-directory> --confirm-empty-target

Restores a complete PracticeFlow bundle only into an empty PostgreSQL database
and an empty backend_storage volume. The target postgres service must already
be running. The script refuses a database that already has public tables.
EOF
  exit 2
}

backup_directory="${1:-}"
confirmation="${2:-}"
if [ -z "$backup_directory" ] || [ "$confirmation" != "--confirm-empty-target" ]; then
  usage
fi

compose_file="${COMPOSE_FILE:-docker-compose.prod.yml}"
env_file="${ENV_FILE:-.env.production}"
project_name="${COMPOSE_PROJECT_NAME:-}"
manifest_file="$backup_directory/manifest.json"
manifest_checksum_file="$backup_directory/manifest.sha256"
database_file="$backup_directory/database.dump"
storage_file="$backup_directory/backend-storage.tar.gz"
helper_id=""
backend_was_running=false

if [ ! -f "$compose_file" ]; then
  echo "Compose file does not exist: $compose_file" >&2
  exit 1
fi
if [ ! -f "$manifest_file" ] || [ ! -f "$manifest_checksum_file" ] || [ ! -f "$database_file" ] || [ ! -f "$storage_file" ]; then
  echo "Backup bundle is incomplete: expected manifest.json, manifest.sha256, database.dump and backend-storage.tar.gz in $backup_directory" >&2
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

python_command=""
if command -v python3 >/dev/null 2>&1; then
  python_command="python3"
elif command -v python >/dev/null 2>&1; then
  python_command="python"
else
  echo "Python 3 is required to validate manifest.json" >&2
  exit 1
fi

"$python_command" - "$manifest_file" "$manifest_checksum_file" "$backup_directory" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
manifest_checksum_path = pathlib.Path(sys.argv[2])
bundle = pathlib.Path(sys.argv[3])
checksum_parts = manifest_checksum_path.read_text(encoding="utf-8").strip().split()
if len(checksum_parts) != 2 or checksum_parts[1] != "manifest.json":
    raise SystemExit("Invalid manifest.sha256 format")
if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != checksum_parts[0].lower():
    raise SystemExit("Checksum mismatch for manifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if manifest.get("format_version") != 1:
    raise SystemExit("Unsupported backup manifest format")
expected = {item.get("name"): item for item in manifest.get("artifacts", [])}
for name in ("database.dump", "backend-storage.tar.gz"):
    item = expected.get(name)
    path = bundle / name
    if not item or not isinstance(item.get("sha256"), str):
        raise SystemExit(f"Manifest does not describe {name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["sha256"]:
        raise SystemExit(f"Checksum mismatch for {name}")
    if path.stat().st_size != item.get("size_bytes"):
        raise SystemExit(f"Size mismatch for {name}")
PY

postgres_id="$(compose ps -q postgres || true)"
if [ -z "$postgres_id" ] || [ "$(docker inspect -f '{{.State.Running}}' "$postgres_id")" != "true" ]; then
  echo "Target postgres service is not running. Start only the clean postgres target first." >&2
  exit 1
fi

table_count="$(compose exec -T postgres sh -eu -c 'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = '\''public'\'' AND table_type = '\''BASE TABLE'\'';"')"
table_count="$(printf '%s' "$table_count" | tr -d '[:space:]')"
if [ "$table_count" != "0" ]; then
  echo "Refusing restore: target database contains $table_count public tables and is not empty." >&2
  exit 1
fi

cleanup() {
  if [ -n "$helper_id" ]; then
    docker rm -f "$helper_id" >/dev/null 2>&1 || true
  fi
  if [ "$backend_was_running" = true ]; then
    compose up -d backend >/dev/null || echo "WARNING: restore completed but backend restart failed; start it manually." >&2
  fi
}
trap cleanup EXIT INT TERM

backend_id="$(compose ps -q backend || true)"
if [ -n "$backend_id" ] && [ "$(docker inspect -f '{{.State.Running}}' "$backend_id")" = "true" ]; then
  backend_was_running=true
  echo "Stopping backend before restore..."
  compose stop backend
fi

helper_id="$(compose run -d --no-deps --entrypoint sh backend -c 'sleep 300')"
if docker exec "$helper_id" sh -eu -c 'test -z "$(find /app/storage_data -mindepth 1 -print -quit)"'; then
  :
else
  echo "Refusing restore: target backend_storage is not empty." >&2
  exit 1
fi

docker cp "$storage_file" "$helper_id:/tmp/backend-storage.tar.gz"
docker exec "$helper_id" sh -eu -c 'tar -tzf /tmp/backend-storage.tar.gz >/dev/null'

echo "Restoring persistent backend storage..."
docker exec "$helper_id" sh -eu -c 'tar -C /app/storage_data --numeric-owner -xzf /tmp/backend-storage.tar.gz'

echo "Restoring PostgreSQL database..."
compose cp "$database_file" "postgres:/tmp/database.dump"
compose exec -T postgres sh -eu -c 'exec pg_restore --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error /tmp/database.dump'
compose exec -T postgres rm -f -- /tmp/database.dump

echo "Restore completed. Start backend only after the target storage and database checks have both succeeded."
