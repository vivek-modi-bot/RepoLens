# Design Decisions

## Why FastAPI + Pydantic v2?

FastAPI provides production-ready OpenAPI docs, dependency injection, and first-class async support. Pydantic v2 gives strict request/response validation—critical when validating both client input and LLM JSON output.

## Why SQLite instead of PostgreSQL?

The scope explicitly avoids PostgreSQL for the initial deliverable. SQLite (via SQLAlchemy async + aiosqlite) provides enough persistence for users and review history while keeping Docker Compose simple. The ORM boundary makes a later PostgreSQL swap straightforward.

## Why GitHub tarball download instead of `git clone`?

- Avoids shelling out to git with untrusted arguments.
- Works for public repos without credentials.
- Easier to enforce download size limits while streaming.
- Aligns with the “never execute repository code” constraint.

## Why chunk before calling the LLM?

Local models have finite context windows. Chunking by character budget keeps prompts bounded, enables partial progress, and lets the aggregator merge findings across files.

## Why force JSON from the model?

Raw prose is hard to productize. Structured JSON + Pydantic validation yields a stable API contract. Retries handle occasional malformed model output.

## Why abstract `LLMProvider`?

Review orchestration should not know about Ollama HTTP details. An interface keeps the door open for other local/remote providers without rewriting the pipeline.

## Why exclude secrets aggressively?

Even for public repositories, `.env` samples and key material must not be forwarded into prompts. This reduces accidental secret leakage into model logs/context.

## What was intentionally deferred?

- React frontend
- PostgreSQL / Redis / Kubernetes
- Auth0 / GitHub OAuth
- Background job processing / webhooks

These remain valid future enhancements and are called out in the README.
