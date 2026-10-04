"""Authentication tests."""

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token, get_subject_from_token, hash_password, verify_password


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "password12345"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "bob"
    assert "hashed_password" not in body

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "bob", "password": "password12345"},
    )
    assert login.status_code == 200
    token_body = login.json()
    assert token_body["token_type"] == "bearer"
    assert token_body["access_token"]


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient) -> None:
    payload = {"username": "dupuser", "password": "password12345"}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"username": "carol", "password": "password12345"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "carol", "password": "wrong-password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


@pytest.mark.asyncio
async def test_invalid_jwt(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


def test_password_hashing_not_plaintext() -> None:
    password = "super-secret-password"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_roundtrip() -> None:
    token = create_access_token("dave")
    assert get_subject_from_token(token) == "dave"
