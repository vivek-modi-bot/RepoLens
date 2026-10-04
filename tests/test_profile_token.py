"""Profile GitHub token storage tests."""

import pytest
from httpx import AsyncClient

from app.core.token_crypto import decrypt_secret, encrypt_secret


def test_token_crypto_roundtrip() -> None:
    token = "ghp_test_token_value_123456"
    encrypted = encrypt_secret(token)
    assert encrypted != token
    assert decrypt_secret(encrypted) == token


@pytest.mark.asyncio
async def test_profile_stores_github_token(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    before = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert before.status_code == 200
    assert before.json()["github_token_configured"] is False

    updated = await client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"github_token": "ghp_profile_token_abc12345"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["github_token_configured"] is True
    assert "github_token" not in body
    assert "ghp_profile_token_abc12345" not in str(body)

    cleared = await client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={"clear_github_token": True},
    )
    assert cleared.status_code == 200
    assert cleared.json()["github_token_configured"] is False
