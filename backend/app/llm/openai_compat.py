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


def _token_limit_payload(model: str, max_tokens: int) -> dict[str, Any]:
    """Use the token limit field supported by the target model."""
    if model.startswith(("o1", "o3", "gpt-5")):
        # Reasoning models need a larger budget; output JSON can exceed 2k tokens.
        limit = max(max_tokens, 8192)
        return {"max_completion_tokens": limit}
    return {"max_tokens": max_tokens}


def _should_retry_with_completion_tokens(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except json.JSONDecodeError:
        return False
    error = body.get("error", {})
    return error.get("param") == "max_tokens" and error.get("code") == "unsupported_parameter"


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
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            **_token_limit_payload(self._settings.llm_model, self._settings.llm_max_tokens),
        }

        try:
            timeout = self._settings.llm_timeout_seconds
            if self._settings.llm_model.startswith(("o1", "o3", "gpt-5")):
                timeout = max(timeout, 120)
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                if _should_retry_with_completion_tokens(response):
                    retry_payload = dict(payload)
                    retry_payload.pop("max_tokens", None)
                    retry_payload["max_completion_tokens"] = max(
                        self._settings.llm_max_tokens,
                        8192,
                    )
                    response = client.post(url, headers=headers, json=retry_payload)
                if response.is_error:
                    logger.warning(
                        "LLM HTTP error: status=%s body=%s",
                        response.status_code,
                        response.text[:500],
                    )
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
