from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager
from utu.practice.training_free_grpo import TrainingFreeGRPO
from utu.utils.experience_cache import ExperienceCache


class FakeHierarchy:
    def __init__(self, checkpoints, *, audited_epochs=(), audited_transitions=None):
        self.checkpoints = list(checkpoints)
        self.audited_epochs = set(audited_epochs)
        self.audited_transitions = (
            {
                (epoch, source_level, target_level)
                for epoch in self.audited_epochs
                for source_level, target_level in (("L0", "L1"), ("L1", "L2"))
            }
            if audited_transitions is None
            else set(audited_transitions)
        )
        self.process_step_experiences = AsyncMock(return_value={})
        self.review_pending_candidates = AsyncMock(
            return_value={"committed": 0, "failed": 0, "stale": 0, "skipped": 0}
        )
        self.aggregate_epoch = AsyncMock()
        self.aggregate_levels = AsyncMock()

    def get_injectable_experience_pool(self):
        return {}

    def get_l0_batch_checkpoints(self, *, run_id):
        assert run_id == "resume-run"
        return list(self.checkpoints)

    def has_aggregation_audit(
        self,
        *,
        epoch,
        source_level,
        target_level,
        run_id=None,
        allow_legacy=False,
    ):
        assert (source_level, target_level) in {("L0", "L1"), ("L1", "L2")}
        assert run_id == "resume-run"
        assert allow_legacy is True
        return (epoch, source_level, target_level) in self.audited_transitions


def checkpoint(step, *, num_batches=8):
    return {
        "epoch": step // num_batches,
        "batch": step % num_batches,
        "step": step,
        "batch_fingerprint": f"fingerprint-{step}",
        "candidate_count": 1,
    }


def make_runner(checkpoints, *, epochs=2, audited_epochs=(), audited_transitions=None):
    runner = TrainingFreeGRPO.__new__(TrainingFreeGRPO)
    runner.config = SimpleNamespace(
        exp_id="resume-run",
        practice=SimpleNamespace(epochs=epochs),
    )
    runner.hierarchical_experience_manager = FakeHierarchy(
        checkpoints,
        audited_epochs=audited_epochs,
        audited_transitions=audited_transitions,
    )
    return runner


def raw_candidate(candidate_id, *, epoch, batch, step, fingerprint):
    return SimpleNamespace(
        id=candidate_id,
        level="L0",
        run_id="resume-run",
        epoch=epoch,
        batch=batch,
        step=step,
        batch_fingerprint=fingerprint,
    )


def test_manager_exposes_one_checkpoint_per_immutable_batch():
    manager = HierarchicalExperienceManager.__new__(HierarchicalExperienceManager)
    manager._candidate_records = {
        "a": raw_candidate("a", epoch=0, batch=0, step=0, fingerprint="same"),
        "b": raw_candidate("b", epoch=0, batch=0, step=0, fingerprint="same"),
    }

    assert manager.get_l0_batch_checkpoints(run_id="resume-run") == [
        {
            "epoch": 0,
            "batch": 0,
            "step": 0,
            "batch_fingerprint": "same",
            "candidate_count": 2,
        }
    ]


def test_manager_rejects_multiple_fingerprints_for_one_batch():
    manager = HierarchicalExperienceManager.__new__(HierarchicalExperienceManager)
    manager._candidate_records = {
        "a": raw_candidate("a", epoch=0, batch=0, step=0, fingerprint="old"),
        "b": raw_candidate("b", epoch=0, batch=0, step=0, fingerprint="new"),
    }

    with pytest.raises(RuntimeError, match="ambiguous fingerprints"):
        manager.get_l0_batch_checkpoints(run_id="resume-run")


def test_resolve_hierarchical_resume_step_accepts_contiguous_15_of_16_prefix():
    runner = make_runner(
        [checkpoint(step) for step in range(15)],
        audited_epochs={0},
    )

    assert runner._resolve_hierarchical_resume_step(num_batches=8) == 15


def test_resolve_hierarchical_resume_step_rejects_gap():
    runner = make_runner([checkpoint(0), checkpoint(2)], epochs=1)

    with pytest.raises(RuntimeError, match="not a contiguous prefix"):
        runner._resolve_hierarchical_resume_step(num_batches=8)


def test_resolve_hierarchical_resume_step_leaves_missing_epoch_audit_for_finish_recovery():
    runner = make_runner([checkpoint(step) for step in range(9)])

    assert runner._resolve_hierarchical_resume_step(num_batches=8) == 9


def test_resolve_hierarchical_resume_step_rejects_batching_drift():
    changed_layout = checkpoint(8)
    changed_layout["step"] = 7
    runner = make_runner([checkpoint(step) for step in range(8)] + [changed_layout])

    with pytest.raises(RuntimeError, match="checkpoint step does not match"):
        runner._resolve_hierarchical_resume_step(num_batches=8)


def test_resume_rejects_judged_db_batch_that_does_not_match_checkpoint():
    runner = make_runner([checkpoint(0)], epochs=1)
    runner.practice_rollout_manager = SimpleNamespace(
        get_committed_batch_for_resume=Mock(return_value=[object()])
    )
    runner._candidate_generation_fingerprint = Mock(return_value="different-fingerprint")

    with pytest.raises(RuntimeError, match="does not match its hierarchy checkpoint"):
        runner._validate_resume_batch_fingerprints(
            {(0, 0): checkpoint(0)},
            epoch=0,
        )


@pytest.mark.asyncio
async def test_practice_prefix_resume_never_runs_or_aggregates_skipped_batches(monkeypatch):
    runner = make_runner(
        [checkpoint(step, num_batches=2) for step in range(3)],
        audited_epochs={0},
    )
    runner.config.practice = SimpleNamespace(
        epochs=2,
        batch_size=1,
        grpo_n=1,
        shuffle_data=False,
        rollout_data_truncate=None,
        resume_from_hierarchy=True,
        restart_step=None,
        rollout_concurrency=1,
        given_ground_truth=True,
        num_experiences_per_query=1,
    )
    runner.practice_rollout_manager = SimpleNamespace(
        load_epoch_data=Mock(side_effect=lambda *_args, **_kwargs: [object(), object()]),
        get_committed_batch_for_resume=Mock(
            side_effect=[
                [SimpleNamespace(resume_fingerprint="fingerprint-0")],
                [SimpleNamespace(resume_fingerprint="fingerprint-1")],
                [SimpleNamespace(resume_fingerprint="fingerprint-2")],
            ]
        ),
        main=AsyncMock(
            return_value=(
                [SimpleNamespace(resume_fingerprint="fingerprint-3", meta={})],
                {},
            )
        ),
    )
    runner.experience_quality_tracker = None
    runner.eval_rollout_manager = None
    runner.experience_updater = SimpleNamespace(reuse_generation_cache=True)
    runner.recorder = SimpleNamespace(
        experiment_name="resume-run",
        experiences={},
        stats=None,
        stat_update=Mock(),
    )
    runner._uses_candidate_review = Mock(return_value=True)
    runner._candidate_generation_fingerprint = Mock(
        side_effect=lambda rollouts: rollouts[0].resume_fingerprint
    )
    runner._recover_hierarchical_candidates = Mock(return_value=([{"content": "new candidate"}], False))
    runner._sync_hierarchical_recorder = Mock(return_value={})
    monkeypatch.setattr(
        ExperienceCache,
        "load_experiences",
        staticmethod(lambda **_kwargs: None),
    )

    await runner.practice()

    runner.practice_rollout_manager.main.assert_awaited_once()
    assert runner.practice_rollout_manager.main.await_args.kwargs["batch_idx"] == 1
    runner.hierarchical_experience_manager.process_step_experiences.assert_awaited_once()
    assert runner.hierarchical_experience_manager.process_step_experiences.await_args.kwargs["step"] == 3
    runner.hierarchical_experience_manager.aggregate_epoch.assert_awaited_once_with(
        1,
        run_id="resume-run",
    )


@pytest.mark.asyncio
async def test_fully_skipped_epoch_retries_staged_l0_before_deciding_to_skip_aggregation():
    runner = make_runner([], epochs=1, audited_epochs={0})
    runner.config.practice = SimpleNamespace(resume_from_hierarchy=True)
    runner.recorder = SimpleNamespace(experiment_name="resume-run")
    runner._uses_candidate_review = Mock(return_value=True)
    runner._sync_hierarchical_recorder = Mock(return_value={})
    runner.hierarchical_experience_manager.review_pending_candidates.return_value = {
        "committed": 1,
        "failed": 0,
        "stale": 0,
        "skipped": 0,
    }

    await runner._finish_epoch_hierarchy(0, fully_skipped=True)

    runner.hierarchical_experience_manager.review_pending_candidates.assert_awaited_once_with(
        candidate_level="L0"
    )
    runner.hierarchical_experience_manager.aggregate_epoch.assert_awaited_once_with(
        0,
        run_id="resume-run",
    )


@pytest.mark.asyncio
async def test_fully_skipped_epoch_with_only_l1_audit_resumes_l2_transition():
    runner = make_runner(
        [],
        epochs=1,
        audited_transitions={(0, "L0", "L1")},
    )
    runner.config.practice = SimpleNamespace(resume_from_hierarchy=True)
    runner.recorder = SimpleNamespace(experiment_name="resume-run")
    runner._uses_candidate_review = Mock(return_value=True)
    runner._sync_hierarchical_recorder = Mock(return_value={})

    await runner._finish_epoch_hierarchy(0, fully_skipped=True)

    runner.hierarchical_experience_manager.aggregate_epoch.assert_not_awaited()
    runner.hierarchical_experience_manager.aggregate_levels.assert_awaited_once_with(
        ("L2",),
        epoch=0,
        run_id="resume-run",
    )


@pytest.mark.asyncio
async def test_skipped_review_count_does_not_invalidate_complete_epoch_audits():
    runner = make_runner([], epochs=1, audited_epochs={0})
    runner.config.practice = SimpleNamespace(resume_from_hierarchy=True)
    runner.recorder = SimpleNamespace(experiment_name="resume-run")
    runner._uses_candidate_review = Mock(return_value=True)
    runner._sync_hierarchical_recorder = Mock(return_value={})
    runner.hierarchical_experience_manager.review_pending_candidates.return_value = {
        "committed": 0,
        "failed": 0,
        "stale": 0,
        "skipped": 1,
    }

    await runner._finish_epoch_hierarchy(0, fully_skipped=True)

    runner.hierarchical_experience_manager.aggregate_epoch.assert_not_awaited()
    runner.hierarchical_experience_manager.aggregate_levels.assert_not_awaited()
