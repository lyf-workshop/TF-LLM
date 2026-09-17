"""Versioned snapshot assembly and atomic persistence for experience state."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from ..experience_models import ExperienceCandidateRecord, ExperienceLevel, ExperienceRecord

if TYPE_CHECKING:
    from ..hierarchical_experience_manager import HierarchicalExperienceManager

SCHEMA_VERSION = 4
STRICT_SNAPSHOT_VERSION = 3
WarningCallback = Callable[..., Any]


def normalise_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int)):
        return [str(value)]
    return sorted({str(item) for item in value if item is not None and str(item)})


def load_level(
    raw: Any,
    level: ExperienceLevel,
    legacy_aggregated_ids: set[str],
    *,
    strict: bool = False,
    warning: WarningCallback,
) -> dict[str, ExperienceRecord]:
    records: dict[str, ExperienceRecord] = {}
    mapping_payload = isinstance(raw, dict)
    if mapping_payload:
        items = list(raw.items())
    elif isinstance(raw, list):
        items = []
        for index, item in enumerate(raw):
            if isinstance(item, dict):
                items.append((str(item.get("id") or f"{level}_{index}"), item))
            else:
                items.append((f"{level}_{index}", item))
    else:
        if strict:
            raise ValueError(f"{level} experiences must be a list or object")
        return records

    for exp_id, value in items:
        status = "aggregated" if str(exp_id) in legacy_aggregated_ids else "pending"
        if level == "L2":
            status = "terminal"
        if isinstance(value, dict):
            payload = dict(value)
            payload_id = payload.get("id")
            if (
                strict
                and mapping_payload
                and payload_id is not None
                and str(payload_id) != str(exp_id)
            ):
                raise ValueError(
                    f"{level} experience key {exp_id} disagrees with payload id={payload_id}"
                )
            payload.setdefault("id", str(exp_id))
            payload_level = payload.get("level")
            if payload_level is not None and payload_level != level:
                if strict:
                    raise ValueError(
                        f"{level} experience bucket contains level={payload_level}: {exp_id}"
                    )
                warning(
                    "Normalising legacy experience %s from level %s to bucket %s",
                    exp_id,
                    payload_level,
                    level,
                )
                payload["level"] = level
            else:
                payload.setdefault("level", level)
            payload.setdefault("aggregation_status", status)
            if not payload.get("parent_ids"):
                if level == "L1":
                    payload["parent_ids"] = payload.get("source_l0_ids", [])
                elif level == "L2":
                    payload["parent_ids"] = payload.get("source_l1_ids", [])
            try:
                record = ExperienceRecord.model_validate(payload)
            except ValidationError as error:
                if strict:
                    raise ValueError(f"invalid {level} experience {exp_id}: {error}") from error
                warning("Skipping invalid %s experience %s: %s", level, exp_id, error)
                continue
        else:
            record = ExperienceRecord.from_legacy(
                str(exp_id),
                str(value),
                level,
                aggregation_status=status,
            )
        if record.id in records:
            if strict:
                raise ValueError(f"duplicate {level} experience ID: {record.id}")
            warning("Ignoring duplicate legacy %s experience ID %s", level, record.id)
            continue
        records[record.id] = record
    return records


def load_candidates(
    raw: Any,
    *,
    default_level: ExperienceLevel = "L0",
    strict_level: bool = False,
) -> dict[str, ExperienceCandidateRecord]:
    records: dict[str, ExperienceCandidateRecord] = {}
    if raw is None:
        return records
    if not isinstance(raw, (list, dict)):
        raise ValueError("experience candidates must be a list or object")
    items = raw.values() if isinstance(raw, dict) else raw
    for item in items:
        payload = dict(item) if isinstance(item, dict) else item
        if isinstance(payload, dict):
            payload_level = payload.get("level")
            if payload_level is not None and payload_level != default_level:
                if strict_level:
                    raise ValueError(
                        f"{default_level} candidate bucket contains level={payload_level}"
                    )
                payload["level"] = default_level
            else:
                payload.setdefault("level", default_level)
        candidate = ExperienceCandidateRecord.model_validate(payload)
        if candidate.id in records and records[candidate.id] != candidate:
            raise ValueError(f"conflicting duplicate candidate ID: {candidate.id}")
        records[candidate.id] = candidate
    return records


def ordered_records(records: dict[str, ExperienceRecord]) -> list[dict[str, Any]]:
    ordered = sorted(records.values(), key=lambda record: (record.created_at, record.id))
    return [record.public_dict() for record in ordered]


def ordered_candidates(
    records: dict[str, ExperienceCandidateRecord],
) -> list[dict[str, Any]]:
    ordered = sorted(
        records.values(),
        key=lambda candidate: (
            candidate.step,
            candidate.level,
            tuple(candidate.source_task_ids),
            tuple(candidate.source_rollout_ids),
            candidate.id,
        ),
    )
    return [candidate.public_dict() for candidate in ordered]


def state_payload(
    manager: HierarchicalExperienceManager,
    l0_records: dict[str, ExperienceRecord],
    l1_records: dict[str, ExperienceRecord],
    l2_records: dict[str, ExperienceRecord],
    candidate_records: dict[str, ExperienceCandidateRecord] | None = None,
    l0_archive: dict[str, ExperienceRecord] | None = None,
    l1_archive: dict[str, ExperienceRecord] | None = None,
    l2_archive: dict[str, ExperienceRecord] | None = None,
) -> dict[str, Any]:
    candidate_records = manager._candidate_records if candidate_records is None else candidate_records
    l0_archive = manager._l0_archive if l0_archive is None else l0_archive
    l1_archive = manager._l1_archive if l1_archive is None else l1_archive
    l2_archive = manager._l2_archive if l2_archive is None else l2_archive
    return {
        "schema_version": SCHEMA_VERSION,
        "experience_output_language": manager.experience_output_language,
        **manager._snapshot_provenance,
        "l0_candidates": ordered_candidates(
            {key: value for key, value in candidate_records.items() if value.level == "L0"}
        ),
        "l1_candidates": ordered_candidates(
            {key: value for key, value in candidate_records.items() if value.level == "L1"}
        ),
        "l2_candidates": ordered_candidates(
            {key: value for key, value in candidate_records.items() if value.level == "L2"}
        ),
        "l0_experiences": ordered_records(l0_records),
        "l0_archive": ordered_records(l0_archive),
        "l1_experiences": ordered_records(l1_records),
        "l1_archive": ordered_records(l1_archive),
        "l2_experiences": ordered_records(l2_records),
        "l2_archive": ordered_records(l2_archive),
        "l0_aggregated_ids": sorted(
            exp_id for exp_id, record in l0_records.items() if record.aggregation_status == "aggregated"
        ),
        "l1_aggregated_ids": sorted(
            exp_id for exp_id, record in l1_records.items() if record.aggregation_status == "aggregated"
        ),
        "stats": {
            "total_candidates": len(candidate_records),
            "pending_candidates": sum(
                candidate.status in {"pending", "review_failed"}
                for candidate in candidate_records.values()
            ),
            "active_l0": len(l0_records),
            "archived_l0": len(l0_archive),
            "active_l1": len(l1_records),
            "archived_l1": len(l1_archive),
            "active_l2": len(l2_records),
            "archived_l2": len(l2_archive),
            "total_l0": len(l0_records) + len(l0_archive),
            "total_l1": len(l1_records) + len(l1_archive),
            "total_l2": len(l2_records) + len(l2_archive),
            "pending_l0": sum(
                record.lifecycle_status == "active" and record.aggregation_status == "pending"
                for record in l0_records.values()
            ),
            "pending_l1": sum(
                record.lifecycle_status == "active" and record.aggregation_status == "pending"
                for record in l1_records.values()
            ),
            "l0_metadata_coverage": manager._metadata_coverage(list(l0_records.values())),
        },
    }


def write_state(
    manager: HierarchicalExperienceManager,
    l0_records: dict[str, ExperienceRecord],
    l1_records: dict[str, ExperienceRecord],
    l2_records: dict[str, ExperienceRecord],
    candidate_records: dict[str, ExperienceCandidateRecord] | None = None,
    l0_archive: dict[str, ExperienceRecord] | None = None,
    l1_archive: dict[str, ExperienceRecord] | None = None,
    l2_archive: dict[str, ExperienceRecord] | None = None,
) -> None:
    save_path = Path(manager.h_config.experience_save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = save_path.with_suffix(save_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(
            state_payload(
                manager,
                l0_records,
                l1_records,
                l2_records,
                candidate_records,
                l0_archive,
                l1_archive,
                l2_archive,
            ),
            file,
            indent=2,
            ensure_ascii=False,
        )
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary_path, save_path)


__all__ = [
    "SCHEMA_VERSION",
    "STRICT_SNAPSHOT_VERSION",
    "load_candidates",
    "load_level",
    "normalise_ids",
    "ordered_candidates",
    "ordered_records",
    "state_payload",
    "write_state",
]
