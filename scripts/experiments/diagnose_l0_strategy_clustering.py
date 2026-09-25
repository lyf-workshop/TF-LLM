#!/usr/bin/env python3
"""Compare legacy full-text L0 clustering with strategy-aware clustering."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

from utu.config import ConfigLoader
from utu.practice.experience_clusterer import (
    ExperienceClusterer,
    HashingEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from utu.practice.experience_models import ExperienceRecord
from utu.practice.strategy_canonicalization import CANONICAL_STRATEGY_VERSION
from utu.utils import DIR_ROOT


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose L0 strategy clusters without modifying a snapshot or calling an LLM.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config-name",
        required=True,
        help="Training-free GRPO config under configs/practice, without the practice/ prefix.",
    )
    parser.add_argument(
        "--snapshot",
        help="Optional hierarchy JSON override; defaults to the configured experience_save_path.",
    )
    parser.add_argument("--output", help="Optional JSON report path; stdout is always populated.")
    parser.add_argument(
        "--excerpt-chars",
        type=int,
        default=280,
        help="Maximum original-content characters shown per clustered L0.",
    )
    args = parser.parse_args(argv)
    if args.excerpt_chars < 40:
        parser.error("--excerpt-chars must be at least 40")
    return args


def _resolve_path(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    return path.resolve() if path.is_absolute() else (DIR_ROOT / path).resolve()


def _items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _load_active_l0(path: Path) -> list[ExperienceRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = []
    for item in _items(payload.get("l0_experiences")):
        if not isinstance(item, dict) or item.get("lifecycle_status", "active") != "active":
            continue
        records.append(ExperienceRecord.model_validate(item))
    if not records:
        raise ValueError(f"Snapshot contains no active L0 records: {path}")
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _embedding_provider(config: Any):
    if config.embedding_provider == "hashing":
        return HashingEmbeddingProvider(seed=config.random_seed)
    cache_path = _resolve_path(config.embedding_cache_path)
    return SentenceTransformerEmbeddingProvider(
        model_name=config.embedding_model_name,
        model_revision=config.embedding_model_revision,
        expected_dimensions=config.embedding_dimensions,
        cache_path=cache_path,
        device=config.embedding_device,
        batch_size=config.embedding_batch_size,
        local_files_only=config.embedding_local_files_only,
        random_seed=config.random_seed,
    )


def _clusterer(config: Any, provider: Any, *, strategy_aware: bool) -> ExperienceClusterer:
    return ExperienceClusterer(
        provider,
        max_cluster_size=config.max_cluster_size,
        use_metadata_constraints=config.use_metadata_constraints,
        hard_constraint_fields=config.hard_constraint_fields,
        soft_constraint_fields=config.soft_constraint_fields,
        random_seed=config.random_seed,
        strategy_aware_l0_clustering=strategy_aware,
        l0_strategy_compatibility_threshold=config.l0_strategy_compatibility_threshold,
        l0_strategy_fallback_threshold=config.l0_strategy_fallback_threshold,
        l0_strategy_ignore_failure_mode=config.l0_strategy_ignore_failure_mode,
    )


def _cluster_summary(
    report: Any,
    *,
    records_by_id: dict[str, ExperienceRecord],
    canonical: dict[str, Any],
    compatibility: dict[tuple[str, str], Any],
    minimum_size: int,
    minimum_distinct_tasks: int,
    excerpt_chars: int,
) -> dict[str, Any]:
    size_distribution = Counter(len(cluster.experience_ids) for cluster in report.clusters)
    diversity_distribution = Counter(cluster.distinct_source_task_count for cluster in report.clusters)
    count_ready_diversity_blocked = []
    multi_member_clusters = []
    suspected_miscluster_count = 0
    independent_warning_counts: Counter[str] = Counter()
    for cluster in report.clusters:
        if len(cluster.experience_ids) >= minimum_size and cluster.distinct_source_task_count < minimum_distinct_tasks:
            count_ready_diversity_blocked.append(cluster.cluster_id)
        if len(cluster.experience_ids) < 2:
            continue
        pair_diagnostics = []
        suspicious_pairs = []
        for left_id, right_id in combinations(cluster.experience_ids, 2):
            key = tuple(sorted((left_id, right_id)))
            decision = compatibility[key]
            left = canonical[left_id]
            right = canonical[right_id]
            shared_distinctive = sorted(set(left.distinctive_strategy_labels) & set(right.distinctive_strategy_labels))
            shared_auxiliary = sorted(set(left.auxiliary_strategy_labels) & set(right.auxiliary_strategy_labels))
            pair_warnings = []
            if left.task_family and right.task_family and left.task_family != right.task_family:
                pair_warnings.append("task_family_mismatch")
            source_overlap = set(records_by_id[left_id].source_task_ids) & set(records_by_id[right_id].source_task_ids)
            if not source_overlap and not shared_distinctive:
                pair_warnings.append(
                    "cross_task_auxiliary_only_overlap" if shared_auxiliary else "cross_task_no_distinctive_strategy"
                )
            if not source_overlap and shared_distinctive and decision.strategy_anchor_similarity < 0.08:
                pair_warnings.append("low_anchor_overlap_despite_distinctive_label")
            pair_diagnostic = {
                "experience_ids": list(key),
                "warnings": pair_warnings,
                "shared_distinctive_strategy_labels": shared_distinctive,
                "shared_auxiliary_strategy_labels": shared_auxiliary,
                "production_compatibility": decision.as_dict(),
            }
            pair_diagnostics.append(pair_diagnostic)
            if pair_warnings:
                independent_warning_counts.update(pair_warnings)
                suspicious_pairs.append(pair_diagnostic)
        if suspicious_pairs:
            suspected_miscluster_count += 1
        multi_member_clusters.append(
            {
                "cluster_id": cluster.cluster_id,
                "size": len(cluster.experience_ids),
                "distinct_source_task_count": cluster.distinct_source_task_count,
                "source_task_ids": cluster.source_task_ids,
                "intra_cluster_similarity": cluster.intra_cluster_similarity,
                "eligible_for_l1": (
                    len(cluster.experience_ids) >= minimum_size
                    and cluster.distinct_source_task_count >= minimum_distinct_tasks
                ),
                "source_task_diversity_warning": (
                    "single_source_task_cluster" if cluster.distinct_source_task_count == 1 else None
                ),
                "suspected_miscluster": bool(suspicious_pairs),
                "pair_diagnostics": pair_diagnostics,
                "suspicious_pairs": suspicious_pairs,
                "members": [
                    {
                        "id": record_id,
                        "source_task_ids": records_by_id[record_id].source_task_ids,
                        "content_excerpt": records_by_id[record_id].content[:excerpt_chars],
                        "canonical": canonical[record_id].as_dict(),
                    }
                    for record_id in cluster.experience_ids
                ],
            }
        )
    return {
        "cluster_count": len(report.clusters),
        "cluster_size_distribution": {str(size): count for size, count in sorted(size_distribution.items())},
        "source_task_diversity_distribution": {
            str(size): count for size, count in sorted(diversity_distribution.items())
        },
        "multi_member_cluster_count": len(multi_member_clusters),
        "l1_eligible_cluster_count": sum(
            len(cluster.experience_ids) >= minimum_size and cluster.distinct_source_task_count >= minimum_distinct_tasks
            for cluster in report.clusters
        ),
        "count_ready_but_diversity_blocked_cluster_ids": count_ready_diversity_blocked,
        "suspected_miscluster_count": suspected_miscluster_count,
        "independent_warning_counts": dict(sorted(independent_warning_counts.items())),
        "multi_member_clusters": multi_member_clusters,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    loaded = ConfigLoader.load_training_free_grpo_config(args.config_name)
    config = loaded.practice.hierarchical_learning
    snapshot_path = _resolve_path(args.snapshot or config.experience_save_path)
    records = _load_active_l0(snapshot_path)
    records_by_id = {record.id: record for record in records}
    provider = _embedding_provider(config)
    baseline_clusterer = _clusterer(config, provider, strategy_aware=False)
    strategy_clusterer = _clusterer(config, provider, strategy_aware=True)

    baseline = baseline_clusterer.cluster(
        records,
        level="L0",
        similarity_threshold=config.l0_similarity_threshold,
    )
    strategy_aware = strategy_clusterer.cluster(
        records,
        level="L0",
        similarity_threshold=config.l0_similarity_threshold,
    )
    canonical, compatibility = strategy_clusterer.assess_l0_strategy_pairs(records)
    common = {
        "records_by_id": records_by_id,
        "canonical": canonical,
        "compatibility": compatibility,
        "minimum_size": config.min_l0_per_l1,
        "minimum_distinct_tasks": config.min_distinct_source_tasks_per_l1,
        "excerpt_chars": args.excerpt_chars,
    }
    report = {
        "mode": "read_only_offline_diagnostic",
        "config_name": args.config_name,
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": _sha256(snapshot_path),
        "canonical_strategy_version": CANONICAL_STRATEGY_VERSION,
        "active_l0_count": len(records),
        "distinct_source_task_count": len({task_id for record in records for task_id in record.source_task_ids}),
        "thresholds": {
            "recall_similarity": config.l0_similarity_threshold,
            "strategy_compatibility": config.l0_strategy_compatibility_threshold,
            "strategy_fallback": config.l0_strategy_fallback_threshold,
            "min_l0_per_l1": config.min_l0_per_l1,
            "min_distinct_source_tasks_per_l1": config.min_distinct_source_tasks_per_l1,
        },
        "strategy_compatibility_rejection_counts": (strategy_aware.strategy_compatibility_rejection_counts),
        "strategy_compatibility_rejection_examples": (strategy_aware.strategy_compatibility_rejection_examples),
        "baseline_full_text": _cluster_summary(baseline, **common),
        "strategy_aware": _cluster_summary(strategy_aware, **common),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output_path = _resolve_path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return report


def main(argv: Sequence[str] | None = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()
