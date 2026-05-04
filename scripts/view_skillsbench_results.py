#!/usr/bin/env python3
"""
SkillsBench 评估结果查看与对比工具

Usage:
    # 查看单个实验
    python scripts/view_skillsbench_results.py -e skillsbench_baseline_eval

    # 对比多个实验
    python scripts/view_skillsbench_results.py -e skillsbench_baseline_eval skillsbench_with_skills_eval

    # 显示每个任务的详细结果
    python scripts/view_skillsbench_results.py -e skillsbench_baseline_eval --detailed

    # 只看失败的任务
    python scripts/view_skillsbench_results.py -e skillsbench_baseline_eval --failed

    # 导出为 JSON
    python scripts/view_skillsbench_results.py -e skillsbench_baseline_eval --export results.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import select
from utu.db import EvaluationSample
from utu.utils import SQLModelUtils

# SkillsBench 官方榜单数据 (2026-04, 84 tasks × 5 trials)
LEADERBOARD = {
    "With Skills": {
        "Gemini CLI + Gemini 3 Flash":   0.487,
        "Claude Code + Opus 4.5":        0.453,
        "Codex + GPT-5.2":              0.447,
        "Claude Code + Opus 4.6":        0.445,
        "Gemini CLI + Gemini 3 Pro":     0.412,
        "Claude Code + Sonnet 4.5":      0.318,
        "Claude Code + Haiku 4.5":       0.277,
    },
    "Without Skills": {
        "Gemini CLI + Gemini 3 Flash":   0.313,
        "Codex + GPT-5.2":              0.306,
        "Claude Code + Opus 4.6":        0.306,
        "Gemini CLI + Gemini 3 Pro":     0.276,
        "Claude Code + Opus 4.5":        0.220,
        "Claude Code + Sonnet 4.5":      0.173,
        "Claude Code + Haiku 4.5":       0.110,
    },
}


def _parse_meta(sample):
    meta = sample.meta or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    return meta


def _load_samples(session, exp_id):
    return list(session.exec(
        select(EvaluationSample)
        .where(EvaluationSample.exp_id == exp_id)
    ))


def _calc_stats(samples):
    """Calculate comprehensive stats for a set of samples."""
    if not samples:
        return None

    rewards = []
    by_domain = defaultdict(list)
    by_difficulty = defaultdict(list)
    task_results = []

    for s in samples:
        r = float(s.reward) if s.reward is not None else 0.0
        rewards.append(r)
        meta = _parse_meta(s)

        domain = meta.get("domain", "unknown")
        difficulty = meta.get("difficulty", "unknown")
        task_id = meta.get("task_id", s.dataset_index or "?")

        by_domain[domain].append(r)
        by_difficulty[difficulty].append(r)
        task_results.append({
            "task_id": task_id,
            "domain": domain,
            "difficulty": difficulty,
            "reward": r,
            "passed": r >= 1.0,
            "time_cost": s.time_cost,
            "error": (s.response or "")[:200] if r == 0.0 and s.response and "error" in (s.response or "").lower() else "",
        })

    passed = sum(1 for r in rewards if r >= 1.0)
    return {
        "total": len(samples),
        "passed": passed,
        "pass_rate": passed / len(samples) if samples else 0,
        "mean_reward": mean(rewards),
        "by_domain": {d: {"count": len(v), "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in v), "mean_reward": round(mean(v), 4)} for d, v in sorted(by_domain.items())},
        "by_difficulty": {d: {"count": len(v), "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in v), "mean_reward": round(mean(v), 4)} for d, v in sorted(by_difficulty.items())},
        "tasks": sorted(task_results, key=lambda t: (-t["reward"], t["task_id"])),
    }


def view_single(exp_id, detailed=False, show_failed=False):
    """View results for a single experiment."""
    with SQLModelUtils.create_session() as session:
        samples = _load_samples(session, exp_id)

    if not samples:
        print(f"\n  No data found for experiment: {exp_id}\n")
        return None

    stats = _calc_stats(samples)

    print(f"\n{'=' * 78}")
    print(f"  SkillsBench Results: {exp_id}")
    print(f"{'=' * 78}")
    print(f"  Tasks evaluated : {stats['total']}")
    print(f"  Tasks passed    : {stats['passed']}")
    print(f"  Pass rate       : {stats['pass_rate']:.1%}")
    print(f"  Mean reward     : {stats['mean_reward']:.4f}")

    # Domain breakdown
    print(f"\n  {'Domain':<35} {'Tasks':>6} {'Pass%':>8} {'Reward':>8}")
    print(f"  {'-' * 60}")
    for domain, info in stats["by_domain"].items():
        print(f"  {domain:<35} {info['count']:>6} {info['pass_rate']:>7.1%} {info['mean_reward']:>8.4f}")

    # Difficulty breakdown
    print(f"\n  {'Difficulty':<35} {'Tasks':>6} {'Pass%':>8} {'Reward':>8}")
    print(f"  {'-' * 60}")
    for diff, info in stats["by_difficulty"].items():
        print(f"  {diff:<35} {info['count']:>6} {info['pass_rate']:>7.1%} {info['mean_reward']:>8.4f}")

    # Task-level details
    if detailed or show_failed:
        tasks = stats["tasks"]
        if show_failed:
            tasks = [t for t in tasks if not t["passed"]]
            label = "Failed tasks"
        else:
            label = "All tasks"

        print(f"\n  {label} ({len(tasks)}):")
        print(f"  {'Task ID':<45} {'Domain':<20} {'Diff':<8} {'Reward':>7} {'Time':>7}")
        print(f"  {'-' * 90}")
        for t in tasks:
            time_str = f"{t['time_cost']:.0f}s" if t["time_cost"] else "N/A"
            marker = "PASS" if t["passed"] else ""
            print(f"  {t['task_id']:<45} {t['domain']:<20} {t['difficulty']:<8} {t['reward']:>7.2f} {time_str:>7}  {marker}")

    print(f"{'=' * 78}\n")
    return stats


def compare_experiments(exp_ids):
    """Compare multiple experiments side by side."""
    all_stats = {}
    with SQLModelUtils.create_session() as session:
        for eid in exp_ids:
            samples = _load_samples(session, eid)
            if not samples:
                print(f"  Warning: no data for {eid}")
                continue
            all_stats[eid] = _calc_stats(samples)

    if len(all_stats) < 2:
        print("  Need at least 2 experiments to compare.")
        return

    ids = list(all_stats.keys())
    col_w = max(22, max(len(e) for e in ids) + 2)

    print(f"\n{'=' * (30 + col_w * len(ids))}")
    print(f"  SkillsBench Experiment Comparison")
    print(f"{'=' * (30 + col_w * len(ids))}")

    # Header
    header = f"  {'Metric':<28}"
    for eid in ids:
        header += f" {eid:>{col_w}}"
    print(header)
    print(f"  {'-' * (26 + col_w * len(ids))}")

    # Overall
    row = f"  {'Tasks':<28}"
    for eid in ids:
        row += f" {all_stats[eid]['total']:>{col_w}}"
    print(row)

    row = f"  {'Passed':<28}"
    for eid in ids:
        row += f" {all_stats[eid]['passed']:>{col_w}}"
    print(row)

    row = f"  {'Pass rate':<28}"
    for eid in ids:
        row += f" {all_stats[eid]['pass_rate']:>{col_w}.1%}"
    print(row)

    row = f"  {'Mean reward':<28}"
    for eid in ids:
        row += f" {all_stats[eid]['mean_reward']:>{col_w}.4f}"
    print(row)

    # Improvement over first experiment
    baseline = all_stats[ids[0]]
    print(f"\n  {'Improvement vs ' + ids[0]:<28}", end="")
    for eid in ids:
        if eid == ids[0]:
            print(f" {'(baseline)':>{col_w}}", end="")
        else:
            delta = all_stats[eid]["pass_rate"] - baseline["pass_rate"]
            print(f" {delta:>{col_w - 2}.1%}pp", end="")
    print()

    # Domain breakdown comparison
    all_domains = set()
    for s in all_stats.values():
        all_domains |= set(s["by_domain"].keys())

    print(f"\n  Per-domain pass rate:")
    header = f"  {'Domain':<28}"
    for eid in ids:
        header += f" {eid[-col_w:]:>{col_w}}"
    print(header)
    print(f"  {'-' * (26 + col_w * len(ids))}")

    for domain in sorted(all_domains):
        row = f"  {domain:<28}"
        for eid in ids:
            info = all_stats[eid]["by_domain"].get(domain)
            if info:
                row += f" {info['pass_rate']:>{col_w}.1%}"
            else:
                row += f" {'N/A':>{col_w}}"
        print(row)

    # Difficulty breakdown
    all_diffs = set()
    for s in all_stats.values():
        all_diffs |= set(s["by_difficulty"].keys())

    print(f"\n  Per-difficulty pass rate:")
    header = f"  {'Difficulty':<28}"
    for eid in ids:
        header += f" {eid[-col_w:]:>{col_w}}"
    print(header)
    print(f"  {'-' * (26 + col_w * len(ids))}")

    for diff in sorted(all_diffs):
        row = f"  {diff:<28}"
        for eid in ids:
            info = all_stats[eid]["by_difficulty"].get(diff)
            if info:
                row += f" {info['pass_rate']:>{col_w}.1%}"
            else:
                row += f" {'N/A':>{col_w}}"
        print(row)

    # Per-task diff between first and last experiment
    first, last = ids[0], ids[-1]
    first_tasks = {t["task_id"]: t for t in all_stats[first]["tasks"]}
    last_tasks = {t["task_id"]: t for t in all_stats[last]["tasks"]}
    common = set(first_tasks) & set(last_tasks)

    gained = [tid for tid in common if not first_tasks[tid]["passed"] and last_tasks[tid]["passed"]]
    lost = [tid for tid in common if first_tasks[tid]["passed"] and not last_tasks[tid]["passed"]]

    if gained:
        print(f"\n  Gained ({len(gained)} tasks now passing):")
        for tid in sorted(gained):
            d = last_tasks[tid]["domain"]
            print(f"    + {tid:<40} [{d}]")
    if lost:
        print(f"\n  Lost ({len(lost)} tasks now failing):")
        for tid in sorted(lost):
            d = first_tasks[tid]["domain"]
            print(f"    - {tid:<40} [{d}]")

    print(f"\n{'=' * (30 + col_w * len(ids))}\n")
    return all_stats


def show_leaderboard(exp_id, stats):
    """Show where the experiment ranks vs the official leaderboard."""
    if stats is None:
        return

    my_rate = stats["pass_rate"]

    # Determine which leaderboard column to compare against
    # Use "Without Skills" unless exp_id contains "with_skills"
    if "with_skills" in exp_id:
        board_key = "With Skills"
    else:
        board_key = "Without Skills"

    board = LEADERBOARD.get(board_key, {})
    if not board:
        return

    entries = [(name, rate) for name, rate in board.items()]
    entries.append((f">> {exp_id}", my_rate))
    entries.sort(key=lambda x: -x[1])

    print(f"  Official Leaderboard Comparison ({board_key}):")
    print(f"  {'#':<4} {'Agent + Model':<45} {'Pass Rate':>10}")
    print(f"  {'-' * 62}")
    for i, (name, rate) in enumerate(entries, 1):
        marker = "  <<" if name.startswith(">>") else ""
        display = name.lstrip("> ")
        print(f"  {i:<4} {display:<45} {rate:>9.1%}{marker}")
    print()


def export_results(exp_ids, output_path):
    """Export results as JSON."""
    all_data = {}
    with SQLModelUtils.create_session() as session:
        for eid in exp_ids:
            samples = _load_samples(session, eid)
            if samples:
                all_data[eid] = _calc_stats(samples)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"  Exported to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="SkillsBench 评估结果查看与对比",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-e", "--exp_ids", nargs="+", metavar="EXP_ID",
        help="Experiment ID(s). One = view, two+ = compare.",
    )
    parser.add_argument(
        "-d", "--detailed", action="store_true",
        help="Show per-task results",
    )
    parser.add_argument(
        "--failed", action="store_true",
        help="Only show failed tasks (implies --detailed)",
    )
    parser.add_argument(
        "--leaderboard", action="store_true",
        help="Show ranking vs official SkillsBench leaderboard",
    )
    parser.add_argument(
        "--export", type=str, metavar="FILE",
        help="Export results to JSON file",
    )

    args = parser.parse_args()

    if not args.exp_ids:
        args.exp_ids = [
            "skillsbench_baseline_eval",
            "skillsbench_with_skills_eval",
            "skillsbench_practice_eval",
        ]
        print("  (No experiments specified, trying default SkillsBench exp IDs)")

    if args.export:
        export_results(args.exp_ids, args.export)
        return

    if len(args.exp_ids) == 1:
        stats = view_single(args.exp_ids[0], detailed=args.detailed, show_failed=args.failed)
        if args.leaderboard:
            show_leaderboard(args.exp_ids[0], stats)
    else:
        all_stats = compare_experiments(args.exp_ids)
        if args.leaderboard and all_stats:
            for eid, stats in all_stats.items():
                show_leaderboard(eid, stats)


if __name__ == "__main__":
    main()
