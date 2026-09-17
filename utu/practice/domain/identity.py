"""Stable identity and content normalisation for experience records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from .contracts import ExperienceLevel


def normalise_content(content: str) -> str:
    """Collapse whitespace before content-addressing an experience."""

    return re.sub(r"\s+", " ", content or "").strip()


def _sorted_values(values: Iterable[str | int] | None) -> list[str]:
    return sorted(str(value) for value in values or [])


def stable_experience_id(
    level: ExperienceLevel,
    content: str,
    parent_ids: list[str] | tuple[str, ...] | None = None,
    *,
    identity_context: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Return a deterministic ID independent of insertion order."""

    payload = {
        "level": level,
        "content": normalise_content(content),
        "parents": _sorted_values(parent_ids),
        "identity_context": _sorted_values(identity_context),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return f"{level}_{digest}"


def stable_l0_candidate_id(
    content: str,
    *,
    source_task_ids: list[str] | tuple[str, ...] | None = None,
    source_rollout_ids: list[str] | tuple[str, ...] | None = None,
    identity_context: list[str] | tuple[str, ...] | None = None,
    generator_version: str = "l0-summary-v1",
) -> str:
    """Return a restart-stable ID for an unreviewed L0 candidate."""

    payload = {
        "content": normalise_content(content),
        "source_task_ids": _sorted_values(source_task_ids),
        "source_rollout_ids": _sorted_values(source_rollout_ids),
        "identity_context": _sorted_values(identity_context),
        "generator_version": generator_version,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return f"C0_{digest}"


def stable_experience_candidate_id(
    level: ExperienceLevel,
    content: str,
    *,
    parent_ids: list[str] | tuple[str, ...] | None = None,
    source_versions: dict[str, str] | None = None,
    source_task_ids: list[str] | tuple[str, ...] | None = None,
    source_rollout_ids: list[str] | tuple[str, ...] | None = None,
    identity_context: list[str] | tuple[str, ...] | None = None,
    generator_version: str = "hierarchical-summary-v1",
) -> str:
    """Return a stable candidate ID including its direct evidence."""

    if level == "L0":
        return stable_l0_candidate_id(
            content,
            source_task_ids=source_task_ids,
            source_rollout_ids=source_rollout_ids,
            identity_context=identity_context,
            generator_version=generator_version,
        )
    payload = {
        "level": level,
        "content": normalise_content(content),
        "parents": _sorted_values(parent_ids),
        "source_versions": dict(sorted((source_versions or {}).items())),
        "source_task_ids": _sorted_values(source_task_ids),
        "source_rollout_ids": _sorted_values(source_rollout_ids),
        "identity_context": _sorted_values(identity_context),
        "generator_version": generator_version,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return f"C{level[-1]}_{digest}"
