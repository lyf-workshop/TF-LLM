from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from utu.practice.experience_clusterer import (
    ExperienceClusterer,
    SentenceTransformerEmbeddingProvider,
    detect_strategy_conflicts,
)
from utu.practice.experience_models import ExperienceRecord, FailureMode, TaskStage, stable_experience_id
from utu.practice.experience_updater import ExperienceUpdater
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager


class KeywordEmbedding:
    """Deterministic semantic groups without an external embedding service."""

    def embed(self, texts):
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "alpha" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "beta" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def aggregation_json(title: str = "Concrete shared pattern", confidence: float = 0.95) -> str:
    return json.dumps(
        {
            "decision": "aggregate",
            "title": title,
            "principle": "Use the shared concrete procedure only after its trigger is observed.",
            "applicable_when": ["the shared precondition is present"],
            "not_applicable_when": ["the required precondition is absent"],
            "recommended_actions": ["check the trigger", "execute the shared procedure"],
            "evidence_summary": "Every parent demonstrates the same trigger and action relationship.",
            "confidence": confidence,
        }
    )


class QueueLLM:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = 0

    async def query_one(self, **_kwargs):
        self.calls += 1
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def hierarchy_config(tmp_path, **overrides):
    values = {
        "experience_save_path": str(tmp_path / "experiences.json"),
        "clustering_audit_path": str(tmp_path / "clusters.jsonl"),
        "clustering_enabled": True,
        "clustering_method": "agglomerative",
        "embedding_provider": "hashing",
        "l0_similarity_threshold": 0.8,
        "l1_similarity_threshold": 0.75,
        "min_l0_per_l1": 2,
        "min_l1_per_l2": 2,
        "max_cluster_size": 20,
        "use_metadata_constraints": True,
        "hard_constraint_fields": ["task_stage", "failure_mode"],
        "soft_constraint_fields": ["domain", "task_family", "tool_type", "strategy_type"],
        "random_seed": 42,
        "aggregation_temperature": 0.0,
        "max_l0_per_problem": 10,
        "max_l1_total": 50,
        "max_l2_total": 10,
        "include_l0_in_prompt": True,
        "max_l0_recent": 10,
        "l1_confidence_threshold": 0.7,
        "l2_confidence_threshold": 0.8,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def manager(tmp_path, responses=(), **config_overrides):
    llm = QueueLLM(responses)
    instance = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=hierarchy_config(tmp_path, **config_overrides),
        agent_objective="complete technical tasks",
        learning_objective="learn executable patterns",
        llm=llm,
        embedding_provider=KeywordEmbedding(),
    )
    return instance, llm


def record(content: str, *, failure_mode="same", task_stage="solve", domain="tests"):
    return ExperienceRecord(
        id=stable_experience_id(
            "L0",
            content,
            identity_context=[
                f"failure_mode={failure_mode}",
                f"task_stage={task_stage}",
                f"domain={domain}",
            ],
        ),
        level="L0",
        content=content,
        failure_mode=failure_mode,
        task_stage=task_stage,
        domain=domain,
    )


def test_experience_updater_preserves_available_l0_source_metadata():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    metadata = updater._l0_source_metadata(
        [
            {
                "dataset": "SkillsBench",
                "dataset_index": 7,
                "source": "SkillsBench",
                "trace_id": "trace-a",
                "reward": 0,
                "meta": {
                    "task_id": "task-seven",
                    "domain": "Office Productivity",
                    "task_family": "formatting",
                    "required_tools": ["terminal", "python"],
                    "strategy_type": "inspect_then_modify",
                    "task_stage": "verification",
                },
            },
            {
                "dataset": "SkillsBench",
                "dataset_index": 7,
                "source": "SkillsBench",
                "trace_id": "trace-b",
                "reward": 0,
                "meta": {
                    "task_id": "task-seven",
                    "domain": "Office Productivity",
                    "task_family": "formatting",
                    "required_tools": ["python", "terminal"],
                    "strategy_type": "inspect_then_modify",
                    "task_stage": "verification",
                },
            },
        ]
    )
    assert metadata["source_task_ids"] == ["SkillsBench:task-seven"]
    assert metadata["source_rollout_ids"] == ["trace-a", "trace-b"]
    assert metadata["domain"] == "Office Productivity"
    assert metadata["task_family"] == "formatting"
    assert metadata["tool_type"] == "python|terminal"
    assert metadata["strategy_type"] == "inspect_then_modify"
    assert metadata["task_stage"] == "verification"
    assert metadata["failure_mode"] == "verifier_failure"


@pytest.mark.asyncio
async def test_rollout_metadata_reaches_persisted_l0(tmp_path):
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    metadata = updater._l0_source_metadata(
        [
            {
                "source": "SkillsBench",
                "trace_id": "trace-1",
                "reward": 1.0,
                "meta": {
                    "task_id": "data-to-d3",
                    "domain": "Software Engineering",
                    "task_family": "implementation",
                    "required_tools": ["terminal"],
                    "strategy_type": "inspect_then_modify",
                    "task_stage": "execution",
                },
            }
        ]
    )
    instance, _ = manager(tmp_path)
    await instance.process_step_experiences(
        [{"content": "Use a local asset bundle for deterministic rendering.", **metadata}],
        step=0,
    )
    stored = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    l0 = stored["l0_experiences"][0]
    assert l0["source_task_ids"] == ["SkillsBench:data-to-d3"]
    assert l0["source_rollout_ids"] == ["trace-1"]
    assert l0["domain"] == "Software Engineering"
    assert l0["task_family"] == "implementation"
    assert l0["tool_type"] == "terminal"
    assert l0["strategy_type"] == "inspect_then_modify"
    assert l0["task_stage"] == "execution"
    assert l0["failure_mode"] == "none"
    assert stored["stats"]["l0_metadata_coverage"]["task_family"]["ratio"] == 1.0


def test_similar_metadata_compatible_experiences_cluster_together():
    clusterer = ExperienceClusterer(
        KeywordEmbedding(),
        hard_constraint_fields=["task_stage", "failure_mode"],
        soft_constraint_fields=["domain"],
        random_seed=42,
    )
    report = clusterer.cluster(
        [record("alpha command one"), record("alpha command two")],
        level="L0",
        similarity_threshold=0.8,
    )
    assert len(report.clusters) == 1
    assert len(report.clusters[0].experience_ids) == 2
    assert report.clusters[0].intra_cluster_similarity == pytest.approx(1.0)
    assert report.clusters[0].metadata_consistency == pytest.approx(1.0)


def test_unrecognised_hard_metadata_is_normalised_to_unknown_and_does_not_split():
    left = record("alpha same strategy", failure_mode="model guessed root cause", task_stage="middle")
    right = record("alpha same procedure", failure_mode="another guess", task_stage="somewhere")
    assert left.failure_mode.value == right.failure_mode.value == "unknown"
    assert left.task_stage.value == right.task_stage.value == "unknown"
    report = ExperienceClusterer(
        KeywordEmbedding(), hard_constraint_fields=["task_stage", "failure_mode"]
    ).cluster([left, right], level="L0", similarity_threshold=0.8)
    assert len(report.clusters) == 1
    assert report.metadata_constraint_splits == []


def test_enum_instances_survive_metadata_validation():
    item = ExperienceRecord(
        id="enum-test",
        level="L0",
        content="validated metadata",
        failure_mode=FailureMode.NONE,
        task_stage=TaskStage.VERIFICATION,
    )
    assert item.failure_mode is FailureMode.NONE
    assert item.task_stage is TaskStage.VERIFICATION


@pytest.mark.parametrize(
    ("left", "right", "split_field"),
    [
        (
            record("alpha same text", failure_mode="timeout"),
            record("alpha same text", failure_mode="bad_output"),
            "failure_mode",
        ),
        (record("alpha same text", task_stage="plan"), record("alpha same text", task_stage="submit"), "task_stage"),
    ],
)
def test_hard_metadata_mismatch_prevents_semantic_merge(left, right, split_field):
    clusterer = ExperienceClusterer(
        KeywordEmbedding(),
        hard_constraint_fields=["task_stage", "failure_mode"],
        soft_constraint_fields=[],
    )
    report = clusterer.cluster([left, right], level="L0", similarity_threshold=0.8)
    assert sorted(len(cluster.experience_ids) for cluster in report.clusters) == [1, 1]
    assert any(item["field"] == split_field for item in report.metadata_constraint_splits)


def test_clustering_is_reproducible_for_same_input_and_seed():
    records = [record("alpha one"), record("beta one"), record("alpha two")]
    first = ExperienceClusterer(KeywordEmbedding(), random_seed=17).cluster(
        records, level="L0", similarity_threshold=0.8
    )
    second = ExperienceClusterer(KeywordEmbedding(), random_seed=17).cluster(
        list(reversed(records)), level="L0", similarity_threshold=0.8
    )
    assert first.as_dict() == second.as_dict()


def test_hashing_embedding_is_stable_across_python_hash_seeds():
    script = (
        "import json; from utu.practice.experience_clusterer import HashingEmbeddingProvider; "
        "print(json.dumps(HashingEmbeddingProvider(dimensions=16, seed=42).embed(['stable tokens'])[0]))"
    )
    outputs = []
    for python_hash_seed in ("1", "999"):
        environment = dict(os.environ, PYTHONHASHSEED=python_hash_seed)
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        outputs.append(result.stdout.strip().splitlines()[-1])
    assert outputs[0] == outputs[1]


def test_max_cluster_size_is_not_a_creation_order_cutoff():
    records = []
    for index in range(12):
        records.extend(
            [
                record(f"alpha semantic family {index}"),
                record(f"beta semantic family {index}"),
            ]
        )
    clusterer = ExperienceClusterer(KeywordEmbedding(), max_cluster_size=20, random_seed=42)
    report = clusterer.cluster(records, level="L0", similarity_threshold=0.8)
    contents_by_id = {item.id: item.content for item in records}
    groups = [
        {"alpha" if "alpha" in contents_by_id[item_id] else "beta" for item_id in cluster.experience_ids}
        for cluster in report.clusters
    ]
    assert sorted(len(cluster.experience_ids) for cluster in report.clusters) == [12, 12]
    assert groups == [{"alpha"}, {"beta"}] or groups == [{"beta"}, {"alpha"}]


def test_optional_real_sentence_embedding_semantics(tmp_path):
    pytest.importorskip("sentence_transformers")
    provider = SentenceTransformerEmbeddingProvider(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_revision="c9745ed1d9f207416be6d2e6f8de32d1f16199bf",
        expected_dimensions=384,
        cache_path=tmp_path / "embeddings.sqlite3",
        device="cpu",
        batch_size=3,
        local_files_only=True,
        random_seed=42,
    )
    try:
        vectors = provider.embed(
            [
                "Validate the output before submitting it.",
                "Check the result prior to submission.",
                "Delete unrelated temporary audio files.",
            ]
        )
    except RuntimeError as error:
        pytest.skip(f"pinned sentence model is not installed locally: {error}")
    from utu.practice.experience_clusterer import cosine_similarity

    assert cosine_similarity(vectors[0], vectors[1]) > cosine_similarity(vectors[0], vectors[2])
    opposites = [
        record("Always delete the cache before retrying the build."),
        record("Do not delete the cache before retrying the build."),
    ]
    assert detect_strategy_conflicts(opposites, lexical_overlap_threshold=0.65)


@pytest.mark.asyncio
async def test_five_plus_one_creates_only_valid_cluster_and_leaves_tail_pending(tmp_path):
    instance, llm = manager(
        tmp_path,
        [aggregation_json()],
        min_l0_per_l1=5,
        min_l1_per_l2=3,
    )
    candidates = [
        {"content": f"alpha technique {index}", "source_task_ids": [f"task-{index}"]} for index in range(5)
    ] + [{"content": "beta unrelated technique", "source_task_ids": ["task-tail"]}]
    await instance.process_step_experiences(candidates, step=0)
    await instance._aggregate_l1(epoch=0)

    l1 = instance.get_all_l1_experiences()
    l0 = instance.get_all_l0_experiences()
    assert llm.calls == 1
    assert len(l1) == 1
    assert len(l1[0]["source_l0_ids"]) == 5
    assert sum(item["aggregation_status"] == "pending" for item in l0) == 1
    assert sum(item["aggregation_status"] == "aggregated" for item in l0) == 5


@pytest.mark.asyncio
async def test_failed_cluster_remains_retryable_while_success_cluster_commits(tmp_path):
    instance, llm = manager(
        tmp_path,
        [aggregation_json("First cluster"), "not-json"],
        min_l0_per_l1=2,
        min_l1_per_l2=3,
    )
    await instance.process_step_experiences(
        [
            {"content": "alpha one", "source_task_ids": ["a1"]},
            {"content": "alpha two", "source_task_ids": ["a2"]},
            {"content": "beta one", "source_task_ids": ["b1"]},
            {"content": "beta two", "source_task_ids": ["b2"]},
        ],
        step=0,
    )
    await instance._aggregate_l1(epoch=0)
    assert len(instance.l1) == 1
    assert sum(item["aggregation_status"] == "pending" for item in instance.l0_experiences) == 2

    llm.responses.append(aggregation_json("Retried cluster"))
    await instance._aggregate_l1(epoch=1)
    assert len(instance.l1) == 2
    assert all(item["aggregation_status"] == "aggregated" for item in instance.l0_experiences)


@pytest.mark.asyncio
async def test_opposite_strategy_cluster_stays_pending_without_llm_call(tmp_path):
    instance, llm = manager(
        tmp_path,
        [],
        min_l0_per_l1=2,
        strategy_conflict_check_enabled=True,
        strategy_conflict_lexical_overlap=0.65,
    )
    await instance.process_step_experiences(
        [
            "Always delete the cache before retrying the build.",
            "Do not delete the cache before retrying the build.",
        ],
        step=0,
    )
    await instance._aggregate_l1(epoch=0)
    assert llm.calls == 0
    assert not instance.l1_experiences
    assert all(item["aggregation_status"] == "pending" for item in instance.l0_experiences)
    audits = [json.loads(line) for line in (tmp_path / "clusters.jsonl").read_text().splitlines()]
    assert audits[-1]["aggregation_attempts"][0]["status"] == "pending_conflict"


@pytest.mark.asyncio
async def test_provisional_threshold_blocks_clustered_aggregation(tmp_path):
    instance, llm = manager(
        tmp_path,
        [],
        min_l0_per_l1=2,
        similarity_thresholds_provisional=True,
        allow_provisional_aggregation=False,
    )
    await instance.process_step_experiences(["alpha one", "alpha two"], step=0)
    await instance._aggregate_l1(epoch=0)
    assert llm.calls == 0
    assert all(item["aggregation_status"] == "pending" for item in instance.l0_experiences)
    audit = json.loads((tmp_path / "clusters.jsonl").read_text().splitlines()[-1])
    assert audit["status"] == "waiting_for_threshold_calibration"


@pytest.mark.asyncio
async def test_parent_links_transitive_ancestry_and_restart_deduplication(tmp_path):
    instance, llm = manager(
        tmp_path,
        [
            aggregation_json("First operational pattern"),
            aggregation_json("Second operational pattern"),
            aggregation_json("Shared meta strategy"),
        ],
    )
    await instance.process_step_experiences(
        [
            {"content": "alpha one", "source_task_ids": ["a1"], "source_rollout_ids": ["ra1"]},
            {"content": "alpha two", "source_task_ids": ["a2"], "source_rollout_ids": ["ra2"]},
            {"content": "beta one", "source_task_ids": ["b1"], "source_rollout_ids": ["rb1"]},
            {"content": "beta two", "source_task_ids": ["b2"], "source_rollout_ids": ["rb2"]},
        ],
        step=0,
    )
    await instance.aggregate_epoch(epoch=0)
    assert llm.calls == 3
    l1 = instance.get_all_l1_experiences()
    l2 = instance.get_all_l2_experiences()
    assert len(l1) == 2 and len(l2) == 1
    assert all(item["source_l0_ids"] == item["parent_ids"] for item in l1)
    assert sorted(l2[0]["source_l1_ids"]) == sorted(item["id"] for item in l1)
    assert sorted(l2[0]["source_l0_ids"]) == sorted(source_id for item in l1 for source_id in item["source_l0_ids"])
    ancestry = instance.trace_ancestry(l2[0]["id"])
    assert len(ancestry["parents"]) == 2
    assert sum(len(parent["parents"]) for parent in ancestry["parents"]) == 4

    restarted, restarted_llm = manager(tmp_path, [])
    await restarted.aggregate_epoch(epoch=1)
    assert restarted_llm.calls == 0
    assert len(restarted.l1) == 2 and len(restarted.l2) == 1


@pytest.mark.asyncio
async def test_invalid_schema_or_save_failure_never_marks_parents(tmp_path, monkeypatch):
    instance, _ = manager(tmp_path, [json.dumps({"title": "missing required fields"})])
    await instance.process_step_experiences(["alpha one", "alpha two"], step=0)
    await instance._aggregate_l1(epoch=0)
    assert not instance.l1
    assert all(item["aggregation_status"] == "pending" for item in instance.l0_experiences)

    instance.llm.responses.append(aggregation_json())
    original_write = instance._write_state

    def fail_write(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(instance, "_write_state", fail_write)
    await instance._aggregate_l1(epoch=1)
    assert not instance.l1
    assert all(item["aggregation_status"] == "pending" for item in instance.l0_experiences)
    monkeypatch.setattr(instance, "_write_state", original_write)


def test_legacy_dict_and_list_formats_load_without_reaggregation(tmp_path):
    path = tmp_path / "experiences.json"
    path.write_text(
        json.dumps(
            {
                "l0_experiences": {"L0_old": "old concrete lesson"},
                "l1_experiences": [{"id": "L1_old", "content": "old pattern"}],
                "l2_experiences": {"L2_old": "old principle"},
                "l0_aggregated_ids": ["L0_old"],
            }
        ),
        encoding="utf-8",
    )
    instance, _ = manager(tmp_path, [])
    assert list(instance.l0) == ["L0_old"]
    assert list(instance.l1) == ["L1_old"]
    assert list(instance.l2) == ["L2_old"]
    assert instance.l0_experiences[0]["aggregation_status"] == "aggregated"
    assert instance.l1_experiences[0]["aggregation_status"] == "aggregated"


@pytest.mark.asyncio
async def test_clustering_disabled_preserves_sequential_grouping(tmp_path):
    instance, llm = manager(
        tmp_path,
        [aggregation_json()],
        clustering_enabled=False,
        min_l0_per_l1=2,
        min_l1_per_l2=3,
    )
    await instance.process_step_experiences(["alpha unrelated", "beta unrelated"], step=0)
    await instance._aggregate_l1(epoch=0)
    assert llm.calls == 1
    assert len(instance.l1_experiences) == 1
    assert len(instance.l1_experiences[0]["parent_ids"]) == 2


@pytest.mark.asyncio
async def test_stable_l0_id_merges_evidence_without_resetting_aggregated_status(tmp_path):
    instance, _ = manager(tmp_path, [aggregation_json()])
    await instance.process_step_experiences(
        [
            {"content": "alpha same lesson", "source_task_ids": ["task-1"]},
            {"content": "alpha another lesson", "source_task_ids": ["task-2"]},
        ],
        step=0,
    )
    await instance._aggregate_l1(epoch=0)
    original_id = stable_experience_id("L0", "alpha same lesson")
    await instance.process_step_experiences(
        [{"content": "alpha same lesson", "source_task_ids": ["task-3"]}],
        step=1,
    )
    item = next(item for item in instance.l0_experiences if item["id"] == original_id)
    assert item["source_task_ids"] == ["task-1", "task-3"]
    assert item["aggregation_status"] == "aggregated"
