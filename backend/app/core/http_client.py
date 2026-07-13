"""SSR-safe HTTP client with retries and exponential backoff."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

RETRYABLE_STATUS_CODES = frozenset({403, 429, 500, 502, 503, 504})


class HttpClientError(Exception):
    """Raised when an HTTP request fails after retries or validation."""


class HttpClient:
    """Async HTTP client with allowlisted hosts, retries, and response size limits."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        max_response_bytes: int = 50 * 1024 * 1024,
        allowed_hosts: frozenset[str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_response_bytes = max_response_bytes
        self.allowed_hosts = allowed_hosts or frozenset()
        self._transport = transport

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise HttpClientError(f"Invalid URL scheme: {parsed.scheme}")
        host = parsed.hostname
        if not host:
            raise HttpClientError("URL missing hostname")
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise HttpClientError(f"Host not allowlisted: {host}")

    def _extract_next_url(self, response: httpx.Response, data: dict[str, Any]) -> str | None:
        pagination = data.get("pagination")
        if isinstance(pagination, dict):
            next_url = pagination.get("next")
            if isinstance(next_url, str) and next_url:
                return next_url

        link_header = response.headers.get("link", "")
        for part in link_header.split(","):
            section = part.strip()
            if 'rel="next"' in section or "rel=next" in section:
                url_part = section.split(";")[0].strip()
                if url_part.startswith("<") and url_part.endswith(">"):
                    return url_part[1:-1]
        return None

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data, _ = await self._request_json(url, params=params)
        return data

    async def get_json_paginated(self, url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        next_url: str | None = url
        next_params = params

        while next_url:
            data, response = await self._request_json(next_url, params=next_params)
            pages.append(data)
            next_url = self._extract_next_url(response, data)
            next_params = None

        return pages

    async def _request_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], httpx.Response]:
        self._validate_url(url)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    transport=self._transport,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(
                        url,
                        params=params,
                        headers={"User-Agent": self.user_agent, "Accept": "application/geo+json"},
                    )

                    if len(response.content) > self.max_response_bytes:
                        raise HttpClientError(
                            f"Response exceeds max size ({self.max_response_bytes} bytes)"
                        )

                    if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                        delay = 2**attempt
                        logger.warning(
                            "HTTP %s from %s, retrying in %ss (attempt %s/%s)",
                            response.status_code,
                            url,
                            delay,
                            attempt + 1,
                            self.max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                    response.raise_for_status()

                    data = response.json()
                    if not isinstance(data, dict):
                        raise HttpClientError("Expected JSON object response")
                    return data, response

            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = 2**attempt
                    logger.warning("Timeout for %s, retrying in %ss", url, delay)
                    await asyncio.sleep(delay)
                    continue
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code not in RETRYABLE_STATUS_CODES:
                    raise HttpClientError(str(exc)) from exc
                if attempt < self.max_retries:
                    delay = 2**attempt
                    await asyncio.sleep(delay)
                    continue
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = 2**attempt
                    await asyncio.sleep(delay)
                    continue

        raise HttpClientError(f"Request failed after {self.max_retries + 1} attempts: {last_error}")
