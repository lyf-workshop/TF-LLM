"""Fail-closed dataset manifest checks for measured practice runs.

This module deliberately does not import ``scripts/data/create_dapo_100.py``.
Training entry points must be able to validate an already-created snapshot
without importing data-generation code (or accidentally downloading/writing
data).  The canonical JSON, row and snapshot functions below are therefore a
small compatibility implementation of that script's signed-manifest contract.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlmodel import select

from ..db import DatasetSample
from ..utils import DIR_ROOT, SQLModelUtils

_ENRICHMENT_KEY = "_tf_llm_metadata_enrichment"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DAPO_PREFIX = re.compile(
    r"^\s*Solve the following math problem step by step\.\s*"
    r"The last line of your response should be of the form Answer:\s*\$Answer\s*"
    r"\(without quotes\) where \$Answer is the answer to the problem\.\s*",
    re.IGNORECASE,
)
_DAPO_SUFFIX = re.compile(
    r"\s*Remember to put your answer on its own line after [\"']Answer:[\"']\.\s*$",
    re.IGNORECASE,
)
_PRESENTATION_TEX = re.compile(r"\\(?:(?:left|right|quad|qquad)\b|[,!;:])")


def canonical_sha256(value: Any) -> str:
    """Hash JSON exactly as the DAPO snapshot builder does."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_row_payload(sample: DatasetSample) -> dict[str, Any]:
    """Return the fields covered by a DAPO dataset snapshot signature."""

    return {
        "index": sample.index,
        "source": sample.source,
        "source_index": sample.source_index,
        "question": sample.question,
        "answer": sample.answer,
        "topic": sample.topic,
        "level": sample.level,
        "file_name": sample.file_name,
        "meta": sample.meta,
    }


def canonical_row_sha256(sample: DatasetSample) -> str:
    return canonical_sha256(canonical_row_payload(sample))


def snapshot_sha256(samples: Sequence[DatasetSample]) -> str:
    """Hash rows in stable index order, matching ``create_dapo_100``."""

    ordered = sorted(
        samples,
        key=lambda sample: (
            sample.index is None,
            sample.index,
            canonical_row_sha256(sample),
        ),
    )
    return canonical_sha256([canonical_row_payload(sample) for sample in ordered])


def exclusion_snapshot_sha256(samples: Sequence[DatasetSample]) -> str:
    """Hash a source/exclusion population using the builder's stable order.

    This intentionally differs from :func:`snapshot_sha256`: the frozen AIME
    exclusion contract signs the ordered list of *row hashes*, sorted by
    normalized question identity and answer metadata, rather than signing the
    ordered row payloads directly.
    """

    ordered = sorted(
        samples,
        key=lambda sample: (
            question_sha256(sample.question, relaxed=True),
            canonical_sha256(
                {
                    "answer": sample.answer,
                    "topic": sample.topic,
                    "level": sample.level,
                }
            ),
            canonical_row_sha256(sample),
        ),
    )
    return canonical_sha256([canonical_row_sha256(sample) for sample in ordered])


def normalize_math_question(question: str | None, *, relaxed: bool = False) -> str:
    """Normalize math text using the frozen ``math-question-v1`` contract."""

    value = unicodedata.normalize("NFKC", question or "")
    value = value.replace("\ufeff", "").replace("\u200b", "").replace("\r\n", "\n").replace("\r", "\n")
    value = value.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2212": "-",
                "\u2013": "-",
                "\u2014": "-",
            }
        )
    )
    value = _DAPO_PREFIX.sub("", value)
    value = _DAPO_SUFFIX.sub("", value)
    value = value.casefold().strip()
    if relaxed:
        value = _PRESENTATION_TEX.sub("", value)
        for marker in ("$", r"\(", r"\)", r"\[", r"\]"):
            value = value.replace(marker, "")
        return re.sub(r"\s+", "", value)
    return re.sub(r"\s+", " ", value)


def question_sha256(question: str | None, *, relaxed: bool = False) -> str:
    normalized = normalize_math_question(question, relaxed=relaxed)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"Practice manifest field {field} must be a lowercase SHA-256")
    return value


def _resolve_manifest_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = DIR_ROOT / candidate
    return candidate.resolve()


def _load_signed_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = _resolve_manifest_path(path)
    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except FileNotFoundError as error:
        raise ValueError(f"Required practice manifest does not exist: {manifest_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Required practice manifest is not valid JSON: {manifest_path}") from error
    if not isinstance(manifest, dict):
        raise ValueError(f"Required practice manifest must contain a JSON object: {manifest_path}")
    expected = _require_sha256(manifest.get("manifest_sha256"), field="manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if canonical_sha256(unsigned) != expected:
        raise ValueError(f"Practice manifest signature mismatch: {manifest_path}")
    return manifest_path, manifest


def _manifest_task_namespace(
    manifest: Mapping[str, Any],
    *,
    practice_dataset: str,
) -> tuple[str, set[str]]:
    """Validate the signed inventory and return its exact source identities."""

    if manifest.get("schema_version") != 3:
        raise ValueError("Strict practice runs require a schema_version=3 enriched manifest")
    if manifest.get("target_dataset") != practice_dataset:
        raise ValueError("Practice manifest target_dataset does not match configuration")
    dataset = _require_mapping(manifest.get("dataset"), field="dataset")
    if dataset.get("name") != practice_dataset:
        raise ValueError("Practice manifest dataset.name does not match the configured dataset")
    namespace = dataset.get("namespace")
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("Practice manifest dataset.namespace must be a non-empty string")
    dataset_version = dataset.get("version")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("Practice manifest dataset.version must be a non-empty string")

    tasks = _require_list(manifest.get("tasks"), field="tasks")
    inventory_count = dataset.get("inventory_task_count")
    if isinstance(inventory_count, bool) or not isinstance(inventory_count, int):
        raise ValueError("Practice manifest dataset.inventory_task_count must be an integer")
    if inventory_count != len(tasks):
        raise ValueError("Practice manifest inventory_task_count does not match tasks")
    inventory_hash = _require_sha256(dataset.get("inventory_sha256"), field="dataset.inventory_sha256")
    if canonical_sha256(tasks) != inventory_hash:
        raise ValueError("Practice manifest task inventory hash mismatch")

    allowed_ids: set[str] = set()
    seen_task_ids: set[str] = set()
    seen_indices: set[int] = set()
    for position, raw_task in enumerate(tasks):
        task = _require_mapping(raw_task, field=f"tasks[{position}]")
        target_index = task.get("target_index")
        if isinstance(target_index, bool) or not isinstance(target_index, int):
            raise ValueError(f"Practice manifest tasks[{position}].target_index must be an integer")
        task_id = task.get("task_id")
        if task_id != str(target_index) or task_id in seen_task_ids or target_index in seen_indices:
            raise ValueError("Practice manifest task IDs and target indices must be unique and aligned")
        namespaced_id = task.get("namespaced_task_id")
        if namespaced_id != f"{namespace}:{target_index}":
            raise ValueError("Practice manifest namespaced_task_id does not match its namespace and target_index")
        seen_task_ids.add(task_id)
        seen_indices.add(target_index)
        allowed_ids.add(namespaced_id)
    if len(allowed_ids) != inventory_count:
        raise ValueError("Practice manifest contains duplicate namespaced task IDs")
    return namespace, allowed_ids


def _hierarchy_items(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key, [])
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        return list(value.values())
    raise ValueError(f"Hierarchy snapshot field {key} must be a list or object")


def validate_hierarchy_snapshot_sources(
    payload: Mapping[str, Any],
    *,
    manifest_path: str | Path,
    practice_dataset: str,
) -> dict[str, Any]:
    """Bind every persisted hierarchy record to one signed task inventory.

    This check is intentionally database- and model-free so both plan and
    execute modes of the standalone aggregation command can call it before
    constructing :class:`HierarchicalExperienceManager`.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("Hierarchy snapshot must contain a JSON object")
    if not practice_dataset:
        raise ValueError("practice_dataset is required for strict hierarchy validation")
    resolved_path, manifest = _load_signed_manifest(manifest_path)
    namespace, allowed_source_ids = _manifest_task_namespace(
        manifest,
        practice_dataset=practice_dataset,
    )

    collection_counts: dict[str, int] = {}
    referenced_source_ids: set[str] = set()
    for level in ("l0", "l1", "l2"):
        for suffix in ("experiences", "archive", "candidates"):
            key = f"{level}_{suffix}"
            items = _hierarchy_items(payload, key)
            collection_counts[key] = len(items)
            for position, raw_record in enumerate(items):
                if not isinstance(raw_record, Mapping):
                    raise ValueError(f"Hierarchy snapshot {key}[{position}] must be an object")
                record_id = raw_record.get("id", f"index-{position}")
                source_task_ids = raw_record.get("source_task_ids")
                if not isinstance(source_task_ids, list) or not source_task_ids:
                    raise ValueError(f"Strict hierarchy record {key}[{record_id}] requires non-empty source_task_ids")
                if any(not isinstance(task_id, str) or not task_id for task_id in source_task_ids):
                    raise ValueError(f"Hierarchy record {key}[{record_id}] has invalid source_task_ids")
                unknown = sorted(set(source_task_ids) - allowed_source_ids)
                if unknown:
                    raise ValueError(
                        f"Hierarchy record {key}[{record_id}] references task IDs outside "
                        f"manifest namespace {namespace!r}: {', '.join(unknown)}"
                    )
                referenced_source_ids.update(source_task_ids)

    return {
        "manifest_path": str(resolved_path),
        "manifest_sha256": manifest["manifest_sha256"],
        "practice_dataset": practice_dataset,
        "practice_namespace": namespace,
        "inventory_task_count": len(allowed_source_ids),
        "inventory_source_ids_sha256": canonical_sha256(sorted(allowed_source_ids)),
        "referenced_source_task_count": len(referenced_source_ids),
        "referenced_source_ids_sha256": canonical_sha256(sorted(referenced_source_ids)),
        "collection_counts": collection_counts,
    }


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Practice manifest field {field} must be an object")
    return value


def _require_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Practice manifest field {field} must be a list")
    return value


def _load_dataset_rows(dataset: str) -> list[DatasetSample]:
    with SQLModelUtils.create_session() as session:
        rows = session.exec(select(DatasetSample).where(DatasetSample.dataset == dataset)).all()
        # Materialize JSON attributes before the session closes.
        for row in rows:
            canonical_row_payload(row)
    return list(rows)


def _validate_contiguous_indices(rows: Sequence[DatasetSample], *, expected_count: int, label: str) -> None:
    indices = [row.index for row in rows]
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise ValueError(f"{label} must use integer indices")
    if len(indices) != len(set(indices)):
        raise ValueError(f"{label} contains duplicate indices")
    expected = list(range(expected_count))
    if sorted(indices) != expected:
        raise ValueError(f"{label} indices must be exactly 0..{expected_count - 1}")


def _validate_task_inventory(
    manifest: Mapping[str, Any],
    rows: Sequence[DatasetSample],
    *,
    target_dataset: str,
    split_name: str,
    expected_count: int,
) -> tuple[str, list[str]]:
    dataset = _require_mapping(manifest.get("dataset"), field="dataset")
    if dataset.get("name") != target_dataset:
        raise ValueError("Practice manifest dataset.name does not match the configured dataset")
    dataset_version = dataset.get("version")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("Practice manifest dataset.version must be a non-empty string")
    namespace = dataset.get("namespace")
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("Practice manifest dataset.namespace must be a non-empty string")
    if dataset.get("inventory_task_count") != expected_count:
        raise ValueError("Practice manifest inventory_task_count does not match the required size")

    tasks = _require_list(manifest.get("tasks"), field="tasks")
    if len(tasks) != expected_count:
        raise ValueError("Practice manifest task inventory does not contain the required number of tasks")
    inventory_hash = _require_sha256(dataset.get("inventory_sha256"), field="dataset.inventory_sha256")
    if canonical_sha256(tasks) != inventory_hash:
        raise ValueError("Practice manifest task inventory hash mismatch")

    rows_by_index = {row.index: row for row in rows}
    task_ids: list[str] = []
    seen_indices: set[int] = set()
    seen_task_ids: set[str] = set()
    for position, raw_task in enumerate(tasks):
        task = _require_mapping(raw_task, field=f"tasks[{position}]")
        target_index = task.get("target_index")
        if isinstance(target_index, bool) or not isinstance(target_index, int):
            raise ValueError(f"Practice manifest tasks[{position}].target_index must be an integer")
        if target_index in seen_indices or target_index not in rows_by_index:
            raise ValueError("Practice manifest task indices are duplicate or absent from the practice dataset")
        seen_indices.add(target_index)
        task_id = task.get("task_id")
        if task_id != str(target_index) or task_id in seen_task_ids:
            raise ValueError("Practice manifest task_id values must be unique string forms of target_index")
        seen_task_ids.add(task_id)
        task_ids.append(task_id)
        if task.get("namespaced_task_id") != f"{namespace}:{target_index}":
            raise ValueError("Practice manifest namespaced_task_id does not match dataset.namespace and target_index")

        row = rows_by_index[target_index]
        if task.get("source_index") != row.source_index:
            raise ValueError(f"Practice manifest source_index mismatch for task {task_id}")
        expected_question_hash = _require_sha256(
            task.get("question_sha256"), field=f"tasks[{position}].question_sha256"
        )
        if question_sha256(row.question) != expected_question_hash:
            raise ValueError(f"Practice manifest question hash mismatch for task {task_id}")
        source_record_hash = _require_sha256(
            task.get("source_record_sha256"), field=f"tasks[{position}].source_record_sha256"
        )

        meta = row.meta if isinstance(row.meta, Mapping) else {}
        enrichment = meta.get(_ENRICHMENT_KEY)
        if not isinstance(enrichment, Mapping):
            raise ValueError(f"Practice row {task_id} is missing signed metadata enrichment provenance")
        if enrichment.get("target_dataset") != target_dataset or enrichment.get("target_index") != target_index:
            raise ValueError(f"Practice row {task_id} has invalid enrichment target provenance")
        if enrichment.get("question_sha256") != expected_question_hash:
            raise ValueError(f"Practice row {task_id} enrichment question hash mismatch")
        if enrichment.get("source_record_sha256") != source_record_hash:
            raise ValueError(f"Practice row {task_id} enrichment source hash mismatch")
        if meta.get("domain") != task.get("domain") or meta.get("task_family") != task.get("task_family"):
            raise ValueError(f"Practice row {task_id} metadata does not match the task inventory")

    if seen_indices != set(range(expected_count)):
        raise ValueError("Practice manifest task inventory indices are not contiguous")

    splits = _require_mapping(manifest.get("splits"), field="splits")
    if split_name not in splits:
        raise ValueError(f"Practice manifest does not define required split {split_name!r}")
    split = _require_mapping(splits[split_name], field=f"splits.{split_name}")
    train_ids = _require_list(split.get("train_task_ids"), field=f"splits.{split_name}.train_task_ids")
    eval_ids = _require_list(split.get("eval_task_ids"), field=f"splits.{split_name}.eval_task_ids")
    excluded_ids = _require_list(split.get("excluded_task_ids"), field=f"splits.{split_name}.excluded_task_ids")
    if train_ids != task_ids:
        raise ValueError("Practice manifest split does not exactly match the ordered task inventory")
    if eval_ids or excluded_ids:
        raise ValueError("Practice-only calibration split must not claim evaluation or excluded task IDs")
    if split.get("train_task_ids_sha256") != canonical_sha256(train_ids):
        raise ValueError("Practice manifest train_task_ids hash mismatch")
    if split.get("eval_task_ids_sha256") != canonical_sha256(eval_ids):
        raise ValueError("Practice manifest eval_task_ids hash mismatch")
    split_payload = {
        "train_task_ids": train_ids,
        "eval_task_ids": eval_ids,
        "excluded_task_ids": excluded_ids,
    }
    if split.get("split_sha256") != canonical_sha256(split_payload):
        raise ValueError("Practice manifest split hash mismatch")
    return namespace, task_ids


def validate_practice_dataset_manifest(
    *,
    practice_dataset: str | None,
    manifest_path: str | Path | None,
    split_name: str | None,
    expected_record_count: int | None,
    evaluation_dataset: str | None,
    db_url: str | None = None,
) -> dict[str, Any]:
    """Validate a measured practice snapshot and its frozen evaluation set.

    The check is read-only and fail-closed.  Numeric indices are scoped by the
    dataset namespace; leakage is checked by normalized question content, not
    by comparing unrelated datasets' local integer indices.
    """

    if (
        isinstance(expected_record_count, bool)
        or not isinstance(expected_record_count, int)
        or expected_record_count <= 0
    ):
        raise ValueError("expected_record_count must be positive")
    if not practice_dataset or not evaluation_dataset:
        raise ValueError("Both practice_dataset and evaluation_dataset are required")
    if not manifest_path or not split_name:
        raise ValueError("Both manifest_path and split_name are required")
    if practice_dataset == evaluation_dataset:
        raise ValueError("Practice and evaluation datasets must be distinct")
    if db_url:
        # Manifest validation must not create or migrate schemas in a measured DB.
        SQLModelUtils.configure(db_url, initialize_schema=False)

    resolved_path, manifest = _load_signed_manifest(manifest_path)
    if manifest.get("schema_version") != 3:
        raise ValueError("Strict practice runs require a schema_version=3 enriched manifest")
    if manifest.get("target_dataset") != practice_dataset:
        raise ValueError("Practice manifest target_dataset does not match configuration")
    target_hash = _require_sha256(manifest.get("target_dataset_sha256"), field="target_dataset_sha256")

    practice_rows = _load_dataset_rows(practice_dataset)
    if len(practice_rows) != expected_record_count:
        raise ValueError(
            f"Practice dataset {practice_dataset!r} has {len(practice_rows)} rows; "
            f"expected exactly {expected_record_count}"
        )
    _validate_contiguous_indices(
        practice_rows,
        expected_count=expected_record_count,
        label=f"Practice dataset {practice_dataset!r}",
    )
    actual_target_hash = snapshot_sha256(practice_rows)
    if actual_target_hash != target_hash:
        raise ValueError("Practice dataset rows do not match target_dataset_sha256")
    namespace, task_ids = _validate_task_inventory(
        manifest,
        practice_rows,
        target_dataset=practice_dataset,
        split_name=split_name,
        expected_count=expected_record_count,
    )

    exclusion = _require_mapping(manifest.get("evaluation_exclusion"), field="evaluation_exclusion")
    if exclusion.get("dataset") != evaluation_dataset:
        raise ValueError("Practice manifest evaluation_exclusion dataset does not match evaluation configuration")
    exclusion_count = exclusion.get("record_count")
    if isinstance(exclusion_count, bool) or not isinstance(exclusion_count, int) or exclusion_count <= 0:
        raise ValueError("Practice manifest evaluation_exclusion.record_count must be positive")
    exclusion_hash = _require_sha256(exclusion.get("snapshot_sha256"), field="evaluation_exclusion.snapshot_sha256")
    evaluation_rows = _load_dataset_rows(evaluation_dataset)
    if len(evaluation_rows) != exclusion_count:
        raise ValueError(
            f"Evaluation dataset {evaluation_dataset!r} has {len(evaluation_rows)} rows; "
            f"frozen manifest requires {exclusion_count}"
        )
    actual_exclusion_hash = exclusion_snapshot_sha256(evaluation_rows)
    if actual_exclusion_hash != exclusion_hash:
        raise ValueError("Evaluation dataset rows do not match the frozen exclusion snapshot_sha256")

    training_hashes = {question_sha256(row.question) for row in practice_rows}
    evaluation_hashes = {question_sha256(row.question) for row in evaluation_rows}
    relaxed_training_hashes = {question_sha256(row.question, relaxed=True) for row in practice_rows}
    relaxed_evaluation_hashes = {question_sha256(row.question, relaxed=True) for row in evaluation_rows}
    exact_overlap = training_hashes & evaluation_hashes
    relaxed_overlap = relaxed_training_hashes & relaxed_evaluation_hashes
    if exact_overlap or relaxed_overlap:
        raise ValueError(
            "Practice/evaluation content leakage detected by frozen normalized question hashes: "
            f"exact={len(exact_overlap)}, relaxed={len(relaxed_overlap)}"
        )

    namespaced_ids = [f"{namespace}:{task_id}" for task_id in task_ids]
    return {
        "manifest_path": str(resolved_path),
        "manifest_sha256": manifest["manifest_sha256"],
        "practice_dataset": practice_dataset,
        "practice_namespace": namespace,
        "practice_dataset_version": manifest["dataset"]["version"],
        "practice_record_count": len(practice_rows),
        "practice_snapshot_sha256": actual_target_hash,
        "practice_namespaced_task_ids_sha256": canonical_sha256(namespaced_ids),
        "split_name": split_name,
        "evaluation_dataset": evaluation_dataset,
        "evaluation_record_count": len(evaluation_rows),
        "evaluation_snapshot_sha256": actual_exclusion_hash,
        "content_overlap_count": 0,
    }
