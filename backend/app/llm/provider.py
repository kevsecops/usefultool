"""LLM provider abstraction and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.config import Settings, get_settings


class LLMProvider(ABC):
    """Abstract interface for LLM completion with JSON output."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier for persistence."""

    @abstractmethod
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
    ) -> dict[str, Any]:
        """Return parsed JSON object from the LLM response."""


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the configured LLM provider."""
    settings = settings or get_settings()

    if settings.demo_mode or settings.llm_provider == "mock":
        from app.llm.mock import MockLLMProvider

        return MockLLMProvider()

    if settings.llm_provider == "ollama":
        from app.llm.ollama import OllamaLLMProvider

        return OllamaLLMProvider(settings)

    from app.llm.openai_compat import OpenAICompatProvider

    return OpenAICompatProvider(settings)
