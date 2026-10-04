"""Authentication and user management service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.core.token_crypto import decrypt_secret, encrypt_secret
from app.models.user import User
from app.schemas.auth import (
    TokenResponse,
    UserProfileUpdateRequest,
    UserRegisterRequest,
    UserResponse,
)


class AuthService:
    """Username/password authentication with JWT tokens.

    Designed so additional identity providers (Auth0, GitHub OAuth) can be
    introduced later without changing API route contracts.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def register(self, payload: UserRegisterRequest) -> UserResponse:
        existing = await self._db.execute(
            select(User).where(User.username == payload.username)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("Username already registered")

        user = User(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
        )
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)
        return self._to_response(user)

    async def login(self, username: str, password: str) -> TokenResponse:
        result = await self._db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid username or password")

        token = create_access_token(subject=user.username)
        return TokenResponse(access_token=token, token_type="bearer")

    async def get_profile(self, user: User) -> UserResponse:
        return self._to_response(user)

    async def update_profile(
        self, user: User, payload: UserProfileUpdateRequest
    ) -> UserResponse:
        if payload.email is not None:
            cleaned_email = payload.email.strip()
            user.email = cleaned_email or None

        if payload.clear_github_token:
            user.github_token_encrypted = None
        elif payload.github_token:
            user.github_token_encrypted = encrypt_secret(payload.github_token)

        await self._db.commit()
        await self._db.refresh(user)
        return self._to_response(user)

    def get_github_token(self, user: User) -> str | None:
        if not user.github_token_encrypted:
            return None
        return decrypt_secret(user.github_token_encrypted)

    def _to_response(self, user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            created_at=user.created_at,
            github_token_configured=bool(user.github_token_encrypted),
        )
