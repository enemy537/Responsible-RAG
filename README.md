# 🔍 RAG Chatbot — Canadian Academic Assistant

A **Retrieval-Augmented Generation (RAG)** chatbot tailored for Canadian academic contexts.  It combines a hybrid ensemble retriever (dense vector + BM25) with audience-specific system prompts so the same knowledge base can communicate appropriately to 2SLGBTQI+ teens, seniors, Indigenous community leaders, and disabled adults.

---

## Features

- **Hybrid retrieval** — ensemble of Qdrant (vector similarity) + BM25 (keyword), weighted 70/30
- **Smart chunking** — semantic-first via `SemanticChunker`, with automatic recursive fallback
- **Population profiles** — four research-cited system-prompt personas (`RAGPopulation`)
- **Cloud embeddings** — Hugging Face Inference API (same BAAI/bge-large-en-v1.5 model, zero local deps)
- **Clean architecture** — UI, core logic, profiles, and config are fully decoupled
- **Docker-ready** — full `docker compose` setup for the entire stack
- **API-expansion-ready** — `src/core` is framework-agnostic; add FastAPI without touching business logic

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-org/rag-chatbot.git
cd rag-chatbot
cp .env.example .env
# Edit .env and set at minimum: DEEPSEEK_API_KEY
```

### 2. Add knowledge-base documents

Drop `.txt` or `.pdf` files into `resources/` (sub-directories are scanned recursively).  The index is built automatically on first launch.

### 3a. Run locally (backend only)

Requires a running MongoDB instance.  The easiest way is via Docker:

```bash
docker run -d --name rag-mongo \
  -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=rag \
  -e MONGO_INITDB_ROOT_PASSWORD=ragpassword \
  -e MONGO_INITDB_DATABASE=responsible_rag \
  mongo:7
```

Then start the backend:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app:app --reload --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs).

For the frontend, see `frontend/package.json` scripts (requires Bun or Node):

```bash
cd frontend
bun install    # or npm install
bun run dev    # or npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 3b. Run via Docker

Build and start the dev stack (MongoDB, Qdrant, backend, frontend):

```bash
docker compose up --build
```

Open the frontend at [http://localhost:3000](http://localhost:3000) and the backend API at [http://localhost:8000/docs](http://localhost:8000/docs).

Caddy is **not** part of this command — it is the TLS reverse proxy and binds the
privileged ports 80/443, so it lives in `docker-compose.prod.yml`. Use the prod
command below if you need to test through the proxy.

---

## Docker Compose Reference

The stack consists of five services:

| Service   | Container         | Port(s)   | Tech                             |
|-----------|-------------------|-----------|----------------------------------|
| Caddy     | `rag-caddy`       | 80 / 443  | Reverse proxy — **prod stack only** |
| Qdrant    | `qdrant-server`   | 6333/6334 | Qdrant 1.19 (host-persisted)     |
| MongoDB   | `rag-mongo`       | 27017     | MongoDB 7 (host-persisted)       |
| Frontend  | `rag-frontend`    | 3000      | Vite + React (nginx)             |
| Backend   | `rag-backend`     | 8000      | FastAPI (Python)                 |

> **Note:** Both datastores are persisted on the host, outside the repo, so they survive `docker compose down`, rebuilds and image upgrades:
>
> * MongoDB — `../storage/mongo/data` → `/data/db`
> * Qdrant — `../storage/qdrant` → `/qdrant/storage`
>
> `docker/mongo-init.js` runs only while `/data/db` is **empty** (MongoDB's own rule): it creates the app user, the collections and the indexes. On an existing data directory it is skipped, so it can never modify live data.

> **Dev vs prod:** Caddy is only defined in `docker-compose.prod.yml`. Plain
> `docker compose up` therefore starts four services and never touches ports 80/443 —
> useful when the machine already runs another web server.
>
> | | Dev | Prod |
> |---|---|---|
> | Command | `docker compose up --build -d` | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d` |
> | Reverse proxy | none — use `:3000` / `:8000` | Caddy on 80/443, TLS for `${DOMAIN}` |
> | Datastores | host-persisted | host-persisted (same paths) |

Releases are automated with GitHub Actions (CI on every pull request, SSH deploy with an
on-host backup and automatic rollback on merge to `main`) — see
[docs/deployment.md](docs/deployment.md) for setup, secrets and rollback instructions.

### Common commands

| Action | Command |
|---|---|
| **Build & start** | `docker compose up --build` |
| **Start in background** | `docker compose up --build -d` |
| **Stop** | `docker compose down` |
| **Stop & delete named volumes** | `docker compose down -v` — safe here: this stack uses host bind mounts, not named volumes |
| **Rebuild a single service** | `docker compose build frontend` (or `backend`) |
| **Restart a service** | `docker compose restart frontend` |
| **View logs (all)** | `docker compose logs -f` |
| **View logs (one service)** | `docker compose logs -f backend` (or `mongo`) |
| **View running containers** | `docker compose ps` |
| **Shell into a container** | `docker compose exec mongo mongosh --quiet` |

> ⚠️ **Never** delete or rename `../storage/mongo/data` or `../storage/qdrant` on a server that holds real data. If a datastore's host directory is missing, Docker creates an empty one and the service starts empty — which looks exactly like data loss. Take a backup first.

---

## Backup & restore

Both stateful services have a dedicated tool plus one wrapper that covers everything.
Backups land in `../storage/backups/<timestamp>/` and are self-describing
(checksums + manifests), so they can be verified later, even off-site.

| Action | Command |
|---|---|
| **Back up everything** | `scripts/backup.sh dump` |
| **Back up one service** | `scripts/backup.sh dump --only mongo` (or `--only qdrant`) |
| **Verify a backup** | `scripts/backup.sh verify <dir>` (offline: gzip/tar + SHA-256) |
| **Restore everything** | `scripts/backup.sh restore <dir> --yes` |
| **List backups** | `scripts/backup.sh list` |

What each backup contains:

* `mongo.archive.gz` — `mongodump` of every database (or `MONGO_DB`), plus a JSON manifest with size and SHA-256.
* `qdrant/<collection>.snapshot` — a consistent, point-in-time Qdrant snapshot per collection (a tar archive holding config, segments and WAL). Snapshots are created on the live server, downloaded, checksum-verified, and then **removed from the server** so they never fill the data disk.

Restore semantics (both need `--yes`; nothing runs without it):

* **Mongo** merges by default. Add `--drop` to replace the collections present in the archive.
* **Qdrant** uses `priority=snapshot`, which **replaces** the points in the target collection. To recover into a fresh collection and keep the original intact, use the service tool directly:
  ```bash
  scripts/qdrant-backup.sh restore <dir>/qdrant --yes --into <new_collection>
  ```

Credentials and remote targets:

```bash
# dumping is automatic for containers started with MONGO_INITDB_ROOT_* (the default)
MONGO_DUMP_AUTH="-u rag -p secret --authenticationDatabase admin" scripts/backup.sh dump

# restore into a server that requires auth
MONGO_RESTORE_URI="mongodb://rag:secret@127.0.0.1:27017" scripts/backup.sh restore <dir> --yes

# production does not publish 27017/6334 — reach the datastores over the compose network
MONGO_RESTORE_NETWORK=responsible-rag_default MONGO_RESTORE_URI=mongodb://mongo:27017 \
  scripts/backup.sh restore <dir> --yes
```

> A backup on the same disk as the databases does not protect you. Copy
> `../storage/backups/<timestamp>/` to another host or object store, and verify it
> there with `scripts/backup.sh verify <dir>`.

---

## Project Structure

```
rag-chatbot/
├── docker-compose.yml             # Orchestrates MongoDB + frontend + backend
├── .env.example                   # Copy to .env and configure
│
├── data/
│   └── mongo/
│       ├── init.js                # First-run DB/user/index creation
│       └── ...                    # MongoDB data files (gitignored)
│
├── backend/
│   ├── Dockerfile                 # Multi-stage build (uv + hatchling)
│   ├── app.py                     # Streamlit entry point (wiring only)
│   └── src/
│       ├── config/
│       │   └── settings.py        # Pydantic-settings; all env vars in one place
│       │
│       ├── core/                  # ⚡ Framework-agnostic business logic
│       │   ├── chunker.py         # SmartChunker (semantic → recursive fallback)
│       │   ├── embeddings.py      # EmbeddingFactory (OpenVINO | Nomic)
│       │   ├── profiles.py        # Audience-specific prompts
│       │   ├── rag_chain.py       # RAGChain (full pipeline, invocable)
│       │   ├── retrievers.py      # RetrieverFactory (ensemble BM25 + vector)
│       │   └── vector_store.py    # Qdrant lifecycle
│       └── ui/
│           ├── app.py             # ChatView — Streamlit page controller
│           ├── components.py      # Stateless HTML rendering helpers
│           └── styles.py          # APP_STYLES CSS constant
│
├── frontend/
│   ├── Dockerfile                 # Multi-stage Vite build (Bun)
│   ├── package.json
│   ├── vite.config.ts
│   └── src/                       # React app (see frontend/src/)
│
├── resources/                     # ← drop knowledge-base documents here
└── vectordb/                      # ← auto-generated vector store (gitignored)
```

---

## Configuration Reference

All settings live in `.env`.  See `.env.example` for the full annotated list.

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `deepseek-chat` | LangChain model string |
| `DEEPSEEK_API_KEY` | — | Required for DeepSeek |
| `EMBEDDING_DEVICE` | `CPU` | `CPU` \| `NPU` \| `GPU` |
| `USE_NOMIC` | `false` | Switch to Nomic Embed backend |
| `USE_SEMANTIC_CHUNKING` | `true` | Disable to always use recursive splitter |
| `VEC_WEIGHT` | `0.7` | Ensemble weight for vector retriever |
| `MONGO_URI` | — | MongoDB connection string (local Docker or external) |
| `MONGO_DB` | `responsible_rag` | MongoDB database name |
| `MONGO_ROOT_USER` | `rag` | MongoDB root username (Docker init only) |
| `MONGO_ROOT_PASSWORD` | `ragpassword` | MongoDB root password (Docker init only) |
| `MONGO_APP_USER` | `rag` | MongoDB app user (created by init.js) |
| `MONGO_APP_PASSWORD` | `ragpassword` | MongoDB app user password |

---

## Audience Profiles

| Key | Audience | Research baseline |
|---|---|---|
| `LGBT_CANADIAN_TEEN` | 2SLGBTQI+ youth | NIH PMC 12919746 · Egale Canada |
| `SENIOR_LOW_EDU_CANADA` | Older adults, limited schooling | Frontiers Digital Health 2026 |
| `INDIGENOUS_COMMUNITY_LEADER_CA` | First Nations / Inuit / Métis leaders | TRC AI Standards |
| `MIDAGED_DISABLED_CANADIAN` | Disabled mid-aged adults | Accessibility Standards Canada |

To add a profile: add a new `StrEnum` member in `src/profiles/population_profiles.py`.  The UI and API pick it up automatically.

---

## Expanding to an API

`backend/src/core` contains zero UI or framework dependencies.  To expose the same pipeline via a REST API:

```
backend/src/
└── api/                           # New package — add when ready
    ├── __init__.py
    ├── main.py                    # FastAPI app
    ├── routers/
    │   └── chat.py                # POST /chat  →  RAGChain.invoke()
    └── schemas.py                 # Pydantic request / response models
```

Then add a third service in `docker-compose.yml`.

---

## Contributing

1. Fork → feature branch → PR against `main`
2. Follow existing module docstring conventions
3. Run `ruff check .` and `mypy src/` before opening a PR

---

## License

MIT — see `LICENSE` for details.
