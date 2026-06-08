"""
Benchmark 专属结果查看工具（SkillsBench / LiveCodeBench）

用法 / Usage:
  # 自动从 exp_id 推断 benchmark 类型
  python scripts/utils/view_benchmark_results.py -e skillsbench_baseline_eval
  python scripts/utils/view_benchmark_results.py -e lcb_baseline_eval

  # 显式指定 benchmark
  python scripts/utils/view_benchmark_results.py -e exp_id --benchmark skillsbench
  python scripts/utils/view_benchmark_results.py -e exp_id --benchmark lcb

  # 对比多个实验
  python scripts/utils/view_benchmark_results.py -e skillsbench_baseline_eval skillsbench_with_skills_eval
  python scripts/utils/view_benchmark_results.py -e lcb_baseline_eval lcb_practice_eval

  # 显示每个任务/题目的详细结果
  python scripts/utils/view_benchmark_results.py -e exp_id --detailed

  # 只显示失败的任务/题目
  python scripts/utils/view_benchmark_results.py -e exp_id --failed

  # SkillsBench: 对比官方榜单排名
  python scripts/utils/view_benchmark_results.py -e exp_id --leaderboard

  # 导出为 JSON
  python scripts/utils/view_benchmark_results.py -e exp_id --export results.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlmodel import select
from utu.db import EvaluationSample
from utu.utils import SQLModelUtils


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_meta(sample: EvaluationSample) -> dict:
    meta = sample.meta or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    return meta


def _load_samples(session, exp_id: str) -> list[EvaluationSample]:
    return list(session.exec(
        select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
    ))


def export_results(exp_ids: list[str], output_path: str, calc_fn) -> None:
    all_data = {}
    with SQLModelUtils.create_session() as session:
        for eid in exp_ids:
            samples = _load_samples(session, eid)
            if samples:
                all_data[eid] = calc_fn(samples)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Exported to: {output_path}")


def _detect_benchmark(exp_ids: list[str]) -> str:
    """Guess benchmark from experiment IDs."""
    joined = " ".join(exp_ids).lower()
    if "lcb" in joined or "livecodebench" in joined or "livecode" in joined:
        return "lcb"
    return "skillsbench"


# ===========================================================================
# SkillsBench
# ===========================================================================

LEADERBOARD = {
    "With Skills": {
        "Gemini CLI + Gemini 3 Flash":  0.487,
        "Claude Code + Opus 4.5":       0.453,
        "Codex + GPT-5.2":              0.447,
        "Claude Code + Opus 4.6":       0.445,
        "Gemini CLI + Gemini 3 Pro":    0.412,
        "Claude Code + Sonnet 4.5":     0.318,
        "Claude Code + Haiku 4.5":      0.277,
    },
    "Without Skills": {
        "Gemini CLI + Gemini 3 Flash":  0.313,
        "Codex + GPT-5.2":              0.306,
        "Claude Code + Opus 4.6":       0.306,
        "Gemini CLI + Gemini 3 Pro":    0.276,
        "Claude Code + Opus 4.5":       0.220,
        "Claude Code + Sonnet 4.5":     0.173,
        "Claude Code + Haiku 4.5":      0.110,
    },
}


def _calc_stats_skillsbench(samples: list[EvaluationSample]) -> dict | None:
    if not samples:
        return None
    rewards, by_domain, by_difficulty, tasks = [], defaultdict(list), defaultdict(list), []
    for s in samples:
        r = float(s.reward) if s.reward is not None else 0.0
        rewards.append(r)
        meta = _parse_meta(s)
        domain     = meta.get("domain", "unknown")
        difficulty = meta.get("difficulty", "unknown")
        task_id    = meta.get("task_id", s.dataset_index or "?")
        by_domain[domain].append(r)
        by_difficulty[difficulty].append(r)
        tasks.append({
            "task_id": task_id, "domain": domain, "difficulty": difficulty,
            "reward": r, "passed": r >= 1.0, "time_cost": s.time_cost,
        })
    passed = sum(1 for r in rewards if r >= 1.0)
    return {
        "total": len(samples), "passed": passed,
        "pass_rate": passed / len(samples),
        "mean_reward": mean(rewards),
        "by_domain": {
            d: {"count": len(v), "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in v),
                "mean_reward": round(mean(v), 4)}
            for d, v in sorted(by_domain.items())
        },
        "by_difficulty": {
            d: {"count": len(v), "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in v),
                "mean_reward": round(mean(v), 4)}
            for d, v in sorted(by_difficulty.items())
        },
        "tasks": sorted(tasks, key=lambda t: (-t["reward"], t["task_id"])),
    }


def _view_single_skillsbench(exp_id: str, detailed: bool, show_failed: bool) -> dict | None:
    with SQLModelUtils.create_session() as session:
        samples = _load_samples(session, exp_id)
    if not samples:
        print(f"\n  No data found for: {exp_id}\n")
        return None
    stats = _calc_stats_skillsbench(samples)
    W = 78
    print(f"\n{'=' * W}")
    print(f"  SkillsBench Results: {exp_id}")
    print(f"{'=' * W}")
    print(f"  Tasks evaluated : {stats['total']}")
    print(f"  Tasks passed    : {stats['passed']}")
    print(f"  Pass rate       : {stats['pass_rate']:.1%}")
    print(f"  Mean reward     : {stats['mean_reward']:.4f}")

    print(f"\n  {'Domain':<35} {'Tasks':>6} {'Pass%':>8} {'Reward':>8}")
    print(f"  {'-' * 60}")
    for domain, info in stats["by_domain"].items():
        print(f"  {domain:<35} {info['count']:>6} {info['pass_rate']:>7.1%} {info['mean_reward']:>8.4f}")

    print(f"\n  {'Difficulty':<35} {'Tasks':>6} {'Pass%':>8} {'Reward':>8}")
    print(f"  {'-' * 60}")
    for diff, info in stats["by_difficulty"].items():
        print(f"  {diff:<35} {info['count']:>6} {info['pass_rate']:>7.1%} {info['mean_reward']:>8.4f}")

    if detailed or show_failed:
        tasks = [t for t in stats["tasks"] if not t["passed"]] if show_failed else stats["tasks"]
        label = f"{'Failed' if show_failed else 'All'} tasks ({len(tasks)})"
        print(f"\n  {label}:")
        print(f"  {'Task ID':<45} {'Domain':<20} {'Diff':<8} {'Reward':>7} {'Time':>7}")
        print(f"  {'-' * 90}")
        for t in tasks:
            ts = f"{t['time_cost']:.0f}s" if t["time_cost"] else "N/A"
            mark = "PASS" if t["passed"] else ""
            print(f"  {t['task_id']:<45} {t['domain']:<20} {t['difficulty']:<8} {t['reward']:>7.2f} {ts:>7}  {mark}")
    print(f"{'=' * W}\n")
    return stats


def _compare_skillsbench(exp_ids: list[str]) -> dict:
    all_stats = {}
    with SQLModelUtils.create_session() as session:
        for eid in exp_ids:
            s = _load_samples(session, eid)
            if not s:
                print(f"  Warning: no data for {eid}")
                continue
            all_stats[eid] = _calc_stats_skillsbench(s)

    if len(all_stats) < 2:
        print("  Need ≥2 experiments to compare.")
        return all_stats

    ids   = list(all_stats.keys())
    col_w = max(22, max(len(e) for e in ids) + 2)
    W     = 30 + col_w * len(ids)

    print(f"\n{'=' * W}")
    print(f"  SkillsBench — Experiment Comparison")
    print(f"{'=' * W}")
    header = f"  {'Metric':<28}" + "".join(f" {e:>{col_w}}" for e in ids)
    print(header)
    print(f"  {'-' * (W - 2)}")
    for label, fn in [("Tasks", lambda s: s["total"]), ("Passed", lambda s: s["passed"]),
                      ("Pass rate", lambda s: f"{s['pass_rate']:.1%}"),
                      ("Mean reward", lambda s: f"{s['mean_reward']:.4f}")]:
        print(f"  {label:<28}" + "".join(f" {fn(all_stats[e]):>{col_w}}" for e in ids))

    baseline = all_stats[ids[0]]
    row = f"  {'Δ vs ' + ids[0][:18]:<28}"
    for eid in ids:
        if eid == ids[0]:
            row += f" {'(baseline)':>{col_w}}"
        else:
            d = all_stats[eid]["pass_rate"] - baseline["pass_rate"]
            row += f" {('+' if d >= 0 else '') + f'{d:.1%}':>{col_w}}"
    print(row)

    for breakdown, key in [("Per-domain", "by_domain"), ("Per-difficulty", "by_difficulty")]:
        all_keys = set()
        for s in all_stats.values():
            all_keys |= set(s[key].keys())
        print(f"\n  {breakdown} pass rate:")
        print(f"  {'':28}" + "".join(f" {e[-col_w:]:>{col_w}}" for e in ids))
        print(f"  {'-' * (W - 2)}")
        for k in sorted(all_keys):
            row = f"  {k:<28}"
            for eid in ids:
                info = all_stats[eid][key].get(k)
                row += f" {info['pass_rate']:>{col_w}.1%}" if info else f" {'N/A':>{col_w}}"
            print(row)

    first_tasks = {t["task_id"]: t for t in all_stats[ids[0]]["tasks"]}
    last_tasks  = {t["task_id"]: t for t in all_stats[ids[-1]]["tasks"]}
    common = set(first_tasks) & set(last_tasks)
    gained = sorted(t for t in common if not first_tasks[t]["passed"] and last_tasks[t]["passed"])
    lost   = sorted(t for t in common if first_tasks[t]["passed"]     and not last_tasks[t]["passed"])
    if gained:
        print(f"\n  Gained ({len(gained)} tasks now passing):")
        for tid in gained:
            print(f"    + {tid:<40} [{last_tasks[tid]['domain']}]")
    if lost:
        print(f"\n  Lost ({len(lost)} tasks now failing):")
        for tid in lost:
            print(f"    - {tid:<40} [{first_tasks[tid]['domain']}]")

    print(f"\n{'=' * W}\n")
    return all_stats


def _show_leaderboard(exp_id: str, stats: dict) -> None:
    if not stats:
        return
    board_key = "With Skills" if "with_skills" in exp_id else "Without Skills"
    board = LEADERBOARD.get(board_key, {})
    entries = list(board.items()) + [(f">> {exp_id}", stats["pass_rate"])]
    entries.sort(key=lambda x: -x[1])
    print(f"  Official Leaderboard Comparison ({board_key}):")
    print(f"  {'#':<4} {'Agent + Model':<45} {'Pass Rate':>10}")
    print(f"  {'-' * 62}")
    for i, (name, rate) in enumerate(entries, 1):
        marker = "  <<" if name.startswith(">>") else ""
        print(f"  {i:<4} {name.lstrip('> '):<45} {rate:>9.1%}{marker}")
    print()


# ===========================================================================
# LiveCodeBench
# ===========================================================================

def _calc_stats_lcb(samples: list[EvaluationSample]) -> dict | None:
    if not samples:
        return None
    rewards, by_difficulty, by_platform, problems = [], defaultdict(list), defaultdict(list), []
    for s in samples:
        r = float(s.reward) if s.reward is not None else 0.0
        rewards.append(r)
        meta = _parse_meta(s)
        difficulty = meta.get("difficulty", "unknown")
        platform   = meta.get("platform",   "unknown")
        title      = meta.get("question_title", s.dataset_index or "?")
        by_difficulty[difficulty].append(r)
        by_platform[platform].append(r)
        problems.append({
            "title": title, "difficulty": difficulty, "platform": platform,
            "reward": r, "passed": r >= 1.0, "time_cost": s.time_cost,
        })
    passed = sum(1 for r in rewards if r >= 1.0)
    return {
        "total": len(samples), "passed": passed,
        "pass_rate": passed / len(samples),
        "mean_reward": mean(rewards),
        "by_difficulty": {
            d: {"count": len(v), "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in v),
                "mean_reward": round(mean(v), 4)}
            for d, v in sorted(by_difficulty.items())
        },
        "by_platform": {
            p: {"count": len(v), "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in v),
                "mean_reward": round(mean(v), 4)}
            for p, v in sorted(by_platform.items())
        },
        "problems": sorted(problems, key=lambda t: (-t["reward"], t["title"])),
    }


def _view_single_lcb(exp_id: str, detailed: bool, show_failed: bool) -> dict | None:
    with SQLModelUtils.create_session() as session:
        samples = _load_samples(session, exp_id)
    if not samples:
        print(f"\n  No data found for: '{exp_id}'\n")
        return None
    stats = _calc_stats_lcb(samples)
    W = 70
    print(f"\n{'=' * W}")
    print(f"  LiveCodeBench Results: {exp_id}")
    print(f"{'=' * W}")
    print(f"  Problems evaluated : {stats['total']}")
    print(f"  Problems passed    : {stats['passed']}")
    print(f"  Pass rate  (pass@1): {stats['pass_rate']:.1%}")
    print(f"  Mean reward        : {stats['mean_reward']:.4f}")

    for label, key in [("Difficulty", "by_difficulty"), ("Platform", "by_platform")]:
        print(f"\n  {label:<20} {'Count':>6} {'Pass%':>8} {'Reward':>8}")
        print(f"  {'-' * 46}")
        for k, info in stats[key].items():
            print(f"  {k:<20} {info['count']:>6} {info['pass_rate']:>7.1%} {info['mean_reward']:>8.4f}")

    if detailed or show_failed:
        probs = [p for p in stats["problems"] if not p["passed"]] if show_failed else stats["problems"]
        label = f"{'Failed' if show_failed else 'All'} problems ({len(probs)})"
        print(f"\n  {label}:")
        print(f"  {'Title':<45} {'Diff':<8} {'Plat':<12} {'Reward':>7}")
        print(f"  {'-' * 76}")
        for p in probs:
            mark = "✓" if p["passed"] else " "
            print(f"  {mark} {str(p['title'])[:44]:<44} {p['difficulty']:<8} {p['platform']:<12} {p['reward']:>7.3f}")
    print(f"{'=' * W}\n")
    return stats


def _compare_lcb(exp_ids: list[str]) -> dict:
    all_stats = {}
    with SQLModelUtils.create_session() as session:
        for eid in exp_ids:
            s = _load_samples(session, eid)
            if not s:
                print(f"  Warning: no data for '{eid}'")
                continue
            all_stats[eid] = _calc_stats_lcb(s)

    if len(all_stats) < 2:
        print("  Need ≥2 experiments to compare.")
        return all_stats

    ids   = list(all_stats.keys())
    col_w = max(20, max(len(e) for e in ids) + 2)
    W     = 30 + col_w * len(ids)

    print(f"\n{'=' * W}")
    print(f"  LiveCodeBench — Experiment Comparison")
    print(f"{'=' * W}")
    header = f"  {'Metric':<28}" + "".join(f" {e:>{col_w}}" for e in ids)
    print(header)
    print(f"  {'-' * (W - 2)}")
    for label, fn in [("Problems", lambda s: s["total"]), ("Passed", lambda s: s["passed"]),
                      ("Pass rate", lambda s: f"{s['pass_rate']:.1%}"),
                      ("Mean reward", lambda s: f"{s['mean_reward']:.4f}")]:
        print(f"  {label:<28}" + "".join(f" {fn(all_stats[e]):>{col_w}}" for e in ids))

    baseline_rate = all_stats[ids[0]]["pass_rate"]
    row = f"  {'Δ vs ' + ids[0][:18]:<28}"
    for eid in ids:
        if eid == ids[0]:
            row += f" {'(baseline)':>{col_w}}"
        else:
            d = all_stats[eid]["pass_rate"] - baseline_rate
            row += f" {('+' if d >= 0 else '') + f'{d:.1%}':>{col_w}}"
    print(row)

    for label, key in [("Per-difficulty", "by_difficulty"), ("Per-platform", "by_platform")]:
        all_keys = set()
        for s in all_stats.values():
            all_keys |= set(s[key].keys())
        print(f"\n  {label} pass rate:")
        print(f"  {'':28}" + "".join(f" {e[-col_w:]:>{col_w}}" for e in ids))
        print(f"  {'-' * (W - 2)}")
        for k in sorted(all_keys):
            row = f"  {k:<28}"
            for eid in ids:
                info = all_stats[eid][key].get(k)
                row += f" {info['pass_rate']:>{col_w}.1%}" if info else f" {'N/A':>{col_w}}"
            print(row)

    first_map = {p["title"]: p for p in all_stats[ids[0]]["problems"]}
    last_map  = {p["title"]: p for p in all_stats[ids[-1]]["problems"]}
    common = set(first_map) & set(last_map)
    gained = sorted(t for t in common if not first_map[t]["passed"] and last_map[t]["passed"])
    lost   = sorted(t for t in common if first_map[t]["passed"]     and not last_map[t]["passed"])
    if gained:
        print(f"\n  Gained ({len(gained)} problems now passing):")
        for t in gained:
            print(f"    + [{last_map[t]['difficulty']:<6}] {t}")
    if lost:
        print(f"\n  Lost ({len(lost)} problems now failing):")
        for t in lost:
            print(f"    - [{first_map[t]['difficulty']:<6}] {t}")

    print(f"\n{'=' * W}\n")
    return all_stats


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark 专属结果查看（SkillsBench / LiveCodeBench）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-e", "--exp_ids", nargs="+", metavar="EXP_ID",
        help="Experiment ID(s). One = view, two+ = compare.",
    )
    parser.add_argument(
        "--benchmark", "-b", choices=["skillsbench", "lcb"], default=None,
        help="Benchmark 类型（不指定时从 exp_id 自动推断）",
    )
    parser.add_argument(
        "-d", "--detailed", action="store_true",
        help="显示每个任务/题目的详细结果",
    )
    parser.add_argument(
        "--failed", action="store_true",
        help="只显示失败的任务/题目",
    )
    parser.add_argument(
        "--leaderboard", action="store_true",
        help="（SkillsBench）对比官方榜单排名",
    )
    parser.add_argument(
        "--export", type=str, metavar="FILE",
        help="导出结果为 JSON 文件",
    )
    args = parser.parse_args()

    if not args.exp_ids:
        parser.print_help()
        return

    benchmark = args.benchmark or _detect_benchmark(args.exp_ids)

    if benchmark == "skillsbench":
        calc_fn       = _calc_stats_skillsbench
        view_single   = _view_single_skillsbench
        compare_fn    = _compare_skillsbench
    else:
        calc_fn       = _calc_stats_lcb
        view_single   = _view_single_lcb
        compare_fn    = _compare_lcb

    if args.export:
        export_results(args.exp_ids, args.export, calc_fn)
        return

    if len(args.exp_ids) == 1:
        stats = view_single(args.exp_ids[0], detailed=args.detailed, show_failed=args.failed)
        if args.leaderboard and benchmark == "skillsbench" and stats:
            _show_leaderboard(args.exp_ids[0], stats)
    else:
        all_stats = compare_fn(args.exp_ids)
        if args.leaderboard and benchmark == "skillsbench" and all_stats:
            for eid, stats in all_stats.items():
                _show_leaderboard(eid, stats)


if __name__ == "__main__":
    main()
