from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utu.db import EvaluationSample
from utu.eval.experience_loader import ExperienceLoader
from utu.practice.experience_clusterer import ExperienceCluster
from utu.practice.experience_models import (
    AggregatedExperienceContent,
    ExperienceCandidateRecord,
    ExperienceRecord,
    ExperienceReviewDecision,
    experience_output_language_instruction,
    stable_experience_id,
    stable_l0_candidate_id,
    validate_experience_output_language,
)
from utu.practice.experience_updater import ExperienceUpdater, L0CandidateGenerationError
from utu.practice.hierarchical_experience_manager import (
    CandidateDecisionError,
    HierarchicalExperienceManager,
)
from utu.practice.training_free_grpo import (
    HIERARCHICAL_CANDIDATE_CACHE_KIND,
    HIERARCHICAL_FLAT_CACHE_KIND,
    TrainingFreeGRPO,
)
from utu.practice.utils import TaskRecorder
from utu.utils import FileUtils


class ConstantEmbedding:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class ParaphraseEmbedding:
    def embed(self, texts):
        vectors = []
        for text in texts:
            if "ensure accuracy" in text.lower() or "validate output" in text.lower():
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


class QueueLLM:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def query_one(self, **kwargs):
        self.calls.append(kwargs)
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
        "max_l1_total": 50,
        "max_l2_total": 10,
        "l1_confidence_threshold": 0.7,
        "l2_confidence_threshold": 0.8,
        "l0_candidate_review_enabled": True,
        # Keep legacy direct admission as the default in existing tests.  Tests
        # for upper-level review opt in explicitly, matching production config.
        "l1_candidate_review_enabled": False,
        "l2_candidate_review_enabled": False,
        "l0_review_temperature": 0.0,
        "l0_review_full_pool_limit": 50,
        "l0_review_retrieval": "semantic",
        "l0_review_top_k": 12,
        "l0_review_max_attempts": 3,
        "max_l0_per_problem": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_manager(tmp_path, responses=(), **overrides):
    llm = QueueLLM(responses)
    instance = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=hierarchy_config(tmp_path, **overrides),
        agent_objective="complete technical tasks",
        learning_objective="learn evidence-backed procedures",
        llm=llm,
        embedding_provider=ConstantEmbedding(),
    )
    return instance, llm


def candidate_id(content: str, task_id: str) -> str:
    return stable_l0_candidate_id(content, source_task_ids=[task_id])


def decision(
    action: str,
    candidate: str,
    *,
    target: str | None = None,
    content: str | None = None,
    evidence: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "action": action,
            "candidate_id": candidate,
            "target_id": target,
            "new_content": content,
            "reason": f"mock {action.lower()} decision grounded in supplied evidence",
            "evidence_ids": evidence if evidence is not None else [candidate],
        }
    )


def aggregation_decision(title: str = "Replacement pattern") -> str:
    return json.dumps(
        {
            "decision": "aggregate",
            "title": title,
            "principle": "Use the shared verified procedure when the matching trigger is observed.",
            "applicable_when": ["the same observable trigger is present"],
            "not_applicable_when": ["the source conditions do not match"],
            "recommended_actions": ["execute the verified procedure and check its result"],
            "evidence_summary": "The active source experiences provide matching operational evidence.",
            "confidence": 0.8,
        }
    )


@pytest.mark.asyncio
async def test_duplicate_candidates_are_reviewed_in_stable_order_against_fresh_pool(tmp_path):
    raw_a = "Inspect the generated artifact before submission."
    raw_b = "Check the produced artifact prior to submitting it."
    id_a = candidate_id(raw_a, "task-a")
    id_b = candidate_id(raw_b, "task-b")
    active_content = "Inspect the generated artifact and verify it before submission."
    active_id = stable_experience_id("L0", active_content)
    instance, llm = make_manager(
        tmp_path,
        [
            decision("ADD", id_a, content=active_content),
            decision("KEEP", id_b, evidence=[id_b, active_id]),
        ],
    )

    # Reverse arrival order simulates nondeterministic parallel completion.
    await instance.process_step_experiences(
        [
            {"content": raw_b, "source_task_ids": ["task-b"]},
            {"content": raw_a, "source_task_ids": ["task-a"]},
        ],
        step=0,
    )

    assert list(instance.l0) == [active_id]
    assert len(instance.get_l0_candidates()) == 2
    assert all(item["status"] == "committed" for item in instance.get_l0_candidates())
    first_prompt = llm.calls[0]["messages"][1]["content"]
    second_prompt = llm.calls[1]["messages"][1]["content"]
    assert id_a in first_prompt and id_b not in first_prompt.split("Candidate", 1)[1].split("Current", 1)[0]
    assert active_id in second_prompt
    assert active_content in second_prompt
    assert all(call["temperature"] == 0.0 for call in llm.calls)


@pytest.mark.asyncio
async def test_add_update_keep_delete_and_version_archive_semantics(tmp_path):
    add_raw, update_raw, keep_raw, delete_raw = "raw add", "raw update", "raw keep", "raw delete"
    add_cid = candidate_id(add_raw, "task-a")
    initial_content = "Use the verifier after generating the file."
    initial_id = stable_experience_id("L0", initial_content)
    update_cid = candidate_id(update_raw, "task-b")
    revised_content = "Use the verifier after generation, except when no verifier is available."
    revised_id = stable_experience_id("L0", revised_content)
    keep_cid = candidate_id(keep_raw, "task-c")
    delete_cid = candidate_id(delete_raw, "task-d")
    instance, llm = make_manager(
        tmp_path,
        [
            decision("ADD", add_cid, content=initial_content),
            decision("UPDATE", update_cid, target=initial_id, content=revised_content),
            decision("KEEP", keep_cid),
            decision("DELETE", delete_cid, target=revised_id, evidence=[delete_cid, revised_id]),
        ],
    )

    await instance.process_step_experiences(
        [{"content": add_raw, "source_task_ids": ["task-a"]}], step=0
    )
    assert set(instance.l0) == {initial_id}
    await instance.process_step_experiences(
        [{"content": update_raw, "source_task_ids": ["task-b"]}], step=1
    )
    assert set(instance.l0) == {revised_id}
    before_keep = dict(instance.l0)
    await instance.process_step_experiences(
        [{"content": keep_raw, "source_task_ids": ["task-c"]}], step=2
    )
    assert instance.l0 == before_keep
    await instance.process_step_experiences(
        [{"content": delete_raw, "source_task_ids": ["task-d"]}], step=3
    )

    assert instance.l0 == {}
    archive = {item["id"]: item for item in instance.get_archived_l0_experiences()}
    assert set(archive) == {initial_id, revised_id}
    assert archive[initial_id]["superseded_by_id"] == revised_id
    assert archive[revised_id]["supersedes_id"] == initial_id
    assert archive[initial_id]["lifecycle_status"] == "inactive"
    assert archive[revised_id]["lifecycle_status"] == "inactive"
    assert [item["review_decision"]["action"] for item in instance.get_l0_candidates()] == [
        "ADD",
        "UPDATE",
        "KEEP",
        "DELETE",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
async def test_invalid_update_or_delete_target_is_rejected(tmp_path, action):
    target = ExperienceRecord(id="L0_real", level="L0", content="Keep this valid lesson.")
    raw = f"candidate for invalid {action.lower()}"
    cid = candidate_id(raw, "task-a")
    new_content = "Replacement content with a valid procedure." if action == "UPDATE" else None
    instance, _ = make_manager(
        tmp_path,
        [decision(action, cid, target="L0_missing", content=new_content)],
    )
    instance._l0_records[target.id] = target
    instance.save_experiences()

    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )

    assert instance.l0 == {target.id: target.content}
    reviewed = instance.get_l0_candidates()[0]
    assert reviewed["status"] == "review_failed"
    assert "target_id" in reviewed["last_error"]


@pytest.mark.asyncio
async def test_mutating_action_must_cite_current_candidate_evidence(tmp_path):
    target = ExperienceRecord(id="L0_real", level="L0", content="Existing lesson.")
    raw = "Unsupported request to delete an existing lesson."
    cid = candidate_id(raw, "task-a")
    instance, _ = make_manager(
        tmp_path,
        [decision("DELETE", cid, target=target.id, evidence=[target.id])],
    )
    instance._l0_records[target.id] = target
    instance.save_experiences()

    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )

    assert instance.l0 == {target.id: target.content}
    assert "current candidate" in instance.get_l0_candidates()[0]["last_error"]


@pytest.mark.asyncio
async def test_mutating_action_must_cite_displayed_rollout_evidence_when_available(tmp_path):
    raw = "A candidate backed by a concrete verifier result."
    rollout_id = "rollout-1"
    cid = stable_l0_candidate_id(
        raw,
        source_task_ids=["task-a"],
        source_rollout_ids=[rollout_id],
    )
    instance, llm = make_manager(
        tmp_path,
        [
            decision("ADD", cid, content="Evidence-backed reusable procedure.", evidence=[cid]),
            decision(
                "ADD",
                cid,
                content="Evidence-backed reusable procedure.",
                evidence=[cid, rollout_id],
            ),
        ],
    )
    candidate = {
        "content": raw,
        "source_task_ids": ["task-a"],
        "source_rollout_ids": [rollout_id],
        "source_evidence": [
            {
                "id": rollout_id,
                "task_id": "task-a",
                "reward": 0.0,
                "outcome": "failed",
                "trajectory_summary": "The verifier rejected an unchecked artifact.",
            }
        ],
    }

    await instance.process_step_experiences([candidate], step=0)
    assert instance.l0 == {}
    assert "rollout evidence" in instance.get_l0_candidates()[0]["last_error"]
    assert "The verifier rejected" in llm.calls[0]["messages"][1]["content"]

    await instance.retry_candidate(cid)
    assert len(instance.l0) == 1


@pytest.mark.asyncio
async def test_review_of_existing_l0_includes_its_bounded_source_evidence(tmp_path):
    first_raw = "First evidence-backed candidate."
    second_raw = "Second candidate to compare."
    first_id = stable_l0_candidate_id(
        first_raw,
        source_task_ids=["task-a"],
        source_rollout_ids=["rollout-a"],
    )
    second_id = stable_l0_candidate_id(
        second_raw,
        source_task_ids=["task-b"],
        source_rollout_ids=["rollout-b"],
    )
    instance, llm = make_manager(
        tmp_path,
        [
            decision(
                "ADD",
                first_id,
                content="Check the artifact against verifier evidence.",
                evidence=[first_id, "rollout-a"],
            ),
            decision("KEEP", second_id),
        ],
    )
    await instance.process_step_experiences(
        [
            {
                "content": second_raw,
                "source_task_ids": ["task-b"],
                "source_rollout_ids": ["rollout-b"],
                "source_evidence": [
                    {"id": "rollout-b", "task_id": "task-b", "reward": 0.0}
                ],
            },
            {
                "content": first_raw,
                "source_task_ids": ["task-a"],
                "source_rollout_ids": ["rollout-a"],
                "source_evidence": [
                    {
                        "id": "rollout-a",
                        "task_id": "task-a",
                        "reward": 1.0,
                        "trajectory_summary": "Prior verifier evidence confirmed the artifact.",
                    }
                ],
            },
        ],
        step=0,
    )

    second_prompt = llm.calls[1]["messages"][1]["content"]
    assert "supporting_candidate_evidence" in second_prompt
    assert "Prior verifier evidence confirmed the artifact" in second_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_response", [RuntimeError("mock outage"), "not-json"])
async def test_model_or_schema_failure_is_retryable_and_restart_is_idempotent(tmp_path, bad_response):
    raw = "Validate checksums before accepting copied artifacts."
    cid = candidate_id(raw, "task-a")
    content = "Validate a checksum before accepting a copied artifact."
    instance, llm = make_manager(tmp_path, [bad_response])

    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    assert instance.l0 == {}
    assert instance.get_l0_candidates()[0]["status"] == "review_failed"

    llm.responses.append(decision("ADD", cid, content=content))
    await instance.process_step_experiences([], step=1)
    assert len(instance.l0) == 1
    assert instance.get_l0_candidates()[0]["attempt_count"] == 2

    restarted, restarted_llm = make_manager(tmp_path, [])
    await restarted.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    assert len(restarted.l0) == 1
    assert restarted_llm.calls == []


@pytest.mark.asyncio
async def test_one_bad_candidate_does_not_block_later_candidate(tmp_path):
    raw_a, raw_b = "Malformed first candidate.", "Valid later candidate."
    id_b = candidate_id(raw_b, "task-b")
    instance, _ = make_manager(
        tmp_path,
        ["not-json", decision("ADD", id_b, content="Commit this later valid lesson.")],
    )

    await instance.process_step_experiences(
        [
            {"content": raw_b, "source_task_ids": ["task-b"]},
            {"content": raw_a, "source_task_ids": ["task-a"]},
        ],
        step=0,
    )

    statuses = {item["id"]: item["status"] for item in instance.get_l0_candidates()}
    assert statuses[candidate_id(raw_a, "task-a")] == "review_failed"
    assert statuses[id_b] == "committed"
    assert len(instance.l0) == 1


@pytest.mark.asyncio
async def test_duplicate_candidate_id_with_changed_evidence_fails_closed(tmp_path):
    raw = "The same summary and source ID must retain the same evidence."
    rollout_id = "rollout-1"
    cid = stable_l0_candidate_id(
        raw,
        source_task_ids=["task-a"],
        source_rollout_ids=[rollout_id],
    )
    instance, llm = make_manager(tmp_path, [decision("KEEP", cid)])
    base = {
        "content": raw,
        "source_task_ids": ["task-a"],
        "source_rollout_ids": [rollout_id],
        "source_evidence": [
            {"id": rollout_id, "task_id": "task-a", "reward": 0.0}
        ],
    }
    await instance.process_step_experiences([base], step=0)
    before = instance.get_l0_candidates()

    changed = {
        **base,
        "source_evidence": [
            {"id": rollout_id, "task_id": "task-a", "reward": 1.0}
        ],
    }
    with pytest.raises(CandidateDecisionError, match="different immutable evidence"):
        await instance.process_step_experiences([changed], step=0)

    assert instance.get_l0_candidates() == before
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_review_write_failure_never_partially_commits(tmp_path, monkeypatch):
    raw = "Verify the result before final submission."
    cid = candidate_id(raw, "task-a")
    content = "Verify the final result before submission."
    instance, llm = make_manager(tmp_path, ["not-json"])
    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    before = (dict(instance.l0), instance.get_l0_candidates())
    original_write = instance._write_state

    def fail_write(*_args, **_kwargs):
        raise OSError("mock atomic replace failure")

    monkeypatch.setattr(instance, "_write_state", fail_write)
    llm.responses.append(decision("ADD", cid, content=content))
    await instance.review_pending_candidates()
    assert (dict(instance.l0), instance.get_l0_candidates()) == before

    monkeypatch.setattr(instance, "_write_state", original_write)
    llm.responses.append(decision("ADD", cid, content=content))
    await instance.review_pending_candidates()
    assert len(instance.l0) == 1


@pytest.mark.asyncio
async def test_explicit_retry_can_override_automatic_attempt_limit(tmp_path):
    raw = "Retry this candidate after a transient review failure."
    cid = candidate_id(raw, "task-a")
    instance, llm = make_manager(tmp_path, ["not-json"], l0_review_max_attempts=1)
    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    llm.responses.append(decision("ADD", cid, content="Persist retries safely after transient failures."))

    automatic = await instance.review_pending_candidates()
    assert automatic["skipped"] == 1
    assert instance.l0 == {}
    forced = await instance.retry_candidate(cid)

    assert forced["committed"] == 1
    assert len(instance.l0) == 1


@pytest.mark.asyncio
async def test_update_does_not_claim_one_side_of_conflicting_soft_metadata(tmp_path):
    target = ExperienceRecord(
        id="L0_target",
        level="L0",
        content="Existing procedure.",
        domain="office",
        task_family="documents",
        tool_type="libreoffice",
    )
    raw = "A related procedure from another supported context."
    cid = stable_l0_candidate_id(
        raw,
        source_task_ids=["task-a"],
        identity_context=["domain=engineering", "task_family=builds", "tool_type=terminal"],
    )
    revised = "Apply the shared procedure only after checking the current task context."
    instance, _ = make_manager(
        tmp_path,
        [decision("UPDATE", cid, target=target.id, content=revised, evidence=[cid, target.id])],
    )
    instance._l0_records[target.id] = target
    instance.save_experiences()

    await instance.process_step_experiences(
        [
            {
                "content": raw,
                "source_task_ids": ["task-a"],
                "domain": "engineering",
                "task_family": "builds",
                "tool_type": "terminal",
            }
        ],
        step=0,
    )

    updated = instance.get_injectable_l0_experiences()[0]
    assert updated["domain"] is None
    assert updated["task_family"] is None
    assert updated["tool_type"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
async def test_updating_or_deleting_aggregated_l0_invalidates_ancestors_without_deleting_them(
    tmp_path, action
):
    target = ExperienceRecord(
        id="L0_target", level="L0", content="Old source lesson.", aggregation_status="aggregated"
    )
    sibling = ExperienceRecord(
        id="L0_sibling", level="L0", content="Sibling source lesson.", aggregation_status="aggregated"
    )
    l1 = ExperienceRecord(
        id="L1_parent",
        level="L1",
        content="Aggregated pattern.",
        parent_ids=[target.id, sibling.id],
        source_l0_ids=[target.id, sibling.id],
        aggregation_status="aggregated",
    )
    l2 = ExperienceRecord(
        id="L2_parent",
        level="L2",
        content="Aggregated meta pattern.",
        parent_ids=[l1.id],
        source_l1_ids=[l1.id],
        source_l0_ids=[target.id, sibling.id],
        aggregation_status="terminal",
    )
    raw = "Evidence correcting the old source lesson."
    cid = candidate_id(raw, "task-a")
    revised = "Corrected source lesson with a supported applicability boundary."
    instance, llm = make_manager(
        tmp_path,
        [
            decision(
                action,
                cid,
                target=target.id,
                content=revised if action == "UPDATE" else None,
                evidence=[cid, target.id],
            )
        ],
    )
    instance._l0_records = {target.id: target, sibling.id: sibling}
    instance._l1_records = {l1.id: l1}
    instance._l2_records = {l2.id: l2}
    instance.save_experiences()

    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )

    assert instance.get_all_l1_experiences()[0]["lifecycle_status"] == "needs_review"
    assert instance.get_all_l2_experiences()[0]["lifecycle_status"] == "needs_review"
    assert instance.get_injectable_l1_experiences() == []
    assert instance.get_injectable_l2_experiences() == []
    assert next(item for item in instance.l0_experiences if item["id"] == sibling.id)[
        "aggregation_status"
    ] == "pending"
    ancestry = instance.trace_ancestry(l2.id)
    assert ancestry["parents"][0]["parents"][0]["experience"]["id"] == target.id
    if action == "UPDATE":
        llm.responses.append(aggregation_decision())
        await instance._aggregate_l1(epoch=1)
        replacement_l1 = instance.get_injectable_l1_experiences()
        assert len(replacement_l1) == 1
        assert replacement_l1[0]["id"] != l1.id
    else:
        await instance._aggregate_l1(epoch=1)
        assert instance.get_injectable_l1_experiences() == []
    assert next(
        item for item in instance.get_all_l1_experiences() if item["id"] == l1.id
    )["lifecycle_status"] == "needs_review"


@pytest.mark.asyncio
async def test_unreviewed_inactive_and_needs_review_items_are_not_aggregated_or_injected(tmp_path):
    raw = "Unreviewed raw candidate."
    instance, llm = make_manager(tmp_path, ["not-json"])
    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    instance._l0_records["L0_inactive"] = ExperienceRecord(
        id="L0_inactive",
        level="L0",
        content="Inactive lesson.",
        lifecycle_status="inactive",
    )
    instance._l1_records["L1_review"] = ExperienceRecord(
        id="L1_review",
        level="L1",
        content="Stale parent lesson.",
        lifecycle_status="needs_review",
    )
    await instance._aggregate_l1(epoch=0)
    await instance._aggregate_l2(epoch=0)

    assert len(llm.calls) == 1
    assert instance.get_injectable_experience_pool() == {}
    assert instance.get_l0_candidates()[0]["status"] == "review_failed"


@pytest.mark.asyncio
async def test_per_task_cap_records_rejection_instead_of_dropping_candidate(tmp_path):
    first_raw, second_raw = "First lesson.", "Second distinct lesson."
    first_id = candidate_id(first_raw, "same-task")
    second_id = candidate_id(second_raw, "same-task")
    instance, _ = make_manager(
        tmp_path,
        [
            decision("ADD", first_id, content="First effective lesson."),
            decision("ADD", second_id, content="Second effective lesson."),
        ],
        max_l0_per_problem=1,
    )
    await instance.process_step_experiences(
        [
            {"content": first_raw, "source_task_ids": ["same-task"]},
            {"content": second_raw, "source_task_ids": ["same-task"]},
        ],
        step=0,
    )

    assert len(instance.l0) == 1
    statuses = {item["id"]: item for item in instance.get_l0_candidates()}
    assert statuses[first_id]["status"] == "committed"
    assert statuses[second_id]["status"] == "review_failed"
    assert "max_l0_per_problem" in statuses[second_id]["last_error"]


@pytest.mark.asyncio
async def test_review_only_updater_mode_never_calls_legacy_flat_merge():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.last_generated_experience_groups = []
    updater.generate_l0_candidates = AsyncMock(return_value=[])
    updater._group_update = AsyncMock(side_effect=AssertionError("legacy group update called"))
    updater._batch_update = AsyncMock(side_effect=AssertionError("legacy batch update called"))
    recorder = TaskRecorder(experiment_name="test", experiences={"old": "unchanged"})

    result = await updater.run([], recorder, maintain_flat_pool=False)

    assert result == {"old": "unchanged"}
    updater._group_update.assert_not_awaited()
    updater._batch_update.assert_not_awaited()


def test_external_loader_filters_non_active_hierarchy_records(tmp_path):
    path = tmp_path / "experiences.json"
    path.write_text(
        json.dumps(
            {
                "l0_experiences": [
                    {"id": "L0_active", "content": "active", "lifecycle_status": "active"},
                    {"id": "L0_inactive", "content": "inactive", "lifecycle_status": "inactive"},
                ],
                "l1_experiences": [
                    {"id": "L1_review", "content": "review", "lifecycle_status": "needs_review"}
                ],
                "l2_experiences": [
                    {"id": "L2_legacy", "content": "legacy active by default"}
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = ExperienceLoader(path).load()

    assert {item.id for item in loaded} == {"L0_active", "L2_legacy"}


def test_candidate_cache_envelope_is_strictly_decoded():
    valid = {
        "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
        "l0_candidates": [{"content": "raw"}],
    }
    malformed = {
        "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
        "l0_candidates": {"not": "a list"},
    }

    assert TrainingFreeGRPO._candidates_from_cache(valid) == [{"content": "raw"}]
    assert TrainingFreeGRPO._candidates_from_cache(malformed) is None
    assert (
        TrainingFreeGRPO._candidates_from_cache(
            {"cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND, "l0_candidates": []}
        )
        is None
    )
    assert TrainingFreeGRPO._candidates_from_cache({"G0": "legacy flat"}) is None
    for invalid_items in ([42], [{"bad": "missing content"}], [{"content": "  "}]):
        assert (
            TrainingFreeGRPO._candidates_from_cache(
                {
                    "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
                    "l0_candidates": invalid_items,
                }
            )
            is None
        )
    cross_task_evidence = {
        "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
        "l0_candidates": [
            {
                "content": "raw",
                "source_task_ids": ["task-a"],
                "source_rollout_ids": ["rollout-1"],
                "source_evidence": [
                    {"id": "rollout-1", "task_id": "task-b", "reward": 0.0}
                ],
            }
        ],
    }
    assert TrainingFreeGRPO._candidates_from_cache(cross_task_evidence) is None
    assert (
        TrainingFreeGRPO._candidates_from_cache(
            {**valid, "batch_fingerprint": "old"},
            expected_batch_fingerprint="current",
        )
        is None
    )


def test_review_off_cache_accepts_only_strict_flat_or_replayable_hierarchy_envelope():
    assert TrainingFreeGRPO._flat_experiences_from_cache({"G0": "legacy flat"}) == {
        "G0": "legacy flat"
    }
    for invalid in (
        {"G0": 42},
        {"cache_kind": "unknown", "G0": "must not be injected"},
        {"l0_candidates": [{"content": "raw"}]},
    ):
        assert TrainingFreeGRPO._flat_experiences_from_cache(invalid) is None

    payload = TrainingFreeGRPO._hierarchical_flat_cache_payload(
        {"G0": "sequential"},
        [{"content": "raw candidate"}],
        batch_fingerprint="batch-sha",
    )
    assert payload["cache_kind"] == HIERARCHICAL_FLAT_CACHE_KIND
    assert TrainingFreeGRPO._hierarchical_flat_from_cache(
        payload,
        expected_batch_fingerprint="batch-sha",
    ) == ({"G0": "sequential"}, [{"content": "raw candidate"}])
    assert (
        TrainingFreeGRPO._hierarchical_flat_from_cache(
            payload,
            expected_batch_fingerprint="changed-sha",
        )
        is None
    )
    tampered_context = {
        "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
        "batch_fingerprint": "batch-sha",
        "l0_candidates": [
            {
                "content": "raw",
                "run_id": "wrong-run",
                "epoch": 1,
                "batch": 2,
                "batch_fingerprint": "batch-sha",
            }
        ],
    }
    assert (
        TrainingFreeGRPO._candidates_from_cache(
            tampered_context,
            expected_batch_fingerprint="batch-sha",
            expected_run_id="run-a",
            expected_epoch=1,
            expected_batch=2,
        )
        is None
    )


@pytest.mark.asyncio
async def test_hierarchy_snapshot_recovers_exact_candidates_when_db_cache_is_missing(tmp_path):
    raw = "Persist the candidate before reviewing it."
    cid = candidate_id(raw, "task-a")
    instance, _ = make_manager(
        tmp_path,
        [decision("ADD", cid, content="Persist candidates before sequential review.")],
    )
    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}],
        step=4,
        run_id="run-a",
        epoch=1,
        batch=2,
        batch_fingerprint="batch-sha",
    )
    restarted, _ = make_manager(tmp_path, [])
    runner = TrainingFreeGRPO.__new__(TrainingFreeGRPO)
    runner.hierarchical_experience_manager = restarted

    recovered_batches = []
    for cached_experiences in (
        None,
        {
            "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
            "batch_fingerprint": "batch-sha",
            "l0_candidates": [42],
        },
        {
            "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
            "batch_fingerprint": "old-sha",
            "l0_candidates": [{"content": "stale"}],
        },
    ):
        recovered_batches.append(
            runner._recover_hierarchical_candidates(
                step=4,
                run_id="run-a",
                epoch=1,
                batch=2,
                batch_fingerprint="batch-sha",
                cached_experiences=cached_experiences,
                cache_reuse_allowed=True,
            )
        )
    step_drift, _ = runner._recover_hierarchical_candidates(
        step=999,
        run_id="run-a",
        epoch=1,
        batch=2,
        batch_fingerprint="batch-sha",
        cached_experiences=None,
        cache_reuse_allowed=True,
    )
    with pytest.raises(RuntimeError, match="generation fingerprint changed"):
        runner._recover_hierarchical_candidates(
            step=999,
            run_id="run-a",
            epoch=1,
            batch=2,
            batch_fingerprint="different-sha",
            cached_experiences=None,
            cache_reuse_allowed=True,
        )

    assert all(
        recovered is not None
        and [item["content"] for item in recovered] == [raw]
        and repair_cache is True
        for recovered, repair_cache in recovered_batches
    )
    assert step_drift is not None and [item["content"] for item in step_drift] == [raw]


def test_restart_step_rejects_every_populated_hierarchy_state(tmp_path):
    instance, _ = make_manager(tmp_path, [])
    instance.assert_restart_step_safe(0)
    instance._candidate_records["candidate"] = instance._candidate_from_input(
        {"content": "future candidate", "source_task_ids": ["task-a"]},
        step=4,
    )

    with pytest.raises(RuntimeError, match="Cannot safely rewind"):
        instance.assert_restart_step_safe(4)
    with pytest.raises(RuntimeError, match="Cannot safely rewind"):
        instance.assert_restart_step_safe(5)

    # Epoch-end L1/L2 have no trustworthy numeric creation step either.
    instance._candidate_records.clear()
    instance._l1_records["L1_future"] = ExperienceRecord(
        id="L1_future",
        level="L1",
        content="Created only after an epoch finished.",
    )
    with pytest.raises(RuntimeError, match="Cannot safely rewind"):
        instance.assert_restart_step_safe(999)


def test_rollout_batch_fingerprint_is_order_independent_and_content_sensitive():
    first = {"trace_id": "trace-a", "response": "one", "reward": 1.0}
    second = {"trace_id": "trace-b", "response": "two", "reward": 0.0}

    original = TrainingFreeGRPO._rollout_batch_fingerprint([first, second])
    reordered = TrainingFreeGRPO._rollout_batch_fingerprint([second, first])
    changed = TrainingFreeGRPO._rollout_batch_fingerprint(
        [first, {**second, "response": "changed"}]
    )

    assert original == reordered
    assert original != changed
    assert original != TrainingFreeGRPO._rollout_batch_fingerprint(
        [{**first, "id": 99}, second]
    )


def test_rollout_selection_is_order_independent_with_reward_ties():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    rollouts = [
        EvaluationSample(id=index, raw_question="same task", reward=1.0)
        for index in range(1, 7)
    ]
    forward = updater._select_representative_rollouts(rollouts, max_items=4)
    reverse = updater._select_representative_rollouts(list(reversed(rollouts)), max_items=4)
    assert [item.id for item in forward] == [item.id for item in reverse] == [1, 2, 3, 4]

    summaries = [
        {"id": index, "raw_question": "same task", "reward": 1.0}
        for index in range(1, 7)
    ]
    forward_summaries = updater._select_counterfactual_summaries(summaries, max_items=4)
    reverse_summaries = updater._select_counterfactual_summaries(
        list(reversed(summaries)), max_items=4
    )
    assert [item["id"] for item in forward_summaries] == [1, 2, 3, 4]
    assert reverse_summaries == forward_summaries


def test_candidate_generation_fingerprint_changes_with_generation_config():
    runner = TrainingFreeGRPO.__new__(TrainingFreeGRPO)
    model_params = SimpleNamespace(model_dump=lambda **_kwargs: {"temperature": 0.0})
    model_provider = SimpleNamespace(type="chat.completions", model="mock-model", base_url=None)
    model = SimpleNamespace(model_provider=model_provider, model_params=model_params)
    practice = SimpleNamespace(
        given_ground_truth=True,
        num_experiences_per_query=2,
        agent_objective="complete tasks",
        learning_objective="learn procedures",
        hierarchical_learning=SimpleNamespace(
            experience_output_language="same_as_input"
        ),
    )
    runner.config = SimpleNamespace(
        practice=practice,
        evaluation=SimpleNamespace(agent=SimpleNamespace(model=model)),
    )
    runner.experience_updater = SimpleNamespace(prompts={"summary": "prompt-v1"})
    rollouts = [{"trace_id": "trace-a", "response": "result", "reward": 1.0}]

    original = runner._candidate_generation_fingerprint(rollouts)
    practice.hierarchical_learning.experience_output_language = "english"
    language_changed = runner._candidate_generation_fingerprint(rollouts)
    practice.num_experiences_per_query = 3
    changed = runner._candidate_generation_fingerprint(rollouts)

    assert original != language_changed
    assert original != changed


def test_stable_task_grouping_reads_official_metadata_from_evaluation_sample():
    sample = EvaluationSample(
        source="SkillsBench",
        dataset="SkillsBench-v1.1",
        dataset_index=7,
        raw_question="same wording is not identity",
        meta={"task_id": "official-task-id"},
    )

    assert ExperienceUpdater._stable_task_id(sample) == "SkillsBench:official-task-id"


def test_compact_rollout_evidence_is_preserved_from_verifier_metadata():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    metadata = updater._l0_source_metadata(
        [
            {
                "source": "SkillsBench",
                "raw_question": "task",
                "trace_id": "trace-1",
                "reward": 0.0,
                "reasoning": "Verifier says the output file is missing.",
                "trajectory_summary": "The agent never checked the output directory.",
                "meta": {
                    "task_id": "official-task",
                    "domain": "software",
                    "task_family": "artifact_creation",
                    "trial_outcome": "failed",
                    "error_type": "missing_artifact",
                },
            }
        ]
    )

    assert metadata["source_rollout_ids"] == ["trace-1"]
    assert metadata["source_evidence"] == [
        {
            "id": "trace-1",
            "task_id": "SkillsBench:official-task",
            "reward": 0.0,
            "outcome": "failed",
            "error_type": "missing_artifact",
            "infra_error_type": None,
            "trajectory_summary": "The agent never checked the output directory.",
            "verifier_feedback": "Verifier says the output file is missing.",
        }
    ]


def test_rollout_evidence_deduplicates_identical_ids_and_rejects_conflicts():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    rollout = {
        "id": 101,
        "raw_question": "task",
        "reward": 1.0,
        "trajectory_summary": "same evidence",
    }

    assert len(updater._source_evidence([rollout, dict(rollout)])) == 1
    with pytest.raises(L0CandidateGenerationError, match="evidence ID collision"):
        updater._source_evidence([rollout, {**rollout, "reward": 0.0}])


@pytest.mark.asyncio
async def test_single_summary_preserves_meta_and_verifier_feedback_for_candidate_evidence():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.agent_objective = "complete tasks"
    updater.learning_objective = "learn procedures"
    updater.prompts = {
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP": "summarize",
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP": "{{ question }}",
    }
    updater.llm = QueueLLM(["trajectory summary"])
    updater.config = SimpleNamespace(
        model=SimpleNamespace(model_params=SimpleNamespace(model_dump=lambda: {}))
    )
    rollout = EvaluationSample(
        source="SkillsBench",
        raw_question="task",
        trace_id="trace-1",
        reward=0.0,
        reasoning="Verifier rejected the missing artifact.",
        meta={"task_id": "official-task", "trial_outcome": "failed"},
    )

    grouped = await updater._single_rollout_summary(
        [rollout], concurrency=1, given_ground_truth=False
    )
    summarized = next(iter(grouped.values()))
    evidence = updater._l0_source_metadata(summarized)["source_evidence"][0]

    assert evidence["task_id"] == "SkillsBench:official-task"
    assert evidence["outcome"] == "failed"
    assert evidence["trajectory_summary"] == "trajectory summary"
    assert evidence["verifier_feedback"] == "Verifier rejected the missing artifact."


@pytest.mark.asyncio
async def test_single_summary_preserves_database_ids_for_trace_less_duplicate_rollouts():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.agent_objective = "complete tasks"
    updater.learning_objective = "learn procedures"
    updater.prompts = {
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP": "summarize",
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP": "{{ question }}",
    }
    updater.llm = QueueLLM(["same summary", "same summary"])
    updater.config = SimpleNamespace(
        model=SimpleNamespace(model_params=SimpleNamespace(model_dump=lambda: {}))
    )
    rollouts = [
        EvaluationSample(id=101, raw_question="same task", reward=1.0),
        EvaluationSample(id=102, raw_question="same task", reward=1.0),
    ]

    grouped = await updater._single_rollout_summary(
        rollouts,
        concurrency=2,
        given_ground_truth=False,
    )
    summarized = next(iter(grouped.values()))
    metadata = updater._l0_source_metadata(summarized)

    assert metadata["source_rollout_ids"] == ["101", "102"]
    assert {item["id"] for item in metadata["source_evidence"]} == {"101", "102"}


@pytest.mark.asyncio
async def test_parallel_summary_failure_aborts_instead_of_returning_partial_candidates():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.agent_objective = "complete tasks"
    updater.learning_objective = "learn procedures"
    updater.prompts = {
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP": "summarize",
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP": "{{ question }}",
    }
    updater.llm = QueueLLM(["valid summary", RuntimeError("summary unavailable")])
    updater.config = SimpleNamespace(
        model=SimpleNamespace(model_params=SimpleNamespace(model_dump=lambda: {}))
    )
    rollouts = [
        EvaluationSample(raw_question="task one", trace_id="trace-1", reward=1.0),
        EvaluationSample(raw_question="task two", trace_id="trace-2", reward=0.0),
    ]

    with pytest.raises(L0CandidateGenerationError, match="refusing a partial candidate batch"):
        await updater._single_rollout_summary(rollouts, concurrency=2, given_ground_truth=False)


@pytest.mark.asyncio
async def test_rollout_summaries_for_distinct_tasks_execute_concurrently():
    class BarrierLLM:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.both_started = asyncio.Event()

        async def query_one(self, **_kwargs):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active == 2:
                self.both_started.set()
            await asyncio.wait_for(self.both_started.wait(), timeout=1.0)
            self.active -= 1
            return "summary"

    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.agent_objective = "complete tasks"
    updater.learning_objective = "learn procedures"
    updater.prompts = {
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP": "summarize",
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP": "{{ question }}",
    }
    updater.llm = BarrierLLM()
    updater.config = SimpleNamespace(
        model=SimpleNamespace(model_params=SimpleNamespace(model_dump=lambda: {}))
    )
    rollouts = [
        EvaluationSample(raw_question="task one", trace_id="trace-1"),
        EvaluationSample(raw_question="task two", trace_id="trace-2"),
    ]

    summaries = await updater._single_rollout_summary(
        rollouts,
        concurrency=2,
        given_ground_truth=False,
    )

    assert len(summaries) == 2
    assert updater.llm.max_active == 2


@pytest.mark.asyncio
async def test_group_advantage_parse_failure_aborts_candidate_batch():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.agent_objective = "complete tasks"
    updater.learning_objective = "learn procedures"
    updater.prompts = {
        "SINGLE_QUERY_GROUP_ADVANTAGE_SP": "extract {{ num_experiences }} experiences",
        "SINGLE_QUERY_GROUP_ADVANTAGE_UP": "{{ question }} {{ trajectories }}",
    }
    updater.llm = QueueLLM(
        [
            "<Experiences>valid candidate</Experiences>",
            "malformed response without the required tags",
        ]
    )
    updater.config = SimpleNamespace(
        model=SimpleNamespace(model_params=SimpleNamespace(model_dump=lambda: {}))
    )
    summaries = {
        task_id: [
            {
                "raw_question": task_id,
                "correct_answer": "answer",
                "reward": 0.0,
                "trajectory_summary": "The attempted workflow failed verification.",
                "source": "SkillsBench",
                "meta": {"task_id": task_id},
            }
        ]
        for task_id in ("task-a", "task-b")
    }

    with pytest.raises(L0CandidateGenerationError, match="refusing a partial candidate batch"):
        await updater._group_advantage(
            summaries,
            concurrency=1,
            given_ground_truth=True,
            num_experiences=1,
        )


@pytest.mark.asyncio
async def test_candidate_generation_failure_clears_previous_call_state():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.last_l0_candidates = [{"content": "stale candidate"}]
    updater.last_generated_experience_groups = [{"experiences": "stale group"}]
    updater.last_l0_metadata_coverage = {"domain": {"known": 1, "total": 1, "ratio": 1.0}}
    updater._single_rollout_summary = AsyncMock(
        side_effect=L0CandidateGenerationError("mock partial failure")
    )

    with pytest.raises(L0CandidateGenerationError, match="mock partial failure"):
        await updater.generate_l0_candidates([])

    assert updater.last_l0_candidates == []
    assert updater.last_generated_experience_groups == []
    assert updater.last_l0_metadata_coverage == {}


def test_large_pool_review_recall_uses_configured_semantic_embedding(tmp_path):
    instance, _ = make_manager(
        tmp_path,
        l0_review_full_pool_limit=1,
        l0_review_top_k=1,
        l0_review_retrieval="semantic",
    )
    instance.clusterer.embedding_provider = ParaphraseEmbedding()
    target = ExperienceRecord(
        id="L0_target",
        level="L0",
        content="Validate output prior to submission.",
    )
    distractors = {
        f"L0_distractor_{index}": ExperienceRecord(
            id=f"L0_distractor_{index}",
            level="L0",
            content=f"Unrelated package installation detail {index}.",
        )
        for index in range(55)
    }
    instance._l0_records = {target.id: target, **distractors}
    candidate = instance._candidate_from_input(
        {"content": "Ensure accuracy before delivery.", "source_task_ids": ["task-a"]},
        step=0,
    )
    assert candidate is not None

    related, scope = instance._related_active_l0(candidate)

    assert [item.id for item in related] == [target.id]
    assert scope == "semantic_top_1_of_56"


def test_review_prompt_evidence_is_bounded_without_changing_persisted_sources(tmp_path):
    instance, _ = make_manager(
        tmp_path,
        l0_review_evidence_per_experience=10,
        l0_review_rollout_evidence_per_candidate=1,
        l0_review_source_ids_per_item=4,
        l0_review_max_supporting_evidence_chars=3000,
    )
    candidate_ids = []
    for index in range(8):
        candidate = instance._candidate_from_input(
            {
                "content": f"support candidate {index} " + ("detail " * 30),
                "source_task_ids": [f"task-{index}"],
                "source_rollout_ids": [f"rollout-{index}-a", f"rollout-{index}-b"],
                "source_evidence": [
                    {
                        "id": f"rollout-{index}-a",
                        "task_id": f"task-{index}",
                        "trajectory_summary": "evidence A " * 30,
                    },
                    {
                        "id": f"rollout-{index}-b",
                        "task_id": f"task-{index}",
                        "trajectory_summary": "evidence B " * 30,
                    },
                ],
            },
            step=index,
        )
        assert candidate is not None
        instance._candidate_records[candidate.id] = candidate
        candidate_ids.append(candidate.id)
    record = ExperienceRecord(
        id="L0_existing",
        level="L0",
        content="A bounded evidence example.",
        source_task_ids=[f"historical-task-{index}" for index in range(1000)],
        source_rollout_ids=[f"historical-rollout-{index}" for index in range(1000)],
        review_candidate_ids=candidate_ids,
    )

    views, _, displayed_records = instance._related_l0_review_views([record])
    support = views[0]["supporting_candidate_evidence"]
    encoded_chars = sum(
        len(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        for item in support
    )

    assert 0 < len(support) < len(candidate_ids)
    assert [item.id for item in displayed_records] == [record.id]
    assert len(json.dumps(views, ensure_ascii=False, sort_keys=True)) <= 3000
    assert len(views[0]["source_task_ids"]) == 4
    assert len(views[0]["source_rollout_ids"]) == 4
    assert encoded_chars <= 3000
    assert all(len(item["source_evidence"]) <= 1 for item in support)
    assert all(len(item.source_evidence) == 2 for item in instance._candidate_records.values())


def test_schema_v2_pending_l1_is_not_misclassified_as_legacy(tmp_path):
    path = tmp_path / "experiences.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "l0_experiences": [],
                "l1_experiences": [
                    {
                        "id": "L1_pending",
                        "level": "L1",
                        "content": "A valid pending L1 experience.",
                        "aggregation_status": "pending",
                    }
                ],
                "l2_experiences": [
                    {
                        "id": "L2_existing",
                        "level": "L2",
                        "content": "An existing terminal L2 experience.",
                        "aggregation_status": "terminal",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    instance, _ = make_manager(tmp_path, [])

    assert instance.get_all_l1_experiences()[0]["aggregation_status"] == "pending"


# ---------------------------------------------------------------------------
# L1/L2 candidate review
# ---------------------------------------------------------------------------


def upper_structured(title: str) -> dict:
    return {
        "decision": "aggregate",
        "title": title,
        "principle": "Use the shared verified procedure when its observable trigger is present.",
        "applicable_when": ["the source-specific trigger is observable"],
        "not_applicable_when": ["the source conditions or tool contract differ"],
        "recommended_actions": ["apply the procedure and verify the resulting artifact"],
        "evidence_summary": "The cited direct parents contain matching operational evidence.",
        "confidence": 0.8,
    }


def upper_decision(
    action: str,
    candidate: ExperienceCandidateRecord,
    *,
    target: str | None = None,
    evidence: list[str] | None = None,
    title: str = "Reviewed upper-level pattern",
) -> str:
    return json.dumps(
        {
            "action": action,
            "candidate_id": candidate.id,
            "level": candidate.level,
            "target_id": target,
            "new_content": "complete canonical content" if action in {"ADD", "UPDATE"} else None,
            "new_structured_content": (
                upper_structured(title) if action in {"ADD", "UPDATE"} else None
            ),
            "reason": f"mock {action.lower()} grounded in direct lower-level evidence",
            "evidence_ids": evidence if evidence is not None else [candidate.id],
        }
    )


def make_test_cluster(cluster_id: str, parents: list[ExperienceRecord]) -> ExperienceCluster:
    return ExperienceCluster(
        cluster_id=cluster_id,
        experience_ids=sorted(parent.id for parent in parents),
        centroid=[1.0, 0.0],
        representative_id=sorted(parent.id for parent in parents)[0],
        representative_content=parents[0].content,
        intra_cluster_similarity=1.0,
        metadata_consistency=1.0,
        metadata_completeness=0.0,
    )


def make_l0(exp_id: str, content: str | None = None) -> ExperienceRecord:
    return ExperienceRecord(
        id=exp_id,
        level="L0",
        content=content or f"Verified procedure from {exp_id}.",
        source_task_ids=[f"task-{exp_id}"],
        source_rollout_ids=[f"rollout-{exp_id}"],
        aggregation_status="pending",
    )


def make_l1(
    exp_id: str,
    l0_parent: ExperienceRecord,
    content: str | None = None,
) -> ExperienceRecord:
    return ExperienceRecord(
        id=exp_id,
        level="L1",
        content=content or f"Reusable operational pattern from {exp_id}.",
        source_task_ids=list(l0_parent.source_task_ids),
        source_rollout_ids=list(l0_parent.source_rollout_ids),
        parent_ids=[l0_parent.id],
        source_l0_ids=[l0_parent.id],
        aggregation_status="pending",
    )


def stage_upper_candidate(
    instance: HierarchicalExperienceManager,
    level: str,
    parents: list[ExperienceRecord],
    *,
    title: str,
    cluster_id: str,
    epoch: int = 0,
) -> ExperienceCandidateRecord:
    cluster = make_test_cluster(cluster_id, parents)
    child = instance._make_child(
        level,
        parents,
        cluster,
        AggregatedExperienceContent.model_validate(upper_structured(title)),
    )
    candidate = instance._make_upper_candidate(child, cluster, epoch=epoch)
    staged, created = instance._stage_upper_candidate(candidate)
    assert created
    return staged


def prepare_upper_review_case(
    tmp_path,
    level: str,
    *,
    action: str,
):
    instance, llm = make_manager(
        tmp_path,
        l1_candidate_review_enabled=True,
        l2_candidate_review_enabled=True,
    )
    old_l0 = make_l0("L0_old")
    new_l0_a = make_l0("L0_new_a")
    new_l0_b = make_l0("L0_new_b")
    instance._l0_records = {
        record.id: record for record in (old_l0, new_l0_a, new_l0_b)
    }

    if level == "L1":
        parents = [new_l0_a, new_l0_b]
        lower_old = old_l0
        target = ExperienceRecord(
            id="L1_existing",
            level="L1",
            content="Existing bounded L1 operational pattern.",
            source_task_ids=list(old_l0.source_task_ids),
            source_rollout_ids=list(old_l0.source_rollout_ids),
            parent_ids=[old_l0.id],
            source_l0_ids=[old_l0.id],
            aggregation_status="pending",
        )
        instance._l1_records[target.id] = target
    else:
        old_l1 = make_l1("L1_old", old_l0)
        new_l1_a = make_l1("L1_new_a", new_l0_a)
        new_l1_b = make_l1("L1_new_b", new_l0_b)
        instance._l1_records = {
            record.id: record for record in (old_l1, new_l1_a, new_l1_b)
        }
        parents = [new_l1_a, new_l1_b]
        lower_old = old_l1
        target = ExperienceRecord(
            id="L2_existing",
            level="L2",
            content="Existing evidence-bounded L2 conditional strategy.",
            source_task_ids=list(old_l1.source_task_ids),
            source_rollout_ids=list(old_l1.source_rollout_ids),
            parent_ids=[old_l1.id],
            source_l1_ids=[old_l1.id],
            source_l0_ids=[old_l0.id],
            aggregation_status="terminal",
        )
        instance._l2_records[target.id] = target

    # Represent the pre-existing child relationship accurately so DELETE and
    # UPDATE tests exercise release/repointing rather than malformed fixtures.
    lower_store = instance._store("L0" if level == "L1" else "L1")
    lower_store[lower_old.id] = lower_store[lower_old.id].model_copy(
        update={
            "aggregation_status": "aggregated",
            "aggregated_into_experience_id": target.id,
        }
    )
    candidate = stage_upper_candidate(
        instance,
        level,
        [lower_store[parent.id] for parent in parents],
        title=f"Candidate {level} pattern",
        cluster_id=f"cluster-{level.lower()}-candidate",
    )
    evidence = [candidate.parent_ids[0]]
    if action in {"UPDATE", "DELETE"}:
        evidence.append(target.id)
    llm.responses = [
        upper_decision(
            action,
            candidate,
            target=target.id if action in {"UPDATE", "DELETE"} else None,
            evidence=evidence,
            title=f"Reviewed {level} {action.lower()} pattern",
        )
    ]
    return instance, llm, candidate, target, lower_old


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["L1", "L2"])
@pytest.mark.parametrize("action", ["ADD", "UPDATE", "DELETE", "KEEP"])
async def test_upper_level_four_actions_are_atomic_and_same_level(
    tmp_path,
    level,
    action,
):
    instance, _, candidate, target, lower_old = prepare_upper_review_case(
        tmp_path,
        level,
        action=action,
    )

    counts = await instance.review_pending_candidates(candidate_level=level)

    assert counts == {"committed": 1, "failed": 0, "stale": 0, "skipped": 0}
    reviewed = instance._candidate_records[candidate.id]
    store = instance._store(level)
    archive = instance._l1_archive if level == "L1" else instance._l2_archive
    lower_store = instance._store("L0" if level == "L1" else "L1")
    if action == "ADD":
        assert reviewed.resolution == "adopted"
        assert target.id in store and reviewed.result_experience_id in store
        assert all(
            lower_store[parent_id].aggregated_into_experience_id
            == reviewed.result_experience_id
            for parent_id in candidate.parent_ids
        )
    elif action == "UPDATE":
        assert reviewed.resolution == "adopted"
        assert target.id not in store and target.id in archive
        assert archive[target.id].superseded_by_id == reviewed.result_experience_id
        replacement = store[str(reviewed.result_experience_id)]
        assert replacement.supersedes_id == target.id
        assert set(replacement.parent_ids) == {*candidate.parent_ids, lower_old.id}
        assert all(
            lower_store[parent_id].aggregated_into_experience_id == replacement.id
            for parent_id in replacement.parent_ids
        )
    elif action == "DELETE":
        assert reviewed.resolution == "not_adopted"
        assert reviewed.result_experience_id is None
        assert target.id not in store and target.id in archive
        assert lower_store[lower_old.id].aggregation_status == "pending"
        assert all(lower_store[parent_id].aggregation_status == "pending" for parent_id in candidate.parent_ids)
    else:
        assert reviewed.resolution == "not_adopted"
        assert reviewed.result_experience_id is None
        assert target.id in store and target.id not in archive
        assert lower_store[lower_old.id].aggregated_into_experience_id == target.id
        assert all(lower_store[parent_id].aggregation_status == "pending" for parent_id in candidate.parent_ids)


@pytest.mark.asyncio
@pytest.mark.parametrize("level,wrong_level", [("L1", "L2"), ("L2", "L1")])
async def test_upper_review_rejects_cross_level_target(tmp_path, level, wrong_level):
    instance, llm, candidate, _, _ = prepare_upper_review_case(
        tmp_path,
        level,
        action="KEEP",
    )
    wrong_target = ExperienceRecord(
        id=f"{wrong_level}_wrong_target",
        level=wrong_level,
        content="A target from the wrong abstraction level.",
        aggregation_status="terminal" if wrong_level == "L2" else "pending",
    )
    instance._store(wrong_level)[wrong_target.id] = wrong_target
    llm.responses = [
        upper_decision(
            "UPDATE",
            candidate,
            target=wrong_target.id,
            evidence=[candidate.parent_ids[0], wrong_target.id],
        )
    ]

    before = instance.get_injectable_experience_pool()
    counts = await instance.review_pending_candidates(candidate_level=level)

    assert counts["failed"] == 1
    assert instance._candidate_records[candidate.id].status == "review_failed"
    assert instance.get_injectable_experience_pool() == before


@pytest.mark.asyncio
async def test_duplicate_l1_candidates_from_different_parent_clusters_do_not_duplicate_pool(tmp_path):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents_a = [make_l0("L0_a1"), make_l0("L0_a2")]
    parents_b = [make_l0("L0_b1"), make_l0("L0_b2")]
    instance._l0_records = {item.id: item for item in [*parents_a, *parents_b]}
    first = stage_upper_candidate(
        instance,
        "L1",
        parents_a,
        title="Same semantic procedure",
        cluster_id="cluster-a",
    )
    second = stage_upper_candidate(
        instance,
        "L1",
        parents_b,
        title="Same semantic procedure",
        cluster_id="cluster-b",
    )
    ordered = sorted([first, second], key=instance._review_sort_key)
    llm.responses = [
        upper_decision("ADD", ordered[0], evidence=[ordered[0].parent_ids[0]]),
        upper_decision("KEEP", ordered[1], evidence=[ordered[1].id]),
    ]

    await instance.review_pending_candidates(candidate_level="L1")

    assert len(instance.l1) == 1
    assert instance._candidate_records[ordered[0].id].resolution == "adopted"
    assert instance._candidate_records[ordered[1].id].resolution == "not_adopted"
    assert instance._candidate_records[ordered[1].id].result_experience_id is None
    assert list(instance.l1.values())[0] in llm.calls[1]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_staged_l1_candidate_is_not_active_or_consumed_before_review(tmp_path):
    instance, llm = make_manager(
        tmp_path,
        l1_candidate_review_enabled=True,
        l2_candidate_review_enabled=True,
    )
    parents = [make_l0("L0_wait_a"), make_l0("L0_wait_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Persisted but unreviewed pattern",
        cluster_id="cluster-unreviewed",
    )

    assert candidate.status == "pending"
    assert instance.l1 == {}
    assert candidate.id not in instance.get_injectable_experience_pool()
    assert all(parent.aggregation_status == "pending" for parent in instance._l0_records.values())
    await instance._aggregate_l2(epoch=0)
    assert instance.l2 == {}
    assert llm.calls == []


@pytest.mark.asyncio
async def test_keep_is_terminal_for_unchanged_generation_but_leaves_parents_pending(tmp_path):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_keep_a"), make_l0("L0_keep_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    report = instance._cluster_pending(
        parents,
        level="L0",
        minimum_size=2,
        similarity_threshold=0.8,
    )
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    child = instance._make_child(
        "L1",
        parents,
        cluster,
        AggregatedExperienceContent.model_validate(
            upper_structured("Candidate intentionally kept out")
        ),
    )
    candidate, created = instance._stage_upper_candidate(
        instance._make_upper_candidate(child, cluster, epoch=0)
    )
    assert created
    llm.responses = [upper_decision("KEEP", candidate)]
    await instance.review_pending_candidates(candidate_level="L1")
    llm.calls.clear()

    await instance._aggregate_l1(epoch=1)

    assert llm.calls == []
    assert instance._candidate_records[candidate.id].resolution == "not_adopted"
    assert all(parent.aggregation_status == "pending" for parent in instance._l0_records.values())
    audit = json.loads((tmp_path / "clusters.jsonl").read_text().splitlines()[-1])
    assert audit["aggregation_summary"] == {
        "direct_success": 0,
        "adopted": 0,
        "not_adopted": 1,
        "generation_failed": 0,
        "review_failed": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
async def test_l1_revision_or_deletion_marks_dependent_l2_needs_review(tmp_path, action):
    instance, llm, candidate, target, _ = prepare_upper_review_case(
        tmp_path,
        "L1",
        action=action,
    )
    dependent = ExperienceRecord(
        id="L2_dependent",
        level="L2",
        content="A dependent higher-order strategy.",
        parent_ids=[target.id],
        source_l1_ids=[target.id],
        source_l0_ids=list(target.source_l0_ids),
        aggregation_status="terminal",
    )
    instance._l2_records[dependent.id] = dependent

    await instance.review_pending_candidates(candidate_level="L1")

    invalidated = instance._l2_records[dependent.id]
    assert invalidated.lifecycle_status == "needs_review"
    assert target.id in invalidated.invalidated_by_ids
    assert dependent.id not in instance.get_injectable_experience_pool()
    assert llm.responses == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["model", "json", "evidence", "structure"])
async def test_upper_review_failures_leave_pool_unchanged_and_candidate_retryable(
    tmp_path,
    failure_kind,
):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_fail_a"), make_l0("L0_fail_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Retryable candidate pattern",
        cluster_id=f"cluster-failure-{failure_kind}",
    )
    if failure_kind == "model":
        response = RuntimeError("mock review outage")
    elif failure_kind == "json":
        response = "not JSON"
    elif failure_kind == "evidence":
        response = upper_decision("ADD", candidate, evidence=["not-supplied"])
    else:
        payload = json.loads(upper_decision("ADD", candidate, evidence=[parents[0].id]))
        payload["new_structured_content"] = {"decision": "aggregate", "title": "incomplete"}
        response = json.dumps(payload)
    llm.responses = [response]

    counts = await instance.review_pending_candidates(candidate_level="L1")

    assert counts["failed"] == 1
    assert instance.l1 == {}
    assert instance._candidate_records[candidate.id].status == "review_failed"
    assert all(parent.aggregation_status == "pending" for parent in instance._l0_records.values())


@pytest.mark.asyncio
async def test_upper_candidate_source_version_drift_becomes_stale_without_model_call(tmp_path):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_stale_a"), make_l0("L0_stale_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Candidate based on pinned parent versions",
        cluster_id="cluster-stale",
    )
    instance._l0_records[parents[0].id] = parents[0].model_copy(
        update={"content": "A materially revised source experience."}
    )

    counts = await instance.review_pending_candidates(candidate_level="L1")

    assert counts["stale"] == 1
    assert instance._candidate_records[candidate.id].status == "stale"
    assert instance.l1 == {}
    assert llm.calls == []


@pytest.mark.asyncio
async def test_upper_review_write_failure_cannot_partially_commit(tmp_path, monkeypatch):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_write_a"), make_l0("L0_write_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Atomic candidate pattern",
        cluster_id="cluster-write-failure",
    )
    llm.responses = [upper_decision("ADD", candidate, evidence=[parents[0].id])]
    persisted_before = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))

    def fail_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(instance, "_write_state", fail_write)
    counts = await instance.review_pending_candidates(candidate_level="L1")

    assert counts["failed"] == 1
    assert instance.l1 == {}
    assert instance._candidate_records[candidate.id].status == "pending"
    assert all(parent.aggregation_status == "pending" for parent in instance._l0_records.values())
    assert json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8")) == persisted_before


@pytest.mark.asyncio
async def test_committed_upper_candidate_is_restart_idempotent(tmp_path):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_restart_a"), make_l0("L0_restart_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Restart-stable upper candidate",
        cluster_id="cluster-restart",
    )
    llm.responses = [upper_decision("ADD", candidate, evidence=[parents[0].id])]
    await instance.review_pending_candidates(candidate_level="L1")
    expected_l1 = instance.get_all_l1_experiences()

    restarted, restarted_llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    counts = await restarted.review_pending_candidates(candidate_level="L1")
    await restarted._aggregate_l1(epoch=1)

    assert counts == {"committed": 0, "failed": 0, "stale": 0, "skipped": 0}
    assert restarted.get_all_l1_experiences() == expected_l1
    assert restarted_llm.calls == []


class TwoStageEmbedding:
    """Separate two L0 themes, then join reviewed L1 operational patterns."""

    def embed(self, texts):
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "upper-shared" in lowered:
                vectors.append([0.0, 0.0, 1.0])
            elif "alpha" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "beta" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


class HierarchyWorkflowLLM:
    """Deterministic aggregation/review responder for the real epoch entry."""

    def __init__(self):
        self.calls: list[dict] = []

    @staticmethod
    def _candidate_segment(user_prompt: str) -> str:
        return user_prompt.split("Current active", 1)[0]

    async def query_one(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs["messages"][0]["content"]
        user = kwargs["messages"][1]["content"]
        if "maintain an evidence-backed pool" not in system:
            if "alpha" in user.lower() and "beta" not in user.lower():
                title = "upper-shared alpha procedure"
            elif "beta" in user.lower() and "alpha" not in user.lower():
                title = "upper-shared beta procedure"
            else:
                title = "cross-pattern conditional procedure"
            return json.dumps(upper_structured(title))

        candidate_text = self._candidate_segment(user)
        candidate_payload = json.loads(
            next(line for line in candidate_text.splitlines() if line.lstrip().startswith("{"))
        )
        candidate_id_value = candidate_payload["id"]
        level = candidate_payload["level"]
        parent_ids = candidate_payload["parent_ids"]
        if "alpha" in candidate_text.lower() and "beta" not in candidate_text.lower():
            title = "upper-shared alpha reviewed pattern"
        elif "beta" in candidate_text.lower() and "alpha" not in candidate_text.lower():
            title = "upper-shared beta reviewed pattern"
        else:
            title = "cross-pattern reviewed strategy"
        candidate = SimpleNamespace(id=candidate_id_value, level=level)
        return upper_decision(
            "ADD",
            candidate,
            evidence=[parent_ids[0]],
            title=title,
        )


@pytest.mark.asyncio
async def test_full_epoch_routes_effective_l0_through_reviewed_l1_and_l2_candidates(tmp_path):
    llm = HierarchyWorkflowLLM()
    instance = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=hierarchy_config(
            tmp_path,
            l1_candidate_review_enabled=True,
            l2_candidate_review_enabled=True,
            similarity_thresholds_provisional=False,
            min_l0_per_l1=2,
            min_l1_per_l2=2,
            experience_output_language="english",
        ),
        agent_objective="complete technical tasks",
        learning_objective="learn evidence-backed procedures",
        llm=llm,
        embedding_provider=TwoStageEmbedding(),
    )
    l0_records = [
        make_l0("L0_alpha_1", "Alpha workflow checks the generated table."),
        make_l0("L0_alpha_2", "Alpha workflow validates the table before submission."),
        make_l0("L0_beta_1", "Beta workflow inspects the exported slide deck."),
        make_l0("L0_beta_2", "Beta workflow validates the deck before submission."),
    ]
    instance._l0_records = {record.id: record for record in l0_records}

    await instance.aggregate_epoch(epoch=0)

    assert len(instance.l1) == 2
    assert len(instance.l2) == 1
    assert len(instance.get_candidates("L1")) == 2
    assert len(instance.get_candidates("L2")) == 1
    assert all(item["status"] == "committed" for item in instance.get_candidates("L1"))
    assert all(item["status"] == "committed" for item in instance.get_candidates("L2"))
    assert all(record.aggregation_status == "aggregated" for record in instance._l0_records.values())
    assert all(record.aggregation_status == "aggregated" for record in instance._l1_records.values())
    assert all(record.lifecycle_status == "active" for record in instance._l2_records.values())
    injectable = instance.get_injectable_experience_pool()
    assert set(instance.l1).issubset(injectable)
    assert set(instance.l2).issubset(injectable)
    assert not any(candidate.id in injectable for candidate in instance._candidate_records.values())
    assert all(call["temperature"] == 0.0 for call in llm.calls)
    assert all(
        "Write all generated summaries" in call["messages"][0]["content"]
        for call in llm.calls
    )
    for record in (
        *instance._l0_records.values(),
        *instance._l1_records.values(),
        *instance._l2_records.values(),
    ):
        validate_experience_output_language(record.content, "english")
    audits = [json.loads(line) for line in (tmp_path / "clusters.jsonl").read_text().splitlines()]
    summary_by_target = {audit["target_level"]: audit["aggregation_summary"] for audit in audits}
    assert summary_by_target["L1"] == {
        "direct_success": 0,
        "adopted": 2,
        "not_adopted": 0,
        "generation_failed": 0,
        "review_failed": 0,
    }
    assert summary_by_target["L2"] == {
        "direct_success": 0,
        "adopted": 1,
        "not_adopted": 0,
        "generation_failed": 0,
        "review_failed": 0,
    }


class AggregateThenFailReviewLLM:
    def __init__(self):
        self.calls: list[dict] = []

    async def query_one(self, **kwargs):
        self.calls.append(kwargs)
        system = kwargs["messages"][0]["content"]
        if "maintain an evidence-backed pool" in system:
            raise RuntimeError("temporary reviewer outage")
        return aggregation_decision("Persisted before review")


@pytest.mark.asyncio
async def test_public_aggregation_restart_retries_review_without_regenerating_candidate(tmp_path):
    first_llm = AggregateThenFailReviewLLM()
    config = hierarchy_config(tmp_path, l1_candidate_review_enabled=True)
    first = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=config,
        agent_objective="complete technical tasks",
        learning_objective="learn evidence-backed procedures",
        llm=first_llm,
        embedding_provider=ConstantEmbedding(),
    )
    parents = [make_l0("L0_resume_a"), make_l0("L0_resume_b")]
    first._l0_records = {parent.id: parent for parent in parents}

    await first._aggregate_l1(epoch=0)

    persisted = first.get_candidates("L1")
    assert len(persisted) == 1 and persisted[0]["status"] == "review_failed"
    assert first.l1 == {}
    assert all(parent.aggregation_status == "pending" for parent in first._l0_records.values())
    assert len(first_llm.calls) == 2  # one aggregation, then one failed review
    failure_audit = json.loads((tmp_path / "clusters.jsonl").read_text().splitlines()[-1])
    assert failure_audit["aggregation_summary"]["review_failed"] == 1
    assert failure_audit["aggregation_summary"]["adopted"] == 0

    # Re-enable the L0 threshold gate before recovery. The persisted candidate
    # must not be reviewed or committed merely because it predates this process.
    config.l0_similarity_threshold_provisional = True
    retry_llm = HierarchyWorkflowLLM()
    restarted = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=config,
        agent_objective="complete technical tasks",
        learning_objective="learn evidence-backed procedures",
        llm=retry_llm,
        embedding_provider=ConstantEmbedding(),
    )
    await restarted._aggregate_l1(epoch=1)

    assert retry_llm.calls == []
    assert restarted.l1 == {}
    assert restarted.get_candidates("L1")[0]["status"] == "review_failed"
    assert all(parent.aggregation_status == "pending" for parent in restarted._l0_records.values())
    gate_audit = json.loads((tmp_path / "clusters.jsonl").read_text().splitlines()[-1])
    assert gate_audit["status"] == "waiting_for_threshold_calibration"
    assert gate_audit["pending_candidate_ids"] == [persisted[0]["id"]]

    config.l0_similarity_threshold_provisional = False
    await restarted._aggregate_l1(epoch=2)

    assert len(retry_llm.calls) == 1
    assert "maintain an evidence-backed pool" in retry_llm.calls[0]["messages"][0]["content"]
    assert len(restarted.l1) == 1
    assert restarted.get_candidates("L1")[0]["status"] == "committed"
    assert restarted.get_candidates("L1")[0]["attempt_count"] == 2
    recovered_audit = json.loads((tmp_path / "clusters.jsonl").read_text().splitlines()[-1])
    assert recovered_audit["aggregation_summary"]["adopted"] == 1
    assert recovered_audit["aggregation_summary"]["review_failed"] == 0


@pytest.mark.asyncio
async def test_l1_gate_blocks_recovered_l2_candidate_before_review_or_commit(tmp_path):
    config = hierarchy_config(tmp_path, l2_candidate_review_enabled=True)
    first = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=config,
        agent_objective="complete technical tasks",
        learning_objective="learn evidence-backed procedures",
        llm=QueueLLM(),
        embedding_provider=ConstantEmbedding(),
    )
    l0_parents = [make_l0("L0_for_l2_a"), make_l0("L0_for_l2_b")]
    first._l0_records = {parent.id: parent for parent in l0_parents}
    l1_parents = []
    for index, l0_parent in enumerate(l0_parents):
        cluster = make_test_cluster(f"cluster-l1-parent-{index}", [l0_parent])
        l1_parents.append(
            first._make_child(
                "L1",
                [l0_parent],
                cluster,
                AggregatedExperienceContent.model_validate(
                    upper_structured(f"Persisted L1 parent {index}")
                ),
            )
        )
    first._l1_records = {parent.id: parent for parent in l1_parents}
    candidate = stage_upper_candidate(
        first,
        "L2",
        l1_parents,
        title="Persisted L2 candidate",
        cluster_id="cluster-persisted-l2-candidate",
    )

    # Simulate restart under a restored/provisional L1 threshold gate.
    config.l1_similarity_threshold_provisional = True
    review_response = upper_decision(
        "ADD",
        candidate,
        evidence=[candidate.parent_ids[0]],
        title="Reviewed L2 candidate",
    )
    restarted, llm = make_manager(
        tmp_path,
        [review_response],
        l2_candidate_review_enabled=True,
        l1_similarity_threshold_provisional=True,
    )

    direct_retry = await restarted.retry_candidate(candidate.id)
    assert direct_retry == {"committed": 0, "failed": 0, "stale": 0, "skipped": 1}
    assert llm.calls == []
    assert restarted.get_candidates("L2")[0]["status"] == "pending"

    await restarted._aggregate_l2(epoch=1)

    assert llm.calls == []
    assert restarted.l2 == {}
    assert restarted.get_candidates("L2")[0]["status"] == "pending"
    assert all(parent.aggregation_status == "pending" for parent in restarted._l1_records.values())

    restarted.h_config.l1_similarity_threshold_provisional = False
    await restarted._aggregate_l2(epoch=2)

    assert len(llm.calls) == 1
    assert len(restarted.l2) == 1
    assert restarted.get_candidates("L2")[0]["status"] == "committed"
    recovered_audit = json.loads((tmp_path / "clusters.jsonl").read_text().splitlines()[-1])
    assert recovered_audit["aggregation_summary"]["adopted"] == 1


def test_schema_v3_backfills_unique_parent_child_pointer(tmp_path):
    parent = make_l0("L0_migrated").model_copy(update={"aggregation_status": "aggregated"})
    child = ExperienceRecord(
        id="L1_migrated",
        level="L1",
        content="A traceable legacy-v3 operational pattern.",
        parent_ids=[parent.id],
        source_l0_ids=[parent.id],
        aggregation_status="pending",
    )
    (tmp_path / "experiences.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "l0_experiences": [parent.public_dict()],
                "l1_experiences": [child.public_dict()],
                "l2_experiences": [],
            }
        ),
        encoding="utf-8",
    )

    instance, _ = make_manager(tmp_path)

    loaded_parent = instance._l0_records[parent.id]
    loaded_child = instance._l1_records[child.id]
    assert loaded_parent.aggregation_status == "aggregated"
    assert loaded_parent.aggregated_into_experience_id == child.id
    assert set(loaded_child.parent_version_fingerprints) == {parent.id}
    assert loaded_child.source_version_fingerprint == instance._source_fingerprint(
        "L1", loaded_child.parent_version_fingerprints
    )

    # A subsequent schema-v4 save/restart keeps the newly pinned relation.
    instance.save_experiences()
    restarted, _ = make_manager(tmp_path)
    assert restarted._l1_records[child.id].lifecycle_status == "active"


def test_schema_v3_rejects_multiple_active_children_for_one_parent(tmp_path):
    parent = make_l0("L0_ambiguous").model_copy(update={"aggregation_status": "aggregated"})
    children = [
        ExperienceRecord(
            id=f"L1_ambiguous_{index}",
            level="L1",
            content=f"Conflicting active child {index}.",
            parent_ids=[parent.id],
            source_l0_ids=[parent.id],
        )
        for index in range(2)
    ]
    (tmp_path / "experiences.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "l0_experiences": [parent.public_dict()],
                "l1_experiences": [child.public_dict() for child in children],
                "l2_experiences": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="multiple active upper consumers"):
        make_manager(tmp_path)


def test_future_snapshot_schema_is_rejected_instead_of_downgraded(tmp_path):
    (tmp_path / "experiences.json").write_text(
        json.dumps(
            {
                "schema_version": 5,
                "l0_experiences": [],
                "l1_experiences": [],
                "l2_experiences": [],
                "future_state": {"must_not_be_lost": True},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="newer than supported schema"):
        make_manager(tmp_path)


def test_schema_v4_rejects_adopted_candidate_with_missing_result(tmp_path):
    instance, _ = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_missing_result_a"), make_l0("L0_missing_result_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Candidate whose result will be missing",
        cluster_id="cluster-missing-result",
    )
    payload = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    broken = payload["l1_candidates"][0]
    broken.update(
        {
            "status": "committed",
            "resolution": "adopted",
            "result_experience_id": "L1_missing",
            "reviewed_at": "2026-01-01T00:00:00+00:00",
            "review_decision": json.loads(
                upper_decision("ADD", candidate, evidence=[parents[0].id])
            ),
        }
    )
    (tmp_path / "experiences.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="references missing result"):
        make_manager(tmp_path, l1_candidate_review_enabled=True)


@pytest.mark.asyncio
async def test_schema_v4_rejects_l0_adopted_candidate_with_missing_result(tmp_path):
    raw = "Persist a valid L0 result before marking its candidate adopted."
    candidate = candidate_id(raw, "task-a")
    instance, _ = make_manager(
        tmp_path,
        [decision("ADD", candidate, content="Persist the L0 result atomically with review state.")],
    )
    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    payload = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    payload["l0_experiences"] = []
    (tmp_path / "experiences.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="references missing result"):
        make_manager(tmp_path)


@pytest.mark.asyncio
async def test_schema_v3_migrates_committed_l0_candidate_result_before_v4_save(tmp_path):
    raw = "Migrate the committed L0 review relationship without replaying it."
    candidate_id_value = candidate_id(raw, "task-a")
    instance, _ = make_manager(
        tmp_path,
        [
            decision(
                "ADD",
                candidate_id_value,
                content="Keep the committed candidate and result relationship restart-safe.",
            )
        ],
    )
    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    payload = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    payload["schema_version"] = 3
    legacy_candidate = payload["l0_candidates"][0]
    expected_result = legacy_candidate.pop("result_experience_id")
    legacy_candidate.pop("resolution")
    (tmp_path / "experiences.json").write_text(json.dumps(payload), encoding="utf-8")

    migrated, migrated_llm = make_manager(tmp_path)
    migrated_candidate = migrated._candidate_records[candidate_id_value]
    assert migrated_candidate.resolution == "adopted"
    assert migrated_candidate.result_experience_id == expected_result
    migrated.save_experiences()

    restarted, restarted_llm = make_manager(tmp_path)
    assert restarted._candidate_records[candidate_id_value].result_experience_id == expected_result
    assert migrated_llm.calls == []
    assert restarted_llm.calls == []


@pytest.mark.asyncio
async def test_schema_v3_candidate_migration_finds_direct_results_across_update_chain(tmp_path):
    raws = ["initial evidence", "first correction", "second correction"]
    candidate_ids = [candidate_id(raw, f"task-{index}") for index, raw in enumerate(raws)]
    contents = [
        "Start with the evidence-backed procedure.",
        "Use the procedure only after checking its first boundary.",
        "Use the procedure after checking both documented boundaries.",
    ]
    experience_ids = [stable_experience_id("L0", content) for content in contents]
    instance, _ = make_manager(
        tmp_path,
        [
            decision("ADD", candidate_ids[0], content=contents[0]),
            decision(
                "UPDATE",
                candidate_ids[1],
                target=experience_ids[0],
                content=contents[1],
                evidence=[candidate_ids[1], experience_ids[0]],
            ),
            decision(
                "UPDATE",
                candidate_ids[2],
                target=experience_ids[1],
                content=contents[2],
                evidence=[candidate_ids[2], experience_ids[1]],
            ),
        ],
    )
    for step, (raw, task_id) in enumerate(
        zip(raws, ("task-0", "task-1", "task-2"), strict=True)
    ):
        await instance.process_step_experiences(
            [{"content": raw, "source_task_ids": [task_id]}], step=step
        )

    payload = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    payload["schema_version"] = 3
    for candidate in payload["l0_candidates"]:
        candidate.pop("resolution")
        candidate.pop("result_experience_id")
    (tmp_path / "experiences.json").write_text(json.dumps(payload), encoding="utf-8")

    migrated, _ = make_manager(tmp_path)

    assert {
        candidate_id_value: migrated._candidate_records[candidate_id_value].result_experience_id
        for candidate_id_value in candidate_ids
    } == dict(zip(candidate_ids, experience_ids, strict=True))
    migrated.save_experiences()
    restarted, _ = make_manager(tmp_path)
    assert len(restarted._candidate_records) == 3


@pytest.mark.parametrize(
    ("bucket", "record_level"),
    [("l0_experiences", "L1"), ("l1_experiences", "L2")],
)
def test_schema_v4_rejects_experience_whose_level_disagrees_with_bucket(
    tmp_path, bucket, record_level
):
    (tmp_path / "experiences.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "l0_experiences": [],
                "l1_experiences": [],
                "l2_experiences": [],
                bucket: [
                    {
                        "id": "wrong-level",
                        "level": record_level,
                        "content": "A record must not escape its persisted level bucket.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="bucket contains level"):
        make_manager(tmp_path)


def test_schema_v4_rejects_candidate_whose_level_disagrees_with_bucket(tmp_path):
    instance, _ = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_wrong_bucket_a"), make_l0("L0_wrong_bucket_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Candidate placed in the wrong persisted bucket",
        cluster_id="cluster-wrong-bucket",
    )
    payload = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    payload["l0_candidates"] = payload.pop("l1_candidates")
    payload["l1_candidates"] = []
    (tmp_path / "experiences.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="candidate bucket contains level"):
        make_manager(tmp_path, l1_candidate_review_enabled=True)


def test_schema_v4_quarantines_upper_record_without_parent_version_pins(tmp_path):
    parent = make_l0("L0_unpinned")
    child = ExperienceRecord(
        id="L1_unpinned",
        level="L1",
        content="An unpinned schema-v4 child cannot remain injectable.",
        parent_ids=[parent.id],
        source_l0_ids=[parent.id],
    )
    (tmp_path / "experiences.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "l0_experiences": [parent.public_dict()],
                "l1_experiences": [child.public_dict()],
                "l2_experiences": [],
            }
        ),
        encoding="utf-8",
    )

    instance, _ = make_manager(tmp_path)

    assert instance._l1_records[child.id].lifecycle_status == "needs_review"
    assert child.id not in instance.get_injectable_experience_pool()


def test_schema_v4_quarantines_active_upper_record_without_any_parent(tmp_path):
    child = ExperienceRecord(
        id="L1_parentless",
        level="L1",
        content="A schema-v4 upper experience must have traceable direct parents.",
    )
    (tmp_path / "experiences.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "l0_experiences": [],
                "l1_experiences": [child.public_dict()],
                "l2_experiences": [],
            }
        ),
        encoding="utf-8",
    )

    instance, _ = make_manager(tmp_path)

    assert instance._l1_records[child.id].lifecycle_status == "needs_review"
    assert child.id not in instance.get_injectable_experience_pool()


@pytest.mark.parametrize("shape", ["duplicate-list-id", "mapping-key-mismatch"])
def test_schema_v4_rejects_ambiguous_experience_identity(tmp_path, shape):
    first = ExperienceRecord(id="L0_duplicate", level="L0", content="First record.")
    second = ExperienceRecord(id="L0_duplicate", level="L0", content="Second record.")
    if shape == "duplicate-list-id":
        l0_payload = [first.public_dict(), second.public_dict()]
        match = "duplicate L0 experience ID"
    else:
        l0_payload = {"different-key": first.public_dict()}
        match = "disagrees with payload id"
    (tmp_path / "experiences.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "l0_experiences": l0_payload,
                "l1_experiences": [],
                "l2_experiences": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match=match):
        make_manager(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["candidate_id", "level"])
async def test_schema_v4_rejects_committed_candidate_decision_identity_mismatch(
    tmp_path, tamper
):
    raw = "Cross-check the committed review decision with its candidate."
    candidate_id_value = candidate_id(raw, "task-a")
    instance, _ = make_manager(
        tmp_path,
        [decision("ADD", candidate_id_value, content="Cross-check persisted review identity.")],
    )
    await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["task-a"]}], step=0
    )
    payload = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    review = payload["l0_candidates"][0]["review_decision"]
    review[tamper] = "C0_other" if tamper == "candidate_id" else "L1"
    (tmp_path / "experiences.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="has a decision for|has decision level"):
        make_manager(tmp_path)


def test_upper_generation_fingerprint_binds_provider_protocol_and_endpoint(tmp_path):
    instance, _ = make_manager(tmp_path)

    def fingerprint(provider_type, base_url):
        instance.config = SimpleNamespace(
            model=SimpleNamespace(
                model_provider=SimpleNamespace(
                    type=provider_type,
                    model="local-semantic-reviewer-v1",
                    base_url=base_url,
                )
            )
        )
        return instance._generation_fingerprint("L1", "source-fingerprint", "cluster-a")

    original = fingerprint("chat.completions", "http://provider-a.invalid/v1")
    assert original != fingerprint("responses", "http://provider-a.invalid/v1")
    assert original != fingerprint("chat.completions", "http://provider-b.invalid/v1")


@pytest.mark.parametrize(
    "payload",
    [
        {
            "action": "KEEP",
            "candidate_id": "C0_candidate",
            "target_id": "",
            "new_content": None,
            "reason": "Empty target is not JSON null.",
            "evidence_ids": ["C0_candidate"],
        },
        {
            "action": "DELETE",
            "candidate_id": "C0_candidate",
            "target_id": "L0_target",
            "new_content": "",
            "reason": "Empty content is not JSON null.",
            "evidence_ids": ["C0_candidate", "L0_target"],
        },
    ],
)
def test_review_decision_requires_forbidden_fields_to_be_json_null(payload):
    with pytest.raises(ValueError):
        ExperienceReviewDecision.model_validate(payload)


@pytest.mark.asyncio
async def test_upper_delete_or_keep_rejects_non_null_empty_structured_payload(tmp_path):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_empty_struct_a"), make_l0("L0_empty_struct_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Candidate with malformed review action",
        cluster_id="cluster-empty-structured",
    )
    payload = json.loads(upper_decision("KEEP", candidate))
    payload["new_structured_content"] = {}
    llm.responses = [json.dumps(payload)]

    counts = await instance.review_pending_candidates(candidate_level="L1")

    assert counts["failed"] == 1
    assert instance._candidate_records[candidate.id].status == "review_failed"
    assert instance.l1 == {}


def test_english_language_guard_accepts_math_notation_and_rejects_chinese_prose():
    validate_experience_output_language(
        "Apply the AM-GM inequality to x^2 + y^2, then verify equality at x = y.",
        "english",
    )
    validate_experience_output_language("先检查等号成立条件。", "same_as_input")

    with pytest.raises(ValueError, match="experience_output_language='english'"):
        validate_experience_output_language("先检查等号成立条件。", "english")


@pytest.mark.asyncio
async def test_l0_generation_prompts_and_candidate_follow_english_contract():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.agent_objective = "solve the mathematical problem"
    updater.learning_objective = "learn reusable mathematical procedures"
    updater.experience_output_language = "english"
    updater.experience_output_language_instruction = experience_output_language_instruction(
        "english"
    )
    updater.prompts = FileUtils.load_prompts("practice/experience.yaml")
    updater.llm = QueueLLM(
        [
            "The attempt expanded the expression but omitted the equality check.",
            "<Experiences>\n1. After applying an inequality, verify every equality condition.\n</Experiences>",
        ]
    )
    updater.config = SimpleNamespace(
        model=SimpleNamespace(model_params=SimpleNamespace(model_dump=lambda: {}))
    )
    rollout = EvaluationSample(
        source="DAPO-Math-17k",
        raw_question="求满足条件的最小值。",
        correct_answer="2",
        response="The minimum is 2.",
        trace_id="trace-english-contract",
        reward=1.0,
        meta={"task_id": "math-task"},
    )

    candidates = await updater.generate_l0_candidates(
        [rollout],
        concurrency=1,
        given_ground_truth=True,
        num_experiences=1,
    )

    assert candidates[0]["content"] == (
        "After applying an inequality, verify every equality condition."
    )
    assert len(updater.llm.calls) == 2
    for call in updater.llm.calls:
        system_prompt = call["messages"][0]["content"]
        assert "Write all generated summaries" in system_prompt
        assert "Use the same language as the input trajectory." not in system_prompt


@pytest.mark.asyncio
async def test_non_english_l0_generation_fails_without_reusing_partial_state():
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.experience_output_language = "english"
    updater.last_l0_candidates = [{"content": "stale candidate"}]
    updater.last_generated_experience_groups = [{"experiences": "stale group"}]
    updater.last_l0_metadata_coverage = {
        "domain": {"known": 1, "total": 1, "ratio": 1.0}
    }
    updater._single_rollout_summary = AsyncMock(return_value={"task": [{}]})
    updater._group_advantage = AsyncMock(
        return_value=[{"rollouts": [], "experiences": "先验证最终答案。"}]
    )

    with pytest.raises(L0CandidateGenerationError, match="generated L0 candidate"):
        await updater.generate_l0_candidates([object()])

    assert updater.last_l0_candidates == []
    assert updater.last_generated_experience_groups == []
    assert updater.last_l0_metadata_coverage == {}


@pytest.mark.asyncio
async def test_english_l0_review_rejects_chinese_mutation_and_remains_retryable(tmp_path):
    raw = "Review the equality conditions after applying an inequality."
    review_candidate_id = candidate_id(raw, "math-task")
    instance, llm = make_manager(
        tmp_path,
        [decision("ADD", review_candidate_id, content="先验证等号成立条件。")],
        experience_output_language="english",
    )

    counts = await instance.process_step_experiences(
        [{"content": raw, "source_task_ids": ["math-task"]}],
        step=0,
    )

    assert counts["failed"] == 1
    assert instance.l0 == {}
    assert instance._candidate_records[review_candidate_id].status == "review_failed"
    assert "Write all generated summaries" in llm.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_english_upper_aggregation_rejects_chinese_before_candidate_staging(tmp_path):
    chinese_aggregation = json.loads(aggregation_decision())
    chinese_aggregation["title"] = "等号条件检查"
    instance, llm = make_manager(
        tmp_path,
        [json.dumps(chinese_aggregation)],
        experience_output_language="english",
        l1_candidate_review_enabled=True,
    )
    parents = [make_l0("L0_english_a"), make_l0("L0_english_b")]
    instance._l0_records = {parent.id: parent for parent in parents}

    await instance._aggregate_l1(epoch=0)

    assert instance.l1 == {}
    assert instance.get_candidates("L1") == []
    assert all(parent.aggregation_status == "pending" for parent in instance._l0_records.values())
    assert "Write all generated summaries" in llm.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_english_upper_review_rejects_chinese_structured_content(tmp_path):
    instance, llm = make_manager(
        tmp_path,
        l1_candidate_review_enabled=True,
        experience_output_language="english",
    )
    parents = [make_l0("L0_review_en_a"), make_l0("L0_review_en_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Candidate equality-check procedure",
        cluster_id="cluster-english-review",
    )
    payload = json.loads(upper_decision("ADD", candidate, evidence=[parents[0].id]))
    payload["new_structured_content"]["principle"] = "先检查所有等号成立条件再提交答案。"
    payload["new_content"] = "先检查所有等号成立条件再提交答案。"
    llm.responses = [json.dumps(payload)]

    counts = await instance.review_pending_candidates(candidate_level="L1")

    assert counts["failed"] == 1
    assert instance.l1 == {}
    assert instance._candidate_records[candidate.id].status == "review_failed"
    assert all(parent.aggregation_status == "pending" for parent in instance._l0_records.values())
    assert "Write all generated summaries" in llm.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_upper_candidate_contract_change_marks_candidate_stale_without_llm_call(tmp_path):
    instance, llm = make_manager(tmp_path, l1_candidate_review_enabled=True)
    parents = [make_l0("L0_contract_a"), make_l0("L0_contract_b")]
    instance._l0_records = {parent.id: parent for parent in parents}
    candidate = stage_upper_candidate(
        instance,
        "L1",
        parents,
        title="Candidate tied to the original language contract",
        cluster_id="cluster-language-contract",
    )
    instance.experience_output_language = "english"
    instance.experience_output_language_instruction = experience_output_language_instruction(
        "english"
    )

    counts = await instance.review_pending_candidates(candidate_level="L1")

    assert counts["stale"] == 1
    assert instance._candidate_records[candidate.id].status == "stale"
    assert instance.l1 == {}
    assert llm.calls == []


def test_snapshot_language_contract_prevents_cross_language_reuse(tmp_path):
    original, _ = make_manager(tmp_path)
    original._l0_records = {"L0_old": make_l0("L0_old")}
    original.save_experiences()

    with pytest.raises(RuntimeError, match="experience_output_language does not match"):
        make_manager(tmp_path, experience_output_language="english")


def test_upper_generation_fingerprint_binds_output_language(tmp_path):
    same_language, _ = make_manager(tmp_path / "same")
    english, _ = make_manager(
        tmp_path / "english",
        experience_output_language="english",
    )

    assert same_language._generation_fingerprint(
        "L1", "source-fingerprint", "cluster-a"
    ) != english._generation_fingerprint("L1", "source-fingerprint", "cluster-a")
