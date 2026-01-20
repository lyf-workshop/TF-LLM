"""
查看评估结果脚本
View evaluation results from database
"""
import argparse
import json
from collections import defaultdict

from utu.db import EvaluationSample
from utu.utils import SQLModelUtils, get_logger
from sqlmodel import select

logger = get_logger(__name__)


def view_experiment_results(exp_id: str, detailed: bool = False):
    """查看特定实验的结果"""
    
    with SQLModelUtils.create_session() as session:
        # 获取实验的所有样本
        samples = session.exec(
            select(EvaluationSample)
            .where(EvaluationSample.exp_id == exp_id)
            .order_by(EvaluationSample.dataset_index)
        ).all()
        
        if not samples:
            print(f"\n❌ 未找到实验: {exp_id}\n")
            return
        
        # 统计信息
        total = len(samples)
        judged_samples = [s for s in samples if s.stage == "judged"]
        correct_samples = [s for s in judged_samples if s.correct]
        
        # 按问题分组（用于Pass@K计算）
        problem_to_samples = defaultdict(list)
        for sample in judged_samples:
            problem_to_samples[sample.raw_question].append(sample)
        
        # Pass@K: 每个问题至少有一个正确答案
        pass_at_k = sum(
            1 for samples in problem_to_samples.values()
            if any(s.correct for s in samples)
        ) / len(problem_to_samples) if problem_to_samples else 0
        
        # 平均reward
        rewards = [s.reward for s in judged_samples if s.reward is not None]
        avg_reward = sum(rewards) / len(rewards) if rewards else 0
        
        # 打印统计信息
        print("\n" + "=" * 70)
        print(f"实验结果: {exp_id}")
        print("=" * 70)
        print(f"总样本数: {total}")
        print(f"已判断样本: {len(judged_samples)}")
        print(f"正确样本: {len(correct_samples)}")
        print(f"准确率: {len(correct_samples)/len(judged_samples)*100:.2f}%" if judged_samples else "N/A")
        print(f"Pass@K: {pass_at_k:.4f} ({pass_at_k*100:.2f}%)")
        print(f"平均Reward: {avg_reward:.4f}")
        print(f"唯一问题数: {len(problem_to_samples)}")
        print("=" * 70)
        
        # 详细信息
        if detailed and judged_samples:
            print("\n详细结果（前10个样本）:")
            print("-" * 70)
            for i, sample in enumerate(judged_samples[:10]):
                print(f"\n[{i+1}] 问题: {sample.raw_question[:80]}...")
                print(f"    正确: {'✓' if sample.correct else '✗'}")
                print(f"    Reward: {sample.reward}")
                if sample.judged_response:
                    print(f"    判断: {sample.judged_response[:100]}...")
        
        print("\n")


def compare_experiments(baseline_exp_id: str, practice_exp_id: str):
    """对比两个实验的结果"""
    
    with SQLModelUtils.create_session() as session:
        # 获取基线实验
        baseline_samples = session.exec(
            select(EvaluationSample)
            .where(EvaluationSample.exp_id == baseline_exp_id)
            .where(EvaluationSample.stage == "judged")
        ).all()
        
        # 获取训练后实验
        practice_samples = session.exec(
            select(EvaluationSample)
            .where(EvaluationSample.exp_id == practice_exp_id)
            .where(EvaluationSample.stage == "judged")
        ).all()
        
        if not baseline_samples:
            print(f"\n❌ 未找到基线实验: {baseline_exp_id}\n")
            return
        
        if not practice_samples:
            print(f"\n❌ 未找到训练后实验: {practice_exp_id}\n")
            return
        
        # 计算统计
        def calc_stats(samples):
            correct = sum(1 for s in samples if s.correct)
            total = len(samples)
            accuracy = correct / total if total > 0 else 0
            
            rewards = [s.reward for s in samples if s.reward is not None]
            avg_reward = sum(rewards) / len(rewards) if rewards else 0
            
            return {
                'total': total,
                'correct': correct,
                'accuracy': accuracy,
                'avg_reward': avg_reward
            }
        
        baseline_stats = calc_stats(baseline_samples)
        practice_stats = calc_stats(practice_samples)
        
        # 打印对比
        print("\n" + "=" * 70)
        print("实验对比")
        print("=" * 70)
        print(f"\n{'指标':<20} {'基线':<20} {'训练后':<20} {'提升':<15}")
        print("-" * 70)
        print(f"{'总样本数':<20} {baseline_stats['total']:<20} {practice_stats['total']:<20} -")
        print(f"{'正确数':<20} {baseline_stats['correct']:<20} {practice_stats['correct']:<20} {practice_stats['correct']-baseline_stats['correct']:+d}")
        print(f"{'准确率':<20} {baseline_stats['accuracy']:.2%}{'':>14} {practice_stats['accuracy']:.2%}{'':>14} {(practice_stats['accuracy']-baseline_stats['accuracy'])*100:+.2f}%")
        print(f"{'平均Reward':<20} {baseline_stats['avg_reward']:.4f}{'':>14} {practice_stats['avg_reward']:.4f}{'':>14} {(practice_stats['avg_reward']-baseline_stats['avg_reward'])*100:+.2f}%")
        print("=" * 70)
        print("\n")


def main():
    parser = argparse.ArgumentParser(description="查看评估结果")
    
    parser.add_argument(
        "--exp_id", "-e",
        type=str,
        help="实验ID"
    )
    
    parser.add_argument(
        "--compare", "-c",
        nargs=2,
        metavar=('BASELINE', 'PRACTICE'),
        help="对比两个实验（基线 vs 训练后）"
    )
    
    parser.add_argument(
        "--detailed", "-d",
        action="store_true",
        help="显示详细信息"
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有实验"
    )
    
    args = parser.parse_args()
    
    # 列出实验
    if args.list:
        import sys
        sys.path.insert(0, '.')
        from scripts.clean_experiment_data import list_experiments
        list_experiments()
        return
    
    # 查看单个实验
    if args.exp_id:
        view_experiment_results(args.exp_id, detailed=args.detailed)
        return
    
    # 对比两个实验
    if args.compare:
        compare_experiments(args.compare[0], args.compare[1])
        return
    
    # 如果没有参数，显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
