"""Application-specific exceptions and HTTP mappings."""

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error with an HTTP status mapping."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "internal_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(message)


class InvalidRepositoryURLError(AppError):
    def __init__(self, message: str = "Invalid GitHub repository URL") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_repository_url",
        )


class RepositoryNotFoundError(AppError):
    def __init__(self, message: str = "Repository not found or not public") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="repository_not_found",
        )


class RepositoryTooLargeError(AppError):
    def __init__(self, message: str = "Repository exceeds size limits") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="repository_too_large",
        )


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
        )


class AuthorizationError(AppError):
    def __init__(self, message: str = "Not authorized") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_403_FORBIDDEN,
            code="forbidden",
        )


class ConflictError(AppError):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_409_CONFLICT,
            code="conflict",
        )


class RateLimitError(AppError):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="rate_limit_exceeded",
        )


class LLMUnavailableError(AppError):
    def __init__(self, message: str = "LLM service unavailable") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="llm_unavailable",
        )


class LLMResponseError(AppError):
    def __init__(self, message: str = "Failed to parse LLM response") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="llm_response_error",
        )


class ReviewNotFoundError(AppError):
    def __init__(self, message: str = "Review not found") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="review_not_found",
        )


class FindingNotFoundError(AppError):
    def __init__(self, message: str = "Finding not found on this review") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="finding_not_found",
        )


class FixNotFoundError(AppError):
    def __init__(self, message: str = "No generated fix found for this finding") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="fix_not_found",
        )


class GitHubWriteError(AppError):
    def __init__(self, message: str = "Unable to create GitHub pull request") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="github_write_error",
        )


def error_payload(exc: AppError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": exc.code,
            "message": exc.message,
        }
    }
    if exc.details:
        payload["error"]["details"] = exc.details
    return payload


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc))


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": message,
            }
        },
        headers=getattr(exc, "headers", None),
    )


def _jsonable_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make Pydantic error dicts JSON-serializable."""
    cleaned: list[dict[str, Any]] = []
    for err in errors:
        item = dict(err)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                key: (str(value) if isinstance(value, Exception) else value)
                for key, value in ctx.items()
            }
        cleaned.append(item)
    return cleaned


async def validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = _jsonable_errors(exc.errors())
    # Surface invalid GitHub URLs as 400 (business validation), not 422.
    for err in errors:
        loc = err.get("loc") or ()
        msg = str(err.get("msg", "")).lower()
        if "repository_url" in loc or "github" in msg or "repository url" in msg:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": {
                        "code": "invalid_repository_url",
                        "message": "Invalid GitHub repository URL",
                        "details": {"errors": errors},
                    }
                },
            )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": errors},
            }
        },
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    # Never expose stack traces or internal details to clients.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
            }
        },
    )
