"""Bounded retries and exact-request checkpoints for experience generation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError

from ...utils import get_logger
from ...utils.security import redact_sensitive_text

logger = get_logger("utu.practice.generation_recovery")
CACHE_VERSION = "experience-generation-request-v1"


class GenerationOutputError(ValueError):
    """The model returned an unusable summary or experience envelope."""


class GenerationServiceUnavailable(RuntimeError):
    """Stop queued requests after repeated service failures in this run."""


def error_detail(error: Exception) -> str:
    """Retain the cause chain without printing credentials or entire responses."""
    parts = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(parts) < 5:
        seen.add(id(current))
        text = str(current)
        for name in ("UTU_LLM_API_KEY", "OPENAI_API_KEY", "UTU_LLM_BASE_URL"):
            secret = os.getenv(name)
            if secret:
                text = text.replace(secret, "[redacted]")
        parts.append(f"{type(current).__name__}: {redact_sensitive_text(text)[:240]}")
        current = current.__cause__
    return " <- ".join(parts)


def transient_error(error: Exception) -> bool:
    if isinstance(error, (APIConnectionError, httpx.TransportError, TimeoutError, ConnectionError)):
        return True
    if isinstance(error, APIStatusError):
        return error.status_code in {408, 409, 429} or error.status_code >= 500
    # Preserve compatibility with wrappers that expose a rate-limit error as text.
    return any(marker in str(error).lower() for marker in ("rate limit", "tpm limit"))


class GenerationRecovery:
    def __init__(
        self,
        cache_path: str | Path | None = None,
        *,
        max_attempts: int = 3,
        retry_delay: float = 2.0,
        request_timeout: float = 300.0,
        failure_limit: int = 3,
    ):
        self.cache_path = Path(cache_path) if cache_path is not None else None
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.request_timeout = request_timeout
        self.failure_limit = failure_limit
        self.consecutive_failures = 0
        self.blocked = False
        if self.cache_path is not None:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.cache_path) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS responses "
                    "(request_key TEXT PRIMARY KEY, response TEXT NOT NULL)"
                )

    def _read(self, key: str) -> str | None:
        if self.cache_path is None:
            return None
        with sqlite3.connect(self.cache_path) as connection:
            row = connection.execute("SELECT response FROM responses WHERE request_key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _write(self, key: str, response: str) -> None:
        if self.cache_path is None:
            return
        with sqlite3.connect(self.cache_path) as connection:
            connection.execute("INSERT OR REPLACE INTO responses VALUES (?, ?)", (key, response))

    async def query(
        self,
        llm: Any,
        *,
        request: dict[str, Any],
        identity: dict[str, Any],
        validate: Callable[[str], None],
        reuse_cache: bool = True,
    ) -> str:
        # Only the digest is stored: endpoint/credential differences invalidate reuse
        # without persisting those values in the checkpoint database.
        payload = {
            "version": CACHE_VERSION,
            "request": request,
            "identity": identity,
            "client_defaults": getattr(llm, "default_config", {}),
            "endpoint": str(getattr(llm, "base_url", "")),
            "credential_fingerprint": hashlib.sha256(str(getattr(llm, "api_key", "")).encode()).hexdigest(),
            "api_type": getattr(llm, "type", None),
        }
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cached = self._read(key) if reuse_cache else None
        if cached is not None:
            try:
                validate(cached)
            except GenerationOutputError:
                logger.warning("Ignoring invalid generation checkpoint %s", key[:12])
            else:
                return cached
        for attempt in range(self.max_attempts):
            if self.blocked:
                raise GenerationServiceUnavailable(
                    "Repeated model service failures; queued requests stopped. "
                    "Successful checkpoints are preserved; check connectivity before resuming."
                )
            try:
                response = await asyncio.wait_for(llm.query_one(**request), timeout=self.request_timeout)
                validate(response)
            except Exception as error:
                transient = transient_error(error)
                retryable = transient or isinstance(error, GenerationOutputError)
                if retryable and attempt + 1 < self.max_attempts:
                    delay = min(self.retry_delay * 2**attempt, 20.0)
                    logger.warning(
                        "Generation request %s attempt %d/%d failed (%s); retrying in %.1fs",
                        key[:12], attempt + 1, self.max_attempts, error_detail(error), delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                if transient:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= self.failure_limit:
                        self.blocked = True
                elif isinstance(error, APIStatusError) and error.status_code in {400, 401, 403, 404, 422}:
                    self.blocked = True
                logger.warning(
                    "Generation request %s failed after %d attempt(s): %s; queued requests stopped=%s",
                    key[:12], attempt + 1, error_detail(error), self.blocked,
                )
                raise
            else:
                self.consecutive_failures = 0
                self._write(key, response)
                return response
        raise AssertionError("unreachable generation retry state")
