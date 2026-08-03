from types import SimpleNamespace

import pytest

from scripts.experiments.run_skillsbench_paired_eval import build_paired_schedule
from scripts.utils.view_benchmark_results import _calc_stats_skillsbench
from utu.eval.processer.skillsbench_processor import SkillsBenchProcesser


def _config(expected_num_tasks: int = 2):
    return SimpleNamespace(
        pass_k=3,
        skillsbench=SimpleNamespace(
            expected_num_tasks=expected_num_tasks,
            require_complete_coverage=True,
        ),
    )


def _sample(
    task_id: str,
    trial_index: int,
    reward: float | None,
    *,
    stage: str = "judged",
    eval_status: str = "valid",
    error_type: str | None = None,
):
    meta = {
        "evaluation_protocol": "skillsbench_v4",
        "eval_status": eval_status,
        "task_id": task_id,
        "trial_index": trial_index,
        "expected_num_tasks": 2,
        "expected_trials_per_task": 3,
        "paper_domain": "Software Engineering",
        "paper_diff": "medium",
    }
    if error_type:
        meta["infra_error_type"] = error_type
    return SimpleNamespace(
        meta=meta,
        stage=stage,
        reward=reward,
        dataset_index=0 if task_id == "task-a" else 1,
        time_cost=1.0,
        exp_id="skillsbench_test_v4",
        id=trial_index,
    )


def _complete_samples():
    return [
        _sample("task-a", 0, 1.0),
        _sample("task-a", 1, 0.0),
        _sample("task-a", 2, 1.0),
        _sample("task-b", 0, 0.0),
        _sample("task-b", 1, 0.0),
        _sample("task-b", 2, 1.0),
    ]


def test_processor_publishes_only_complete_unique_trials():
    metrics = SkillsBenchProcesser(_config()).calculate_metrics(_complete_samples())

    assert metrics["publishable"] is True
    assert metrics["valid_trials"] == 6
    assert metrics["tasks_with_full_valid_trials"] == 2
    assert metrics["task_macro_pass_rate"] == pytest.approx(0.5)
    assert metrics["pass_rate"] == pytest.approx(0.5)


def test_infra_error_is_not_counted_as_verifier_failure():
    samples = _complete_samples()
    samples[-1] = _sample(
        "task-b",
        2,
        None,
        stage="infra_error",
        eval_status="infra_error",
        error_type="api_connection_error",
    )
    metrics = SkillsBenchProcesser(_config()).calculate_metrics(samples)

    assert metrics["publishable"] is False
    assert metrics["pass_rate"] is None
    assert metrics["valid_trials"] == 5
    assert metrics["infra_error_trials"] == 1
    assert metrics["infra_error_types"] == {"api_connection_error": 1}


def test_task_timeout_remains_a_valid_zero_reward_trial():
    samples = _complete_samples()
    samples[-1] = _sample("task-b", 2, 0.0)
    samples[-1].meta["trial_outcome"] = "task_timeout"
    metrics = SkillsBenchProcesser(_config()).calculate_metrics(samples)

    assert metrics["publishable"] is True
    assert metrics["valid_trials"] == 6
    assert metrics["infra_error_trials"] == 0


def test_duplicate_trial_index_blocks_publication():
    samples = _complete_samples()
    samples[-1].meta["trial_index"] = 1
    metrics = SkillsBenchProcesser(_config()).calculate_metrics(samples)

    assert metrics["publishable"] is False
    assert metrics["invalid_trial_index_tasks"] == ["task-b"]


def test_result_viewer_withholds_incomplete_v4_metrics():
    samples = _complete_samples()
    samples[-1] = _sample(
        "task-b",
        2,
        None,
        stage="infra_error",
        eval_status="infra_error",
        error_type="api_5xx",
    )
    stats = _calc_stats_skillsbench(samples)

    assert stats["publishable"] is False
    assert stats["pass_rate"] is None
    assert stats["valid_trials"] == 5
    assert stats["infra_error_trials"] == 1


def test_paired_schedule_is_deterministic_and_balanced():
    baseline = [
        _sample(task, trial, None, stage="init", eval_status="pending")
        for task in ("a", "b")
        for trial in range(3)
    ]
    experience = [
        _sample(task, trial, None, stage="init", eval_status="pending")
        for task in ("a", "b")
        for trial in range(3)
    ]

    first = build_paired_schedule(baseline, experience, seed=17)
    second = build_paired_schedule(baseline, experience, seed=17)

    assert [item.key for item in first] == [item.key for item in second]
    assert sum(item.order[0] == "baseline" for item in first) == 3
    assert sum(item.order[0] == "experience" for item in first) == 3
    assert all(item.baseline is not None and item.experience is not None for item in first)
