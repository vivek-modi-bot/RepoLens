# RepoLens

**AI-Powered GitHub Repository Code Review Microservice**

RepoLens is a production-oriented FastAPI microservice that accepts a **public GitHub repository URL**, downloads the source for **static analysis only**, sends filtered code chunks to a locally running open-source LLM via **Ollama**, and returns a **structured** code-review report.

> RepoLens analyzes **public** repositories only. It **never executes** repository code, install scripts, or shell commands from downloaded content.

---

## Key features

- JWT username/password authentication (bcrypt password hashing)
- Public GitHub repository review API
- Review types: `full`, `security`, `performance`, `quality`, `architecture`
- Modular analysis pipeline (fetch → filter → detect → chunk → LLM → aggregate)
- Ollama provider behind an `LLMProvider` interface
- Structured JSON responses validated with Pydantic v2
- Size limits, secret-file exclusion, safe temp cleanup
- React web UI for auth, review submission, and results
- Docker Compose stack (`frontend` + `repo-review-api` + `ollama`)
- OpenAPI/Swagger at `/docs`
- Pytest suite with mocked GitHub/Ollama calls

---

## Architecture

```
Browser UI (React)
  │  Bearer JWT
  ▼
FastAPI (auth / repository / health)
  │
  ├─ AuthService ──▶ SQLite (users, reviews)
  │
  └─ ReviewService
        │
        ├─ RepositoryFetcher ──▶ GitHub public tarball API
        ├─ FileFilter / LanguageDetector / CodeChunker
        ├─ PromptService
        ├─ LLMProvider (OllamaProvider) ──▶ Ollama
        └─ ReviewAggregator ──▶ ReviewResponse
```

See [docs/architecture.md](docs/architecture.md) for full request flows and security notes.

---

## Technology stack

| Area | Choice |
|------|--------|
| Language | Python 3.12+ |
| API | FastAPI |
| Validation | Pydantic v2 |
| Auth | JWT (HS256) + bcrypt |
| HTTP | httpx |
| Persistence | SQLAlchemy async + SQLite |
| LLM | Ollama (local) |
| Frontend | React + Vite + TypeScript |
| Packaging | Docker / Docker Compose |
| Tests | pytest + pytest-asyncio |

---

## Project structure

```
app/
├── main.py
├── api/                 # HTTP routers
├── core/                # config, security, deps, errors
├── schemas/             # Pydantic models
├── services/            # business logic
├── github/              # URL validation + fetch
├── llm/                 # LLMProvider + Ollama
├── analysis/            # filter, detect, chunk, aggregate
├── models/              # ORM models
└── db/                  # engine/session
frontend/                # React UI (Vite)
tests/
docs/
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

---

## Prerequisites

- Python 3.12+
- Docker + Docker Compose (recommended)
- ~4–8 GB RAM for a coding LLM model (depends on model size)

---

## Local setup (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — set JWT_SECRET_KEY and OLLAMA_BASE_URL=http://localhost:11434

# Start Ollama separately, then API:
uvicorn app.main:app --reload --port 8000

# In another terminal, start the UI:
cd frontend
npm install
npm run dev
```

UI: `http://localhost:5173` (Vite proxies `/api` → `http://localhost:8000`)  
API: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

---

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET_KEY` | HMAC secret for JWTs | *(change me)* |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_EXPIRATION_MINUTES` | Token TTL | `60` |
| `DATABASE_URL` | SQLAlchemy async URL | SQLite file |
| `LLM_PROVIDER` | Provider key | `ollama` |
| `OLLAMA_BASE_URL` | Ollama HTTP base | `http://ollama:11434` |
| `OLLAMA_MODEL` | Model name | `qwen2.5-coder` |
| `MAX_FILE_SIZE` | Max bytes per file | `100000` |
| `MAX_FILES` | Max source files | `100` |
| `MAX_REPOSITORY_SIZE` | Max archive/source bytes | `50000000` |
| `MAX_CHUNK_CHARS` | Max chars per LLM chunk | `8000` |
| `TEMP_DIR` | Temp extract directory | `/tmp/repolens` |

See [.env.example](.env.example) for the full list.

---

## Docker setup

```bash
cp .env.example .env
# set JWT_SECRET_KEY in .env (optional; compose has a dev default)

docker compose up -d --build
```

Services:

- UI: `http://localhost:3000` (nginx proxies `/api` to the FastAPI service)
- API: `http://localhost:8000`
- Ollama: `http://localhost:11434`

The API talks to Ollama on the Docker network at `http://ollama:11434`.

---

## Ollama model setup

After Compose is up, pull a model into the Ollama container:

```bash
docker compose exec ollama ollama pull qwen2.5-coder
```

Other solid options:

```bash
docker compose exec ollama ollama pull codellama
docker compose exec ollama ollama pull deepseek-coder-v2
```

Set `OLLAMA_MODEL` to match the pulled model, then restart the API if needed:

```bash
OLLAMA_MODEL=qwen2.5-coder docker compose up -d
```

Verify:

```bash
curl http://localhost:8000/api/v1/health
```

---

## Frontend

The React app in `frontend/` provides:

- Landing page
- Register / sign-in
- Profile page to save a GitHub PAT for raising PRs
- Workspace to submit a public GitHub URL + review type
- Structured results view (score, stats, severity-ranked issues, per-finding fix/PR)

Local UI development uses the Vite proxy. In Docker, nginx serves the built UI and proxies `/api` to `repo-review-api`.

## Authentication

1. Register a user (UI or API)
2. Login to receive `{ "access_token", "token_type": "bearer" }`
3. Send `Authorization: Bearer <token>` on protected routes
4. Optionally `PATCH /api/v1/auth/me` with a GitHub PAT (`repo` scope) — stored encrypted on the user profile and reused when opening pull requests

Passwords are stored only as bcrypt hashes. GitHub tokens are Fernet-encrypted (key derived from `JWT_SECRET_KEY`) and never returned by the API.

---

## API examples

### Register

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"securepass123","email":"alice@example.com"}'
```

### Login

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"securepass123"}'
```

### Review a public repository

```bash
TOKEN="<access_token>"

curl -s -X POST http://localhost:8000/api/v1/repository/review \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "repository_url": "https://github.com/psf/requests",
    "branch": "main",
    "review_type": "security"
  }'
```

### Fetch a stored review

```bash
curl -s http://localhost:8000/api/v1/repository/<review_id> \
  -H "Authorization: Bearer $TOKEN"
```

More detail: [docs/api.md](docs/api.md)

---

## Example review response

```json
{
  "review_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "repository": "owner/repository",
  "branch": "main",
  "review_type": "full",
  "overall_score": 82,
  "summary": "Generally solid structure with a few security and maintainability findings.",
  "statistics": {
    "files_analyzed": 18,
    "languages": ["Python", "JavaScript"],
    "issues_found": 7,
    "total_lines": 2400,
    "chunks_processed": 4
  },
  "issues": [
    {
      "file": "src/auth.py",
      "line": 42,
      "severity": "high",
      "category": "security",
      "title": "Potential hardcoded credential",
      "description": "A secret-like string appears embedded in source.",
      "recommendation": "Load secrets from environment variables or a secret manager."
    }
  ],
  "created_at": "2026-10-04T06:05:00Z"
}
```

---

## Testing

Unit/API tests mock GitHub and Ollama — **Ollama does not need to be running**.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Covered areas include registration/login, JWT validation, URL validation, file filtering / `.env` exclusion, size limits, schema validation, and the authenticated review endpoint.

---

## Security considerations

- JWT auth on review endpoints
- bcrypt password hashing
- Strict GitHub URL validation (HTTPS + github.com only)
- Repository / file / chunk size limits
- HTTP timeouts for GitHub and Ollama
- Safe temporary directories with cleanup
- Path-traversal-safe archive extraction
- `.env` / credential-like files never sent to the LLM
- No execution of downloaded repository code
- Configuration via environment variables; no secrets committed

---

## Limitations

- Public repositories only (no private GitHub access)
- Synchronous review in the request path (large repos can take minutes)
- LLM quality depends on the local model and chunking
- SQLite is not ideal for multi-writer production clusters
- Language detection is extension-based (not a full linguistic model)
- Findings can include false positives; treat as assistive, not authoritative

---

## Future improvements

- Background jobs + progress webhooks for large reviews
- PostgreSQL / Redis for scale-out
- Auth0 or GitHub OAuth providers
- Streaming responses / SSE progress
- Richer language/framework-aware analyzers
- Caching of unchanged commits
- Kubernetes deployment manifests

Design rationale: [docs/design-decisions.md](docs/design-decisions.md)

---

## License

MIT (or project-specific license of your choice).
