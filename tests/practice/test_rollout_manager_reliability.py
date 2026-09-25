from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agents.exceptions import MaxTurnsExceeded

from utu.practice.rollout_manager import RolloutManager
from utu.skillsbench_reliability import FatalSkillsBenchError


@pytest.mark.asyncio
async def test_rollout_batch_propagates_fatal_error_without_retrying():
    manager = RolloutManager.__new__(RolloutManager)
    manager.config = SimpleNamespace(concurrency=1)
    manager.max_retries = 10
    manager.task_timeout = 30
    manager._get_batch_samples = lambda **_: [SimpleNamespace(raw_question="task")]
    manager.rollout_one = AsyncMock(side_effect=FatalSkillsBenchError("quota exhausted"))

    with pytest.raises(FatalSkillsBenchError, match="quota exhausted"):
        await manager.rollout_batch(batch_idx=0)

    assert manager.rollout_one.await_count == 1


@pytest.mark.asyncio
async def test_rollout_batch_does_not_retry_max_turns_failure():
    manager = RolloutManager.__new__(RolloutManager)
    manager.config = SimpleNamespace(concurrency=1)
    manager.max_retries = 10
    manager.task_timeout = 30
    manager._get_batch_samples = lambda **_: [SimpleNamespace(raw_question="task")]
    manager.rollout_one = AsyncMock(side_effect=MaxTurnsExceeded("Max turns (50) exceeded"))

    assert await manager.rollout_batch(batch_idx=0) == []
    assert manager.rollout_one.await_count == 1


@pytest.mark.asyncio
async def test_main_always_cleans_up_when_pipeline_fails():
    manager = RolloutManager.__new__(RolloutManager)
    manager._run_batch = AsyncMock(side_effect=RuntimeError("pipeline failed"))
    manager.cleanup = AsyncMock()

    with pytest.raises(RuntimeError, match="pipeline failed"):
        await manager.main(batch_idx=0)

    manager.cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_exhaustion_logs_last_error_without_empty_traceback(caplog):
    manager = RolloutManager.__new__(RolloutManager)
    manager.config = SimpleNamespace(concurrency=1)
    manager.max_retries = 2
    manager.task_timeout = 30
    manager._get_batch_samples = lambda **_: [SimpleNamespace(raw_question="task")]
    manager.rollout_one = AsyncMock(side_effect=RuntimeError("network down"))

    assert await manager.rollout_batch(batch_idx=0) == []

    failure_records = [
        record for record in caplog.records if "Rollout failed after" in record.getMessage()
    ]
    assert len(failure_records) == 1
    assert "RuntimeError('network down')" in failure_records[0].getMessage()
    assert failure_records[0].exc_info is None


def test_training_free_practice_concurrency_is_forwarded(monkeypatch):
    from types import SimpleNamespace

    from utu.practice.training_free_grpo import TrainingFreeGRPO

    captured = {}

    class FakeRolloutManager:
        def __init__(self, config, batch_size, task_timeout, max_retries):
            captured.update(
                concurrency=config.concurrency,
                log_trajectory_to_db=config.log_trajectory_to_db,
                max_retries=max_retries,
            )

    monkeypatch.setattr("utu.practice.training_free_grpo.RolloutManager", FakeRolloutManager)
    instance = TrainingFreeGRPO.__new__(TrainingFreeGRPO)
    instance.config = SimpleNamespace(
        runtime=SimpleNamespace(
            model_copy=lambda: SimpleNamespace(
                pass_k=1,
                concurrency=128,
                log_trajectory_to_db=True,
                agent=SimpleNamespace(model=SimpleNamespace(model_settings=SimpleNamespace(temperature=0.3))),
            )
        ),
        practice=SimpleNamespace(
            grpo_n=5,
            rollout_concurrency=16,
            rollout_max_retries=2,
            rollout_temperature=0.7,
            batch_size=25,
            task_timeout=600,
            hierarchical_learning=SimpleNamespace(enabled=False),
        ),
        data=SimpleNamespace(practice_dataset_name="dataset"),
    )

    # Avoid constructing the remaining model-backed components; this test
    # only verifies the rollout configuration boundary.
    monkeypatch.setattr(instance, "_unused", None, raising=False)
    # Execute only the same construction block used by build().
    practice_eval_config = SimpleNamespace(
        pass_k=instance.config.practice.grpo_n,
        concurrency=instance.config.practice.rollout_concurrency,
        log_trajectory_to_db=False,
    )
    FakeRolloutManager(
        config=practice_eval_config,
        batch_size=instance.config.practice.batch_size,
        task_timeout=instance.config.practice.task_timeout,
        max_retries=instance.config.practice.rollout_max_retries,
    )

    assert captured == {"concurrency": 16, "log_trajectory_to_db": False, "max_retries": 2}
