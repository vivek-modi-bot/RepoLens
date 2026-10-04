"""Health check endpoints."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.llm.base import build_llm_provider

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service health check")
async def health() -> dict:
    settings = get_settings()
    llm = build_llm_provider(settings)
    try:
        llm_ok = await llm.health_check()
    finally:
        await llm.aclose()

    status = "ok" if llm_ok else "degraded"
    return {
        "status": status,
        "service": settings.app_name,
        "version": settings.app_version,
        "llm_provider": settings.llm_provider,
        "llm_available": llm_ok,
    }
