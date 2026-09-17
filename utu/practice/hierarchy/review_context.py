"""Pure retrieval and prompt-view helpers for candidate review."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..experience_clusterer import EmbeddingProvider, cosine_similarity
from ..experience_models import ExperienceCandidateRecord, ExperienceRecord, L0CandidateRecord

CandidateSortKey = Callable[[ExperienceCandidateRecord], tuple[Any, ...]]


def lexical_tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w]+", (text or "").lower(), flags=re.UNICODE))


def related_active(
    candidate: ExperienceCandidateRecord,
    target_store: Mapping[str, ExperienceRecord],
    *,
    embedding_provider: EmbeddingProvider,
    full_pool_limit: int,
    top_k: int,
    retrieval_method: str,
) -> tuple[list[ExperienceRecord], str]:
    active = sorted(
        (
            record
            for record in target_store.values()
            if record.lifecycle_status == "active"
        ),
        key=lambda record: record.id,
    )
    if len(active) <= full_pool_limit:
        return active, "full_active_pool"

    if retrieval_method == "semantic":
        vectors = embedding_provider.embed(
            [candidate.content, *[record.content for record in active]]
        )
        query_vector = vectors[0]
        ranked = sorted(
            zip(active, vectors[1:], strict=True),
            key=lambda item: (-cosine_similarity(query_vector, item[1]), item[0].id),
        )
        return [record for record, _vector in ranked[:top_k]], (
            f"semantic_top_{top_k}_of_{len(active)}"
        )

    query_tokens = lexical_tokens(candidate.content)

    def rank(record: ExperienceRecord) -> tuple[float, str]:
        record_tokens = lexical_tokens(record.content)
        union = query_tokens | record_tokens
        score = len(query_tokens & record_tokens) / len(union) if union else 0.0
        return (-score, record.id)

    return sorted(active, key=rank)[:top_k], f"lexical_top_{top_k}_of_{len(active)}"


def bounded_source_ids(
    values: Sequence[str],
    limit: int,
    preferred: Sequence[str] = (),
) -> list[str]:
    """Bound provenance IDs while retaining detailed evidence references first."""

    ordered = list(dict.fromkeys([*preferred, *sorted(values)]))
    return ordered[:limit]


def candidate_l0_review_view(
    candidate: L0CandidateRecord,
    *,
    rollout_limit: int,
    source_id_limit: int,
    content_limit: int,
) -> tuple[dict[str, Any], set[str]]:
    """Return a bounded candidate prompt view without mutating persisted evidence."""

    payload = candidate.public_dict()
    displayed = sorted(candidate.source_evidence, key=lambda item: item.id)[:rollout_limit]
    preferred_rollout_ids = [item.id for item in displayed]
    preferred_task_ids = [item.task_id for item in displayed if item.task_id]
    payload["content"] = candidate.content[:content_limit]
    payload["content_truncated"] = len(candidate.content) > content_limit
    payload["source_task_ids"] = bounded_source_ids(
        candidate.source_task_ids,
        source_id_limit,
        preferred_task_ids,
    )
    payload["source_rollout_ids"] = bounded_source_ids(
        candidate.source_rollout_ids,
        source_id_limit,
        preferred_rollout_ids,
    )
    payload["source_evidence"] = [item.model_dump(mode="json") for item in displayed]
    return payload, {item.id for item in displayed}


def supporting_candidate_views(
    record: ExperienceRecord,
    candidate_records: Mapping[str, ExperienceCandidateRecord],
    *,
    evidence_limit: int,
    rollout_limit: int,
    source_id_limit: int,
    content_limit: int,
    sort_key: CandidateSortKey,
) -> list[dict[str, Any]]:
    """Build individually bounded prior-candidate evidence views."""

    candidates = sorted(
        (
            candidate_records[candidate_id]
            for candidate_id in record.review_candidate_ids
            if candidate_id in candidate_records
        ),
        key=sort_key,
    )[-evidence_limit:]

    supporting: list[dict[str, Any]] = []
    for candidate in candidates:
        displayed_rollouts = sorted(candidate.source_evidence, key=lambda item: item.id)[
            :rollout_limit
        ]
        preferred_rollout_ids = [item.id for item in displayed_rollouts]
        preferred_task_ids = [item.task_id for item in displayed_rollouts if item.task_id]
        supporting.append(
            {
                "candidate_id": candidate.id,
                "candidate_content": candidate.content[:content_limit],
                "content_truncated": len(candidate.content) > content_limit,
                "source_task_ids": bounded_source_ids(
                    candidate.source_task_ids,
                    source_id_limit,
                    preferred_task_ids,
                ),
                "source_rollout_ids": bounded_source_ids(
                    candidate.source_rollout_ids,
                    source_id_limit,
                    preferred_rollout_ids,
                ),
                "source_evidence": [
                    evidence.model_dump(mode="json") for evidence in displayed_rollouts
                ],
                "review_action": (
                    candidate.review_decision.action if candidate.review_decision else None
                ),
                "review_reason": (
                    candidate.review_decision.reason if candidate.review_decision else None
                ),
            }
        )
    return supporting


def related_l0_review_views(
    records: Sequence[ExperienceRecord],
    candidate_records: Mapping[str, ExperienceCandidateRecord],
    *,
    max_chars: int,
    source_id_limit: int,
    content_limit: int,
    evidence_limit: int,
    rollout_limit: int,
    sort_key: CandidateSortKey,
) -> tuple[list[dict[str, Any]], set[str], list[ExperienceRecord]]:
    """Build the complete related-pool JSON under one exact global budget."""

    result: list[dict[str, Any]] = []
    displayed_ids: set[str] = set()
    displayed_records: list[ExperienceRecord] = []
    for record in records:
        public = record.public_dict()
        payload = {
            "id": record.id,
            "level": record.level,
            "content": record.content[:content_limit],
            "content_truncated": len(record.content) > content_limit,
            "source_task_ids": bounded_source_ids(
                record.source_task_ids,
                source_id_limit,
            ),
            "source_rollout_ids": bounded_source_ids(
                record.source_rollout_ids,
                source_id_limit,
            ),
            "domain": public.get("domain"),
            "task_family": public.get("task_family"),
            "failure_mode": public.get("failure_mode"),
            "strategy_type": public.get("strategy_type"),
            "tool_type": public.get("tool_type"),
            "task_stage": public.get("task_stage"),
            "version": record.version,
            "lifecycle_status": record.lifecycle_status,
            "supporting_candidate_evidence": [],
        }
        if len(json.dumps([*result, payload], ensure_ascii=False, sort_keys=True)) > max_chars:
            break

        result.append(payload)
        displayed_records.append(record)
        displayed_ids.add(record.id)
        displayed_ids.update(payload["source_task_ids"])
        displayed_ids.update(payload["source_rollout_ids"])

        supporting = supporting_candidate_views(
            record,
            candidate_records,
            evidence_limit=evidence_limit,
            rollout_limit=rollout_limit,
            source_id_limit=source_id_limit,
            content_limit=content_limit,
            sort_key=sort_key,
        )
        for support in supporting:
            trial = [dict(item) for item in result]
            trial[-1] = dict(trial[-1])
            trial[-1]["supporting_candidate_evidence"] = [
                *trial[-1]["supporting_candidate_evidence"],
                support,
            ]
            if len(json.dumps(trial, ensure_ascii=False, sort_keys=True)) > max_chars:
                break
            result = trial
            displayed_ids.add(support["candidate_id"])
            displayed_ids.update(support["source_task_ids"])
            displayed_ids.update(support["source_rollout_ids"])
    return result, displayed_ids, displayed_records


def upper_candidate_review_view(
    candidate: ExperienceCandidateRecord,
    parents: Sequence[ExperienceRecord],
    l0_records: Mapping[str, ExperienceRecord],
    *,
    content_limit: int,
    source_id_limit: int,
) -> tuple[dict[str, Any], set[str]]:
    payload = candidate.public_dict()
    payload["content"] = candidate.content[:content_limit]
    payload["content_truncated"] = len(candidate.content) > content_limit
    payload["direct_source_experiences"] = [parent.public_dict() for parent in parents]
    payload["source_task_ids"] = bounded_source_ids(
        candidate.source_task_ids,
        source_id_limit,
    )
    payload["source_rollout_ids"] = bounded_source_ids(
        candidate.source_rollout_ids,
        source_id_limit,
    )
    displayed = {parent.id for parent in parents}
    if candidate.level == "L2":
        reachable_l0_ids = sorted(
            {source_id for parent in parents for source_id in parent.source_l0_ids}
        )
        payload["reachable_l0_evidence"] = [
            l0_records[source_id].public_dict()
            for source_id in reachable_l0_ids
            if source_id in l0_records
            and l0_records[source_id].lifecycle_status == "active"
        ]
    return payload, displayed


def upper_related_review_views(
    candidate: ExperienceCandidateRecord,
    records: Sequence[ExperienceRecord],
    source_store: Mapping[str, ExperienceRecord],
    *,
    max_chars: int,
) -> tuple[list[dict[str, Any]], set[str], list[ExperienceRecord]]:
    result: list[dict[str, Any]] = []
    displayed_ids: set[str] = set()
    displayed_records: list[ExperienceRecord] = []
    for record in records:
        source_ids = record.parent_ids or (
            record.source_l0_ids if candidate.level == "L1" else record.source_l1_ids
        )
        sources = [
            source_store[source_id].public_dict()
            for source_id in source_ids
            if source_id in source_store
            and source_store[source_id].lifecycle_status == "active"
        ]
        payload = record.public_dict()
        payload["direct_source_experiences"] = sources
        trial = [*result, payload]
        if len(json.dumps(trial, ensure_ascii=False, sort_keys=True)) > max_chars:
            break
        result = trial
        displayed_records.append(record)
        displayed_ids.add(record.id)
        displayed_ids.update(source["id"] for source in sources)
        displayed_ids.update(record.source_task_ids)
        displayed_ids.update(record.source_rollout_ids)
        displayed_ids.update(record.source_l0_ids)
        displayed_ids.update(record.source_l1_ids)
    return result, displayed_ids, displayed_records


__all__ = [
    "bounded_source_ids",
    "candidate_l0_review_view",
    "lexical_tokens",
    "related_active",
    "related_l0_review_views",
    "supporting_candidate_views",
    "upper_candidate_review_view",
    "upper_related_review_views",
]
