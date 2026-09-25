from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import regen_practice_agent_yaml as regen
from utu.config import ConfigLoader
from utu.practice.experience_models import ExperienceRecord


def _snapshot(path: Path) -> None:
    records = [
        ExperienceRecord(
            id=f"L0-{index}",
            level="L0",
            content=content,
            created_at=f"2026-01-0{index + 1}T00:00:00+00:00",
        ).public_dict()
        for index, content in enumerate(("old lesson", "middle lesson", "newest lesson"))
    ]
    path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "experience_output_language": "same_as_input",
                "l0_candidates": [],
                "l1_candidates": [],
                "l2_candidates": [],
                "l0_experiences": records,
                "l1_experiences": [],
                "l2_experiences": [],
                "l0_archive": [],
                "l1_archive": [],
                "l2_archive": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("limit", "expected", "excluded"),
    [
        (None, ("old lesson", "middle lesson", "newest lesson"), ()),
        (0, (), ("old lesson", "middle lesson", "newest lesson")),
        (2, ("middle lesson", "newest lesson"), ("old lesson",)),
    ],
)
def test_regeneration_uses_configured_l0_export_policy(
    tmp_path,
    monkeypatch,
    limit,
    expected,
    excluded,
):
    snapshot = tmp_path / "hierarchy.json"
    output = tmp_path / "nested" / "agent.yaml"
    _snapshot(snapshot)

    config = ConfigLoader.load_training_free_grpo_config("math/TEMPLATE_math_practice")
    config.practice.hierarchical_learning.export_include_l0 = True
    config.practice.hierarchical_learning.export_max_l0 = limit
    monkeypatch.setattr(
        regen.ConfigLoader,
        "load_training_free_grpo_config",
        lambda name: config if name == "arbitrary/config" else None,
    )

    generated = regen.regenerate_agent_config(
        "arbitrary/config",
        experiences_path=snapshot,
        output_path=output,
    )

    assert generated == output.resolve()
    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    instructions = payload["agent"]["instructions"]
    for lesson in expected:
        assert lesson in instructions
    for lesson in excluded:
        assert lesson not in instructions


def test_cli_requires_named_config_and_forwards_only_explicit_overrides(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        regen.build_parser().parse_args([])

    calls = []
    output = tmp_path / "agent.yaml"

    def fake_regenerate(config_name, *, experiences_path=None, output_path=None):
        calls.append((config_name, experiences_path, output_path))
        return output

    monkeypatch.setattr(regen, "regenerate_agent_config", fake_regenerate)

    assert regen.main(["--config_name", "logic/custom_run"]) == 0
    assert calls == [("logic/custom_run", None, None)]


def test_snapshot_loader_uses_offline_dependencies(tmp_path, monkeypatch):
    snapshot = tmp_path / "hierarchy.json"
    _snapshot(snapshot)
    config = ConfigLoader.load_training_free_grpo_config("math/TEMPLATE_math_practice")
    config.practice.hierarchical_learning.experience_save_path = str(snapshot)

    class NetworkClientMustNotBeConstructed:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("network-backed LLM client was constructed")

    monkeypatch.setattr(
        "utu.practice.hierarchical_experience_manager.SimplifiedAsyncOpenAI",
        NetworkClientMustNotBeConstructed,
    )

    manager = regen._load_manager(config)

    assert isinstance(manager.clusterer.embedding_provider, regen.HashingEmbeddingProvider)
    assert [item["content"] for item in manager.get_injectable_l0_experiences()] == [
        "old lesson",
        "middle lesson",
        "newest lesson",
    ]
