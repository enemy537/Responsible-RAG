#!/usr/bin/env bash
# =============================================================================
# qdrant-backup.sh — snapshot backup / verify / restore for the vector database
# =============================================================================
# Qdrant snapshots are consistent, point-in-time and created WITHOUT stopping the
# server. Each snapshot is one .snapshot file (a tar archive holding the
# collection config, segments and WAL), so it restores the collection exactly,
# including its 1024-dim Cosine vectors.
#
#   scripts/qdrant-backup.sh dump    [--dir DIR] [--collections a,b]
#   scripts/qdrant-backup.sh verify  <dir>
#   scripts/qdrant-backup.sh restore <dir> --yes [--into NAME] [--priority snapshot|replica]
#
# Env:
#   QDRANT_URL          REST endpoint          (default: http://127.0.0.1:6333)
#   QDRANT_BACKUP_DIR   where snapshots go     (default: <repo>/../storage/backups)
#   QDRANT_KEEP_REMOTE  1 = keep the server-side snapshot copy (default: remove it)
#
# Safety: `dump` never modifies point data — it creates a snapshot, downloads it,
# checks the checksum, then deletes the server-side copy. `restore` needs --yes
# and REPLACES the target collection's points (`priority=snapshot`); use
# `--into NAME` to restore into a fresh collection and keep the original intact.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
BACKUP_DIR="${QDRANT_BACKUP_DIR:-$(dirname "$REPO_ROOT")/storage/backups}"
KEEP_REMOTE="${QDRANT_KEEP_REMOTE:-0}"
PRIORITY="snapshot"
INTO=""
action="${1:-dump}"
shift || true

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 is required"
command -v tar >/dev/null || die "tar is required"

api() { curl -fsS --max-time 300 "$@"; }

# --- API helpers -------------------------------------------------------------
version() { api "$QDRANT_URL/" | python3 -c 'import sys,json; print(json.load(sys.stdin)["version"])'; }

collections() {
  api "$QDRANT_URL/collections" |
    python3 -c 'import sys,json; [print(c["name"]) for c in json.load(sys.stdin)["result"]["collections"]]'
}

points_of() {
  api "$QDRANT_URL/collections/$1" |
    python3 -c 'import sys,json; print(json.load(sys.stdin)["result"].get("points_count"))'
}

create_snapshot() {
  api -X POST "$QDRANT_URL/collections/$1/snapshots?wait=true" |
    python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["name"])'
}

# checksum + size of a named snapshot
snapshot_meta() {
  api "$QDRANT_URL/collections/$1/snapshots" |
    python3 -c '
import sys, json
want = sys.argv[1]
for s in json.load(sys.stdin)["result"]:
    if s["name"] == want:
        print(s.get("checksum", ""), s.get("size", 0))
        break
' "$2"
}

delete_snapshot() { api -X DELETE "$QDRANT_URL/collections/$1/snapshots/$2" >/dev/null; }

download_snapshot() { api -o "$3" "$QDRANT_URL/collections/$1/snapshots/$2"; }

# --- actions -----------------------------------------------------------------
do_dump() {
  local dir="$BACKUP_DIR" only="$ONLY"
  mkdir -p "$dir"

  local names
  if [[ -n "$only" ]]; then
    names="$(printf '%s\n' "${only//,/ }")"
  else
    names="$(collections)"
  fi
  [[ -n "$names" ]] || die "no collections found at $QDRANT_URL"

  log "qdrant $(version) — backing up $(wc -w <<<"$names") collection(s) into $dir"
  local rows="" name snap meta checksum size file actual points
  while read -r name; do
    [[ -n "$name" ]] || continue
    points="$(points_of "$name")"

    snap="$(create_snapshot "$name")"
    meta="$(snapshot_meta "$name" "$snap")"
    checksum="${meta%% *}"
    size="${meta##* }"

    file="$name.snapshot"
    download_snapshot "$name" "$snap" "$dir/$file"
    actual="$(sha256sum "$dir/$file" | cut -d' ' -f1)"
    [[ "$actual" == "$checksum" ]] ||
      die "checksum mismatch for $name (expected $checksum, got $actual) — keeping the server-side snapshot"

    if [[ "$KEEP_REMOTE" != "1" ]]; then delete_snapshot "$name" "$snap"; fi
    printf '    %-26s %10s points  %8s  %s\n' "$name" "$points" "$(numfmt --to=iec "$size" 2>/dev/null || echo "$size")" "$file"
    rows+="$name|$file|$points|$size|$checksum"$'\n'
  done <<<"$names"

  printf '%s' "$rows" | python3 -c '
import sys, json, datetime
rows = [l.split("|") for l in sys.stdin.read().strip().splitlines() if l]
json.dump({
    "service": "qdrant",
    "qdrant_version": sys.argv[1],
    "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "collections": [
        {"name": r[0], "file": r[1], "points_count": int(r[2]), "size": int(r[3]), "sha256": r[4]}
        for r in rows
    ],
}, open(sys.argv[2], "w"), indent=2)
' "$(version)" "$dir/manifest.json"
  log "done — manifest: $dir/manifest.json"
}

do_verify() {
  local dir="${1:-}"
  [[ -n "$dir" ]] || die "usage: qdrant-backup.sh verify <dir>"
  [[ -r "$dir/manifest.json" ]] || die "no manifest.json in '$dir'"
  python3 - "$dir" <<'PY'
import hashlib, json, os, sys, tarfile

root = sys.argv[1]
manifest = json.load(open(os.path.join(root, "manifest.json")))
ok = True
for entry in manifest["collections"]:
    path = os.path.join(root, entry["file"])
    if not os.path.isfile(path):
        print(f"  MISSING  {entry['file']}")
        ok = False
        continue
    size = os.path.getsize(path)
    if size != entry["size"]:
        print(f"  SIZE     {entry['file']}: {size} != {entry['size']}")
        ok = False
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != entry["sha256"]:
        print(f"  SHA256   {entry['file']}: checksum mismatch")
        ok = False
    if not tarfile.is_tarfile(path):
        print(f"  TAR      {entry['file']}: not a readable tar archive")
        ok = False
    if ok:
        print(f"  OK       {entry['file']}  ({entry['points_count']} points, {size} bytes)")
print(f"\nqdrant backup: qdrant {manifest.get('qdrant_version')}, created {manifest.get('created_at')}")
sys.exit(0 if ok else 1)
PY
  log "verify finished"
}

do_restore() {
  local dir="${1:-}"
  [[ -n "$dir" ]] || die "usage: qdrant-backup.sh restore <dir> --yes [--into NAME]"
  [[ -r "$dir/manifest.json" ]] || die "no manifest.json in '$dir'"

  python3 - "$dir" "$INTO" <<'PY'
import json, os, sys
root, into = sys.argv[1], sys.argv[2]
manifest = json.load(open(os.path.join(root, "manifest.json")))
plan = []
for entry in manifest["collections"]:
    target = into or entry["name"]
    plan.append({"target": target, "file": entry["file"], "points": entry["points_count"]})
json.dump(plan, open(os.path.join(root, ".restore-plan.json"), "w"))
for item in plan:
    print(f"  {item['file']}  ->  collection '{item['target']}'")
PY

  local count
  count="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$dir/.restore-plan.json")"
  [[ "$count" == "1" || -z "$INTO" ]] ||
    die "--into works with a single-collection backup (this one has $count)"

  log "restoring $count collection(s) from $dir with priority=$PRIORITY"
  echo "    priority=$PRIORITY REPLACES all points in the target collection with the snapshot."
  echo "    Give the app a few seconds after this finishes before sending traffic."

  while IFS='|' read -r target file; do
    local current
    current="$(points_of "$target" 2>/dev/null || echo "absent")"
    printf '    %-26s current: %-8s <- %s\n' "$target" "$current" "$file"
    api -X POST "$QDRANT_URL/collections/$target/snapshots/upload?priority=$PRIORITY&wait=true" \
      -F "snapshot=@$dir/$file" >/dev/null
    printf '    %-26s now:     %s points\n' "$target" "$(points_of "$target")"
  done < <(python3 -c 'import json,sys; [print(i["target"] + "|" + i["file"]) for i in json.load(open(sys.argv[1]))]' "$dir/.restore-plan.json")

  rm -f "$dir/.restore-plan.json"
  log "restore finished"
}

# --- dispatch ----------------------------------------------------------------
if [[ "$action" == "restore" && "${*:-}" != *"--yes"* ]]; then
  die "refusing to restore without --yes (priority=$PRIORITY overwrites points)"
fi

ONLY=""
remaining=()
while [[ $# -gt 0 ]]; do
  case "$1" in
  --yes) shift ;;
  --into) INTO="$2"; shift 2 ;;
  --priority) PRIORITY="$2"; shift 2 ;;
  --dir) BACKUP_DIR="$2"; shift 2 ;;
  --collections) ONLY="$2"; shift 2 ;;
  *) remaining+=("$1"); shift ;;
  esac
done

case "$action" in
dump) do_dump ;;
verify) do_verify "${remaining[0]:-}" ;;
restore) do_restore "${remaining[0]:-}" ;;
*) die "unknown action '$action' (expected: dump | verify | restore)" ;;
esac
