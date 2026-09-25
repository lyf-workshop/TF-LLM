from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utu.practice.experience_models import (
    ExperienceCandidateRecord,
    ExperienceRecord,
)
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager


class ConstantEmbedding:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _json_after(user_prompt: str, marker: str):
    lines = user_prompt.splitlines()
    marker_index = next(index for index, line in enumerate(lines) if marker in line)
    return json.loads(next(line for line in lines[marker_index + 1 :] if line.strip()))


def _structured(title: str) -> dict:
    return {
        "decision": "aggregate",
        "title": title,
        "principle": "Apply the evidence-bound procedure when its exact observable trigger is present.",
        "applicable_when": ["the source trigger and boundary conditions match"],
        "not_applicable_when": ["the source boundary conditions do not match"],
        "recommended_actions": ["execute the supported procedure and verify the result"],
        "evidence_summary": "The supplied direct parent records support this bounded procedure.",
        "confidence": 0.9,
    }


class StackedPoolLLM:
    def __init__(self, *, keep_reviews: bool = False, delete_reviews: bool = False):
        self.keep_reviews = keep_reviews
        self.delete_reviews = delete_reviews
        self.calls: list[dict] = []
        self.generation_calls = 0

    async def query_one(self, **kwargs):
        self.calls.append(kwargs)
        system_prompt = kwargs["messages"][0]["content"]
        user_prompt = kwargs["messages"][1]["content"]
        if "You turn one or more incoming case-level L0 experiences" in system_prompt:
            self.generation_calls += 1
            return json.dumps(_structured(f"L1 proposal {self.generation_calls}"))
        if "You turn one or more incoming validated L1 patterns" in system_prompt:
            self.generation_calls += 1
            return json.dumps(_structured(f"L2 proposal {self.generation_calls}"))

        level = "L1" if "L1 operational patterns" in system_prompt else "L2"
        candidate = _json_after(user_prompt, f"Candidate {level}")
        related = _json_after(user_prompt, f"Current active {level}")
        if self.keep_reviews:
            return json.dumps(
                {
                    "action": "KEEP",
                    "candidate_id": candidate["id"],
                    "level": level,
                    "target_id": None,
                    "new_content": None,
                    "new_structured_content": None,
                    "reason": "The candidate is intentionally retained only as reviewed evidence.",
                    "evidence_ids": [candidate["id"]],
                }
            )

        if self.delete_reviews:
            target = related[0]
            return json.dumps(
                {
                    "action": "DELETE",
                    "candidate_id": candidate["id"],
                    "level": level,
                    "target_id": target["id"],
                    "new_content": None,
                    "new_structured_content": None,
                    "reason": "The new direct evidence disproves the active upper-level pattern.",
                    "evidence_ids": [candidate["parent_ids"][0], target["id"]],
                }
            )

        action = "UPDATE" if related else "ADD"
        target_id = related[0]["id"] if related else None
        evidence_ids = [candidate["parent_ids"][0]]
        if target_id is not None:
            evidence_ids.append(target_id)
        reviewed = dict(candidate["structured_content"])
        reviewed["title"] = f"Reviewed {level} pool pattern {len(related) + 1}"
        return json.dumps(
            {
                "action": action,
                "candidate_id": candidate["id"],
                "level": level,
                "target_id": target_id,
                "new_content": "canonical structured content",
                "new_structured_content": reviewed,
                "reason": "The direct parent adds independent support to this bounded pattern.",
                "evidence_ids": evidence_ids,
            }
        )


class FailOnCallLLM:
    async def query_one(self, **kwargs):
        raise AssertionError("restart should not regenerate or rereview a committed candidate")


def hierarchy_config(tmp_path, **overrides):
    values = {
        "experience_save_path": str(tmp_path / "experiences.json"),
        "clustering_audit_path": str(tmp_path / "audit.jsonl"),
        "experience_output_language": "same_as_input",
        "upper_pool_update_mode": "stacked_pool",
        "stacked_pool_source_batch_size": 1,
        "candidate_review_scope": "full_pool",
        "clustering_enabled": True,
        "l0_similarity_threshold_provisional": True,
        "l1_similarity_threshold_provisional": True,
        "allow_provisional_aggregation": False,
        "l0_similarity_threshold": 0.8,
        "l1_similarity_threshold": 0.75,
        "min_l0_per_l1": 5,
        "min_l1_per_l2": 2,
        "max_cluster_size": 20,
        "strategy_conflict_check_enabled": True,
        "strategy_conflict_lexical_overlap": 0.65,
        "aggregation_temperature": 0.0,
        "l1_confidence_threshold": 0.7,
        "l2_confidence_threshold": 0.8,
        "l0_candidate_review_enabled": True,
        "l1_candidate_review_enabled": True,
        "l2_candidate_review_enabled": True,
        "l1_validation_required": True,
        "l0_review_temperature": 0.0,
        "l0_review_full_pool_limit": 10,
        "l0_review_retrieval": "semantic",
        "l0_review_top_k": 3,
        "l0_review_max_supporting_evidence_chars": 160000,
        "l0_review_source_ids_per_item": 32,
        "l0_review_content_chars": 8000,
        "l0_review_max_attempts": 3,
        "max_l0_per_problem": 0,
        "max_l1_total": 100,
        "max_l2_total": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_manager(tmp_path, llm=None, **overrides):
    return HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=hierarchy_config(tmp_path, **overrides),
        agent_objective="solve technical tasks",
        learning_objective="maintain evidence-backed experience pools",
        llm=llm or StackedPoolLLM(),
        embedding_provider=ConstantEmbedding(),
    )


def make_l0(exp_id: str) -> ExperienceRecord:
    return ExperienceRecord(
        id=exp_id,
        level="L0",
        content=f"Use the bounded procedure supported by {exp_id}.",
        source_task_ids=[f"task-{exp_id}"],
        source_rollout_ids=[f"rollout-{exp_id}"],
        aggregation_status="pending",
    )


def make_l1(exp_id: str, l0_parent: ExperienceRecord) -> ExperienceRecord:
    return ExperienceRecord(
        id=exp_id,
        level="L1",
        content=f"Validated operational pattern supported by {exp_id}.",
        source_task_ids=list(l0_parent.source_task_ids),
        source_rollout_ids=list(l0_parent.source_rollout_ids),
        parent_ids=[l0_parent.id],
        source_l0_ids=[l0_parent.id],
        aggregation_status="pending",
        validation_status="validated",
    )


def test_full_pool_review_keeps_every_active_record(tmp_path):
    instance = make_manager(tmp_path)
    records = [make_l0(f"L0_{index:03d}") for index in range(56)]
    instance._l0_records = {record.id: record for record in records}
    candidate = ExperienceCandidateRecord(
        id="C0_new",
        level="L0",
        content="A new bounded procedure.",
        source_task_ids=["task-new"],
        source_rollout_ids=["rollout-new"],
    )

    related, scope = instance._related_active_l0(candidate)
    views, _, displayed = instance._related_review_views(candidate, related)

    assert scope == "full_active_pool"
    assert len(related) == len(views) == len(displayed) == 56
    assert views[0]["id"] == "L0_000"
    assert views[-1]["id"] == "L0_055"


def test_snapshot_stats_distinguish_pool_active_quarantine_and_injectable(tmp_path):
    instance = make_manager(tmp_path)
    l0 = make_l0("L0_active")
    active_l1 = make_l1("L1_active", l0)
    provisional_l1 = make_l1("L1_provisional", l0).model_copy(
        update={"validation_status": "provisional"}
    )
    quarantined_l1 = make_l1("L1_quarantined", l0).model_copy(
        update={"lifecycle_status": "needs_review"}
    )
    archived_l1 = make_l1("L1_archived", l0).model_copy(
        update={"lifecycle_status": "inactive"}
    )
    instance._l0_records = {l0.id: l0}
    instance._l1_records = {
        record.id: record
        for record in (active_l1, provisional_l1, quarantined_l1)
    }
    instance._l1_archive = {archived_l1.id: archived_l1}

    stats = instance._state_payload(
        instance._l0_records,
        instance._l1_records,
        instance._l2_records,
    )["stats"]

    assert stats["pool_l1"] == 3
    assert stats["active_l1"] == 2
    assert stats["needs_review_l1"] == 1
    assert stats["archived_l1"] == 1
    assert stats["total_l1"] == 4
    assert stats["provisional_l1"] == 1
    assert stats["injectable_l1"] == 1


@pytest.mark.asyncio
async def test_stacked_l0_updates_accumulate_into_one_provisional_l1(tmp_path):
    llm = StackedPoolLLM()
    instance = make_manager(tmp_path, llm)
    first = make_l0("L0_first")
    instance._l0_records[first.id] = first

    await instance._aggregate_l1(epoch=0)

    first_l1 = instance.get_all_l1_experiences()
    assert len(first_l1) == 1
    assert first_l1[0]["parent_ids"] == [first.id]
    assert first_l1[0]["validation_status"] == "provisional"
    assert instance.get_injectable_l1_experiences() == []

    second = make_l0("L0_second")
    instance._l0_records[second.id] = second
    await instance._aggregate_l1(epoch=1)

    current = instance.get_all_l1_experiences()
    assert len(current) == 1
    assert set(current[0]["parent_ids"]) == {first.id, second.id}
    assert current[0]["validation_status"] == "provisional"
    assert len(instance.get_archived_l1_experiences()) == 1
    assert all(record.aggregation_status == "aggregated" for record in instance._l0_records.values())
    assert [candidate["review_decision"]["action"] for candidate in instance.get_candidates("L1")] == [
        "ADD",
        "UPDATE",
    ]


@pytest.mark.asyncio
async def test_provisional_l1_is_not_injected_or_used_for_l2(tmp_path):
    llm = StackedPoolLLM()
    instance = make_manager(tmp_path, llm)
    parent = make_l0("L0_only")
    instance._l0_records[parent.id] = parent

    await instance._aggregate_l1(epoch=0)
    calls_after_l1 = len(llm.calls)
    await instance._aggregate_l2(epoch=0)

    assert instance.get_injectable_l1_experiences() == []
    assert instance.get_all_l2_experiences() == []
    assert len(llm.calls) == calls_after_l1


@pytest.mark.asyncio
async def test_stacked_l2_becomes_validated_after_parent_support_update(tmp_path):
    llm = StackedPoolLLM()
    instance = make_manager(tmp_path, llm, min_l1_per_l2=2)
    l0_first = make_l0("L0_for_l1_first")
    l0_second = make_l0("L0_for_l1_second")
    instance._l0_records = {
        l0_first.id: l0_first,
        l0_second.id: l0_second,
    }
    l1_first = make_l1("L1_first", l0_first)
    instance._l1_records[l1_first.id] = l1_first

    await instance._aggregate_l2(epoch=0)

    first_l2 = instance.get_all_l2_experiences()
    assert len(first_l2) == 1
    assert first_l2[0]["validation_status"] == "provisional"
    assert instance.get_injectable_l2_experiences() == []

    l1_second = make_l1("L1_second", l0_second)
    instance._l1_records[l1_second.id] = l1_second
    await instance._aggregate_l2(epoch=1)

    current = instance.get_all_l2_experiences()
    assert len(current) == 1
    assert set(current[0]["parent_ids"]) == {l1_first.id, l1_second.id}
    assert current[0]["validation_status"] == "validated"
    assert len(instance.get_injectable_l2_experiences()) == 1


@pytest.mark.asyncio
async def test_keep_terminalizes_sources_and_restart_does_not_regenerate_candidate(tmp_path):
    first = make_manager(tmp_path, StackedPoolLLM(keep_reviews=True))
    parent = make_l0("L0_restart")
    first._l0_records[parent.id] = parent
    await first._aggregate_l1(epoch=0)

    assert first._l0_records[parent.id].aggregation_status == "terminal"
    assert first.get_candidates("L1")[0]["status"] == "committed"

    restarted = make_manager(tmp_path, FailOnCallLLM())
    await restarted._aggregate_l1(epoch=1)

    assert restarted._l0_records[parent.id].aggregation_status == "terminal"
    assert len(restarted.get_candidates("L1")) == 1


@pytest.mark.asyncio
async def test_aggregation_audit_is_bound_to_run_config_snapshot_and_source_versions(tmp_path):
    instance = make_manager(tmp_path, StackedPoolLLM(keep_reviews=True))
    parent = make_l0("L0_audit")
    instance._l0_records[parent.id] = parent

    await instance._aggregate_l1(epoch=0, run_id="run-a")

    assert instance.has_aggregation_audit(epoch=0, run_id="run-a") is True
    assert instance.has_aggregation_audit(epoch=0, run_id="different-run") is False

    original_limit = instance.h_config.max_l1_total
    instance.h_config.max_l1_total = original_limit + 1
    assert instance.has_aggregation_audit(epoch=0, run_id="run-a") is False
    instance.h_config.max_l1_total = original_limit

    unexplained = make_l0("L0_unexplained_extra")
    instance._l0_records[unexplained.id] = unexplained
    assert instance.has_aggregation_audit(epoch=0, run_id="run-a") is False
    del instance._l0_records[unexplained.id]

    instance._l0_records[parent.id] = instance._l0_records[parent.id].model_copy(
        update={"content": "A semantically different source record."}
    )
    assert instance.has_aggregation_audit(epoch=0, run_id="run-a") is False


def test_arbitrary_legacy_audit_line_is_not_resume_proof(tmp_path):
    instance = make_manager(tmp_path)
    audit_path = instance._audit_path()
    audit_path.write_text(
        json.dumps({"epoch": 0, "source_level": "L0", "target_level": "L1"})
        + "\n",
        encoding="utf-8",
    )

    assert instance.has_aggregation_audit(
        epoch=0,
        run_id="run-a",
        allow_legacy=True,
    ) is False


def test_audit_write_failure_is_not_silently_swallowed(tmp_path):
    instance = make_manager(tmp_path, clustering_audit_path=str(tmp_path))

    with pytest.raises(RuntimeError, match="durably write clustering audit"):
        instance._append_audit({"epoch": 0})


@pytest.mark.asyncio
async def test_delete_terminalizes_candidate_sources_after_removing_target(tmp_path):
    instance = make_manager(tmp_path, StackedPoolLLM(delete_reviews=True))
    old_parent = make_l0("L0_old_parent").model_copy(
        update={
            "aggregation_status": "aggregated",
            "aggregated_into_experience_id": "L1_old",
        }
    )
    target = make_l1("L1_old", old_parent)
    new_parent = make_l0("L0_new_evidence")
    instance._l0_records = {
        old_parent.id: old_parent,
        new_parent.id: new_parent,
    }
    instance._l1_records = {target.id: target}

    await instance._aggregate_l1(epoch=1)

    assert target.id not in instance._l1_records
    assert target.id in instance._l1_archive
    assert instance._l0_records[new_parent.id].aggregation_status == "terminal"
    assert instance._l0_records[old_parent.id].aggregation_status == "pending"
    candidate = instance.get_candidates("L1")[0]
    assert candidate["review_decision"]["action"] == "DELETE"
    assert candidate["resolution"] == "not_adopted"


@pytest.mark.asyncio
async def test_clustered_mode_still_dispatches_to_legacy_aggregation(tmp_path):
    instance = make_manager(tmp_path, upper_pool_update_mode="clustered")
    instance._aggregate_level = AsyncMock()

    await instance._aggregate_l1(epoch=4)

    instance._aggregate_level.assert_awaited_once()
    assert instance._aggregate_level.await_args.kwargs["source_level"] == "L0"
    assert instance._aggregate_level.await_args.kwargs["target_level"] == "L1"
