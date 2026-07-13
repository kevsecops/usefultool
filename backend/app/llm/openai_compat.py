"""OpenAI-compatible chat completions with JSON output."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.llm.provider import LLMProvider

logger = get_logger(__name__)


class LLMProviderError(Exception):
    """Raised when an LLM provider request fails."""


class OpenAICompatProvider(LLMProvider):
    """Provider for OpenAI-compatible APIs (OpenAI, Azure, local proxies)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if not settings.llm_base_url:
            raise LLMProviderError("LLM_BASE_URL is required for openai_compat provider")

    @property
    def model_name(self) -> str:
        return self._settings.llm_model

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
    ) -> dict[str, Any]:
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self._settings.llm_api_key}"

        payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self._settings.llm_max_tokens,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self._settings.llm_timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("LLM HTTP error: %s", exc)
            raise LLMProviderError(str(exc)) from exc

        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                return json.loads(content)
            if isinstance(content, dict):
                return content
            raise LLMProviderError("Unexpected LLM response content type")
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMProviderError(f"Invalid LLM response: {exc}") from exc
