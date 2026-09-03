import asyncio

import pytest

from utu.skillsbench_reliability import (
    FixedCooldownCircuitBreaker,
    classify_infra_error,
    redact_command,
)


class APIConnectionError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class RewardFileNotFoundError(Exception):
    pass


class StatusError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"status code {status_code}")


@pytest.mark.parametrize(
    ("error", "error_type", "retryable", "fatal"),
    [
        (APIConnectionError("connection failed"), "api_connection_error", True, False),
        (APITimeoutError("read timeout"), "api_timeout", True, False),
        (StatusError(429), "api_rate_limit", True, False),
        (StatusError(503), "api_5xx", True, False),
        (StatusError(401), "api_configuration_error", False, True),
        (StatusError(405), "api_configuration_error", False, True),
        (RewardFileNotFoundError("missing"), "reward_file_missing", False, False),
        (RuntimeError("Docker environment build failed"), "harbor_environment_error", True, False),
    ],
)
def test_classify_infra_error(error, error_type, retryable, fatal):
    classification = classify_infra_error(error)
    assert classification.error_type == error_type
    assert classification.retryable is retryable
    assert classification.fatal is fatal


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Error code: 405 - quota_not_enough"),
        RuntimeError("Error code: 429 - insufficient_quota"),
        RuntimeError("Error code: 405 - \u4f59\u989d\u4e0d\u8db3"),
    ],
)
def test_quota_exhaustion_is_fatal_even_with_provider_specific_status(error):
    classification = classify_infra_error(error)
    assert classification.error_type == "api_configuration_error"
    assert classification.retryable is False
    assert classification.fatal is True


def test_redact_command_hides_credentials():
    rendered = redact_command(
        [
            "harbor",
            "--ae",
            "UTU_LLM_API_KEY=top-secret",
            "--ae",
            "ACCESS_TOKEN=also-secret",
            "MODEL=deepseek-v4-pro",
        ]
    )
    assert "top-secret" not in rendered
    assert "also-secret" not in rendered
    assert "UTU_LLM_API_KEY=***" in rendered
    assert "MODEL=deepseek-v4-pro" in rendered


@pytest.mark.asyncio
async def test_circuit_breaker_reopens_with_same_fixed_cooldown():
    now = 0.0
    sleeps: list[float] = []
    probes = 0

    def clock() -> float:
        return now

    async def sleeper(delay: float) -> None:
        nonlocal now
        sleeps.append(delay)
        now += delay

    async def probe() -> None:
        nonlocal probes
        probes += 1

    breaker = FixedCooldownCircuitBreaker(
        failure_threshold=2,
        cooldown_sec=7,
        recovery_probe=probe,
        clock=clock,
        sleeper=sleeper,
    )

    for _ in range(2):
        await breaker.record_failure("api_connection_error")
    await asyncio.gather(breaker.wait_until_ready(), breaker.wait_until_ready())

    for _ in range(2):
        await breaker.record_failure("api_timeout")
    await breaker.wait_until_ready()

    assert sleeps == [7.0, 7.0]
    assert probes == 2


@pytest.mark.asyncio
async def test_failed_recovery_probe_adds_fixed_not_exponential_pause():
    now = 0.0
    sleeps: list[float] = []
    probes = 0

    def clock() -> float:
        return now

    async def sleeper(delay: float) -> None:
        nonlocal now
        sleeps.append(delay)
        now += delay

    async def probe() -> None:
        nonlocal probes
        probes += 1
        if probes == 1:
            raise APIConnectionError("still offline")

    breaker = FixedCooldownCircuitBreaker(
        failure_threshold=1,
        cooldown_sec=5,
        recovery_probe=probe,
        clock=clock,
        sleeper=sleeper,
    )
    await breaker.record_failure("api_connection_error")
    await breaker.wait_until_ready()

    assert sleeps == [5.0, 5.0]
    assert probes == 2
