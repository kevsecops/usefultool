"""Ollama LLM provider — thin wrapper over OpenAI-compatible endpoint."""

from __future__ import annotations

from app.core.config import Settings
from app.llm.openai_compat import OpenAICompatProvider


class OllamaLLMProvider(OpenAICompatProvider):
    """Ollama exposes an OpenAI-compatible API at /v1/chat/completions."""

    def __init__(self, settings: Settings) -> None:
        if not settings.llm_base_url:
            # Default Ollama endpoint reachable from Docker via host.docker.internal
            settings = settings.model_copy(
                update={"llm_base_url": "http://host.docker.internal:11434/v1"}
            )
        super().__init__(settings)
