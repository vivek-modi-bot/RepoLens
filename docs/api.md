# RepoLens API Reference

Base URL (local): `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

All repository endpoints require:

```http
Authorization: Bearer <access_token>
```

## Auth

### Register

`POST /api/v1/auth/register`

```json
{
  "username": "alice",
  "password": "securepass123",
  "email": "alice@example.com"
}
```

**201**

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "created_at": "2026-10-04T06:00:00Z"
}
```

### Login

`POST /api/v1/auth/login`

```json
{
  "username": "alice",
  "password": "securepass123"
}
```

**200**

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

### Me

`GET /api/v1/auth/me`

**200** — current user profile.

## Repository review

### Create review

`POST /api/v1/repository/review`

```json
{
  "repository_url": "https://github.com/owner/repository",
  "branch": "main",
  "review_type": "full"
}
```

Allowed `review_type` values: `full`, `security`, `performance`, `quality`, `architecture`.

**200** — see example review response in the README.

### Get review

`GET /api/v1/repository/{review_id}`

Returns a previously stored review owned by the authenticated user.

## Health

`GET /api/v1/health`

```json
{
  "status": "ok",
  "service": "RepoLens",
  "version": "1.0.0",
  "llm_provider": "ollama",
  "llm_available": true
}
```

## Error shape

```json
{
  "error": {
    "code": "invalid_repository_url",
    "message": "Invalid GitHub repository URL"
  }
}
```
