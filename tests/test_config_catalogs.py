from __future__ import annotations

import os
from pathlib import Path

import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

os.environ["UTU_SKIP_AUTO_SETUP"] = "1"
os.environ.setdefault("UTU_LLM_TYPE", "chat.completions")
os.environ.setdefault("UTU_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_TYPE", "chat.completions")
os.environ.setdefault("JUDGE_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_BASE_URL", "http://127.0.0.1")
os.environ.setdefault("JUDGE_LLM_API_KEY", "offline-config-validation")

from utu.config import ConfigLoader, EvalConfig, TrainingFreeGRPOConfig  # noqa: E402
from utu.config.eval_config import DataConfig  # noqa: E402
from utu.eval.experience_filter import ExperienceFilter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
REASON_CODES = {
    "broken_hydra_reference",
    "empty_stub",
    "historical_unmaintained",
    "legacy_schema",
    "missing_agent_reference",
    "missing_experience_artifact",
    "missing_generated_agent_reference",
    "placeholder_template",
}


def _names(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _legacy(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in _names(path):
        name, reason = line.split("\t", maxsplit=1)
        assert name not in result
        assert reason in REASON_CODES
        result[name] = reason
    return result


def _compose(name: str) -> dict:
    with initialize_config_dir(version_base="1.3", config_dir=str(CONFIG_DIR)):
        cfg = compose(config_name=name)
        OmegaConf.resolve(cfg)
        raw = OmegaConf.to_container(cfg, resolve=True)
    assert isinstance(raw, dict)
    return raw


def test_practice_catalog_classifies_every_non_smoke_yaml_once():
    base = CONFIG_DIR / "practice"
    actual = {
        path.relative_to(base).with_suffix("").as_posix()
        for path in base.rglob("*.yaml")
        if "smoke" not in path.stem.lower()
    }
    supported = set(_names(base / "SUPPORTED_CONFIGS.txt"))
    legacy = set(_legacy(base / "LEGACY_CONFIGS.txt"))

    assert supported.isdisjoint(legacy)
    assert supported | legacy == actual


def test_eval_catalog_classifies_every_entry_point_once():
    base = CONFIG_DIR / "eval"
    actual = {
        path.relative_to(base).with_suffix("").as_posix()
        for path in base.rglob("*.yaml")
        if path.parent != base / "data"
    }
    supported = set(_names(base / "SUPPORTED_CONFIGS.txt"))
    legacy = set(_legacy(base / "LEGACY_CONFIGS.txt"))

    assert supported.isdisjoint(legacy)
    assert supported | legacy == actual


@pytest.mark.parametrize(
    "config_name",
    _names(CONFIG_DIR / "eval" / "SUPPORTED_CONFIGS.txt"),
)
def test_supported_eval_entry_point_matches_strict_runtime(config_name: str):
    raw = _compose(f"eval/{config_name}")
    strict = EvalConfig.model_validate(raw, extra="forbid")
    runtime = ConfigLoader.load_eval_config(config_name)
    assert runtime.model_dump(mode="json") == strict.model_dump(mode="json")

    declared_filter = raw.get("experience_filter")
    if declared_filter is not None and not declared_filter.get("enabled", False):
        assert set(declared_filter) <= {"enabled"}, (
            f"{config_name} declares experience-filter parameters that runtime disables"
        )

    if strict.experience_filter.enabled and strict.experience_filter.experience_source:
        source = Path(strict.experience_filter.experience_source)
        if not source.is_absolute():
            source = ROOT / source
        assert source.is_file(), f"{config_name} requires missing experience source {source}"
        instructions = strict.agent.agent.instructions or ""
        assert not ExperienceFilter.contains_injected_experience_section(instructions), (
            f"{config_name} combines an external source with baked experiences"
        )


@pytest.mark.parametrize(
    "config_name",
    _names(CONFIG_DIR / "practice" / "SUPPORTED_CONFIGS.txt"),
)
def test_supported_practice_entry_point_has_one_runtime_contract(config_name: str):
    config = TrainingFreeGRPOConfig.model_validate(
        _compose(f"practice/{config_name}"),
        extra="forbid",
    )
    assert config.runtime.agent is not None
    assert "evaluation" not in config.model_dump(mode="python")
    assert "korgym" not in config.model_dump(mode="python")
    hierarchy = config.practice.hierarchical_learning
    assert not hierarchy.export_include_l0 or hierarchy.export_max_l0 in {None, 0}, (
        f"{config_name} must export all L0 records or no L0 records"
    )


@pytest.mark.parametrize(
    "path",
    sorted((CONFIG_DIR / "eval" / "data").glob("*.yaml")),
    ids=lambda path: path.name,
)
def test_eval_data_fragment_matches_strict_schema(path: Path):
    raw = OmegaConf.to_container(OmegaConf.load(path), resolve=True)
    DataConfig.model_validate(raw, extra="forbid")


@pytest.mark.parametrize(
    "config_name",
    [
        name
        for name, reason in _legacy(CONFIG_DIR / "practice" / "LEGACY_CONFIGS.txt").items()
        if reason == "historical_unmaintained"
    ],
)
def test_unmaintained_practice_config_is_schema_valid(config_name: str):
    TrainingFreeGRPOConfig.model_validate(
        _compose(f"practice/{config_name}"),
        extra="forbid",
    )
