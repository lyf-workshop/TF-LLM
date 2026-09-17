#!/usr/bin/env python3
"""Build one strict paired report for all three hierarchy conditions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from utu.practice.hierarchical_ablation import build_three_group_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequential-hierarchy", required=True)
    parser.add_argument("--clustered-hierarchy", required=True)
    parser.add_argument("--sequential-audit")
    parser.add_argument("--clustered-audit")
    parser.add_argument("--no-experience-eval")
    parser.add_argument("--sequential-eval")
    parser.add_argument("--clustered-eval")
    parser.add_argument("--no-experience-exp-id")
    parser.add_argument("--sequential-exp-id")
    parser.add_argument("--clustered-exp-id")
    parser.add_argument(
        "--split-manifest",
        default=None,
    )
    parser.add_argument("--split-name", default=None)
    parser.add_argument(
        "--experiment-protocol",
        help="Signed protocol emitted by run_hierarchical_ablation.py (required for DAPO/AIME).",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    paths = {
        "no_experience": args.no_experience_eval,
        "sequential": args.sequential_eval,
        "clustered": args.clustered_eval,
    }
    exp_ids = {
        "no_experience": args.no_experience_exp_id,
        "sequential": args.sequential_exp_id,
        "clustered": args.clustered_exp_id,
    }
    if any(not (paths[name] or exp_ids[name]) for name in paths):
        parser.error("provide an evaluation file or experiment ID for every one of the three conditions")
    if args.experiment_protocol and (args.split_manifest or args.split_name):
        parser.error("use either --experiment-protocol or --split-manifest/--split-name")
    if not args.experiment_protocol and not (args.split_manifest and args.split_name):
        parser.error("provide --experiment-protocol or both --split-manifest and --split-name")

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite ablation report: {output}")
    report = build_three_group_report(
        evaluation_paths=paths,
        evaluation_exp_ids=exp_ids,
        sequential_hierarchy=args.sequential_hierarchy,
        clustered_hierarchy=args.clustered_hierarchy,
        split_manifest_path=args.split_manifest,
        split_name=args.split_name,
        experiment_protocol_path=args.experiment_protocol,
        sequential_audit=args.sequential_audit,
        clustered_audit=args.clustered_audit,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
