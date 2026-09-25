from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from utu.config import ConfigLoader
from utu.config.practice_config import HierarchicalLearningConfig, PracticeArguments
from utu.practice.training_free_grpo import TrainingFreeGRPO


def test_hierarchy_runtime_knobs_are_typed_and_use_canonical_names():
    config = HierarchicalLearningConfig(
        upper_pool_update_mode="stacked_pool",
        stacked_pool_source_batch_size=2,
        candidate_review_scope="full_pool",
        aggregation_disable_thinking=True,
        aggregation_max_tokens=2048,
        min_l0_per_l1_candidate=2,
        min_distinct_source_tasks_per_l1=2,
        min_distinct_source_tasks_per_l1_candidate=2,
        l1_validation_required=True,
        min_distinct_source_tasks_per_l1_promotion=2,
        min_validation_trials_per_l1=20,
        min_distinct_validation_tasks_per_l1=20,
        min_l1_validation_net_help=1,
        max_l1_validation_harms=0,
        strategy_aware_l0_clustering=True,
        l0_strategy_compatibility_threshold=0.6,
        l0_strategy_fallback_threshold=0.78,
        l0_strategy_ignore_failure_mode=False,
        export_include_l0=False,
        export_max_l0=None,
    )

    assert config.upper_pool_update_mode == "stacked_pool"
    assert config.l1_validation_required is True
    assert config.strategy_aware_l0_clustering is True
    assert config.export_include_l0 is False
    assert config.export_max_l0 is None
    dumped = config.model_dump(exclude_none=False)
    assert "export_include_l0" in dumped and "include_l0_in_prompt" not in dumped
    assert "export_max_l0" in dumped and "max_l0_recent" not in dumped


def test_removed_global_similarity_gate_is_rejected():
    with pytest.raises(ValidationError):
        HierarchicalLearningConfig(similarity_thresholds_provisional=False)
    with pytest.raises(ValidationError):
        HierarchicalLearningConfig(clustering_method="agglomerative")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"aggregation_max_tokens": 0},
        {"l0_strategy_compatibility_threshold": 0.8, "l0_strategy_fallback_threshold": 0.7},
        {"l1_confidence_threshold": 1.1},
        {"max_l1_total": -1},
        {"experience_save_path": ""},
        {"clustering_audit_path": "  "},
    ],
)
def test_hierarchy_runtime_knob_constraints_fail_closed(kwargs):
    with pytest.raises(ValidationError):
        HierarchicalLearningConfig(**kwargs)


def test_practice_resume_and_sampling_controls_are_validated():
    config = PracticeArguments(
        rollout_max_retries=3,
        mistake_focus_ratio=0.4,
        data_seed=7,
        resume_from_hierarchy=True,
        hierarchical_learning={"enabled": True},
    )

    assert config.rollout_max_retries == 3
    assert config.mistake_focus_ratio == 0.4
    assert config.data_seed == 7
    with pytest.raises(ValidationError, match="mutually exclusive"):
        PracticeArguments(
            restart_step=1,
            resume_from_hierarchy=True,
            hierarchical_learning={"enabled": True},
        )
    with pytest.raises(ValidationError):
        PracticeArguments(rollout_concurrency=0)
    with pytest.raises(ValidationError):
        PracticeArguments(num_experiences_per_query=0)


def test_practice_rollout_adapter_uses_canonical_runtime():
    config = ConfigLoader.load_training_free_grpo_config("math/TEMPLATE_math_practice")
    config.exp_id = "root-run"
    config.runtime.agent.model.model_settings.temperature = 0.25
    config.practice.rollout_temperature = 0.8
    config.practice.rollout_concurrency = 7
    config.practice.grpo_n = 3
    runner = TrainingFreeGRPO(config)

    derived = runner._make_practice_eval_config()

    assert derived.exp_id == "root-run"
    assert derived.pass_k == 3
    assert derived.concurrency == 7
    assert derived.log_trajectory_to_db is False
    assert derived.agent.model.model_settings.temperature == 0.8
    assert config.runtime.agent.model.model_settings.temperature == 0.25


def test_korgym_runtime_is_not_duplicated():
    config = ConfigLoader.load_training_free_grpo_config(
        "korgym/TEMPLATE_word_puzzle_practice"
    )
    assert config.runtime.korgym.enabled is True
    assert "korgym" not in config.model_dump(mode="python")


@pytest.mark.parametrize(
    ("include_l0", "limit", "expected_all_calls", "expected_recent_calls"),
    [
        (True, None, 1, 0),
        (True, 0, 0, 0),
        (True, 2, 0, 1),
        (False, None, 0, 0),
    ],
)
def test_final_agent_l0_export_has_explicit_all_none_and_recent_semantics(
    tmp_path,
    monkeypatch,
    include_l0,
    limit,
    expected_all_calls,
    expected_recent_calls,
):
    import utu.practice.training_free_grpo as training_module

    config = ConfigLoader.load_training_free_grpo_config("math/TEMPLATE_math_practice")
    config.exp_id = "root-export-run"
    hierarchy = config.practice.hierarchical_learning
    hierarchy.export_include_l0 = include_l0
    hierarchy.export_max_l0 = limit
    runner = TrainingFreeGRPO(config)
    runner.original_temperature = config.runtime.agent.model.model_settings.temperature
    manager = Mock()
    manager.get_injectable_l2_experiences.return_value = []
    manager.get_injectable_l1_experiences.return_value = []
    manager.get_injectable_l0_experiences.return_value = [
        {"content": "all-l0-a"},
        {"content": "all-l0-b"},
    ]
    manager.get_recent_injectable_l0_experiences.return_value = [
        {"content": "recent-l0"}
    ]
    runner.hierarchical_experience_manager = manager
    monkeypatch.setattr(training_module, "DIR_ROOT", tmp_path)
    (tmp_path / "configs" / "agents" / "practice").mkdir(parents=True)

    output_path = runner._create_agent_config_with_experiences({})

    assert output_path.endswith("root-export-run_agent.yaml")
    assert manager.get_injectable_l0_experiences.call_count == expected_all_calls
    assert manager.get_recent_injectable_l0_experiences.call_count == expected_recent_calls
    if expected_recent_calls:
        manager.get_recent_injectable_l0_experiences.assert_called_once_with(2)
