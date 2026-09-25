from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf
from pydantic import ValidationError

# Hydra resolves these values while composing imported agent/evaluator configs.
# Dummy values keep this suite entirely offline and must be set before utu is
# imported because some config defaults are read at module import time.
os.environ["UTU_SKIP_AUTO_SETUP"] = "1"
os.environ.setdefault("UTU_LLM_TYPE", "chat.completions")
os.environ.setdefault("UTU_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_TYPE", "chat.completions")
os.environ.setdefault("JUDGE_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_BASE_URL", "http://127.0.0.1")
os.environ.setdefault("JUDGE_LLM_API_KEY", "offline-config-validation")

from utu.config import ConfigLoader, TrainingFreeGRPOConfig  # noqa: E402, I001


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "configs"
PRACTICE_DIR = CONFIG_DIR / "practice"
SUPPORTED_CONFIGS_MANIFEST = PRACTICE_DIR / "SUPPORTED_CONFIGS.txt"

EXPECTED = {
    Path("math/TEMPLATE_math_practice.yaml"): (
        "DAPO-Math-17k",
        "AIME24",
        "math.py",
    ),
    Path("web/TEMPLATE_webwalkerqa_practice.yaml"): (
        "AFM_web_RL",
        "WebWalkerQA",
        "webwalker.py",
    ),
    Path("logic/TEMPLATE_zebralogic_practice.yaml"): (
        "ZebraLogic-Train-100",
        "ZebraLogic-Test-30",
        "logic.py",
    ),
    Path("livecodebench/TEMPLATE_livecodebench_practice.yaml"): (
        "LiveCodeBench-Train-30",
        "LiveCodeBench-Eval-50",
        None,
    ),
    Path("skillsbench/TEMPLATE_skillsbench_practice.yaml"): (
        "SkillsBench-v1.1-FamilyHoldout-SelfContained-Train",
        "SkillsBench-v1.1-FamilyHoldout-SelfContained-Eval",
        "skillsbench.py",
    ),
    Path("korgym/TEMPLATE_word_puzzle_practice.yaml"): (
        "KORGym-WordPuzzle-Train-100",
        "KORGym-WordPuzzle-Eval-50",
        "korgym.py",
    ),
    Path("korgym/TEMPLATE_alphabetical_sorting_practice.yaml"): (
        "KORGym-AlphabeticalSorting-Train-100",
        "KORGym-AlphabeticalSorting-Eval-50",
        "korgym.py",
    ),
    Path("korgym/TEMPLATE_wordle_practice.yaml"): (
        "KORGym-Wordle-Train-100",
        "KORGym-Wordle-Eval-50",
        "korgym.py",
    ),
}

KORGYM_PROTOCOLS = {
    Path("korgym/TEMPLATE_word_puzzle_practice.yaml"): ("8-word_puzzle", 8775, 1, 1),
    Path("korgym/TEMPLATE_alphabetical_sorting_practice.yaml"): (
        "22-alphabetical_sorting",
        8776,
        3,
        1,
    ),
    Path("korgym/TEMPLATE_wordle_practice.yaml"): ("33-wordle", 8777, 5, 10),
}

PLACEHOLDER_PATTERNS = (
    re.compile(r"\bYOUR_[A-Z0-9_]+\b", re.IGNORECASE),
    re.compile(r"\b(?:TODO|FIXME|TBD|PLACEHOLDER|REPLACE_ME|CHANGEME)\b", re.IGNORECASE),
    re.compile(r"<[A-Z][A-Z0-9_ -]*>"),
)

DEPRECATED_PRACTICE_KEYS = {
    "l1_aggregation_threshold",
    "l2_aggregation_threshold",
    "similarity_thresholds_provisional",
    "include_l0_in_prompt",
    "max_l0_recent",
    "max_l0_per_game",
    "agent_save_path",
    "verify_module",
}


def _template_files() -> list[Path]:
    return sorted(PRACTICE_DIR.rglob("TEMPLATE_*.yaml"))


def _supported_config_names() -> list[str]:
    lines = SUPPORTED_CONFIGS_MANIFEST.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _config_name(path: Path) -> str:
    return path.relative_to(CONFIG_DIR).with_suffix("").as_posix()


def _compose_strict(path: Path) -> tuple[dict[str, Any], TrainingFreeGRPOConfig]:
    with initialize_config_dir(version_base="1.3", config_dir=str(CONFIG_DIR)):
        cfg = compose(config_name=_config_name(path))
        OmegaConf.resolve(cfg)
        raw = OmegaConf.to_container(cfg, resolve=True)
    assert isinstance(raw, dict)
    return raw, TrainingFreeGRPOConfig.model_validate(raw, extra="forbid")


def _walk_strings(value: Any, location: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield f"{location}.<key>", str(key)
            yield from _walk_strings(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{location}[{index}]")
    elif isinstance(value, str):
        yield location, value


def _walk_mapping_keys(value: Any, location: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            yield child_location, str(key)
            yield from _walk_mapping_keys(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_mapping_keys(child, f"{location}[{index}]")


def test_exactly_one_canonical_template_per_supported_dataset():
    actual = {path.relative_to(PRACTICE_DIR) for path in _template_files()}
    assert actual == set(EXPECTED)


def test_supported_config_manifest_is_unique_and_covers_canonical_templates():
    supported = _supported_config_names()
    assert supported
    assert len(supported) == len(set(supported))
    assert all(not name.endswith((".yaml", ".yml")) for name in supported)
    assert {path.with_suffix("").as_posix() for path in EXPECTED} <= set(supported)


@pytest.mark.parametrize("config_name", _supported_config_names())
def test_supported_practice_entry_point_composes_with_strict_schema(config_name: str):
    path = PRACTICE_DIR / f"{config_name}.yaml"
    assert path.is_file(), f"supported practice config is missing: {path}"

    raw, strict_config = _compose_strict(path)
    runtime_config = ConfigLoader.load_training_free_grpo_config(config_name)

    # The production loader and the strict audit must see the same resolved
    # object. A YAML-only key can therefore no longer disappear silently.
    assert runtime_config.model_dump(mode="json") == strict_config.model_dump(mode="json")
    assert raw["exp_id"] == strict_config.exp_id


@pytest.mark.parametrize("config_name", _supported_config_names())
def test_supported_practice_entry_point_uses_canonical_parameter_names(config_name: str):
    raw, _ = _compose_strict(PRACTICE_DIR / f"{config_name}.yaml")
    deprecated = [
        location
        for location, key in _walk_mapping_keys(raw)
        if key in DEPRECATED_PRACTICE_KEYS
    ]
    assert not deprecated, "deprecated config keys:\n" + "\n".join(deprecated)


@pytest.mark.parametrize("relative_path", EXPECTED, ids=lambda path: path.as_posix())
def test_template_composes_and_matches_strict_schema(relative_path: Path):
    path = PRACTICE_DIR / relative_path
    expected_practice, expected_eval, expected_verifier = EXPECTED[relative_path]
    _, config = _compose_strict(path)
    runtime_config = ConfigLoader.load_training_free_grpo_config(relative_path.with_suffix("").as_posix())

    assert config.exp_id.strip() and config.exp_id != "default"
    assert runtime_config.exp_id == config.exp_id
    assert runtime_config.data.practice_dataset_name == config.data.practice_dataset_name
    assert runtime_config.runtime.data == config.runtime.data
    assert config.data.practice_dataset_name == expected_practice
    assert config.runtime.data is not None
    assert config.runtime.data.dataset == expected_eval
    assert config.runtime.agent is not None
    assert config.practice.agent_objective
    assert config.practice.learning_objective
    assert config.runtime.verify_filename == expected_verifier
    if expected_verifier is not None:
        assert config.runtime.verify_func_name == "verify_func"
        assert (ROOT / "utu/practice/verify" / expected_verifier).is_file()

    positive_values = (
        config.practice.epochs,
        config.practice.batch_size,
        config.practice.grpo_n,
        config.practice.rollout_concurrency,
        config.practice.rollout_max_retries,
        config.practice.task_timeout,
        config.practice.num_experiences_per_query,
        config.practice.rollout_concurrency,
    )
    assert all(value > 0 for value in positive_values)
    truncate = config.practice.rollout_data_truncate
    if truncate is not None:
        assert truncate >= config.practice.batch_size
        assert truncate % config.practice.batch_size == 0

    hierarchy = config.practice.hierarchical_learning
    assert hierarchy.enabled is True
    assert hierarchy.clustering_enabled is True
    assert hierarchy.embedding_provider == "sentence_transformer"
    assert hierarchy.embedding_model_revision
    assert hierarchy.embedding_local_files_only is True
    assert hierarchy.l0_similarity_threshold_provisional is True
    assert hierarchy.l1_similarity_threshold_provisional is True
    assert hierarchy.allow_provisional_aggregation is False
    assert hierarchy.aggregation_temperature == 0.0
    assert hierarchy.l0_candidate_review_enabled is True
    assert hierarchy.l1_candidate_review_enabled is True
    assert hierarchy.l2_candidate_review_enabled is True


@pytest.mark.parametrize("relative_path", EXPECTED, ids=lambda path: path.as_posix())
def test_template_values_do_not_contain_unresolved_placeholders(relative_path: Path):
    source = OmegaConf.to_container(
        OmegaConf.load(PRACTICE_DIR / relative_path),
        resolve=False,
    )
    failures: list[str] = []
    for location, value in _walk_strings(source):
        for pattern in PLACEHOLDER_PATTERNS:
            if match := pattern.search(value):
                failures.append(f"{location}: {match.group(0)!r}")
    assert not failures, "\n".join(failures)


def test_template_experiment_ids_and_artifact_paths_are_unique():
    configs = [_compose_strict(PRACTICE_DIR / path)[1] for path in EXPECTED]
    exp_ids = [config.exp_id for config in configs]
    save_paths = [config.practice.hierarchical_learning.experience_save_path for config in configs]
    audit_paths = [config.practice.hierarchical_learning.clustering_audit_path for config in configs]
    assert len(exp_ids) == len(set(exp_ids))
    assert len(save_paths) == len(set(save_paths))
    assert len(audit_paths) == len(set(audit_paths))


def test_dapo_wsl_run_inherits_strategy_aware_l0_gates():
    config = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_full_hierarchy_wsl")
    hierarchy = config.practice.hierarchical_learning

    assert hierarchy.upper_pool_update_mode == "stacked_pool"
    assert hierarchy.stacked_pool_source_batch_size == 1
    assert hierarchy.candidate_review_scope == "full_pool"
    assert hierarchy.l1_validation_required is True
    assert hierarchy.strategy_aware_l0_clustering is True
    assert hierarchy.min_l0_per_l1 == 5
    assert hierarchy.min_distinct_source_tasks_per_l1 == 3
    assert hierarchy.l0_strategy_compatibility_threshold == 0.60
    assert hierarchy.l0_strategy_fallback_threshold == 0.78


def test_qwen38_resume_layout_and_export_policy_are_explicit():
    config = ConfigLoader.load_training_free_grpo_config(
        "math/math_dapo_200_qwen38_flash_stacked_2epoch_retry_20260922"
    )
    hierarchy = config.practice.hierarchical_learning

    assert config.practice.epochs == 2
    assert config.practice.batch_size == 25
    assert config.practice.rollout_data_truncate == 200
    assert config.practice.resume_from_hierarchy is True
    assert hierarchy.export_include_l0 is True
    assert hierarchy.export_max_l0 is None


def test_dapo_200_exploratory_manifest_is_signed_v2_provenance_not_strict_v3():
    path = ROOT / "configs/data/math/dapo_random_200_seed42_no_aime24_v2.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    expected_signature = manifest.pop("manifest_sha256")
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected_signature
    assert manifest["schema_version"] == 2
    assert manifest["target_dataset"] == "DAPO-Math-17k-Random-200-Seed42-No-AIME24-v2"
    assert manifest["sample_size"] == len(manifest["selected_records"]) == 200

    for config_name in (
        "math/math_dapo_200_qwen38_flash_stacked_2epoch",
        "math/math_dapo_200_qwen38_flash_stacked_2epoch_retry_20260922",
    ):
        config = ConfigLoader.load_training_free_grpo_config(config_name)
        assert config.data.require_practice_manifest is False


@pytest.mark.parametrize(
    "relative_path",
    KORGYM_PROTOCOLS,
    ids=lambda path: path.as_posix(),
)
def test_korgym_templates_keep_practice_and_evaluation_protocols_aligned(
    relative_path: Path,
):
    _, config = _compose_strict(PRACTICE_DIR / relative_path)
    practice_game = config.runtime.korgym
    for field in (
        "enabled",
        "game_name",
        "game_host",
        "game_port",
        "level",
        "max_rounds",
        "timeout_per_game",
    ):
        assert hasattr(practice_game, field)
    assert practice_game.timeout_per_game == 600
    assert (
        practice_game.game_name,
        practice_game.game_port,
        practice_game.level,
        practice_game.max_rounds,
    ) == KORGYM_PROTOCOLS[relative_path]


def test_skillsbench_template_uses_versioned_disjoint_split_contract():
    raw, config = _compose_strict(PRACTICE_DIR / "skillsbench/TEMPLATE_skillsbench_practice.yaml")
    assert "skillsbench" not in raw
    skillsbench = config.runtime.skillsbench
    assert skillsbench.enabled is True
    assert skillsbench.experience_condition == "clustered"
    assert skillsbench.require_disjoint_train_eval is True
    assert skillsbench.train_dataset_for_overlap_check == config.data.practice_dataset_name
    assert skillsbench.task_split_name == "family_holdout_self_contained_v1"
    assert skillsbench.task_split_manifest_path
    assert (ROOT / skillsbench.task_split_manifest_path).is_file()


def test_strict_validation_guard_rejects_unknown_nested_fields():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TrainingFreeGRPOConfig.model_validate(
            {"practice": {"unknown_option": True}},
            extra="forbid",
        )
