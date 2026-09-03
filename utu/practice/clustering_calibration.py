"""Training-only calibration utilities for hierarchical experience clustering."""

from __future__ import annotations

import hashlib
import math
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..skillsbench_data import load_task_split_manifest
from .experience_clusterer import EmbeddingProvider, ExperienceClusterer, cosine_similarity
from .experience_models import ExperienceRecord
from .hierarchical_ablation import load_hierarchy


def _known(value: object) -> bool:
    raw = getattr(value, "value", value)
    return raw is not None and str(raw).strip().lower() not in {"", "unknown", "null"}


def _source_task_id(value: str) -> str:
    """Remove the source/dataset namespace used by L0 evidence IDs."""

    return value.split(":", 1)[-1]


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return dict.fromkeys(("min", "mean", "median", "p75", "p90", "p95")) | {"count": 0}

    def percentile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p75": percentile(0.75),
        "p90": percentile(0.90),
        "p95": percentile(0.95),
    }


def inspect_training_l0(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
) -> tuple[list[ExperienceRecord], dict[str, Any]]:
    """Validate that calibration evidence belongs only to the declared train split."""

    manifest = load_task_split_manifest(split_manifest_path)
    split = manifest["splits"][split_name]
    train_ids = set(split["train_task_ids"])
    eval_ids = set(split["eval_task_ids"])
    path = Path(hierarchy_path)
    raw_records = load_hierarchy(path)["L0"]
    records = [ExperienceRecord.model_validate(record) for record in raw_records]
    known_family = [record for record in records if _known(record.task_family)]
    with_source = [record for record in records if record.source_task_ids]
    outside_train: dict[str, list[str]] = {}
    evaluation_leakage: dict[str, list[str]] = {}
    eligible: list[ExperienceRecord] = []
    for record in records:
        sources = {_source_task_id(task_id) for task_id in record.source_task_ids}
        leaked = sorted(sources & eval_ids)
        outside = sorted(sources - train_ids)
        if leaked:
            evaluation_leakage[record.id] = leaked
        if outside:
            outside_train[record.id] = outside
        if sources and not outside and _known(record.task_family):
            eligible.append(record)
    if evaluation_leakage:
        raise ValueError(
            "Calibration input contains formal evaluation task evidence: "
            + "; ".join(f"{record_id}={ids}" for record_id, ids in sorted(evaluation_leakage.items()))
        )
    evidence = {
        "hierarchy_path": str(path),
        "source_l0_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "total_l0": len(records),
        "source_task_coverage": len(with_source) / len(records) if records else 0.0,
        "task_family_coverage": len(known_family) / len(records) if records else 0.0,
        "eligible_training_l0": len(eligible),
        "outside_train_records": outside_train,
        "dataset_version": manifest["dataset"],
        "split_name": split_name,
        "split_sha256": split["split_sha256"],
    }
    return eligible, evidence


def calibrate_training_l0(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
    *,
    embedding_provider: EmbeddingProvider | None,
    thresholds: Sequence[float],
    min_cluster_size: int = 5,
    min_records: int = 20,
    min_positive_pairs: int = 10,
    min_negative_pairs: int = 10,
    max_cluster_size: int = 20,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Calibrate on train L0 only, or return an explicit waiting status.

    Same-primary-task-family pairs are a reproducible proxy label, not a claim
    of true strategy equivalence. The resulting threshold therefore remains a
    candidate until a human inspects the cluster samples.
    """

    records, evidence = inspect_training_l0(hierarchy_path, split_manifest_path, split_name)
    family_counts = Counter(str(record.task_family) for record in records)
    potential_positive_pairs = sum(count * (count - 1) // 2 for count in family_counts.values())
    potential_total_pairs = len(records) * (len(records) - 1) // 2
    potential_negative_pairs = potential_total_pairs - potential_positive_pairs
    reasons = []
    if len(records) < min_records:
        reasons.append(f"need at least {min_records} eligible new-format training L0; found {len(records)}")
    if potential_positive_pairs < min_positive_pairs:
        reasons.append(
            f"need at least {min_positive_pairs} same-family pairs; found {potential_positive_pairs}"
        )
    if potential_negative_pairs < min_negative_pairs:
        reasons.append(
            f"need at least {min_negative_pairs} different-family pairs; found {potential_negative_pairs}"
        )
    if evidence["outside_train_records"]:
        reasons.append("some L0 source IDs cannot be matched to the declared training split")
    if reasons:
        return {
            "status": "waiting_for_data",
            "reasons": reasons,
            "evidence": evidence,
            "family_counts": dict(sorted(family_counts.items())),
            "recommended_threshold": None,
        }
    if embedding_provider is None:
        raise ValueError("embedding_provider is required after calibration data passes readiness checks")

    vectors = embedding_provider.embed([record.content for record in records])
    if len(vectors) != len(records):
        raise ValueError("Embedding provider returned a different number of vectors than L0 records")
    positives: list[float] = []
    negatives: list[float] = []
    for index, left in enumerate(records):
        for right_index in range(index + 1, len(records)):
            similarity = cosine_similarity(vectors[index], vectors[right_index])
            if left.task_family == records[right_index].task_family:
                positives.append(similarity)
            else:
                negatives.append(similarity)

    clusterer = ExperienceClusterer(
        embedding_provider,
        max_cluster_size=max_cluster_size,
        use_metadata_constraints=True,
        hard_constraint_fields=("task_stage", "failure_mode"),
        soft_constraint_fields=("domain", "task_family", "tool_type", "strategy_type"),
        random_seed=random_seed,
    )
    sweep = []
    scoring = []
    for threshold in sorted({float(value) for value in thresholds}):
        report = clusterer.cluster(records, level="L0", similarity_threshold=threshold)
        sizes = sorted(len(cluster.experience_ids) for cluster in report.clusters)
        pending_count = sum(size for size in sizes if size < min_cluster_size)
        true_positive_rate = sum(value >= threshold for value in positives) / len(positives)
        true_negative_rate = sum(value < threshold for value in negatives) / len(negatives)
        balanced_accuracy = (true_positive_rate + true_negative_rate) / 2
        scoring.append((balanced_accuracy, true_negative_rate, threshold))
        sweep.append(
            {
                "threshold": threshold,
                "cluster_count": len(sizes),
                "cluster_sizes": sizes,
                "max_cluster_size": max(sizes, default=0),
                "pending_ratio": pending_count / len(records),
                "same_family_recall": true_positive_rate,
                "different_family_rejection": true_negative_rate,
                "balanced_accuracy": balanced_accuracy,
            }
        )
    # Deterministic tie-breaking prefers stronger negative rejection, then the
    # higher threshold. This is a candidate for review, never an eval-tuned value.
    recommended = max(scoring)[2] if scoring else None
    provider_info = embedding_provider.info() if hasattr(embedding_provider, "info") else {}
    return {
        "status": "calibrated_training_proxy",
        "warning": "same task_family is only a proxy label; inspect clusters before accepting the threshold",
        "evidence": evidence,
        "embedding": provider_info,
        "family_counts": dict(sorted(family_counts.items())),
        "pair_similarity": {
            "positive_same_task_family": _distribution(positives),
            "negative_different_task_family": _distribution(negatives),
        },
        "threshold_sweep": sweep,
        "recommended_threshold": recommended,
        "recommended_threshold_provisional": True,
    }
