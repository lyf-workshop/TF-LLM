"""Training-only calibration utilities for hierarchical experience clustering."""

from __future__ import annotations

import hashlib
import math
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from ..skillsbench_data import load_task_split_manifest
from .experience_clusterer import (
    DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS,
    DEFAULT_HARD_CONSTRAINT_FIELDS,
    TASK_FAMILY_PROXY_LABEL,
    EmbeddingProvider,
    ExperienceClusterer,
    cosine_similarity,
)
from .experience_models import ExperienceRecord
from .hierarchical_ablation import load_hierarchy

CalibrationLevel = Literal["L0", "L1"]

L0_DEFAULT_MIN_RECORDS = 20
L0_DEFAULT_MIN_POSITIVE_PAIRS = 10
L0_DEFAULT_MIN_NEGATIVE_PAIRS = 10

# At most 20 L1 records can be produced from 100 L0 records when
# min_l0_per_l1=5, before candidate KEEP/UPDATE decisions reduce that number.
# Eight records plus several positive and negative pairs is enough to make a
# distribution inspectable, but is explicitly not a statistical-sufficiency
# claim. The resulting threshold always remains provisional for human review.
L1_DEFAULT_MIN_RECORDS = 8
L1_DEFAULT_MIN_POSITIVE_PAIRS = 3
L1_DEFAULT_MIN_NEGATIVE_PAIRS = 6


def _known(value: object) -> bool:
    raw = getattr(value, "value", value)
    return raw is not None and str(raw).strip().lower() not in {"", "unknown", "null"}


def _source_task_id(value: str) -> str:
    """Remove the source/dataset namespace used by L0 evidence IDs."""

    return value.split(":", 1)[-1]


def _source_task_namespace(value: str) -> str | None:
    """Return the evidence namespace when a stable task ID is namespaced."""

    namespace, separator, _task_id = value.partition(":")
    return namespace if separator else None


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


def _resolve_readiness_thresholds(
    level: CalibrationLevel,
    *,
    min_records: int | None,
    min_positive_pairs: int | None,
    min_negative_pairs: int | None,
) -> tuple[int, int, int, dict[str, Any]]:
    if level == "L0":
        defaults = (
            L0_DEFAULT_MIN_RECORDS,
            L0_DEFAULT_MIN_POSITIVE_PAIRS,
            L0_DEFAULT_MIN_NEGATIVE_PAIRS,
        )
        policy = "conservative_training_proxy"
    else:
        defaults = (
            L1_DEFAULT_MIN_RECORDS,
            L1_DEFAULT_MIN_POSITIVE_PAIRS,
            L1_DEFAULT_MIN_NEGATIVE_PAIRS,
        )
        policy = "minimum_analyzable_not_sufficient"
    resolved = (
        defaults[0] if min_records is None else int(min_records),
        defaults[1] if min_positive_pairs is None else int(min_positive_pairs),
        defaults[2] if min_negative_pairs is None else int(min_negative_pairs),
    )
    if resolved[0] < 2:
        raise ValueError("min_records must be at least 2")
    if resolved[1] < 1:
        raise ValueError("min_positive_pairs must be at least 1")
    if resolved[2] < 1:
        raise ValueError("min_negative_pairs must be at least 1")
    return (
        *resolved,
        {
            "policy": policy,
            "is_statistical_sufficiency_claim": False,
            "minimum_records": resolved[0],
            "minimum_positive_pairs": resolved[1],
            "minimum_negative_pairs": resolved[2],
            "uses_layer_defaults": {
                "records": min_records is None,
                "positive_pairs": min_positive_pairs is None,
                "negative_pairs": min_negative_pairs is None,
            },
        },
    )


def inspect_training_level(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
    *,
    level: CalibrationLevel,
) -> tuple[list[ExperienceRecord], dict[str, Any]]:
    """Return eligible active records from one train-only hierarchy level."""

    manifest = load_task_split_manifest(split_manifest_path)
    split = manifest["splits"][split_name]
    train_ids = set(split["train_task_ids"])
    eval_ids = set(split["eval_task_ids"])
    dataset_metadata = manifest.get("dataset")
    expected_namespace = (
        str(dataset_metadata.get("namespace"))
        if isinstance(dataset_metadata, dict) and dataset_metadata.get("namespace")
        else None
    )
    path = Path(hierarchy_path)
    raw_records = load_hierarchy(path)[level]
    all_records = [ExperienceRecord.model_validate(record) for record in raw_records]
    records = [record for record in all_records if record.lifecycle_status == "active"]
    known_family = [record for record in records if _known(record.task_family)]
    with_source = [record for record in records if record.source_task_ids]
    outside_train: dict[str, list[str]] = {}
    namespace_mismatches: dict[str, list[str]] = {}
    evaluation_leakage: dict[str, list[str]] = {}
    eligible: list[ExperienceRecord] = []
    for record in records:
        sources = {_source_task_id(task_id) for task_id in record.source_task_ids}
        wrong_namespaces = sorted(
            task_id
            for task_id in record.source_task_ids
            if expected_namespace is not None
            and _source_task_namespace(task_id) != expected_namespace
        )
        leaked = sorted(sources & eval_ids)
        outside = sorted(sources - train_ids)
        if leaked:
            evaluation_leakage[record.id] = leaked
        if outside:
            outside_train[record.id] = outside
        if wrong_namespaces:
            namespace_mismatches[record.id] = wrong_namespaces
        if sources and not outside and not wrong_namespaces and _known(record.task_family):
            eligible.append(record)
    if evaluation_leakage:
        raise ValueError(
            f"{level} calibration input contains formal evaluation task evidence: "
            + "; ".join(f"{record_id}={ids}" for record_id, ids in sorted(evaluation_leakage.items()))
        )
    level_key = level.lower()
    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = {
        "hierarchy_path": str(path),
        "source_level": level,
        "source_hierarchy_sha256": file_sha256,
        f"source_{level_key}_sha256": file_sha256,
        f"total_{level_key}": len(all_records),
        f"active_{level_key}": len(records),
        f"excluded_non_active_{level_key}_ids": sorted(
            record.id for record in all_records if record.lifecycle_status != "active"
        ),
        "source_task_coverage": len(with_source) / len(records) if records else 0.0,
        "task_family_coverage": len(known_family) / len(records) if records else 0.0,
        f"eligible_training_{level_key}": len(eligible),
        "eligible_training_records": len(eligible),
        "outside_train_records": outside_train,
        "expected_source_namespace": expected_namespace,
        "source_namespace_mismatches": namespace_mismatches,
        "dataset_version": manifest["dataset"],
        "split_name": split_name,
        "split_sha256": split["split_sha256"],
    }
    return eligible, evidence


def inspect_training_l0(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
) -> tuple[list[ExperienceRecord], dict[str, Any]]:
    """Compatibility wrapper for callers of the original L0-only API."""

    return inspect_training_level(
        hierarchy_path,
        split_manifest_path,
        split_name,
        level="L0",
    )


def inspect_training_l1(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
) -> tuple[list[ExperienceRecord], dict[str, Any]]:
    """Inspect active, traceable L1 records without inferring missing families."""

    return inspect_training_level(
        hierarchy_path,
        split_manifest_path,
        split_name,
        level="L1",
    )


def calibrate_training_level(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
    *,
    level: CalibrationLevel,
    embedding_provider: EmbeddingProvider | None,
    thresholds: Sequence[float],
    min_cluster_size: int | None = None,
    min_records: int | None = None,
    min_positive_pairs: int | None = None,
    min_negative_pairs: int | None = None,
    max_cluster_size: int = 20,
    random_seed: int = 42,
    use_metadata_constraints: bool = True,
    hard_constraint_fields: Sequence[str] = DEFAULT_HARD_CONSTRAINT_FIELDS,
    soft_constraint_fields: Sequence[str] = DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS,
) -> dict[str, Any]:
    """Calibrate one source level on training evidence, or explicitly wait.

    Same-primary-task-family pairs are a reproducible proxy label, not a claim
    of true strategy equivalence. The resulting threshold therefore remains a
    candidate until a human inspects the cluster samples.
    """

    min_records, min_positive_pairs, min_negative_pairs, readiness = (
        _resolve_readiness_thresholds(
            level,
            min_records=min_records,
            min_positive_pairs=min_positive_pairs,
            min_negative_pairs=min_negative_pairs,
        )
    )
    records, evidence = inspect_training_level(
        hierarchy_path,
        split_manifest_path,
        split_name,
        level=level,
    )
    if min_cluster_size is None:
        min_cluster_size = 5 if level == "L0" else 3
    family_counts = Counter(str(record.task_family) for record in records)
    potential_positive_pairs = sum(count * (count - 1) // 2 for count in family_counts.values())
    potential_total_pairs = len(records) * (len(records) - 1) // 2
    potential_negative_pairs = potential_total_pairs - potential_positive_pairs
    readiness["observed_records"] = len(records)
    readiness["observed_positive_pairs"] = potential_positive_pairs
    readiness["observed_negative_pairs"] = potential_negative_pairs
    reasons = []
    if len(records) < min_records:
        reasons.append(
            f"need at least {min_records} eligible active training {level}; found {len(records)}"
        )
    if potential_positive_pairs < min_positive_pairs:
        reasons.append(
            f"need at least {min_positive_pairs} same-family pairs; found {potential_positive_pairs}"
        )
    if potential_negative_pairs < min_negative_pairs:
        reasons.append(
            f"need at least {min_negative_pairs} different-family pairs; found {potential_negative_pairs}"
        )
    if evidence["outside_train_records"]:
        reasons.append(
            f"some {level} source IDs cannot be matched to the declared training split"
        )
    if evidence["source_namespace_mismatches"]:
        reasons.append(
            f"some {level} source IDs use a different dataset namespace than the calibration manifest"
        )
    if reasons:
        return {
            "status": "waiting_for_data",
            "reasons": reasons,
            "evidence": evidence,
            "family_counts": dict(sorted(family_counts.items())),
            "source_level": level,
            "readiness": readiness,
            "recommended_threshold": None,
        }
    if embedding_provider is None:
        raise ValueError(
            f"embedding_provider is required after {level} calibration data passes readiness checks"
        )

    # Use every configured metadata feature so the candidate threshold is
    # scored against exactly the runtime contract. task_family is also the
    # proxy label, which creates circular optimism when configured as a soft
    # feature; expose that limitation explicitly instead of silently changing
    # the formal runtime configuration during calibration.
    requested_soft_constraint_fields = tuple(soft_constraint_fields)
    clusterer = ExperienceClusterer(
        embedding_provider,
        max_cluster_size=max_cluster_size,
        use_metadata_constraints=use_metadata_constraints,
        hard_constraint_fields=hard_constraint_fields,
        soft_constraint_fields=requested_soft_constraint_fields,
        random_seed=random_seed,
    )
    vectors = embedding_provider.embed([record.content for record in records])
    if len(vectors) != len(records):
        raise ValueError(
            f"Embedding provider returned a different number of vectors than {level} records"
        )
    positives = []
    negatives = []
    for index, left in enumerate(records):
        for right_index in range(index + 1, len(records)):
            right = records[right_index]
            pair_score = clusterer.score_pair(
                left,
                right,
                semantic_similarity=cosine_similarity(vectors[index], vectors[right_index]),
            )
            if left.task_family == right.task_family:
                positives.append(pair_score)
            else:
                negatives.append(pair_score)
    proxy_label_used_as_score_feature = bool(
        use_metadata_constraints
        and TASK_FAMILY_PROXY_LABEL in requested_soft_constraint_fields
    )
    circularity_warning = {
        "code": "task_family_proxy_feature_circularity",
        "applies": proxy_label_used_as_score_feature,
        "proxy_label": TASK_FAMILY_PROXY_LABEL,
        "score_feature": TASK_FAMILY_PROXY_LABEL,
        "risk": (
            "same-family recall and different-family rejection may be optimistic "
            "because task_family labels also adjust the runtime score"
        ),
        "requires_human_review": True,
    }
    score_contract = clusterer.pair_score_contract()
    score_contract.update(
        {
            "calibration_proxy_label": TASK_FAMILY_PROXY_LABEL,
            "requested_soft_constraint_fields": list(requested_soft_constraint_fields),
            "excluded_soft_constraint_fields": [],
            "proxy_label_used_as_score_feature": proxy_label_used_as_score_feature,
            "circularity_warning": circularity_warning,
            "pair_distribution_value": "adjusted_similarity",
            "recommendation_value": (
                "hard_compatible and adjusted_similarity >= threshold"
            ),
            "hard_incompatible_pairs_never_pass": True,
            "shared_runtime_pair_score_api": True,
            "runtime_configuration_match": (
                "compare use_metadata_constraints, hard_constraint_fields, and "
                "soft_constraint_fields with the formal run"
            ),
        }
    )
    sweep = []
    scoring = []
    for threshold in sorted({float(value) for value in thresholds}):
        report = clusterer.cluster(records, level=level, similarity_threshold=threshold)
        sizes = sorted(len(cluster.experience_ids) for cluster in report.clusters)
        pending_count = sum(size for size in sizes if size < min_cluster_size)
        true_positive_rate = sum(
            pair_score.passes_threshold(threshold) for pair_score in positives
        ) / len(positives)
        true_negative_rate = sum(
            not pair_score.passes_threshold(threshold) for pair_score in negatives
        ) / len(negatives)
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
        "warnings": [circularity_warning] if circularity_warning["applies"] else [],
        "source_level": level,
        "threshold_config_field": f"{level.lower()}_similarity_threshold",
        "provisional_config_field": f"{level.lower()}_similarity_threshold_provisional",
        "readiness": readiness,
        "evidence": evidence,
        "embedding": provider_info,
        "score_contract": score_contract,
        "family_counts": dict(sorted(family_counts.items())),
        "pair_similarity": {
            "positive_same_task_family": _distribution(
                [pair_score.adjusted_similarity for pair_score in positives]
            ),
            "negative_different_task_family": _distribution(
                [pair_score.adjusted_similarity for pair_score in negatives]
            ),
            "raw_cosine": {
                "positive_same_task_family": _distribution(
                    [pair_score.semantic_similarity for pair_score in positives]
                ),
                "negative_different_task_family": _distribution(
                    [pair_score.semantic_similarity for pair_score in negatives]
                ),
            },
        },
        "threshold_sweep": sweep,
        "recommended_threshold": recommended,
        "recommended_threshold_provisional": True,
    }


def calibrate_training_l0(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
    *,
    embedding_provider: EmbeddingProvider | None,
    thresholds: Sequence[float],
    min_cluster_size: int = 5,
    min_records: int | None = None,
    min_positive_pairs: int | None = None,
    min_negative_pairs: int | None = None,
    max_cluster_size: int = 20,
    random_seed: int = 42,
    use_metadata_constraints: bool = True,
    hard_constraint_fields: Sequence[str] = DEFAULT_HARD_CONSTRAINT_FIELDS,
    soft_constraint_fields: Sequence[str] = DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS,
) -> dict[str, Any]:
    """Compatibility wrapper for training-only L0 calibration."""

    return calibrate_training_level(
        hierarchy_path,
        split_manifest_path,
        split_name,
        level="L0",
        embedding_provider=embedding_provider,
        thresholds=thresholds,
        min_cluster_size=min_cluster_size,
        min_records=min_records,
        min_positive_pairs=min_positive_pairs,
        min_negative_pairs=min_negative_pairs,
        max_cluster_size=max_cluster_size,
        random_seed=random_seed,
        use_metadata_constraints=use_metadata_constraints,
        hard_constraint_fields=hard_constraint_fields,
        soft_constraint_fields=soft_constraint_fields,
    )


def calibrate_training_l1(
    hierarchy_path: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
    *,
    embedding_provider: EmbeddingProvider | None,
    thresholds: Sequence[float],
    min_cluster_size: int = 3,
    min_records: int | None = None,
    min_positive_pairs: int | None = None,
    min_negative_pairs: int | None = None,
    max_cluster_size: int = 20,
    random_seed: int = 42,
    use_metadata_constraints: bool = True,
    hard_constraint_fields: Sequence[str] = DEFAULT_HARD_CONSTRAINT_FIELDS,
    soft_constraint_fields: Sequence[str] = DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS,
) -> dict[str, Any]:
    """Calibrate L1->L2 clustering from active, training-only L1 records."""

    return calibrate_training_level(
        hierarchy_path,
        split_manifest_path,
        split_name,
        level="L1",
        embedding_provider=embedding_provider,
        thresholds=thresholds,
        min_cluster_size=min_cluster_size,
        min_records=min_records,
        min_positive_pairs=min_positive_pairs,
        min_negative_pairs=min_negative_pairs,
        max_cluster_size=max_cluster_size,
        random_seed=random_seed,
        use_metadata_constraints=use_metadata_constraints,
        hard_constraint_fields=hard_constraint_fields,
        soft_constraint_fields=soft_constraint_fields,
    )
