"""Dependency-light reliability primitives for SkillsBench evaluation."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .utils import get_logger

logger = get_logger(__name__)

OUTCOME_VALID = "valid"
OUTCOME_INFRA_ERROR = "infra_error"
OUTCOME_TASK_TIMEOUT = "task_timeout"
OUTCOME_FATAL_ERROR = "fatal_error"

TRANSIENT_API_ERROR_TYPES = frozenset(
    {
        "api_connection_error",
        "api_timeout",
        "api_rate_limit",
        "api_5xx",
    }
)


@dataclass(frozen=True)
class InfraErrorClassification:
    """Structured classification for an evaluation infrastructure failure."""

    error_type: str
    retryable: bool
    fatal: bool = False


def _status_code(error: BaseException | str) -> int | None:
    if isinstance(error, BaseException):
        status = getattr(error, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status

    text = str(error)
    match = re.search(r"(?:status|error code)\D{0,8}([1-5]\d{2})", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def classify_infra_error(
    error: BaseException | str,
    *,
    default_type: str = "harbor_error",
) -> InfraErrorClassification:
    """Classify API, Harbor, Docker, and verifier infrastructure failures."""

    name = type(error).__name__.lower() if isinstance(error, BaseException) else ""
    text = str(error).lower()
    status = _status_code(error)

    if "apiconnectionerror" in name or "api connection" in text or "connection error" in text:
        return InfraErrorClassification("api_connection_error", retryable=True)
    if (
        "apitimeouterror" in name
        or "api timeout" in text
        or "request timed out" in text
        or "read timeout" in text
        or "connect timeout" in text
    ):
        return InfraErrorClassification("api_timeout", retryable=True)
    if "ratelimiterror" in name or status == 429 or "rate limit" in text:
        return InfraErrorClassification("api_rate_limit", retryable=True)
    if (status is not None and 500 <= status <= 599) or "internalservererror" in name:
        return InfraErrorClassification("api_5xx", retryable=True)
    # Harbor's RewardFileNotFoundError also ends with NotFoundError, so this
    # must precede the generic API 404/configuration branch.
    if "rewardfilenotfounderror" in name or "rewardfilenotfounderror" in text:
        return InfraErrorClassification("reward_file_missing", retryable=False)
    if "no reward file" in text or "no verifier result" in text or "empty rewards" in text:
        return InfraErrorClassification("reward_file_missing", retryable=False)
    if (
        status in {400, 401, 403, 404, 422}
        or "authenticationerror" in name
        or "permissiondeniederror" in name
        or "badrequesterror" in name
        or "notfounderror" in name
    ):
        return InfraErrorClassification("api_configuration_error", retryable=False, fatal=True)
    if "docker" in text or "container" in text or "environment build" in text:
        return InfraErrorClassification("harbor_environment_error", retryable=True)
    if "harbor cli" in text or "taskrunner" in text or "trial result" in text:
        return InfraErrorClassification("harbor_runtime_error", retryable=True)
    return InfraErrorClassification(default_type, retryable=True)


def redact_command(command: Sequence[str]) -> str:
    """Render a subprocess command without exposing credentials."""

    redacted: list[str] = []
    for arg in command:
        if "=" in arg:
            key, _ = arg.split("=", 1)
            if "KEY" in key.upper() or "TOKEN" in key.upper() or "SECRET" in key.upper():
                redacted.append(f"{key}=***")
                continue
        redacted.append(arg)
    return " ".join(redacted)


class FatalSkillsBenchError(RuntimeError):
    """Abort the evaluation because its API/model configuration is invalid."""


class FixedCooldownCircuitBreaker:
    """Pause new trials after repeated transient API failures.

    Every opening uses the same cooldown. It deliberately does not implement
    exponential cooldown growth.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_sec: float = 60.0,
        recovery_probe: Callable[[], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_sec = max(0.0, float(cooldown_sec))
        self.recovery_probe = recovery_probe
        self._clock = clock
        self._sleeper = sleeper
        self._consecutive_failures = 0
        self._blocked_until = 0.0
        self._lock = asyncio.Lock()
        self._recovery_lock = asyncio.Lock()

    @property
    def blocked_until(self) -> float:
        return self._blocked_until

    async def record_success(self) -> None:
        async with self._lock:
            self._consecutive_failures = 0

    async def record_failure(self, error_type: str) -> bool:
        """Record an error and return True when this call opens the breaker."""

        if error_type not in TRANSIENT_API_ERROR_TYPES:
            return False
        async with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures < self.failure_threshold:
                return False
            self._consecutive_failures = 0
            self._blocked_until = max(self._blocked_until, self._clock() + self.cooldown_sec)
            logger.warning(
                "SkillsBench API circuit opened after %s consecutive failures; "
                "new trials pause for %.0fs.",
                self.failure_threshold,
                self.cooldown_sec,
            )
            return True

    async def wait_until_ready(self) -> None:
        """Wait for the fixed cooldown and pass an optional recovery probe."""

        while True:
            async with self._lock:
                is_blocked = self._blocked_until > 0.0
                delay = max(0.0, self._blocked_until - self._clock())
            if not is_blocked:
                return
            if delay > 0:
                await self._sleeper(delay)

            # All queued trials wake at roughly the same time. Only one of them
            # should probe the endpoint; the rest re-check the shared state.
            async with self._recovery_lock:
                async with self._lock:
                    if self._blocked_until <= 0.0:
                        return
                    delay = max(0.0, self._blocked_until - self._clock())
                if delay > 0:
                    continue

                if self.recovery_probe is not None:
                    try:
                        await self.recovery_probe()
                    except Exception as exc:  # noqa: BLE001
                        classification = classify_infra_error(exc)
                        if classification.error_type not in TRANSIENT_API_ERROR_TYPES:
                            raise
                        async with self._lock:
                            self._blocked_until = self._clock() + self.cooldown_sec
                        logger.warning(
                            "SkillsBench recovery probe failed (%s); pausing another fixed %.0fs.",
                            classification.error_type,
                            self.cooldown_sec,
                        )
                        continue

                async with self._lock:
                    if self._clock() >= self._blocked_until:
                        self._blocked_until = 0.0
                        return
