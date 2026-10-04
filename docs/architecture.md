# RepoLens Architecture

## High-level architecture

RepoLens is a containerized FastAPI microservice that performs **static** AI-assisted code review of **public** GitHub repositories using a locally running Ollama LLM.

```
┌────────────┐     JWT      ┌──────────────────┐     HTTPS      ┌────────────┐
│   Client   │─────────────▶│  RepoLens API    │───────────────▶│  GitHub    │
└────────────┘              │  (FastAPI)       │                │  (public)  │
                            └────────┬─────────┘                └────────────┘
                                     │
                                     │ HTTP (Docker network)
                                     ▼
                            ┌──────────────────┐
                            │     Ollama       │
                            │  (local LLM)     │
                            └──────────────────┘
```

Components:

| Component | Responsibility |
|-----------|----------------|
| FastAPI API layer | Auth, validation, HTTP concerns |
| Auth service | Registration, login, JWT issuance |
| Repository service | URL validation, archive download |
| Analysis pipeline | Filter, language detect, chunk, aggregate |
| LLM provider | Abstracted model access (Ollama) |
| SQLite persistence | Users + stored review results |

## Request flow (repository review)

1. Client authenticates via `POST /api/v1/auth/login` and receives a JWT.
2. Client calls `POST /api/v1/repository/review` with `Authorization: Bearer <token>`.
3. Pydantic validates the request (URL, branch, review type).
4. `ReviewService` orchestrates the pipeline:
   - `RepositoryFetcher` downloads a public tarball (no git clone shelling).
   - `FileFilter` excludes secrets, generated dirs, binaries, oversized files.
   - `LanguageDetector` tags languages and computes stats.
   - `CodeChunker` splits content into bounded chunks.
   - `OllamaProvider` reviews each chunk with a typed prompt.
   - `ReviewAggregator` merges/deduplicates findings.
5. Result is validated, persisted, and returned as structured JSON.
6. Temporary files are always cleaned up.

## Authentication flow

```
Register → hash password (bcrypt) → store user
Login    → verify password → issue JWT (HS256)
Protected routes → HTTPBearer → decode JWT → load user
```

Authentication is intentionally abstract:

- Routes depend on `get_current_user`, not a concrete IdP.
- `AuthService` encapsulates credential checks.
- Future Auth0 / GitHub OAuth can mint the same JWT shape or replace the dependency without rewriting review logic.

## Repository processing flow

```
Validate URL
    → Resolve public metadata / branch (GitHub API)
    → Stream tarball with size limits
    → Safe extract (path-traversal guards)
    → FileFilter (+ .gitignore where practical)
    → LanguageDetector
    → CodeChunker
```

Security constraints:

- Only `https://github.com/owner/repo` public URLs.
- Never execute repository code, install scripts, or shell commands from repo contents.
- Never send `.env` / credential-like files to the LLM.
- Enforce `MAX_FILE_SIZE`, `MAX_FILES`, `MAX_REPOSITORY_SIZE`.

## LLM interaction

```
PromptService (review_type-specific)
    → LLMProvider.generate_review(prompt)
    → JSON parse + Pydantic validate
    → retry on invalid JSON
    → ReviewAggregator
```

### Why an LLM provider interface?

`LLMProvider` isolates transport/model concerns from review orchestration. Today `OllamaProvider` talks to Ollama over HTTP. Tomorrow an OpenAI, vLLM, or Azure provider can be added by implementing the same interface and updating the factory—without changing `ReviewService`, prompts, or aggregation.

## Error handling

Centralized via `AppError` subclasses and FastAPI exception handlers:

| Status | Typical cause |
|--------|----------------|
| 400 | Invalid GitHub URL |
| 401 | Missing/invalid JWT |
| 403 | Forbidden |
| 404 | Repo/review not found |
| 413 | Size limits exceeded |
| 422 | Schema validation |
| 429 | Rate limit (reserved) |
| 500 | Unexpected internal error |
| 502 | Invalid LLM structured output |
| 503 | Ollama unavailable |

Clients never receive stack traces or secrets.

## Security considerations

- Passwords hashed with bcrypt (never stored plaintext).
- JWT secret and TTL via environment variables.
- Input validation with Pydantic v2.
- Safe temp directories + cleanup.
- Archive extraction rejects `..` / absolute paths.
- No repository code execution path exists in the service.
- Secrets excluded from LLM prompts.

## Scalability considerations

Current design targets a polished single-node microservice:

- Sync review in the request path (simple, demo-friendly).
- SQLite for local persistence (easy Docker story).
- Chunking limits LLM context pressure.

Future scale-out options (not implemented):

- Background job queue for large repos.
- PostgreSQL + object storage for review artifacts.
- Horizontal API replicas behind a load balancer.
- Per-user rate limiting with Redis.
- Streaming progress endpoints.
