"""SkillsBench task manifests and train/evaluation leakage guards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlmodel import select

from .db import DatasetSample
from .utils import SQLModelUtils


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_task_split_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("splits"), dict):
        raise ValueError(f"Invalid SkillsBench split manifest: {manifest_path}")
    inventory = manifest.get("tasks", [])
    dataset = manifest.get("dataset", {})
    expected_inventory_hash = dataset.get("inventory_sha256")
    if expected_inventory_hash and canonical_sha256(inventory) != expected_inventory_hash:
        raise ValueError(f"SkillsBench inventory hash mismatch: {manifest_path}")
    for split_name, split in manifest["splits"].items():
        expected = split.get("split_sha256")
        task_lists = {
            "train_task_ids": split.get("train_task_ids", []),
            "eval_task_ids": split.get("eval_task_ids", []),
            "excluded_task_ids": split.get("excluded_task_ids", []),
        }
        if expected and canonical_sha256(task_lists) != expected:
            raise ValueError(f"SkillsBench split hash mismatch for {split_name}: {manifest_path}")
        assert_task_ids_disjoint(task_lists["train_task_ids"], task_lists["eval_task_ids"])
    expected_manifest_hash = manifest.get("manifest_sha256")
    if expected_manifest_hash:
        unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        if canonical_sha256(unsigned) != expected_manifest_hash:
            raise ValueError(f"SkillsBench manifest hash mismatch: {manifest_path}")
    return manifest


def split_task_ids(path: str | Path, split_name: str) -> tuple[list[str], list[str]]:
    manifest = load_task_split_manifest(path)
    try:
        split = manifest["splits"][split_name]
    except KeyError as error:
        raise ValueError(f"Unknown SkillsBench split {split_name!r} in {path}") from error
    return list(split["train_task_ids"]), list(split["eval_task_ids"])


def _task_id(sample: DatasetSample) -> str:
    meta = sample.meta
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    if isinstance(meta, dict) and meta.get("task_id") is not None:
        return str(meta["task_id"])
    return str(sample.index)


def dataset_task_ids(dataset: str, *, db_url: str | None = None) -> list[str]:
    if db_url:
        SQLModelUtils.configure(db_url)
    with SQLModelUtils.create_session() as session:
        samples = session.exec(select(DatasetSample).where(DatasetSample.dataset == dataset)).all()
    if not samples:
        raise ValueError(f"SkillsBench dataset {dataset!r} is missing or empty")
    task_ids = [_task_id(sample) for sample in samples]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError(f"SkillsBench dataset {dataset!r} contains duplicate task IDs")
    return task_ids


def assert_task_ids_disjoint(train_task_ids: list[str], eval_task_ids: list[str]) -> None:
    overlap = sorted(set(train_task_ids) & set(eval_task_ids))
    if overlap:
        raise ValueError(
            "SkillsBench train/eval leakage detected: "
            f"{len(overlap)} overlapping task ID(s): {', '.join(overlap)}"
        )


def assert_datasets_disjoint(
    train_dataset: str,
    eval_dataset: str,
    *,
    db_url: str | None = None,
    split_manifest_path: str | Path | None = None,
    split_name: str | None = None,
) -> dict[str, Any]:
    train_ids = dataset_task_ids(train_dataset, db_url=db_url)
    eval_ids = dataset_task_ids(eval_dataset, db_url=db_url)
    assert_task_ids_disjoint(train_ids, eval_ids)
    if split_manifest_path or split_name:
        if not split_manifest_path or not split_name:
            raise ValueError("Both split_manifest_path and split_name are required")
        expected_train, expected_eval = split_task_ids(split_manifest_path, split_name)
        if set(train_ids) != set(expected_train):
            raise ValueError(
                f"Training dataset {train_dataset!r} does not match manifest split {split_name!r}"
            )
        if set(eval_ids) != set(expected_eval):
            raise ValueError(
                f"Evaluation dataset {eval_dataset!r} does not match manifest split {split_name!r}"
            )
    return {
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "train_task_count": len(train_ids),
        "eval_task_count": len(eval_ids),
        "train_task_ids_sha256": canonical_sha256(sorted(train_ids)),
        "eval_task_ids_sha256": canonical_sha256(sorted(eval_ids)),
        "overlap_count": 0,
        "split_manifest_path": str(split_manifest_path) if split_manifest_path else None,
        "split_name": split_name,
    }
