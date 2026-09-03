#!/usr/bin/env python3
"""Offline, train-only threshold calibration for hierarchical clustering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from utu.practice.clustering_calibration import calibrate_training_l0
from utu.practice.experience_clusterer import (
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
    parser.add_argument("--min-cluster-size", type=int, default=5)
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    common = {
        "hierarchy_path": args.experiences,
        "split_manifest_path": args.split_manifest,
        "split_name": args.split_name,
        "thresholds": args.thresholds,
        "min_cluster_size": args.min_cluster_size,
    }
    # Readiness runs before model construction, so old/incomplete data reports
    # waiting_for_data without importing sentence-transformers or downloading.
    try:
        report = calibrate_training_l0(embedding_provider=None, **common)
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
        report = calibrate_training_l0(embedding_provider=provider, **common)
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
