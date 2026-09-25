#!/usr/bin/env python3
"""Continue hierarchical aggregation from an existing experience snapshot.

The command is deliberately plan-only unless ``--execute`` is supplied.  It
does not construct ``TrainingFreeGRPO`` and therefore never loads a dataset or
starts rollouts.  Execution may still call the configured aggregation and
candidate-review LLMs.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from utu.config import ConfigLoader
from utu.practice.dataset_manifest_guard import (
    validate_hierarchy_snapshot_sources,
    validate_practice_dataset_manifest,
)
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager
from utu.utils import DIR_ROOT

AggregationSelection = Literal["l1", "l2", "all"]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate an existing hierarchy snapshot without running task rollouts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config-name",
        required=True,
        help="Training-free GRPO config name under configs/practice (without the practice/ prefix).",
    )
    parser.add_argument(
        "--snapshot",
        help="Optional hierarchy JSON override. Relative paths are resolved from the repository root.",
    )
    parser.add_argument(
        "--level",
        choices=("l1", "l2", "all"),
        default="all",
        help="Generate/review L1 only, L2 only, or L1 followed by L2.",
    )
    parser.add_argument("--epoch", type=int, default=0, help="Epoch label written to aggregation audit records.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run local embedding plus configured aggregation/review LLM calls and update the snapshot.",
    )
    args = parser.parse_args(argv)
    if args.epoch < 0:
        parser.error("--epoch must be non-negative")
    return args


def _resolve_path(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = DIR_ROOT / path
    return path.resolve()


def _load_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Hierarchy snapshot does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Hierarchy snapshot is not a file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read hierarchy snapshot {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Hierarchy snapshot must contain a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _snapshot_stats(payload: dict[str, Any]) -> dict[str, Any]:
    levels: dict[str, Any] = {}
    for level in ("l0", "l1", "l2"):
        experiences = _items(payload.get(f"{level}_experiences"))
        archive = _items(payload.get(f"{level}_archive"))
        candidates = _items(payload.get(f"{level}_candidates"))
        records = [record for record in experiences if isinstance(record, dict)]
        candidate_records = [record for record in candidates if isinstance(record, dict)]
        lifecycle_counts = Counter(str(record.get("lifecycle_status", "active")) for record in records)
        aggregation_counts = Counter(str(record.get("aggregation_status", "pending")) for record in records)
        candidate_status_counts = Counter(str(record.get("status", "unknown")) for record in candidate_records)
        levels[level.upper()] = {
            "pool_count": len(experiences),
            "active_count": lifecycle_counts.get("active", 0),
            "needs_review_count": lifecycle_counts.get("needs_review", 0),
            "pending_aggregation_count": sum(
                record.get("lifecycle_status", "active") == "active"
                and record.get("aggregation_status", "pending") == "pending"
                for record in records
            ),
            "aggregation_status_counts": dict(sorted(aggregation_counts.items())),
            "archive_count": len(archive),
            "candidate_count": len(candidates),
            "candidate_status_counts": dict(sorted(candidate_status_counts.items())),
        }
    return {"schema_version": payload.get("schema_version"), "levels": levels}


def _selected_targets(selection: AggregationSelection) -> list[str]:
    if selection == "l1":
        return ["L1"]
    if selection == "l2":
        return ["L2"]
    return ["L1", "L2"]


def _threshold_gate_view(hierarchical_config: Any) -> dict[str, Any]:
    """Report the canonical per-layer calibration gates."""

    view: dict[str, Any] = {}
    for name in (
        "l0_similarity_threshold_provisional",
        "l1_similarity_threshold_provisional",
    ):
        view[name] = getattr(hierarchical_config, name)
    view["allow_provisional_aggregation"] = getattr(
        hierarchical_config,
        "allow_provisional_aggregation",
        False,
    )
    return view


async def _run_selected_aggregation(
    manager: HierarchicalExperienceManager,
    selection: AggregationSelection,
    *,
    epoch: int,
) -> None:
    """Use the manager's restart-safe public continuation API."""

    await manager.aggregate_levels(_selected_targets(selection), epoch=epoch)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    config = ConfigLoader.load_training_free_grpo_config(args.config_name)
    hierarchical_config = config.practice.hierarchical_learning.model_copy(deep=True)
    if not hierarchical_config.enabled:
        raise ValueError("Hierarchical learning is disabled in the selected config")

    configured_snapshot = args.snapshot or hierarchical_config.experience_save_path
    snapshot_path = _resolve_path(configured_snapshot)
    snapshot_before = _load_snapshot(snapshot_path)
    sha_before = _sha256(snapshot_path)

    data_config = getattr(config, "data", None)
    require_manifest = bool(getattr(data_config, "require_practice_manifest", False))
    manifest_guard: dict[str, Any] = {"required": require_manifest}
    if require_manifest:
        source_evidence = validate_hierarchy_snapshot_sources(
            snapshot_before,
            manifest_path=data_config.practice_manifest_path,
            practice_dataset=data_config.practice_dataset_name,
        )
        manifest_guard.update(source_evidence)
        if args.execute:
            evaluation_data = getattr(config.runtime, "data", None)
            manifest_guard["database_snapshot"] = validate_practice_dataset_manifest(
                practice_dataset=data_config.practice_dataset_name,
                manifest_path=data_config.practice_manifest_path,
                split_name=data_config.practice_manifest_split,
                expected_record_count=data_config.practice_manifest_expected_records,
                evaluation_dataset=(evaluation_data.dataset if evaluation_data is not None else None),
                db_url=getattr(config.runtime, "db_url", None),
            )
        else:
            manifest_guard["database_snapshot"] = {
                "status": "not_checked",
                "reason": "plan_only",
            }

    # The manager reads and atomically updates this exact file.  When a caller
    # explicitly selects another snapshot, keep its audit beside that snapshot
    # instead of accidentally appending to the config's original audit log.
    hierarchical_config.experience_save_path = str(snapshot_path)
    if args.snapshot:
        hierarchical_config.clustering_audit_path = str(
            snapshot_path.with_suffix(snapshot_path.suffix + ".clusters.jsonl")
        )
    elif hierarchical_config.clustering_audit_path:
        hierarchical_config.clustering_audit_path = str(_resolve_path(hierarchical_config.clustering_audit_path))

    model_provider = config.runtime.agent.model.model_provider
    report: dict[str, Any] = {
        "mode": "execute" if args.execute else "plan_only",
        "config_name": args.config_name,
        "snapshot_path": str(snapshot_path),
        "targets": _selected_targets(args.level),
        "epoch": args.epoch,
        "model": {
            "provider_type": model_provider.type,
            "name": model_provider.model,
        },
        "aggregation_temperature": hierarchical_config.aggregation_temperature,
        "candidate_review": {
            "L1": hierarchical_config.l1_candidate_review_enabled,
            "L2": hierarchical_config.l2_candidate_review_enabled,
        },
        "threshold_gates": _threshold_gate_view(hierarchical_config),
        "manifest_guard": manifest_guard,
        "before": {
            "snapshot_sha256": sha_before,
            "stats": _snapshot_stats(snapshot_before),
        },
    }

    if args.execute:
        manager = HierarchicalExperienceManager(
            config=config.runtime.agent,
            hierarchical_config=hierarchical_config,
            agent_objective=config.practice.agent_objective,
            learning_objective=config.practice.learning_objective,
        )
        await _run_selected_aggregation(manager, args.level, epoch=args.epoch)

    snapshot_after = _load_snapshot(snapshot_path)
    report["after"] = {
        "snapshot_sha256": _sha256(snapshot_path),
        "stats": _snapshot_stats(snapshot_after),
    }
    report["snapshot_changed"] = report["before"]["snapshot_sha256"] != report["after"]["snapshot_sha256"]
    if not args.execute:
        report["notice"] = "Plan only: no manager was constructed and no embedding or LLM call was made."
    else:
        report["notice"] = "Aggregation completed; regenerate an Agent YAML separately before evaluation."
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return report


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    main()
