#!/usr/bin/env python3
"""
检查 word_puzzle_practice_eval 为什么准确率为0

用法:
    uv run python scripts/debug_word_puzzle_results.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import select
from utu.db import EvaluationSample
from utu.utils import SQLModelUtils, get_logger

logger = get_logger(__name__)


def analyze_results():
    """分析 word_puzzle_practice_eval 的结果"""
    
    exp_id = "word_puzzle_practice_eval"
    
    print("\n" + "=" * 80)
    print(f"分析实验: {exp_id}")
    print("=" * 80)
    
    with SQLModelUtils.create_session() as session:
        # 获取所有样本
        samples = list(session.exec(
            select(EvaluationSample)
            .where(EvaluationSample.exp_id == exp_id)
            .limit(5)
        ))
        
        if not samples:
            print(f"\n❌ 未找到实验 {exp_id} 的数据")
            return
        
        print(f"\n📊 找到 {len(samples)} 个样本（显示前5个）")
        print()
        
        for i, sample in enumerate(samples, 1):
            print(f"\n{'='*80}")
            print(f"样本 {i}:")
            print(f"{'='*80}")
            print(f"问题: {sample.raw_question[:100]}...")
            print(f"答案: {sample.response[:200] if sample.response else 'None'}...")
            print(f"正确: {sample.correct}")
            print(f"奖励: {sample.reward}")
            print(f"提取的答案: {sample.extracted_final_answer}")
            print(f"元数据: {sample.meta}")
            
            # 检查trajectories
            if sample.trajectories:
                import json
                try:
                    trajs = json.loads(sample.trajectories)
                    print(f"轨迹数量: {len(trajs)}")
                    if trajs:
                        print(f"第一个轨迹: {str(trajs[0])[:200]}...")
                except:
                    print(f"轨迹: {sample.trajectories[:200]}...")
        
        # 统计信息
        print(f"\n{'='*80}")
        print("统计信息:")
        print(f"{'='*80}")
        
        all_samples = list(session.exec(
            select(EvaluationSample)
            .where(EvaluationSample.exp_id == exp_id)
        ))
        
        correct_count = sum(1 for s in all_samples if s.correct)
        total = len(all_samples)
        
        print(f"总样本数: {total}")
        print(f"正确数: {correct_count}")
        print(f"准确率: {correct_count / total * 100:.2f}%")
        
        # 分析失败原因
        print(f"\n失败原因分析:")
        no_response = sum(1 for s in all_samples if not s.response or s.response.strip() == "")
        no_extracted = sum(1 for s in all_samples if not s.extracted_final_answer)
        zero_reward = sum(1 for s in all_samples if s.reward == 0)
        
        print(f"  - 无响应: {no_response}")
        print(f"  - 未提取答案: {no_extracted}")
        print(f"  - 奖励为0: {zero_reward}")
        
        # 检查是否使用了训练后的agent
        print(f"\n检查配置:")
        sample = all_samples[0]
        if sample.meta:
            print(f"  - meta: {sample.meta}")


if __name__ == "__main__":
    analyze_results()

















