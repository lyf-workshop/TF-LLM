"""
通用评估结果查看工具（含 Training-Free GRPO 训练前后对比）

用法 / Usage:
  # 查看单个实验摘要
  python scripts/utils/view_results.py -e exp_id

  # 同时查看多个实验
  python scripts/utils/view_results.py -e exp1 exp2 exp3

  # 对比两个实验（基线 vs 训练后），显示 improved/regressed/unchanged
  python scripts/utils/view_results.py -e baseline practice --compare

  # 对比时显示 Pass@K 和变化题目详情
  python scripts/utils/view_results.py -e baseline practice --compare --detailed

  # 查看论文实验结果（AIME 2024/2025 默认对比）
  python scripts/utils/view_results.py --paper

  # 显示每题详细输出
  python scripts/utils/view_results.py -e exp_id --details

  # 只看失败的题目
  python scripts/utils/view_results.py -e exp_id --details --failed

  # 限制显示题目数
  python scripts/utils/view_results.py -e exp_id --details --limit 10

  # 列出数据库中所有实验
  python scripts/utils/view_results.py --list

  # 导出为 JSON
  python scripts/utils/view_results.py -e exp_id --export results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlmodel import select
from utu.db import EvaluationSample
from utu.db.eval_datapoint import DatasetSample
from utu.utils import SQLModelUtils


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _load_samples(session, exp_id: str) -> list[EvaluationSample]:
    return list(
        session.exec(
            select(EvaluationSample)
            .where(EvaluationSample.exp_id == exp_id)
            .order_by(EvaluationSample.dataset_index)
        )
    )


def _group_by_problem(samples: list[EvaluationSample]) -> dict[str, list[EvaluationSample]]:
    groups: dict[str, list[EvaluationSample]] = defaultdict(list)
    for s in samples:
        key = s.raw_question or s.question or ""
        groups[key].append(s)
    return groups


def _calc_pass_at_k(groups: dict[str, list], k: int, threshold: float = 0.5) -> float:
    passed = sum(
        1
        for slist in groups.values()
        if any(
            s.reward is not None and s.reward >= threshold
            for s in slist[:k]
        )
    )
    return passed / len(groups) if groups else 0.0


def _calc_stats(samples: list[EvaluationSample], threshold: float = 0.5) -> dict:
    total = len(samples)
    judged = [s for s in samples if s.stage == "judged"] or samples
    correct = sum(
        1 for s in samples
        if (s.correct is True) or (s.reward is not None and s.reward >= threshold)
    )
    rewards = [s.reward for s in samples if s.reward is not None]
    avg_reward = sum(rewards) / len(rewards) if rewards else 0.0
    groups = _group_by_problem(samples)
    pass_at_k = {k: _calc_pass_at_k(groups, k, threshold) for k in [1, 5, 10, 32]}

    return {
        "exp_id": samples[0].exp_id if samples else "",
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "avg_reward": avg_reward,
        "unique_questions": len(groups),
        "samples_per_question": total / len(groups) if groups else 0.0,
        "pass_at_k": pass_at_k,
    }


# ---------------------------------------------------------------------------
# Summary view (single / multiple experiments)
# ---------------------------------------------------------------------------

def view_summary(exp_ids: list[str], detailed: bool = False, threshold: float = 0.5) -> dict[str, dict]:
    results = {}
    with SQLModelUtils.create_session() as session:
        for exp_id in exp_ids:
            samples = _load_samples(session, exp_id)
            if not samples:
                print(f"  ⚠ 未找到实验: {exp_id}")
                continue
            stats = _calc_stats(samples, threshold)
            results[exp_id] = stats

            print(f"\n{'=' * 70}")
            print(f"实验结果: {exp_id}")
            print(f"{'=' * 70}")
            print(f"  总样本数     : {stats['total']}")
            print(f"  唯一问题数   : {stats['unique_questions']}")
            print(f"  每题采样数   : {stats['samples_per_question']:.1f}")
            print(f"  正确样本数   : {stats['correct']}")
            print(f"  准确率       : {stats['accuracy']:.2%}")
            print(f"  平均 Reward  : {stats['avg_reward']:.4f}")

            if detailed:
                print(f"\n  Pass@K 指标:")
                for k, rate in sorted(stats["pass_at_k"].items()):
                    if rate > 0 or k <= 5:
                        print(f"    Pass@{k}: {rate:.2%}")

    print()
    return results


# ---------------------------------------------------------------------------
# Comparison view (two experiments)
# ---------------------------------------------------------------------------

def view_compare(
    baseline_exp_id: str,
    practice_exp_id: str,
    threshold: float = 0.5,
    detailed: bool = False,
) -> None:
    with SQLModelUtils.create_session() as session:
        b_samples = _load_samples(session, baseline_exp_id)
        p_samples = _load_samples(session, practice_exp_id)

    if not b_samples:
        print(f"❌ 未找到 Baseline 数据: {baseline_exp_id}")
        return
    if not p_samples:
        print(f"❌ 未找到 Practice 数据: {practice_exp_id}")
        return

    b = _calc_stats(b_samples, threshold)
    p = _calc_stats(p_samples, threshold)

    print(f"\n{'=' * 70}")
    print("实验对比 (Baseline vs Practice)")
    print(f"{'=' * 70}")
    print(f"  Baseline : {baseline_exp_id}")
    print(f"  Practice : {practice_exp_id}")
    print()

    fmt = f"  {{:<22}} {{:>14}} {{:>14}} {{:>12}}"
    print(fmt.format("指标", "Baseline", "Practice", "变化"))
    print("  " + "-" * 64)
    print(fmt.format("总样本数", b["total"], p["total"], ""))
    print(fmt.format("正确样本数", b["correct"], p["correct"],
                     f"{p['correct'] - b['correct']:+d}"))
    print(fmt.format("准确率",
                     f"{b['accuracy']:.2%}", f"{p['accuracy']:.2%}",
                     f"{p['accuracy'] - b['accuracy']:+.2%}"))
    print(fmt.format("平均 Reward",
                     f"{b['avg_reward']:.4f}", f"{p['avg_reward']:.4f}",
                     f"{p['avg_reward'] - b['avg_reward']:+.4f}"))

    print()
    for k in sorted(b["pass_at_k"].keys()):
        bv, pv = b["pass_at_k"][k], p["pass_at_k"][k]
        if bv == 0 and pv == 0:
            continue
        print(fmt.format(f"Pass@{k}", f"{bv:.2%}", f"{pv:.2%}", f"{pv - bv:+.2%}"))

    # Per-problem analysis
    b_groups = _group_by_problem(b_samples)
    p_groups = _group_by_problem(p_samples)
    common = set(b_groups.keys()) & set(p_groups.keys())

    improved = regressed = ok_ok = fail_fail = 0
    changed: list[tuple[str, str, float, float]] = []

    for q in common:
        b_best = max((s.reward for s in b_groups[q] if s.reward is not None), default=0.0)
        p_best = max((s.reward for s in p_groups[q] if s.reward is not None), default=0.0)
        b_ok, p_ok = b_best >= threshold, p_best >= threshold

        if not b_ok and p_ok:
            improved += 1
            changed.append(("✅ 改进", q, b_best, p_best))
        elif b_ok and not p_ok:
            regressed += 1
            changed.append(("❌ 退化", q, b_best, p_best))
        elif b_ok and p_ok:
            ok_ok += 1
        else:
            fail_fail += 1

    print(f"\n  共同题目: {len(common)}")
    print(f"    ✅ 改进 (错→正): {improved}")
    print(f"    ❌ 退化 (正→错): {regressed}")
    print(f"    ➡️  保持正确    : {ok_ok}")
    print(f"    ➡️  保持错误    : {fail_fail}")

    net = improved - regressed
    symbol = "+" if net >= 0 else ""
    print(f"\n  净变化: {symbol}{net} 题")

    if detailed and changed:
        print("\n  --- 变化详情 ---")
        for tag, q, bv, pv in changed:
            preview = q[:70].replace("\n", " ")
            print(f"  {tag} [{bv:.2f}→{pv:.2f}]  {preview}")

    print(f"{'=' * 70}\n")


# ---------------------------------------------------------------------------
# Detailed per-sample view
# ---------------------------------------------------------------------------

def view_details(
    exp_id: str,
    limit: Optional[int] = None,
    show_correct_only: bool = False,
    show_failed_only: bool = False,
    threshold: float = 0.5,
) -> None:
    with SQLModelUtils.create_session() as session:
        samples = _load_samples(session, exp_id)

        if not samples:
            print(f"❌ 未找到实验: {exp_id}")
            return

        groups = _group_by_problem(samples)
        total = len(samples)
        correct = sum(1 for s in samples if s.reward is not None and s.reward >= threshold)

        print(f"\n{'=' * 80}")
        print(f"实验详情: {exp_id}")
        print(f"{'=' * 80}")
        print(f"  总样本数  : {total}")
        print(f"  问题数    : {len(groups)}")
        print(f"  准确率    : {correct / total:.2%} ({correct}/{total})")
        print()

        shown = 0
        for prob_idx, (question, prob_samples) in enumerate(groups.items(), 1):
            if limit and shown >= limit:
                break

            correct_cnt = sum(
                1 for s in prob_samples if s.reward is not None and s.reward >= threshold
            )
            prob_acc = correct_cnt / len(prob_samples) if prob_samples else 0.0

            if show_correct_only and correct_cnt == 0:
                continue
            if show_failed_only and correct_cnt > 0:
                continue

            shown += 1
            print(f"{'=' * 80}")
            print(f"问题 #{prob_idx}  正确率: {prob_acc:.2%} ({correct_cnt}/{len(prob_samples)})")
            print(f"{'=' * 80}")
            preview = question[:200] + "..." if len(question) > 200 else question
            print(f"📝 {preview}\n")

            # Ground truth from DatasetSample
            first = prob_samples[0]
            if first.data_id:
                ds = session.get(DatasetSample, first.data_id)
                if ds and ds.answer:
                    print("✅ 标准答案:")
                    try:
                        print(json.dumps(json.loads(ds.answer), indent=2, ensure_ascii=False))
                    except (json.JSONDecodeError, TypeError):
                        print(ds.answer)
                    print()

            print(f"🤖 模型输出 (前5个):")
            for i, s in enumerate(prob_samples[:5], 1):
                ok = s.reward is not None and s.reward >= threshold
                symbol = "✅" if ok else "❌"
                rv = s.reward if s.reward is not None else 0.0
                print(f"  [{i}] {symbol} reward={rv:.2f}")
                if s.output:
                    out = s.output[:300] + "..." if len(s.output) > 300 else s.output
                    print(f"      {out}")
                print()

            if len(prob_samples) > 5:
                print(f"  ... 还有 {len(prob_samples) - 5} 个样本\n")
            print("-" * 80 + "\n")

        if limit and shown >= limit:
            print(f"已显示 {limit} 道题。使用 --limit 调整。")


# ---------------------------------------------------------------------------
# Paper experiment mode (hardcoded baseline/practice pairs)
# ---------------------------------------------------------------------------

PAPER_EXPERIMENTS: dict[str, dict[str, str]] = {
    "AIME 2024": {
        "baseline": "math_paper_exp_AIME24_eval",
        "practice": "math_practice_paper_exp_AIME24_eval",
    },
    "AIME 2025": {
        "baseline": "math_paper_exp_AIME25_eval",
        "practice": "math_practice_paper_exp_AIME25_eval",
    },
}


def view_paper_experiments(detailed: bool = False, threshold: float = 1.0) -> None:
    """对比论文中报告的 AIME 实验结果（hardcoded exp IDs）。"""
    print("\n" + "=" * 70)
    print("Training-Free GRPO — 论文实验结果")
    print("=" * 70)
    for dataset_name, ids in PAPER_EXPERIMENTS.items():
        print(f"\n▶ {dataset_name}")
        view_compare(
            ids["baseline"],
            ids["practice"],
            threshold=threshold,
            detailed=detailed,
        )


# ---------------------------------------------------------------------------
# List all experiments
# ---------------------------------------------------------------------------

def list_experiments() -> None:
    with SQLModelUtils.create_session() as session:
        samples = session.exec(select(EvaluationSample)).all()

    exp_counts: dict[str, int] = defaultdict(int)
    for s in samples:
        exp_counts[s.exp_id] += 1

    print(f"\n{'=' * 50}")
    print(f"数据库中共 {len(exp_counts)} 个实验")
    print(f"{'=' * 50}")
    for exp_id, cnt in sorted(exp_counts.items()):
        print(f"  {exp_id:<45} {cnt:>6} 条")
    print()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_results(data: dict, filename: str) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ 结果已导出到: {filename}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="通用评估结果查看工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-e", "--exp_ids",
        nargs="+",
        metavar="EXP_ID",
        help="实验 ID（一个或多个）",
    )
    parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="对比模式：需提供恰好两个 -e 实验 ID（第一个为 baseline）",
    )
    parser.add_argument(
        "--details", "-v",
        action="store_true",
        help="显示每道题的详细输出",
    )
    parser.add_argument(
        "--correct",
        action="store_true",
        help="（--details 模式）只显示至少有一个正确答案的题目",
    )
    parser.add_argument(
        "--failed",
        action="store_true",
        help="（--details 模式）只显示全部错误的题目",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="（--details 模式）最多显示 N 道题",
    )
    parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="在摘要/对比模式下显示 Pass@K 和变化题目列表",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="reward >= 此值视为正确（默认 0.5）",
    )
    parser.add_argument(
        "--paper", "-p",
        action="store_true",
        help="查看论文实验结果（AIME 2024/2025 hardcoded 对比，不需要 -e）",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出数据库中所有实验",
    )
    parser.add_argument(
        "--export", "-o",
        type=str,
        metavar="FILE",
        help="导出结果为 JSON 文件",
    )

    args = parser.parse_args()

    if args.list:
        list_experiments()
        return

    if args.paper:
        view_paper_experiments(detailed=args.detailed, threshold=args.threshold)
        return

    if not args.exp_ids:
        parser.print_help()
        return

    if args.compare:
        if len(args.exp_ids) != 2:
            parser.error("--compare 需要恰好两个实验 ID：-e BASELINE PRACTICE")
        view_compare(
            args.exp_ids[0],
            args.exp_ids[1],
            threshold=args.threshold,
            detailed=args.detailed,
        )
        return

    if args.details:
        for exp_id in args.exp_ids:
            view_details(
                exp_id,
                limit=args.limit,
                show_correct_only=args.correct,
                show_failed_only=args.failed,
                threshold=args.threshold,
            )
        return

    results = view_summary(args.exp_ids, detailed=args.detailed, threshold=args.threshold)

    if args.export:
        export_results(results, args.export)


if __name__ == "__main__":
    main()
