"""Ollama HTTP LLM provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import LLMUnavailableError
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Communicate with a locally running Ollama server over HTTP."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.ollama_base_url.rstrip("/"),
                timeout=self._settings.ollama_timeout_seconds,
            )
        return self._client

    async def generate_review(self, prompt: str) -> str:
        return await self._generate(
            prompt,
            json_mode=True,
            temperature=0.1,
            num_predict=1024,
        )

    async def generate_text(self, prompt: str) -> str:
        return await self._generate(
            prompt,
            json_mode=False,
            temperature=0.3,
            num_predict=512,
        )

    async def generate_fix(self, prompt: str) -> str:
        """Generate a code-fix payload; prefer plain text then parse JSON."""
        return await self._generate(
            prompt,
            json_mode=False,
            temperature=0.1,
            num_predict=2048,
        )

    async def _generate(
        self,
        prompt: str,
        *,
        json_mode: bool,
        temperature: float,
        num_predict: int,
    ) -> str:
        try:
            return await self._post_generate(
                prompt,
                json_mode=json_mode,
                temperature=temperature,
                num_predict=num_predict,
            )
        except LLMUnavailableError:
            # Ollama sometimes 500s on format=json with long coding prompts.
            if json_mode:
                logger.warning("Retrying Ollama call without JSON format mode")
                return await self._post_generate(
                    prompt,
                    json_mode=False,
                    temperature=temperature,
                    num_predict=num_predict,
                )
            raise

    async def _post_generate(
        self,
        prompt: str,
        *,
        json_mode: bool,
        temperature: float,
        num_predict: int,
    ) -> str:
        client = self._get_client()
        payload: dict[str, Any] = {
            "model": self._settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        }
        if json_mode:
            payload["format"] = "json"

        try:
            logger.info(
                "Calling Ollama model=%s json=%s prompt_chars=%s timeout=%ss",
                self._settings.ollama_model,
                json_mode,
                len(prompt),
                self._settings.ollama_timeout_seconds,
            )
            response = await client.post("/api/generate", json=payload)
            if response.status_code >= 400:
                detail = response.text[:300].replace("\n", " ")
                logger.error(
                    "Ollama HTTP %s: %s",
                    response.status_code,
                    detail,
                )
                raise LLMUnavailableError(
                    f"Ollama generate failed ({response.status_code}). "
                    "The model may be overloaded — retry in a moment."
                )
        except httpx.TimeoutException as exc:
            logger.error(
                "Ollama request timed out after %ss",
                self._settings.ollama_timeout_seconds,
            )
            raise LLMUnavailableError("Ollama request timed out") from exc
        except LLMUnavailableError:
            raise
        except httpx.HTTPError as exc:
            logger.error("Ollama HTTP error: %s", exc)
            raise LLMUnavailableError("Ollama service unavailable") from exc

        data = response.json()
        text = data.get("response")
        if not isinstance(text, str) or not text.strip():
            raise LLMUnavailableError("Ollama returned an empty response")
        return text.strip()

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
