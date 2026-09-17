#!/usr/bin/env python3
"""Offline, train-only threshold calibration for hierarchical clustering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from utu.practice.clustering_calibration import (
    L0_DEFAULT_MIN_NEGATIVE_PAIRS,
    L0_DEFAULT_MIN_POSITIVE_PAIRS,
    L0_DEFAULT_MIN_RECORDS,
    L1_DEFAULT_MIN_NEGATIVE_PAIRS,
    L1_DEFAULT_MIN_POSITIVE_PAIRS,
    L1_DEFAULT_MIN_RECORDS,
    calibrate_training_level,
)
from utu.practice.experience_clusterer import (
    DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS,
    DEFAULT_HARD_CONSTRAINT_FIELDS,
    HashingEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiences", required=True)
    parser.add_argument(
        "--split-manifest",
        default="configs/data/skillsbench/skillsbench_v1_1_task_splits.json",
    )
    parser.add_argument("--split-name", default="family_holdout_self_contained_v1")
    parser.add_argument(
        "--level",
        choices=("L0", "L1"),
        default="L0",
        help="Source hierarchy level whose clustering threshold is being calibrated.",
    )
    parser.add_argument("--provider", choices=("sentence_transformer", "hashing"), default="sentence_transformer")
    parser.add_argument("--model-name", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--model-revision", default="c9745ed1d9f207416be6d2e6f8de32d1f16199bf")
    parser.add_argument("--dimensions", type=int, default=384)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--cache", default="workspace/cache/experience_embeddings.sqlite3")
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="+",
        default=[0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80],
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        help="Defaults to 5 for L0 and 3 for L1.",
    )
    parser.add_argument(
        "--min-records",
        type=int,
        help=(
            f"Readiness override; defaults to {L0_DEFAULT_MIN_RECORDS} for L0 and "
            f"{L1_DEFAULT_MIN_RECORDS} for L1. The L1 default is only a minimum "
            "analyzable sample, not a sufficiency claim."
        ),
    )
    parser.add_argument(
        "--min-positive-pairs",
        type=int,
        help=(
            f"Same-family pair readiness override; defaults to "
            f"{L0_DEFAULT_MIN_POSITIVE_PAIRS} for L0 and "
            f"{L1_DEFAULT_MIN_POSITIVE_PAIRS} for L1."
        ),
    )
    parser.add_argument(
        "--min-negative-pairs",
        type=int,
        help=(
            f"Different-family pair readiness override; defaults to "
            f"{L0_DEFAULT_MIN_NEGATIVE_PAIRS} for L0 and "
            f"{L1_DEFAULT_MIN_NEGATIVE_PAIRS} for L1."
        ),
    )
    parser.add_argument(
        "--hard-constraint-fields",
        nargs="+",
        default=list(DEFAULT_HARD_CONSTRAINT_FIELDS),
        help="Hard metadata fields; must match the formal runtime configuration.",
    )
    parser.add_argument(
        "--soft-constraint-fields",
        nargs="*",
        default=list(DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS),
        help=(
            "Soft metadata fields; must match runtime exactly. If task_family is "
            "included, the report flags its circular use as both proxy label and score feature."
        ),
    )
    parser.add_argument(
        "--disable-metadata-constraints",
        action="store_true",
        help="Disable metadata scoring only when the formal runtime does the same.",
    )
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    common = {
        "hierarchy_path": args.experiences,
        "split_manifest_path": args.split_manifest,
        "split_name": args.split_name,
        "level": args.level,
        "thresholds": args.thresholds,
        "min_cluster_size": args.min_cluster_size,
        "min_records": args.min_records,
        "min_positive_pairs": args.min_positive_pairs,
        "min_negative_pairs": args.min_negative_pairs,
        "use_metadata_constraints": not args.disable_metadata_constraints,
        "hard_constraint_fields": args.hard_constraint_fields,
        "soft_constraint_fields": args.soft_constraint_fields,
    }
    # Readiness runs before model construction, so old/incomplete data reports
    # waiting_for_data without importing sentence-transformers or downloading.
    try:
        report = calibrate_training_level(embedding_provider=None, **common)
    except ValueError as error:
        if "embedding_provider is required" not in str(error):
            raise
        if args.provider == "hashing":
            provider = HashingEmbeddingProvider(seed=42)
        else:
            provider = SentenceTransformerEmbeddingProvider(
                model_name=args.model_name,
                model_revision=args.model_revision,
                expected_dimensions=args.dimensions,
                cache_path=args.cache,
                device=args.device,
                batch_size=args.batch_size,
                local_files_only=not args.allow_model_download,
                random_seed=42,
            )
        report = calibrate_training_level(embedding_provider=provider, **common)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        if output.exists():
            raise FileExistsError(f"Refusing to overwrite calibration report: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
