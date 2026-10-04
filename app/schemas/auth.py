"""Authentication request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(min_length=8, max_length=128)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if value.isspace():
            raise ValueError("Password cannot be blank")
        return value


class UserLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    created_at: datetime
    github_token_configured: bool = False


class UserProfileUpdateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    github_token: str | None = Field(
        default=None,
        max_length=512,
        description="GitHub PAT with repo scope. Stored encrypted. Omit to leave unchanged.",
    )
    clear_github_token: bool = Field(
        default=False,
        description="If true, remove the stored GitHub token from the profile.",
    )

    @field_validator("github_token")
    @classmethod
    def validate_github_token(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 8:
            raise ValueError("GitHub token looks too short")
        return cleaned
