#!/usr/bin/env bash
# =============================================================================
# mongo-backup.sh — logical backup / verify / restore for the app MongoDB
# =============================================================================
# Take one of these BEFORE any container or compose change on a machine that
# holds real data (production EC2 included). mongodump is a logical backup, so
# the server stays up and the output is a single portable archive file.
#
#   scripts/mongo-backup.sh dump                            # archive + instructions
#   scripts/mongo-backup.sh verify <archive>                # show what it contains
#   scripts/mongo-backup.sh restore <archive> --yes         # merge (no deletes)
#   scripts/mongo-backup.sh restore <archive> --yes --drop  # replace existing collections
#
# Env:
#   MONGO_CONTAINER   container to dump from        (default: rag-mongo)
#   MONGO_BACKUP_DIR  where archives are written    (default: <repo>/../storage/backups)
#   MONGO_BACKUP_NAME archive file name inside that dir
#   MONGO_DB          dump a single database        (default: everything)
#   MONGO_DUMP_AUTH   mongodump credentials, e.g. "-u rag -p secret --authenticationDatabase admin"
#   MONGO_RESTORE_URI target for verify/restore     (default: mongodb://127.0.0.1:27017)
#   MONGO_RESTORE_AUTH mongorestore credentials, e.g. "-u rag -p secret --authenticationDatabase admin"
#   MONGO_RESTORE_NETWORK docker network for verify/restore (default: host).
#                     Production does not publish 27017, so run with
#                     MONGO_RESTORE_NETWORK=<compose_project>_default and
#                     MONGO_RESTORE_URI=mongodb://mongo:27017 instead.
#
# Safety: `restore` refuses to run without --yes, never drops anything unless
# --drop is passed too, and mongodump never modifies the source data.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER="${MONGO_CONTAINER:-rag-mongo}"
BACKUP_DIR="${MONGO_BACKUP_DIR:-$(dirname "$REPO_ROOT")/storage/backups}"
DUMP_AUTH="${MONGO_DUMP_AUTH:-}"
RESTORE_URI="${MONGO_RESTORE_URI:-mongodb://127.0.0.1:27017}"
RESTORE_AUTH="${MONGO_RESTORE_AUTH:-}"
RESTORE_NETWORK="${MONGO_RESTORE_NETWORK:-host}"

# Reads the archive through a read-only mount. --archive=<path> is mandatory:
# mongorestore cannot read a gzipped archive from stdin or from a positional
# path (it fails with "EOF" / "does not appear to be a mongodump archive").
# shellcheck disable=SC2086
do_mongorestore() {
  local file="$1" dir base
  shift
  dir="$(cd "$(dirname "$file")" && pwd)"
  base="$(basename "$file")"
  docker run --rm --network "$RESTORE_NETWORK" -v "$dir:/backup:ro" mongo:7 \
    mongorestore --uri "$RESTORE_URI" $RESTORE_AUTH --gzip --archive="/backup/$base" "$@"
}

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

db_filter=()
[[ -n "${MONGO_DB:-}" ]] && db_filter=(--db "$MONGO_DB")

do_dump() {
  docker exec "$CONTAINER" mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' \
    >/dev/null 2>&1 || die "container '$CONTAINER' is not running or not responding"

  # If no explicit credentials were given, reuse the root credentials the
  # container was started with, so a local/production backup needs no flags.
  if [[ -z "$DUMP_AUTH" ]]; then
    local root_user root_pass
    root_user="$(docker exec "$CONTAINER" printenv MONGO_INITDB_ROOT_USERNAME 2>/dev/null || true)"
    root_pass="$(docker exec "$CONTAINER" printenv MONGO_INITDB_ROOT_PASSWORD 2>/dev/null || true)"
    if [[ -n "$root_user" && -n "$root_pass" ]]; then
      DUMP_AUTH="-u $root_user -p $root_pass --authenticationDatabase admin"
      echo "    using the container's MONGO_INITDB_ROOT_* credentials"
    fi
  fi

  mkdir -p "$BACKUP_DIR"
  local file="$BACKUP_DIR/${MONGO_BACKUP_NAME:-mongo-$(date +%Y%m%d-%H%M%S).archive.gz}"
  [[ -e "$file" ]] && die "$file already exists"

  log "dumping${MONGO_DB:+ database '$MONGO_DB'} into $file"
  # shellcheck disable=SC2086
  if ! docker exec "$CONTAINER" mongodump --gzip --archive $DUMP_AUTH ${db_filter[@]+"${db_filter[@]}"} >"$file"; then
    rm -f "$file"
    die "mongodump failed — pass MONGO_DUMP_AUTH if this server needs credentials"
  fi

  local size checksum
  size="$(stat -c%s "$file")"
  [[ "$size" -gt 0 ]] || die "archive is empty — nothing was dumped"
  gzip -t "$file" 2>/dev/null || die "archive is not valid gzip"
  checksum="$(sha256sum "$file" | cut -d' ' -f1)"

  # Written next to the archive so an off-site copy can be verified later.
  python3 - "$file" "$size" "$checksum" "${MONGO_DB:-all}" <<'PY'
import json, sys, datetime
json.dump({
    "service": "mongo",
    "file": sys.argv[1].rsplit("/", 1)[-1],
    "size": int(sys.argv[2]),
    "sha256": sys.argv[3],
    "database": sys.argv[4],
    "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
}, open(sys.argv[1] + ".manifest.json", "w"), indent=2)
PY

  log "done: $file ($(numfmt --to=iec "$size" 2>/dev/null || echo "$size bytes"))"
  cat <<EOF

Keep this file off the machine before proceeding, then:
  verify : scripts/mongo-backup.sh verify "$file"
  restore: scripts/mongo-backup.sh restore "$file" --yes
EOF
}

do_verify() {
  local file="${1:-}"
  [[ -n "$file" ]] || die "usage: mongo-backup.sh verify <archive>"
  [[ -r "$file" ]] || die "cannot read '$file'"

  # Integrity only: no server needed, so an off-site copy can be checked.
  local size manifest
  size="$(stat -c%s "$file")"
  gzip -t "$file" && echo "  OK       gzip stream intact" || die "$file is not valid gzip"
  echo "  OK       size $size bytes"

  manifest="$file.manifest.json"
  if [[ -r "$manifest" ]]; then
    local recorded actual
    recorded="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$manifest")"
    actual="$(sha256sum "$file" | cut -d' ' -f1)"
    [[ "$recorded" == "$actual" ]] &&
      echo "  OK       sha256 matches manifest" ||
      die "sha256 mismatch (manifest $recorded, archive $actual)"
    echo "  OK       $(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print("db="+m["database"]+" created="+m["created_at"])' "$manifest")"
  else
    echo "  NOTE     no $manifest — checksum not verified"
  fi

  log "archive readable; restore into a scratch database to fully validate"
}

do_restore() {
  local file="${1:-}" drop=""
  [[ -n "$file" ]] || die "usage: mongo-backup.sh restore <archive> --yes [--drop]"
  [[ -r "$file" ]] || die "cannot read '$file'"
  [[ "${*}" == *"--yes"* ]] || die "refusing to restore without --yes"
  [[ "${*}" == *"--drop"* ]] && drop="--drop"

  log "restoring $file into $RESTORE_URI${drop:+ (REPLACING existing collections)}"
  [[ -n "$drop" ]] &&
    echo "    --drop deletes the collections present in the archive before restoring them."
  do_mongorestore "$file" $drop || die "mongorestore failed — set MONGO_RESTORE_URI with credentials / MONGO_RESTORE_AUTH"
  log "restore finished"
}

case "${1:-dump}" in
dump) shift; do_dump "$@" ;;
verify) shift; do_verify "$@" ;;
restore) shift; do_restore "$@" ;;
*) die "unknown action '${1}' (expected: dump | verify | restore)" ;;
esac
