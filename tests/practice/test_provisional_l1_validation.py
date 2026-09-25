from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace

import pytest

from utu.config.practice_config import HierarchicalLearningConfig
from utu.practice.experience_models import ExperienceRecord
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager


class ConstantEmbedding:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class QueueLLM:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def query_one(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("Unexpected LLM call")
        response = self.responses.pop(0)
        return response(kwargs) if callable(response) else response


def aggregation_json() -> str:
    return json.dumps(
        {
            "decision": "aggregate",
            "title": "Shared bounded procedure",
            "principle": "Apply the shared procedure only when its explicit preconditions hold.",
            "applicable_when": ["the same structural precondition is present"],
            "not_applicable_when": ["the structural precondition is absent"],
            "recommended_actions": ["check the precondition", "apply and verify the procedure"],
            "evidence_summary": "Independent source tasks support the same bounded operation.",
            "confidence": 0.95,
        }
    )


def test_aggregation_parser_repairs_only_invalid_latex_json_escapes():
    malformed = r'''{
      "decision": "aggregate",
      "title": "Modular cycle rule",
      "principle": "Reduce \(a^n\) with a cycle and compute n \mod k before expanding.",
      "applicable_when": ["a modular power is requested"],
      "not_applicable_when": ["the modulus or exponent is unavailable"],
      "recommended_actions": ["find the period", "reduce and verify"],
      "evidence_summary": "Two independent tasks use the same modular-cycle procedure.",
      "confidence": 0.95
    }'''

    parsed = HierarchicalExperienceManager._parse_aggregation_response(malformed)

    assert parsed.title == "Modular cycle rule"
    assert r"\(a^n\)" in parsed.principle
    assert r"\mod" in parsed.principle


def hierarchy_config(tmp_path, **overrides):
    values = {
        "experience_save_path": str(tmp_path / "experiences.json"),
        "clustering_audit_path": str(tmp_path / "clusters.jsonl"),
        "clustering_enabled": True,
        "embedding_provider": "hashing",
        "l0_similarity_threshold": 0.8,
        "l1_similarity_threshold": 0.8,
        "min_l0_per_l1": 5,
        "min_l0_per_l1_candidate": 2,
        "min_distinct_source_tasks_per_l1": 1,
        "min_distinct_source_tasks_per_l1_candidate": 2,
        "min_distinct_source_tasks_per_l1_promotion": 3,
        "min_l1_per_l2": 2,
        "min_validation_trials_per_l1": 3,
        "min_distinct_validation_tasks_per_l1": 3,
        "min_l1_validation_net_help": 1,
        "max_l1_validation_harms": 1,
        "l1_validation_required": True,
        "max_cluster_size": 20,
        "use_metadata_constraints": False,
        "hard_constraint_fields": [],
        "soft_constraint_fields": [],
        "random_seed": 42,
        "aggregation_temperature": 0.0,
        "aggregation_disable_thinking": True,
        "aggregation_max_tokens": 2048,
        "max_l1_total": 50,
        "max_l2_total": 10,
        "l1_confidence_threshold": 0.7,
        "l2_confidence_threshold": 0.8,
        "l0_candidate_review_enabled": False,
        "l1_candidate_review_enabled": False,
        "l2_candidate_review_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def manager(tmp_path, responses=(), **overrides):
    llm = QueueLLM(responses)
    instance = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=hierarchy_config(tmp_path, **overrides),
        agent_objective="solve tasks",
        learning_objective="learn bounded strategies",
        llm=llm,
        embedding_provider=ConstantEmbedding(),
    )
    return instance, llm


async def make_provisional_l1(tmp_path):
    instance, llm = manager(tmp_path, [aggregation_json()])
    await instance.process_step_experiences(
        [
            {"content": "alpha procedure from task one", "source_task_ids": ["source-1"]},
            {"content": "alpha procedure from task two", "source_task_ids": ["source-2"]},
            {"content": "alpha procedure from task three", "source_task_ids": ["source-3"]},
        ],
        step=0,
    )
    await instance._aggregate_l1(epoch=0)
    return instance, llm


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def validation_kwargs(instance, record, task: str, *, trial: str, baseline: float, treatment: float):
    return {
        "experience_id": record.id,
        "task_id": task,
        "trial_id": trial,
        "task_question_sha256": sha(f"question:{task}"),
        "dataset": "calibration-set",
        "dataset_manifest_sha256": sha("calibration-manifest-v1"),
        "dataset_role": "heldout_validation",
        "repeat": 0,
        "model": "qwen3-30b-a3b",
        "protocol_version": "paired-v1",
        "generation_config_sha256": sha("temperature=0;thinking=false;max_tokens=2048"),
        "experience_version_fingerprint": instance._record_version_fingerprint(record),
        "baseline_prompt_sha256": sha(f"baseline:{task}"),
        "treatment_prompt_sha256": sha(f"treatment:{task}:{record.id}"),
        "baseline_score": baseline,
        "treatment_score": treatment,
    }


def test_new_validation_controls_are_opt_in_and_legacy_records_remain_validated():
    config = HierarchicalLearningConfig(embedding_provider="hashing")
    assert config.l1_validation_required is False
    assert config.min_l0_per_l1_candidate is None
    assert ExperienceRecord(id="L1_legacy", level="L1", content="legacy").validation_status == "validated"


@pytest.mark.asyncio
async def test_provisional_l1_is_persisted_but_not_injectable_or_l2_eligible(tmp_path):
    instance, llm = await make_provisional_l1(tmp_path)

    record = next(iter(instance._l1_records.values()))
    assert record.validation_status == "provisional"
    assert instance.l1 == {}
    assert instance.get_injectable_l1_experiences() == []
    assert record.id not in instance.get_injectable_experience_pool()
    assert instance._pending("L1") == []
    assert llm.calls[0]["extra_body"] == {"enable_thinking": False}
    assert llm.calls[0]["max_tokens"] == 2048

    saved = json.loads((tmp_path / "experiences.json").read_text(encoding="utf-8"))
    assert saved["l1_experiences"][0]["validation_status"] == "provisional"


@pytest.mark.asyncio
async def test_disable_thinking_applies_to_generation_and_upper_review(tmp_path):
    aggregate = json.loads(aggregation_json())

    def review_response(kwargs):
        user_prompt = kwargs["messages"][1]["content"]
        candidate_id = re.search(r'"id": "(C1_[0-9a-f]+)"', user_prompt).group(1)
        parent_id = re.search(r'"parent_ids": \["(L0_[0-9a-f]+)"', user_prompt).group(1)
        return json.dumps(
            {
                "action": "ADD",
                "candidate_id": candidate_id,
                "level": "L1",
                "target_id": None,
                "new_content": "canonical rendering is replaced from structured content",
                "new_structured_content": aggregate,
                "reason": "independent parents support this bounded provisional strategy",
                "evidence_ids": [candidate_id, parent_id],
            }
        )

    instance, llm = manager(
        tmp_path,
        [aggregation_json(), review_response],
        l1_candidate_review_enabled=True,
    )
    await instance.process_step_experiences(
        [
            {"content": "alpha procedure from task one", "source_task_ids": ["source-1"]},
            {"content": "alpha procedure from task two", "source_task_ids": ["source-2"]},
            {"content": "alpha procedure from task three", "source_task_ids": ["source-3"]},
        ],
        step=0,
    )
    await instance._aggregate_l1(epoch=0)

    assert len(llm.calls) == 2
    assert all(call["extra_body"] == {"enable_thinking": False} for call in llm.calls)
    assert all(call["max_tokens"] == 2048 for call in llm.calls)
    record = next(iter(instance._l1_records.values()))
    assert record.validation_status == "provisional"
    assert instance.l1 == {}
    assert instance.get_injectable_l1_experiences() == []


@pytest.mark.asyncio
async def test_paired_validation_is_idempotent_and_promotes_atomically(tmp_path):
    instance, _ = await make_provisional_l1(tmp_path)
    record = next(iter(instance._l1_records.values()))

    first = validation_kwargs(instance, record, "heldout-1", trial="trial-1", baseline=0, treatment=1)
    instance.record_l1_paired_validation(**first)
    instance.record_l1_paired_validation(**first)
    assert len(instance._l1_records[record.id].validation_results) == 1

    current = instance._l1_records[record.id]
    second = validation_kwargs(instance, current, "heldout-2", trial="trial-2", baseline=1, treatment=1)
    instance.record_l1_paired_validation(**second)
    current = instance._l1_records[record.id]
    third = validation_kwargs(instance, current, "heldout-3", trial="trial-3", baseline=0, treatment=1)
    promoted = instance.record_l1_paired_validation(**third)

    assert promoted["validation_status"] == "validated"
    assert promoted["validated_at"]
    assert instance.get_l1_promotion_readiness(record.id)["criteria_met"] is True
    assert record.id in instance.get_injectable_experience_pool()
    assert [item.id for item in instance._pending("L1")] == [record.id]

    restarted, _ = manager(tmp_path)
    restored = restarted._l1_records[record.id]
    assert restored.validation_status == "validated"
    assert len(restored.validation_results) == 3
    assert record.id in restarted.get_injectable_experience_pool()


@pytest.mark.asyncio
async def test_validation_rejects_leakage_conflicts_and_repeat_double_counting(tmp_path):
    instance, _ = await make_provisional_l1(tmp_path)
    record = next(iter(instance._l1_records.values()))

    leaked = validation_kwargs(instance, record, "source-1", trial="leaked", baseline=0, treatment=1)
    with pytest.raises(ValueError, match="held-out"):
        instance.record_l1_paired_validation(**leaked)

    first = validation_kwargs(instance, record, "heldout-1", trial="trial-1", baseline=0, treatment=1)
    instance.record_l1_paired_validation(**first)
    conflict = {**first, "treatment_score": 0}
    with pytest.raises(ValueError, match="conflicting"):
        instance.record_l1_paired_validation(**conflict)

    duplicate = {**first, "trial_id": "trial-alias"}
    with pytest.raises(ValueError, match="duplicates"):
        instance.record_l1_paired_validation(**duplicate)

    readiness = instance.get_l1_promotion_readiness(record.id)
    assert readiness["counts"]["trials"] == 1
    assert readiness["counts"]["distinct_validation_tasks"] == 1
