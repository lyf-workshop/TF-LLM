#!/usr/bin/env python3
"""
对比训练前后的评估结果，找出变化的题目

用法:
    python scripts/compare_training_changes.py --baseline_exp_id <baseline_id> --practice_exp_id <practice_id> --output <output_file>
"""

import sys
from pathlib import Path
from sqlmodel import select
import argparse

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def compare_results(baseline_exp_id: str, practice_exp_id: str, output_file: str):
    """对比训练前后的结果，找出变化的题目"""
    
    print("\n" + "=" * 80)
    print("🔍 对比训练前后的评估结果")
    print("=" * 80)
    print(f"\nBaseline 实验: {baseline_exp_id}")
    print(f"Practice 实验: {practice_exp_id}")
    print(f"输出文件: {output_file}")
    print()
    
    with SQLModelUtils.create_session() as session:
        # 获取 baseline 结果
        print("📊 加载 Baseline 数据...")
        baseline_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == baseline_exp_id
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        if not baseline_samples:
            print(f"❌ 未找到 Baseline 数据 (exp_id: {baseline_exp_id})")
            return
        
        print(f"   找到 {len(baseline_samples)} 条 Baseline 记录")
        
        # 获取 practice 结果
        print("📊 加载 Practice 数据...")
        practice_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == practice_exp_id
            ).order_by(EvaluationSample.dataset_index)
        ))
        
        if not practice_samples:
            print(f"❌ 未找到 Practice 数据 (exp_id: {practice_exp_id})")
            return
        
        print(f"   找到 {len(practice_samples)} 条 Practice 记录")
        
        # 按问题建立索引
        print("\n🔗 建立问题索引...")
        baseline_dict = {}
        for sample in baseline_samples:
            key = sample.raw_question or sample.augmented_question
            if key not in baseline_dict:
                baseline_dict[key] = []
            baseline_dict[key].append(sample)
        
        practice_dict = {}
        for sample in practice_samples:
            key = sample.raw_question or sample.augmented_question
            if key not in practice_dict:
                practice_dict[key] = []
            practice_dict[key].append(sample)
        
        # 找出共同的问题
        common_questions = set(baseline_dict.keys()) & set(practice_dict.keys())
        print(f"   找到 {len(common_questions)} 个共同问题")
        
        # 分析变化
        print("\n📈 分析变化...")
        improved = []  # 训练前错误，训练后正确
        regressed = []  # 训练前正确，训练后错误
        
        for question in common_questions:
            baseline_rollouts = baseline_dict[question]
            practice_rollouts = practice_dict[question]
            
            # 计算每个问题的最佳结果
            baseline_best = max((s.reward for s in baseline_rollouts if s.reward is not None), default=0.0)
            practice_best = max((s.reward for s in practice_rollouts if s.reward is not None), default=0.0)
            
            # 判断是否正确（reward > 0.5）
            baseline_correct = baseline_best > 0.5
            practice_correct = practice_best > 0.5
            
            # 找出变化
            if not baseline_correct and practice_correct:
                # 改进：训练前错误，训练后正确
                improved.append({
                    'question': question,
                    'baseline_samples': baseline_rollouts,
                    'practice_samples': practice_rollouts,
                    'baseline_best_reward': baseline_best,
                    'practice_best_reward': practice_best,
                })
            elif baseline_correct and not practice_correct:
                # 退化：训练前正确，训练后错误
                regressed.append({
                    'question': question,
                    'baseline_samples': baseline_rollouts,
                    'practice_samples': practice_rollouts,
                    'baseline_best_reward': baseline_best,
                    'practice_best_reward': practice_best,
                })
        
        print(f"   ✅ 改进的题目: {len(improved)} 个")
        print(f"   ❌ 退化的题目: {len(regressed)} 个")
        
        # 生成报告
        print(f"\n📝 生成报告到 {output_file}...")
        generate_report(improved, regressed, baseline_exp_id, practice_exp_id, output_file)
        
        print("\n" + "=" * 80)
        print("✅ 对比完成！")
        print("=" * 80)
        print()


def generate_report(improved, regressed, baseline_exp_id, practice_exp_id, output_file):
    """生成对比报告"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Training-Free GRPO 训练前后对比报告\n\n")
        f.write(f"**Baseline 实验**: `{baseline_exp_id}`\n")
        f.write(f"**Practice 实验**: `{practice_exp_id}`\n\n")
        f.write("---\n\n")
        
        # 统计摘要
        f.write("## 📊 统计摘要\n\n")
        f.write(f"- ✅ **改进的题目**: {len(improved)} 个（训练前错误 → 训练后正确）\n")
        f.write(f"- ❌ **退化的题目**: {len(regressed)} 个（训练前正确 → 训练后错误）\n")
        f.write(f"- 📈 **净改进**: {len(improved) - len(regressed)} 个\n\n")
        f.write("---\n\n")
        
        # 改进的题目
        if improved:
            f.write("## ✅ 改进的题目（训练前错误 → 训练后正确）\n\n")
            f.write(f"共 {len(improved)} 个题目\n\n")
            
            for i, item in enumerate(improved, 1):
                f.write(f"### 题目 {i}\n\n")
                f.write(f"**完整问题**:\n```\n{item['question']}\n```\n\n")
                
                # Baseline 所有 rollouts 的详细信息
                f.write("**训练前 (Baseline) - 所有 Rollouts**:\n\n")
                f.write(f"- 最佳 Reward: {item['baseline_best_reward']:.2f}\n")
                f.write(f"- Rollouts 数量: {len(item['baseline_samples'])}\n\n")
                
                for idx, sample in enumerate(item['baseline_samples'], 1):
                    f.write(f"#### Baseline Rollout {idx}\n")
                    f.write(f"- Reward: {sample.reward if sample.reward is not None else 'N/A'}\n")
                    f.write(f"- Trace ID: {sample.trace_id or 'N/A'}\n")
                    f.write(f"- Dataset Index: {sample.dataset_index or 'N/A'}\n")
                    if sample.time_cost:
                        f.write(f"- Time Cost: {sample.time_cost:.2f}秒\n")
                    if sample.response:
                        f.write(f"- **完整回答**:\n```\n{sample.response}\n```\n")
                    if sample.reasoning:
                        f.write(f"- Reasoning: {sample.reasoning}\n")
                    if sample.extracted_final_answer:
                        f.write(f"- Extracted Answer: {sample.extracted_final_answer}\n")
                    f.write("\n")
                
                f.write("\n")
                
                # Practice 所有 rollouts 的详细信息
                f.write("**训练后 (Practice) - 所有 Rollouts**:\n\n")
                f.write(f"- 最佳 Reward: {item['practice_best_reward']:.2f}\n")
                f.write(f"- Rollouts 数量: {len(item['practice_samples'])}\n\n")
                
                for idx, sample in enumerate(item['practice_samples'], 1):
                    f.write(f"#### Practice Rollout {idx}\n")
                    f.write(f"- Reward: {sample.reward if sample.reward is not None else 'N/A'}\n")
                    f.write(f"- Trace ID: {sample.trace_id or 'N/A'}\n")
                    f.write(f"- Dataset Index: {sample.dataset_index or 'N/A'}\n")
                    if sample.time_cost:
                        f.write(f"- Time Cost: {sample.time_cost:.2f}秒\n")
                    if sample.response:
                        f.write(f"- **完整回答**:\n```\n{sample.response}\n```\n")
                    if sample.reasoning:
                        f.write(f"- Reasoning: {sample.reasoning}\n")
                    if sample.extracted_final_answer:
                        f.write(f"- Extracted Answer: {sample.extracted_final_answer}\n")
                    f.write("\n")
                
                # 正确答案
                if item['practice_samples'] and item['practice_samples'][0].correct_answer:
                    f.write(f"**正确答案**:\n```\n{item['practice_samples'][0].correct_answer}\n```\n")
                
                f.write("\n---\n\n")
        
        # 退化的题目
        if regressed:
            f.write("## ❌ 退化的题目（训练前正确 → 训练后错误）\n\n")
            f.write(f"共 {len(regressed)} 个题目\n\n")
            
            for i, item in enumerate(regressed, 1):
                f.write(f"### 题目 {i}\n\n")
                f.write(f"**问题**:\n```\n{item['question'][:500]}{'...' if len(item['question']) > 500 else ''}\n```\n\n")
                
                # Baseline 结果
                f.write("**训练前 (Baseline)**:\n")
                f.write(f"- 最佳 Reward: {item['baseline_best_reward']:.2f}\n")
                f.write(f"- Rollouts 数量: {len(item['baseline_samples'])}\n")
                
                # 找出最好的 baseline rollout
                best_baseline = max(item['baseline_samples'], key=lambda s: s.reward if s.reward else 0)
                if best_baseline.response:
                    f.write(f"- 最佳回答:\n```\n{best_baseline.response[:300]}{'...' if len(best_baseline.response) > 300 else ''}\n```\n")
                
                f.write("\n")
                
                # Practice 结果
                f.write("**训练后 (Practice)**:\n")
                f.write(f"- 最佳 Reward: {item['practice_best_reward']:.2f}\n")
                f.write(f"- Rollouts 数量: {len(item['practice_samples'])}\n")
                
                # 找出最好的 practice rollout
                best_practice = max(item['practice_samples'], key=lambda s: s.reward if s.reward else 0)
                if best_practice.response:
                    f.write(f"- 最佳回答:\n```\n{best_practice.response[:300]}{'...' if len(best_practice.response) > 300 else ''}\n```\n")
                
                # 正确答案
                if best_practice.correct_answer:
                    f.write(f"\n**正确答案**:\n```\n{best_practice.correct_answer[:300]}{'...' if len(best_practice.correct_answer) > 300 else ''}\n```\n")
                
                f.write("\n---\n\n")
        
        # 总结
        f.write("## 📝 总结\n\n")
        if len(improved) > len(regressed):
            f.write(f"✅ 训练整体上是**有效的**，净改进了 {len(improved) - len(regressed)} 个题目。\n\n")
        elif len(improved) < len(regressed):
            f.write(f"⚠️ 训练可能需要调整，净退化了 {len(regressed) - len(improved)} 个题目。\n\n")
        else:
            f.write(f"➡️ 训练前后改进和退化的题目数量相同，整体持平。\n\n")
        
        f.write("### 可能的原因分析\n\n")
        f.write("**改进的原因**:\n")
        f.write("- 训练过程中提取的经验帮助模型更好地理解问题\n")
        f.write("- 模型学会了更系统化的推理方法\n")
        f.write("- 约束处理能力得到提升\n\n")
        
        f.write("**退化的原因**:\n")
        f.write("- 经验可能过于具体，导致过拟合\n")
        f.write("- 某些经验可能与特定题目冲突\n")
        f.write("- 温度参数或其他超参数的影响\n\n")


def main():
    parser = argparse.ArgumentParser(
        description="对比训练前后的评估结果，找出变化的题目"
    )
    parser.add_argument(
        "--baseline_exp_id",
        type=str,
        default="logic_zebralogic_test_eval",
        help="Baseline 实验 ID"
    )
    parser.add_argument(
        "--practice_exp_id",
        type=str,
        default="logic_practice_zebralogic_test_eval",
        help="Practice 实验 ID"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="训练前后对比报告.md",
        help="输出文件路径"
    )
    
    args = parser.parse_args()
    
    compare_results(args.baseline_exp_id, args.practice_exp_id, args.output)


if __name__ == "__main__":
    main()


