from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
