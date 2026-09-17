"""Validation and fingerprints for crash-safe L0 candidate caches."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..experience_models import L0CandidateRecord
from ..experience_updater import L0_CANDIDATE_GENERATOR_VERSION

HIERARCHICAL_CANDIDATE_CACHE_KIND = "hierarchical_l0_candidates_v2"
HIERARCHICAL_FLAT_CACHE_KIND = "hierarchical_flat_l0_v1"


def candidate_cache_payload(candidates: list[dict], *, batch_fingerprint: str) -> dict:
    return {
        "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
        "batch_fingerprint": batch_fingerprint,
        "l0_candidates": candidates,
    }


def flat_experiences_from_cache(payload: object) -> dict[str, str] | None:
    """Accept only the legacy flat cache shape, never an unknown envelope."""

    if not isinstance(payload, dict) or "cache_kind" in payload:
        return None
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
        return None
    return dict(payload)


def hierarchical_flat_cache_payload(
    experiences: dict[str, str],
    candidates: list[dict],
    *,
    batch_fingerprint: str,
) -> dict:
    return {
        "cache_kind": HIERARCHICAL_FLAT_CACHE_KIND,
        "batch_fingerprint": batch_fingerprint,
        "flat_experiences": experiences,
        "l0_candidates": candidates,
    }


def candidates_from_cache(
    payload: object,
    *,
    expected_batch_fingerprint: str | None = None,
    expected_run_id: str | None = None,
    expected_epoch: int | None = None,
    expected_batch: int | None = None,
) -> list[dict] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("cache_kind") != HIERARCHICAL_CANDIDATE_CACHE_KIND:
        return None
    if (
        expected_batch_fingerprint is not None
        and payload.get("batch_fingerprint") != expected_batch_fingerprint
    ):
        return None
    candidates = payload.get("l0_candidates")
    if not isinstance(candidates, list) or not candidates:
        return None

    input_fields = {
        "content",
        "source_task_ids",
        "source_rollout_ids",
        "source_evidence",
        "domain",
        "task_family",
        "failure_mode",
        "strategy_type",
        "tool_type",
        "task_stage",
        "generator_version",
        "run_id",
        "epoch",
        "batch",
        "batch_fingerprint",
    }
    validated: list[dict] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not set(candidate).issubset(input_fields):
            return None
        if not isinstance(candidate.get("content"), str) or not candidate["content"].strip():
            return None
        expected_context = {
            "run_id": expected_run_id,
            "epoch": expected_epoch,
            "batch": expected_batch,
            "batch_fingerprint": expected_batch_fingerprint,
        }
        if any(
            expected is not None and candidate.get(field_name) != expected
            for field_name, expected in expected_context.items()
        ):
            return None
        try:
            L0CandidateRecord.model_validate(
                {
                    **candidate,
                    "id": f"cache_validation_{index}",
                    "step": 0,
                }
            )
        except (TypeError, ValueError):
            return None
        validated.append(dict(candidate))
    return validated


def hierarchical_flat_from_cache(
    payload: object,
    *,
    expected_batch_fingerprint: str,
) -> tuple[dict[str, str], list[dict]] | None:
    """Decode the review-off hierarchy cache needed for crash-safe replay."""

    if not isinstance(payload, dict) or set(payload) != {
        "cache_kind",
        "batch_fingerprint",
        "flat_experiences",
        "l0_candidates",
    }:
        return None
    if payload.get("cache_kind") != HIERARCHICAL_FLAT_CACHE_KIND:
        return None
    if payload.get("batch_fingerprint") != expected_batch_fingerprint:
        return None
    flat = flat_experiences_from_cache(payload.get("flat_experiences"))
    candidates = candidates_from_cache(
        {
            "cache_kind": HIERARCHICAL_CANDIDATE_CACHE_KIND,
            "l0_candidates": payload.get("l0_candidates"),
        }
    )
    if flat is None or candidates is None:
        return None
    return flat, candidates


def rollout_batch_fingerprint(rollouts: list) -> str:
    """Bind a candidate cache entry to the exact unordered rollout batch."""

    object_fields = (
        "id",
        "exp_id",
        "dataset",
        "dataset_index",
        "source",
        "raw_question",
        "correct_answer",
        "meta",
        "stage",
        "trace_id",
        "response",
        "trajectory",
        "trajectories",
        "judged_response",
        "reasoning",
        "correct",
        "reward",
    )
    serialized: list[str] = []
    for rollout in rollouts:
        if isinstance(rollout, dict):
            payload = {field_name: rollout.get(field_name) for field_name in object_fields}
        else:
            payload = {
                field_name: getattr(rollout, field_name, None)
                for field_name in object_fields
            }
        serialized.append(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    canonical = json.dumps(sorted(serialized), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def candidate_generation_fingerprint(
    config: Any,
    experience_updater: Any,
    rollouts: list,
) -> str:
    """Hash rollouts plus every configured input that changes L0 generation."""

    model_config = config.evaluation.agent.model
    provider = model_config.model_provider
    payload = {
        "rollout_sha256": rollout_batch_fingerprint(rollouts),
        "generator_version": L0_CANDIDATE_GENERATOR_VERSION,
        "given_ground_truth": config.practice.given_ground_truth,
        "num_experiences": config.practice.num_experiences_per_query,
        "agent_objective": config.practice.agent_objective,
        "learning_objective": config.practice.learning_objective,
        "experience_output_language": getattr(
            getattr(config.practice, "hierarchical_learning", None),
            "experience_output_language",
            "same_as_input",
        ),
        "prompts": experience_updater.prompts,
        "model": {
            "provider_type": provider.type,
            "model": provider.model,
            "base_url": provider.base_url,
            "params": model_config.model_params.model_dump(exclude_none=True),
        },
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "HIERARCHICAL_CANDIDATE_CACHE_KIND",
    "HIERARCHICAL_FLAT_CACHE_KIND",
    "candidate_cache_payload",
    "candidates_from_cache",
    "candidate_generation_fingerprint",
    "flat_experiences_from_cache",
    "hierarchical_flat_cache_payload",
    "hierarchical_flat_from_cache",
    "rollout_batch_fingerprint",
]
