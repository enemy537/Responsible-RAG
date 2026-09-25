#!/usr/bin/env bash
# =============================================================================
# backup.sh — one-command backup / verify / restore for EVERYTHING stateful
# =============================================================================
# Wraps the two service-specific tools so a full environment backup is a single
# command producing a self-describing, timestamped folder:
#
#   scripts/backup.sh dump                    # mongo + qdrant -> ../storage/backups/<ts>/
#   scripts/backup.sh dump --only qdrant      # just the vector DB
#   scripts/backup.sh verify <dir>            # integrity of every file in a backup
#   scripts/backup.sh restore <dir> --yes     # put it all back
#   scripts/backup.sh list                    # what backups exist
#
# Layout of a backup folder:
#   <ts>/mongo.archive.gz        + mongo.archive.gz.manifest.json   (mongodump, gzip)
#   <ts>/qdrant/<collection>.snapshot + manifest.json               (qdrant snapshots)
#   <ts>/README.txt                                                 (how to restore)
#
# Env (see each script for the full list):
#   MONGO_CONTAINER MONGO_DUMP_AUTH MONGO_RESTORE_URI MONGO_RESTORE_AUTH
#   MONGO_RESTORE_NETWORK QDRANT_URL QDRANT_KEEP_REMOTE BACKUP_DIR
#
# Safety: dump only reads (qdrant snapshots are removed from the server after a
# verified download). restore refuses to run without --yes; Mongo merges unless
# --drop is given, and Qdrant's priority=snapshot overwrites the target points.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$REPO_ROOT")/storage/backups}"
MONGO_TOOL="$REPO_ROOT/scripts/mongo-backup.sh"
QDRANT_TOOL="$REPO_ROOT/scripts/qdrant-backup.sh"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ -x "$MONGO_TOOL" && -x "$QDRANT_TOOL" ]] ||
  die "missing tools: $MONGO_TOOL / $QDRANT_TOOL"

action="${1:-dump}"
shift || true

ONLY=""   # "" | mongo | qdrant
DIR=""
YES=""
DROP=""
PASS=()   # extra passthrough flags (e.g. --drop)
while [[ $# -gt 0 ]]; do
  case "$1" in
  --only) ONLY="$2"; shift 2 ;;
  --dir) DIR="$2"; shift 2 ;;
  --yes) YES="--yes"; shift ;;
  --drop) DROP="--drop"; shift ;;
  -h | --help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
  *) PASS+=("$1"); shift ;;
  esac
done
[[ -z "$ONLY" || "$ONLY" == "mongo" || "$ONLY" == "qdrant" ]] ||
  die "--only takes 'mongo' or 'qdrant'"

# Positional argument (verify/restore take a backup folder).
[[ -z "$DIR" && ${#PASS[@]} -gt 0 ]] && DIR="${PASS[0]}"

human() { numfmt --to=iec "$1" 2>/dev/null || echo "$1 bytes"; }
dir_size() { du -sb "$1" 2>/dev/null | cut -f1; }

do_dump() {
  local ts targets=()
  ts="$(date +%Y%m%d-%H%M%S)"
  DIR="${DIR:-$BACKUP_DIR/$ts}"
  mkdir -p "$DIR"
  [[ "$ONLY" == "qdrant" ]] || targets+=(mongo)
  [[ "$ONLY" == "mongo" ]] || targets+=(qdrant)

  for service in "${targets[@]}"; do
    if [[ "$service" == mongo ]]; then
      log "mongo -> $DIR"
      MONGO_BACKUP_DIR="$DIR" MONGO_BACKUP_NAME=mongo.archive.gz bash "$MONGO_TOOL" dump
    else
      log "qdrant -> $DIR/qdrant"
      QDRANT_BACKUP_DIR="$DIR/qdrant" bash "$QDRANT_TOOL" dump
    fi
  done

  cat >"$DIR/README.txt" <<EOF
Backup created $(date -Iseconds) on $(hostname)
Contents: ${targets[*]}

Restore everything (overwrites current data):
  scripts/backup.sh restore "$DIR" --yes

Verify the files first (no server needed):
  scripts/backup.sh verify "$DIR"

Per service:
  scripts/mongo-backup.sh restore "$DIR/mongo.archive.gz" --yes
  scripts/qdrant-backup.sh restore "$DIR/qdrant" --yes
EOF

  local qdrant_count
  qdrant_count="$(python3 -c '
import json, sys
try:
    m = json.load(open(sys.argv[1] + "/qdrant/manifest.json"))
    print(len(m["collections"]))
except Exception:
    print(0)
' "$DIR")"

  python3 - "$DIR" "$BACKUP_DIR" "$qdrant_count" <<'PY'
import json, os, sys, datetime
root, backups, qdrant_count = sys.argv[1], sys.argv[2], int(sys.argv[3])
summary = {
    "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "path": os.path.abspath(root),
    "services": {},
}
mongo = os.path.join(root, "mongo.archive.gz")
if os.path.isfile(mongo):
    summary["services"]["mongo"] = {
        "file": "mongo.archive.gz",
        "size": os.path.getsize(mongo),
        "manifest": json.load(open(mongo + ".manifest.json")),
    }
if qdrant_count:
    summary["services"]["qdrant"] = {
        "dir": "qdrant",
        "collections": qdrant_count,
        "manifest": json.load(open(os.path.join(root, "qdrant", "manifest.json"))),
    }
json.dump(summary, open(os.path.join(root, "manifest.json"), "w"), indent=2)
PY

  log "backup complete: $DIR ($(human "$(dir_size "$DIR")"))"
  echo "    manifest: $DIR/manifest.json"
  echo "    Copy this folder somewhere else (S3, another host) — a backup on the"
  echo "    same disk as the databases does not protect you."
}

do_verify() {
  [[ -n "$DIR" ]] || die "usage: backup.sh verify <dir>"
  [[ -d "$DIR" ]] || die "'$DIR' is not a directory"
  if [[ -f "$DIR/mongo.archive.gz" ]]; then
    log "mongo"
    bash "$MONGO_TOOL" verify "$DIR/mongo.archive.gz"
  fi
  if [[ -f "$DIR/qdrant/manifest.json" ]]; then
    log "qdrant"
    bash "$QDRANT_TOOL" verify "$DIR/qdrant"
  fi
  log "verify finished"
}

do_restore() {
  [[ -n "$DIR" ]] || die "usage: backup.sh restore <dir> --yes"
  [[ -d "$DIR" ]] || die "'$DIR' is not a directory"
  [[ -n "$YES" ]] || die "refusing: add --yes to confirm restoring over current data"

  if [[ -f "$DIR/mongo.archive.gz" && "$ONLY" != "qdrant" ]]; then
    log "mongo"
    MONGO_RESTORE_URI="${MONGO_RESTORE_URI:-mongodb://127.0.0.1:27017}" \
      bash "$MONGO_TOOL" restore "$DIR/mongo.archive.gz" --yes $DROP
  fi
  if [[ -f "$DIR/qdrant/manifest.json" && "$ONLY" != "mongo" ]]; then
    log "qdrant"
    bash "$QDRANT_TOOL" restore "$DIR/qdrant" --yes
  fi
  log "restore finished"
}

do_list() {
  [[ -d "$BACKUP_DIR" ]] || die "no backups yet in $BACKUP_DIR"
  log "backups in $BACKUP_DIR"
  local found=0 dir
  while read -r dir; do
    [[ -n "$dir" ]] || continue
    found=1
    printf '    %-22s %10s  %s\n' "$(basename "$dir")" \
      "$(human "$(dir_size "$dir")")" "$(ls "$dir" | tr '\n' ' ')"
  done < <(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d | sort -r)
  [[ "$found" == "1" ]] || echo "    (none)"
  echo
  echo "    archives: $BACKUP_DIR"
}

case "$action" in
dump) do_dump ;;
verify) do_verify ;;
restore) do_restore ;;
list) do_list ;;
*) die "unknown action '$action' (expected: dump | verify | restore | list)" ;;
esac
