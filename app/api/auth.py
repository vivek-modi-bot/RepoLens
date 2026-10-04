"""Authentication API routes."""

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserProfileUpdateRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new user",
)
async def register(payload: UserRegisterRequest, db: DbSession) -> UserResponse:
    service = AuthService(db)
    return await service.register(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain a JWT access token",
)
async def login(payload: UserLoginRequest, db: DbSession) -> TokenResponse:
    service = AuthService(db)
    return await service.login(payload.username, payload.password)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated user's profile",
)
async def me(current_user: CurrentUser, db: DbSession) -> UserResponse:
    service = AuthService(db)
    return await service.get_profile(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update profile settings (email, GitHub token)",
)
async def update_me(
    payload: UserProfileUpdateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> UserResponse:
    service = AuthService(db)
    return await service.update_profile(current_user, payload)
