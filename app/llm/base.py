"""LLM provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract interface for large-language-model providers.

    Review services depend on this interface so providers (Ollama today,
    OpenAI/vLLM/etc. later) can be swapped without changing pipeline logic.
    """

    @abstractmethod
    async def generate_review(self, prompt: str) -> str:
        """Generate a review response for the given prompt.

        Returns:
            Raw text response from the model (expected to contain JSON).
        """

    async def generate_text(self, prompt: str) -> str:
        """Generate free-form text (used for Q&A). Defaults to review generation."""
        return await self.generate_review(prompt)

    async def generate_fix(self, prompt: str) -> str:
        """Generate a code-fix suggestion. Defaults to free-form text generation."""
        return await self.generate_text(prompt)

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable."""

    async def aclose(self) -> None:
        """Optional cleanup for HTTP clients."""
        return None


def build_llm_provider(settings: Any) -> LLMProvider:
    """Factory for configured LLM providers."""
    from app.llm.ollama import OllamaProvider

    provider = getattr(settings, "llm_provider", "ollama")
    if provider == "ollama":
        return OllamaProvider(settings=settings)
    raise ValueError(f"Unsupported LLM provider: {provider}")
