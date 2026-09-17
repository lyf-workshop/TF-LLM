"""Pure helpers for hierarchical clustering and aggregation state changes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..experience_clusterer import ClusteringReport, ExperienceCluster, ExperienceClusterer
from ..experience_models import (
    AggregatedExperienceContent,
    ExperienceCandidateRecord,
    ExperienceLevel,
    ExperienceRecord,
    stable_experience_candidate_id,
    stable_experience_id,
)


def cluster_pending(
    clusterer: ExperienceClusterer,
    pending: Sequence[ExperienceRecord],
    *,
    level: ExperienceLevel,
    minimum_size: int,
    similarity_threshold: float,
    clustering_enabled: bool,
) -> ClusteringReport:
    """Choose the configured clustering strategy for one pending pool."""

    if clustering_enabled:
        return clusterer.cluster(
            pending,
            level=level,
            similarity_threshold=similarity_threshold,
        )
    return clusterer.sequential_groups(
        pending,
        level=level,
        group_size=minimum_size,
    )


def consensus(records: Sequence[ExperienceRecord], field_name: str) -> str | None:
    """Return a metadata value only when all known values agree."""

    values = {
        str(getattr(value, "value", value))
        for record in records
        if (value := getattr(record, field_name, None)) is not None
        and str(getattr(value, "value", value)).strip().lower() not in {"", "unknown"}
    }
    return next(iter(values)) if len(values) == 1 else None


def make_child(
    target_level: ExperienceLevel,
    parents: Sequence[ExperienceRecord],
    cluster: ExperienceCluster,
    result: AggregatedExperienceContent,
    *,
    metadata_fields: Sequence[str],
    record_version_fingerprint: Callable[[ExperienceRecord], str],
    source_fingerprint: Callable[[ExperienceLevel, dict[str, str]], str],
) -> ExperienceRecord:
    """Build a deterministic upper-level record without mutating a pool."""

    parent_ids = sorted(parent.id for parent in parents)
    parent_versions = {
        parent.id: record_version_fingerprint(parent) for parent in parents
    }
    source_version_fingerprint = source_fingerprint(target_level, parent_versions)
    content = result.render()
    source_l0_ids: list[str] = []
    source_l1_ids: list[str] = []
    if target_level == "L1":
        source_l0_ids = parent_ids
    else:
        source_l1_ids = parent_ids
        source_l0_ids = sorted(
            {
                source_id
                for parent in parents
                for source_id in (parent.source_l0_ids or parent.parent_ids)
            }
        )
    metadata = {
        field_name: consensus(parents, field_name) for field_name in metadata_fields
    }
    return ExperienceRecord(
        id=stable_experience_id(
            target_level,
            content,
            parent_ids,
            identity_context=[f"source_version_fingerprint={source_version_fingerprint}"],
        ),
        level=target_level,
        content=content,
        structured_content=result,
        source_task_ids=sorted(
            {task_id for parent in parents for task_id in parent.source_task_ids}
        ),
        source_rollout_ids=sorted(
            {rollout_id for parent in parents for rollout_id in parent.source_rollout_ids}
        ),
        parent_ids=parent_ids,
        source_l0_ids=source_l0_ids,
        source_l1_ids=source_l1_ids,
        parent_version_fingerprints=parent_versions,
        source_version_fingerprint=source_version_fingerprint,
        cluster_id=cluster.cluster_id,
        aggregation_status="terminal" if target_level == "L2" else "pending",
        **metadata,
    )


def make_upper_candidate(
    child: ExperienceRecord,
    cluster: ExperienceCluster,
    *,
    epoch: int,
    generator_version: str,
    generation_fingerprint: Callable[[ExperienceLevel, str, str], str],
    source_fingerprint: Callable[[ExperienceLevel, dict[str, str]], str],
    identity_context: Callable[[ExperienceCandidateRecord], Sequence[str]],
) -> ExperienceCandidateRecord:
    """Build a deterministic review candidate from an upper-level child."""

    source_versions = dict(child.parent_version_fingerprints)
    child_source_fingerprint = child.source_version_fingerprint or source_fingerprint(
        child.level,
        source_versions,
    )
    candidate_generation_fingerprint = generation_fingerprint(
        child.level,
        child_source_fingerprint,
        cluster.cluster_id,
    )
    payload = {
        "id": "pending_candidate_id",
        "level": child.level,
        "content": child.content,
        "source_task_ids": child.source_task_ids,
        "source_rollout_ids": child.source_rollout_ids,
        "domain": child.domain,
        "task_family": child.task_family,
        "failure_mode": child.failure_mode,
        "strategy_type": child.strategy_type,
        "tool_type": child.tool_type,
        "task_stage": child.task_stage,
        "parent_ids": child.parent_ids,
        "source_l0_ids": child.source_l0_ids,
        "source_l1_ids": child.source_l1_ids,
        "source_versions": source_versions,
        "source_fingerprint": child_source_fingerprint,
        "generation_fingerprint": candidate_generation_fingerprint,
        "cluster_id": cluster.cluster_id,
        "structured_content": child.structured_content.model_dump(mode="json"),
        "step": epoch,
        "epoch": epoch,
        "generator_version": generator_version,
    }
    candidate = ExperienceCandidateRecord.model_validate(payload)
    candidate_id = stable_experience_candidate_id(
        child.level,
        child.content,
        parent_ids=child.parent_ids,
        source_versions=source_versions,
        source_task_ids=child.source_task_ids,
        source_rollout_ids=child.source_rollout_ids,
        identity_context=[
            *identity_context(candidate),
            f"generation_fingerprint={candidate_generation_fingerprint}",
        ],
        generator_version=generator_version,
    )
    return candidate.model_copy(update={"id": candidate_id})


def commit_child(
    stores: dict[ExperienceLevel, dict[str, ExperienceRecord]],
    source_level: ExperienceLevel,
    target_level: ExperienceLevel,
    child: ExperienceRecord,
    parent_ids: Sequence[str],
    *,
    max_total: int,
) -> None:
    """Apply a validated direct aggregation to copied stores."""

    source_store = stores[source_level]
    target_store = stores[target_level]
    active_total = sum(record.lifecycle_status == "active" for record in target_store.values())
    if child.id not in target_store and max_total > 0 and active_total >= max_total:
        raise RuntimeError(f"{target_level} capacity {max_total} reached")
    missing = [parent_id for parent_id in parent_ids if parent_id not in source_store]
    if missing:
        raise RuntimeError(f"missing parent records: {missing}")
    ineligible = [
        parent_id
        for parent_id in parent_ids
        if source_store[parent_id].lifecycle_status != "active"
        or source_store[parent_id].aggregation_status != "pending"
    ]
    if ineligible:
        raise RuntimeError(f"parents are no longer active pending records: {ineligible}")

    target_store[child.id] = child
    for parent_id in parent_ids:
        parent = source_store[parent_id]
        updates: dict[str, Any] = {
            "aggregation_status": "aggregated",
            "aggregated_into_cluster_id": child.cluster_id,
            "aggregated_into_experience_id": child.id,
        }
        if parent.cluster_id is None:
            updates["cluster_id"] = child.cluster_id
        source_store[parent_id] = parent.model_copy(update=updates)


def aggregation_attempt_summary(attempts: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Classify aggregation and review outcomes independently."""

    return {
        "direct_success": sum(attempt.get("status") == "success" for attempt in attempts),
        "adopted": sum(
            attempt.get("candidate_status") == "committed"
            and attempt.get("candidate_resolution") == "adopted"
            and bool(attempt.get("result_experience_id"))
            for attempt in attempts
        ),
        "not_adopted": sum(
            attempt.get("candidate_status") == "committed"
            and attempt.get("candidate_resolution") == "not_adopted"
            for attempt in attempts
        ),
        "generation_failed": sum(attempt.get("status") == "failed" for attempt in attempts),
        "review_failed": sum(
            attempt.get("candidate_status") == "review_failed" for attempt in attempts
        ),
    }


__all__ = [
    "aggregation_attempt_summary",
    "cluster_pending",
    "commit_child",
    "consensus",
    "make_child",
    "make_upper_candidate",
]
