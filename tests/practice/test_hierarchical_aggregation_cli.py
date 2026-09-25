from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("UTU_SKIP_AUTO_SETUP", "1")
os.environ.setdefault("UTU_LLM_TYPE", "chat.completions")
os.environ.setdefault("UTU_LLM_MODEL", "offline-test-model")

from scripts.experiments import aggregate_hierarchical_experiences as cli  # noqa: E402
from utu.practice.dataset_manifest_guard import canonical_sha256  # noqa: E402


class FakeHierarchyConfig(SimpleNamespace):
    def model_copy(self, *, deep: bool = False):
        return copy.deepcopy(self) if deep else copy.copy(self)


def _config(snapshot: Path):
    hierarchy = FakeHierarchyConfig(
        enabled=True,
        experience_save_path=str(snapshot),
        clustering_audit_path=str(snapshot.with_suffix(".audit.jsonl")),
        aggregation_temperature=0.0,
        l1_candidate_review_enabled=True,
        l2_candidate_review_enabled=True,
        l0_similarity_threshold_provisional=True,
        l1_similarity_threshold_provisional=False,
        allow_provisional_aggregation=False,
    )
    provider = SimpleNamespace(type="chat.completions", model="offline-test-model")
    agent = SimpleNamespace(model=SimpleNamespace(model_provider=provider))
    return SimpleNamespace(
        practice=SimpleNamespace(
            hierarchical_learning=hierarchy,
            agent_objective="solve tasks",
            learning_objective="learn reusable evidence-backed strategies",
        ),
        runtime=SimpleNamespace(agent=agent),
        data=SimpleNamespace(require_practice_manifest=False),
    )


def _write_snapshot(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "l0_candidates": [],
                "l1_candidates": [],
                "l2_candidates": [],
                "l0_experiences": [
                    {
                        "id": "L0_one",
                        "content": "verify the final result",
                        "lifecycle_status": "active",
                        "aggregation_status": "pending",
                    },
                    {
                        "id": "L0_stale",
                        "content": "old result",
                        "lifecycle_status": "needs_review",
                        "aggregation_status": "pending",
                    },
                ],
                "l0_archive": [{"id": "L0_old", "content": "archived"}],
                "l1_experiences": [],
                "l1_archive": [],
                "l2_experiences": [],
                "l2_archive": [],
            }
        ),
        encoding="utf-8",
    )


def _write_strict_manifest(path: Path, dataset: str) -> str:
    source_id = f"{dataset}:0"
    tasks = [
        {
            "task_id": "0",
            "namespaced_task_id": source_id,
            "target_index": 0,
        }
    ]
    manifest = {
        "schema_version": 3,
        "target_dataset": dataset,
        "dataset": {
            "name": dataset,
            "namespace": dataset,
            "version": "fixture-v3",
            "inventory_task_count": 1,
            "inventory_sha256": canonical_sha256(tasks),
        },
        "tasks": tasks,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return source_id


def _set_all_snapshot_sources(path: Path, source_id: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for level in ("l0", "l1", "l2"):
        for suffix in ("experiences", "archive", "candidates"):
            records = payload.get(f"{level}_{suffix}", [])
            values = records.values() if isinstance(records, dict) else records
            for record in values:
                record["source_task_ids"] = [source_id]
    path.write_text(json.dumps(payload), encoding="utf-8")


def _args(snapshot: Path, *, level: str = "all", execute: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        config_name="math/offline",
        snapshot=str(snapshot),
        level=level,
        epoch=7,
        execute=execute,
    )


def test_parse_args_is_plan_only_unless_execute_is_explicit():
    planned = cli.parse_args(["--config-name", "math/example"])
    executed = cli.parse_args(["--config-name", "math/example", "--execute"])

    assert planned.execute is False
    assert planned.level == "all"
    assert executed.execute is True
    assert cli._threshold_gate_view(
        SimpleNamespace(
            l0_similarity_threshold_provisional=True,
            l1_similarity_threshold_provisional=True,
            allow_provisional_aggregation=False,
        )
    ) == {
        "l0_similarity_threshold_provisional": True,
        "l1_similarity_threshold_provisional": True,
        "allow_provisional_aggregation": False,
    }


@pytest.mark.asyncio
async def test_plan_only_does_not_construct_manager_or_change_snapshot(tmp_path, monkeypatch, capsys):
    snapshot = tmp_path / "hierarchy.json"
    _write_snapshot(snapshot)
    before = snapshot.read_bytes()
    config = _config(snapshot)
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)

    class ForbiddenManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("plan-only mode must not construct the manager")

    monkeypatch.setattr(cli, "HierarchicalExperienceManager", ForbiddenManager)
    report = await cli.run(_args(snapshot))

    assert snapshot.read_bytes() == before
    assert report["mode"] == "plan_only"
    assert report["snapshot_changed"] is False
    assert report["before"] == report["after"]
    assert report["before"]["stats"]["levels"]["L0"]["active_count"] == 1
    assert report["before"]["stats"]["levels"]["L0"]["needs_review_count"] == 1
    assert report["before"]["stats"]["levels"]["L0"]["pending_aggregation_count"] == 1
    assert json.loads(capsys.readouterr().out)["mode"] == "plan_only"
    assert "TrainingFreeGRPO" not in cli.__dict__


@pytest.mark.asyncio
async def test_strict_plan_validates_snapshot_sources_and_reports_evidence(
    tmp_path,
    monkeypatch,
):
    dataset = "DAPO-Math-17k-Random-100-Seed42-No-AIME24-v3"
    snapshot = tmp_path / "hierarchy.json"
    manifest_path = tmp_path / "manifest.json"
    _write_snapshot(snapshot)
    source_id = _write_strict_manifest(manifest_path, dataset)
    _set_all_snapshot_sources(snapshot, source_id)
    config = _config(snapshot)
    config.data = SimpleNamespace(
        require_practice_manifest=True,
        practice_manifest_path=str(manifest_path),
        practice_dataset_name=dataset,
        practice_manifest_split="training_calibration_v1",
        practice_manifest_expected_records=100,
    )
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)

    class ForbiddenManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("plan-only mode must not construct the manager")

    monkeypatch.setattr(cli, "HierarchicalExperienceManager", ForbiddenManager)
    report = await cli.run(_args(snapshot))

    assert report["manifest_guard"]["required"] is True
    assert report["manifest_guard"]["practice_namespace"] == dataset
    assert report["manifest_guard"]["referenced_source_task_count"] == 1
    assert report["manifest_guard"]["database_snapshot"] == {
        "status": "not_checked",
        "reason": "plan_only",
    }
    assert report["snapshot_changed"] is False


@pytest.mark.asyncio
async def test_formal_v3_config_rejects_smoke_v2_snapshot_before_execute_manager(
    tmp_path,
    monkeypatch,
):
    formal_dataset = "DAPO-Math-17k-Random-100-Seed42-No-AIME24-v3"
    smoke_dataset = "DAPO-Math-17k-Random-100-Seed42-No-AIME24-v2"
    snapshot = tmp_path / "math_dapo_smoke_v2.json"
    manifest_path = tmp_path / "formal-v3-manifest.json"
    _write_snapshot(snapshot)
    _write_strict_manifest(manifest_path, formal_dataset)
    _set_all_snapshot_sources(snapshot, f"{smoke_dataset}:0")
    before = snapshot.read_bytes()
    config = _config(snapshot)
    config.data = SimpleNamespace(
        require_practice_manifest=True,
        practice_manifest_path=str(manifest_path),
        practice_dataset_name=formal_dataset,
        practice_manifest_split="training_calibration_v1",
        practice_manifest_expected_records=100,
    )
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)

    class ForbiddenManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("source mismatch must fail before manager construction")

    monkeypatch.setattr(cli, "HierarchicalExperienceManager", ForbiddenManager)
    args = _args(snapshot, execute=True)
    args.config_name = "math/math_dapo_100_aime24"

    with pytest.raises(ValueError, match="outside manifest namespace"):
        await cli.run(args)

    assert snapshot.read_bytes() == before


@pytest.mark.asyncio
async def test_strict_execute_runs_static_and_database_guards_before_manager(
    tmp_path,
    monkeypatch,
):
    snapshot = tmp_path / "hierarchy.json"
    _write_snapshot(snapshot)
    config = _config(snapshot)
    config.data = SimpleNamespace(
        require_practice_manifest=True,
        practice_manifest_path="manifest.json",
        practice_dataset_name="formal-v3",
        practice_manifest_split="training_calibration_v1",
        practice_manifest_expected_records=100,
    )
    config.runtime.data = SimpleNamespace(dataset="AIME24")
    config.runtime.db_url = "sqlite:///read-only-fixture.db"
    order: list[str] = []
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)

    def static_guard(*_args, **_kwargs):
        order.append("static_guard")
        return {"manifest_sha256": "static-evidence"}

    def database_guard(*_args, **kwargs):
        order.append("database_guard")
        assert kwargs["evaluation_dataset"] == "AIME24"
        assert kwargs["expected_record_count"] == 100
        return {"practice_snapshot_sha256": "database-evidence"}

    class FakeManager:
        def __init__(self, **_kwargs):
            order.append("manager")

        async def aggregate_levels(self, _targets, *, epoch):
            assert epoch == 7
            order.append("aggregate")

    monkeypatch.setattr(cli, "validate_hierarchy_snapshot_sources", static_guard)
    monkeypatch.setattr(cli, "validate_practice_dataset_manifest", database_guard)
    monkeypatch.setattr(cli, "HierarchicalExperienceManager", FakeManager)

    report = await cli.run(_args(snapshot, execute=True))

    assert order == ["static_guard", "database_guard", "manager", "aggregate"]
    assert report["manifest_guard"]["manifest_sha256"] == "static-evidence"
    assert report["manifest_guard"]["database_snapshot"] == {"practice_snapshot_sha256": "database-evidence"}


@pytest.mark.asyncio
async def test_strict_execute_database_guard_failure_prevents_manager(
    tmp_path,
    monkeypatch,
):
    snapshot = tmp_path / "hierarchy.json"
    _write_snapshot(snapshot)
    before = snapshot.read_bytes()
    config = _config(snapshot)
    config.data = SimpleNamespace(
        require_practice_manifest=True,
        practice_manifest_path="manifest.json",
        practice_dataset_name="formal-v3",
        practice_manifest_split="training_calibration_v1",
        practice_manifest_expected_records=100,
    )
    config.runtime.data = SimpleNamespace(dataset="AIME24")
    config.runtime.db_url = "sqlite:///read-only-fixture.db"
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)
    monkeypatch.setattr(
        cli,
        "validate_hierarchy_snapshot_sources",
        lambda *_args, **_kwargs: {"manifest_sha256": "static-evidence"},
    )

    def rejected_database(*_args, **_kwargs):
        raise ValueError("current AIME snapshot changed")

    class ForbiddenManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("database guard failure must precede manager construction")

    monkeypatch.setattr(cli, "validate_practice_dataset_manifest", rejected_database)
    monkeypatch.setattr(cli, "HierarchicalExperienceManager", ForbiddenManager)

    with pytest.raises(ValueError, match="AIME snapshot changed"):
        await cli.run(_args(snapshot, execute=True))

    assert snapshot.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selection", "expected_calls"),
    (("l1", [("L1", 7)]), ("l2", [("L2", 7)]), ("all", [("L1", 7), ("L2", 7)])),
)
async def test_execute_dispatches_only_selected_levels(
    tmp_path,
    monkeypatch,
    selection,
    expected_calls,
):
    snapshot = tmp_path / "hierarchy.json"
    _write_snapshot(snapshot)
    config = _config(snapshot)
    original_hierarchy = config.practice.hierarchical_learning
    calls: list[tuple[str, int]] = []
    constructed: list[dict] = []
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)

    class FakeManager:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

        async def aggregate_levels(self, targets, *, epoch):
            calls.extend((target, epoch) for target in targets)

    monkeypatch.setattr(cli, "HierarchicalExperienceManager", FakeManager)
    report = await cli.run(_args(snapshot, level=selection, execute=True))

    assert calls == expected_calls
    assert len(constructed) == 1
    assert constructed[0]["config"] is config.runtime.agent
    assert constructed[0]["agent_objective"] == "solve tasks"
    assert report["targets"] == [level for level, _epoch in expected_calls]
    assert report["threshold_gates"]["l0_similarity_threshold_provisional"] is True
    assert report["threshold_gates"]["l1_similarity_threshold_provisional"] is False
    assert "legacy_similarity_thresholds_provisional" not in report["threshold_gates"]
    assert report["threshold_gates"]["allow_provisional_aggregation"] is False
    assert original_hierarchy.experience_save_path == str(snapshot)


@pytest.mark.asyncio
async def test_public_manager_l2_only_never_triggers_l1():
    manager = object.__new__(cli.HierarchicalExperienceManager)
    calls: list[tuple[str, int]] = []

    async def aggregate_l1(epoch):
        calls.append(("L1", epoch))

    async def aggregate_l2(epoch):
        calls.append(("L2", epoch))

    manager._aggregate_l1 = aggregate_l1
    manager._aggregate_l2 = aggregate_l2

    await manager.aggregate_levels(("L2",), epoch=11)

    assert calls == [("L2", 11)]


@pytest.mark.asyncio
async def test_public_manager_rejects_invalid_or_duplicate_targets_before_dispatch():
    manager = object.__new__(cli.HierarchicalExperienceManager)
    calls: list[str] = []

    async def aggregate_l1(epoch):
        calls.append(f"L1:{epoch}")

    async def aggregate_l2(epoch):
        calls.append(f"L2:{epoch}")

    manager._aggregate_l1 = aggregate_l1
    manager._aggregate_l2 = aggregate_l2

    with pytest.raises(ValueError, match="Unsupported aggregation target"):
        await manager.aggregate_levels(("L0",), epoch=3)
    with pytest.raises(ValueError, match="must not contain duplicates"):
        await manager.aggregate_levels(("L1", "L1"), epoch=3)

    assert calls == []


@pytest.mark.asyncio
async def test_snapshot_override_keeps_audit_next_to_selected_snapshot(tmp_path, monkeypatch):
    configured_snapshot = tmp_path / "configured.json"
    selected_snapshot = tmp_path / "selected.json"
    _write_snapshot(configured_snapshot)
    _write_snapshot(selected_snapshot)
    config = _config(configured_snapshot)
    captured: dict = {}
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)

    class FakeManager:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def aggregate_levels(self, targets, *, epoch):
            return None

    monkeypatch.setattr(cli, "HierarchicalExperienceManager", FakeManager)
    await cli.run(_args(selected_snapshot, level="l1", execute=True))

    hierarchy = captured["hierarchical_config"]
    assert Path(hierarchy.experience_save_path) == selected_snapshot.resolve()
    assert Path(hierarchy.clustering_audit_path) == selected_snapshot.with_suffix(".json.clusters.jsonl").resolve()
    assert config.practice.hierarchical_learning.experience_save_path == str(configured_snapshot)


@pytest.mark.asyncio
async def test_missing_snapshot_fails_before_manager_construction(tmp_path, monkeypatch):
    snapshot = tmp_path / "missing.json"
    config = _config(snapshot)
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)

    class ForbiddenManager:
        def __init__(self, *args, **kwargs):
            raise AssertionError("missing snapshots must fail before manager construction")

    monkeypatch.setattr(cli, "HierarchicalExperienceManager", ForbiddenManager)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        await cli.run(_args(snapshot, execute=True))
    assert not snapshot.exists()


@pytest.mark.asyncio
async def test_invalid_snapshot_and_disabled_hierarchy_fail_closed(tmp_path, monkeypatch):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    config = _config(invalid)
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)
    with pytest.raises(ValueError, match="JSON object"):
        await cli.run(_args(invalid))

    valid = tmp_path / "valid.json"
    _write_snapshot(valid)
    disabled = _config(valid)
    disabled.practice.hierarchical_learning.enabled = False
    monkeypatch.setattr(cli.ConfigLoader, "load_training_free_grpo_config", lambda _name: disabled)
    with pytest.raises(ValueError, match="disabled"):
        await cli.run(_args(valid))


def test_snapshot_stats_accepts_legacy_dictionary_storage():
    stats = cli._snapshot_stats(
        {
            "schema_version": 1,
            "l0_experiences": {
                "one": {"content": "one"},
                "two": {"content": "two", "aggregation_status": "aggregated"},
            },
            "l0_candidates": {"candidate": {"status": "review_failed"}},
        }
    )

    assert stats["levels"]["L0"]["pool_count"] == 2
    assert stats["levels"]["L0"]["active_count"] == 2
    assert stats["levels"]["L0"]["pending_aggregation_count"] == 1
    assert stats["levels"]["L0"]["candidate_status_counts"] == {"review_failed": 1}
