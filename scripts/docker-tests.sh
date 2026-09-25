#!/usr/bin/env bash
# =============================================================================
# docker-tests.sh — run the test suites in Docker
# =============================================================================
# Runs everything in containers so results don't depend on local Node/Python
# versions:
#
#   backend  : pytest inside the project's own backend image, pointed at a real
#              Qdrant dataset and an EPHEMERAL MongoDB (tmpfs, never mounted
#              from ../storage/mongo, so your data directory is untouched).
#   frontend : npm ci + tsc + eslint + vite build on Node 20 (glibc).
#
# Usage:
#   scripts/docker-tests.sh [all|backend|frontend|clean]
#
# Environment overrides:
#   QDRANT_DATA_DIR  Host path mounted as Qdrant storage.
#                    Default: <repo>/../storage/qdrant   (your real dataset)
#                    Pass an empty string to use a throwaway named volume.
#   MONGO_TEST_DB    Mongo database used by the integration tests (must end in
#                    '_test'; the tests refuse to run otherwise).
#
# Safety: the script never deletes anything inside QDRANT_DATA_DIR, and the
# Mongo container stores its data in RAM only.
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QDRANT_DATA_DIR="${QDRANT_DATA_DIR-$(dirname "$REPO_ROOT")/storage/qdrant}"
MONGO_TEST_DB="${MONGO_TEST_DB:-responsible_rag_refactor_test}"

QDRANT_CONTAINER="rrag-qdrant"
MONGO_CONTAINER="rrag-mongo"
QDRANT_URL="http://127.0.0.1:6333"
MONGO_URI="mongodb://127.0.0.1:27017/${MONGO_TEST_DB}"

log() { printf '\n==> %s\n' "$*"; }

ensure_qdrant() {
  if docker ps --format '{{.Names}}' | grep -qx "$QDRANT_CONTAINER"; then
    return
  fi
  if docker ps -a --format '{{.Names}}' | grep -qx "$QDRANT_CONTAINER"; then
    log "restarting Qdrant ($QDRANT_CONTAINER)"
    docker start "$QDRANT_CONTAINER" >/dev/null
    return
  fi

  log "starting Qdrant ($QDRANT_CONTAINER)"
  if [[ -n "$QDRANT_DATA_DIR" && -d "$QDRANT_DATA_DIR" ]]; then
    echo "    dataset: $QDRANT_DATA_DIR (mounted read/write, never modified destructively)"
    docker run -d --name "$QDRANT_CONTAINER" -p 6333:6333 -p 6334:6334 \
      -v "$QDRANT_DATA_DIR:/qdrant/storage" qdrant/qdrant:latest >/dev/null
  else
    echo "    dataset: throwaway volume (integration tests will have no sources)"
    docker run -d --name "$QDRANT_CONTAINER" -p 6333:6333 -p 6334:6334 \
      qdrant/qdrant:latest >/dev/null
  fi
}

ensure_mongo() {
  if docker ps --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER"; then
    return
  fi
  docker rm -f "$MONGO_CONTAINER" >/dev/null 2>&1 || true
  log "starting ephemeral MongoDB ($MONGO_CONTAINER, tmpfs)"
  docker run -d --name "$MONGO_CONTAINER" --tmpfs /data/db \
    -p 27017:27017 mongo:7 --bind_ip_all >/dev/null
}

wait_for_http() {
  local url="$1"
  for _ in $(seq 1 40); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "timed out waiting for $url" >&2
  return 1
}

build_backend_images() {
  log "building backend images"
  docker build -q -f "$REPO_ROOT/backend/Dockerfile" -t rag-backend:local "$REPO_ROOT" >/dev/null
  docker build -q -f "$REPO_ROOT/backend/Dockerfile.test" -t rag-backend:test "$REPO_ROOT" >/dev/null
}

run_backend() {
  build_backend_images
  log "backend: pytest in Docker"
  echo "    qdrant: $QDRANT_URL"
  echo "    mongo : $MONGO_URI"
  docker run --rm --network host \
    -e TEST_QDRANT_URL="$QDRANT_URL" \
    -e TEST_MONGO_URI="$MONGO_URI" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$REPO_ROOT/tests:/app/tests:ro" \
    rag-backend:test "$@"
}

run_frontend() {
  log "frontend: npm ci + tsc + eslint + vite build in Docker"
  docker run --rm -u "$(id -u):$(id -g)" \
    -e HOME=/tmp -e npm_config_cache=/tmp/.npm \
    -v "$REPO_ROOT/frontend:/app" -w /app node:20-slim sh -euc '
      npm ci --no-audit --no-fund
      npx tsc -b --pretty false
      npx eslint .

      # package-lock.json is lockfileVersion 2 and never recorded the optional
      # native packages, so rollup/lightningcss cannot load their binaries.
      # Install the matching ones WITHOUT touching the lockfile.
      ROLLUP_V=$(node -p "require(\"./node_modules/rollup/package.json\").version")
      LIGHTNING_V=$(node -p "require(\"./node_modules/lightningcss/package.json\").version")
      npm install --no-save --no-package-lock --no-audit --no-fund \
        "@rollup/rollup-linux-x64-gnu@${ROLLUP_V}" \
        "lightningcss-linux-x64-gnu@${LIGHTNING_V}" >/dev/null

      npx vite build --outDir /tmp/dist
      echo "frontend: tsc + eslint + build OK"
    '
}

cleanup() {
  log "removing test containers"
  docker rm -f "$QDRANT_CONTAINER" "$MONGO_CONTAINER" >/dev/null 2>&1 || true
}

case "${1:-all}" in
  backend)
    ensure_qdrant; ensure_mongo; wait_for_http "$QDRANT_URL/collections"
    shift || true; run_backend "$@"
    ;;
  frontend)
    run_frontend
    ;;
  all)
    ensure_qdrant; ensure_mongo; wait_for_http "$QDRANT_URL/collections"
    run_backend
    run_frontend
    ;;
  clean)
    cleanup
    ;;
  *)
    echo "usage: $0 [all|backend|frontend|clean]" >&2
    exit 2
    ;;
esac
