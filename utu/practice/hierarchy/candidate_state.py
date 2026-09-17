"""Pure helpers for persisted candidate identity and lookup."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..experience_models import ExperienceCandidateRecord, ExperienceLevel

CandidateSortKey = Callable[[ExperienceCandidateRecord], tuple[Any, ...]]

_IDENTITY_FIELDS = (
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
    "level",
    "parent_ids",
    "source_l0_ids",
    "source_l1_ids",
    "source_versions",
    "source_fingerprint",
    "generation_fingerprint",
    "cluster_id",
    "structured_content",
    "generator_version",
)


def identity_payload(candidate: ExperienceCandidateRecord) -> dict[str, Any]:
    """Return immutable fields used to validate a stable candidate ID."""

    payload = candidate.public_dict()
    return {field_name: payload[field_name] for field_name in _IDENTITY_FIELDS}


def find_by_generation(
    records: Mapping[str, ExperienceCandidateRecord],
    level: ExperienceLevel,
    generation_fingerprint: str,
    *,
    sort_key: CandidateSortKey,
) -> ExperienceCandidateRecord | None:
    """Find the one candidate generated from an identical input contract."""

    matches = sorted(
        (
            candidate
            for candidate in records.values()
            if candidate.level == level
            and candidate.generation_fingerprint == generation_fingerprint
        ),
        key=sort_key,
    )
    if len(matches) > 1:
        raise ValueError(
            f"multiple {level} candidates share generation fingerprint {generation_fingerprint}"
        )
    return matches[0] if matches else None


def same_identity(
    existing: ExperienceCandidateRecord,
    candidate: ExperienceCandidateRecord,
) -> bool:
    """Compare only immutable candidate fields, excluding review state."""

    return identity_payload(existing) == identity_payload(candidate)


__all__ = ["find_by_generation", "identity_payload", "same_identity"]
