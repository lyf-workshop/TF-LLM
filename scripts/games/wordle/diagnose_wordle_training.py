#!/usr/bin/env python3
"""诊断Wordle训练过程中的得分分布"""
from utu.utils import SQLModelUtils
from utu.db.eval_datapoint import EvaluationSample
from sqlmodel import select
from collections import Counter

print("=" * 80)
print("Wordle训练诊断")
print("=" * 80)

with SQLModelUtils.create_session() as session:
    # 获取第一个epoch的所有样本
    samples = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id == "wordle_qwen72b_grpo_epoch_0"
        )
    ).all()
    
    print(f"\nEpoch 0 样本数: {len(samples)}")
    
    # 分析reward分布
    rewards = [s.reward for s in samples if s.reward is not None]
    
    if rewards:
        print(f"\nReward统计:")
        print(f"  - 总样本数: {len(rewards)}")
        print(f"  - 平均reward: {sum(rewards)/len(rewards):.4f}")
        print(f"  - 最高reward: {max(rewards):.4f}")
        print(f"  - 最低reward: {min(rewards):.4f}")
        
        # Reward分布
        reward_counter = Counter(rewards)
        print(f"\nReward分布:")
        for reward, count in sorted(reward_counter.items()):
            percentage = count / len(rewards) * 100
            print(f"  - Reward={reward:.2f}: {count} 个 ({percentage:.1f}%)")
        
        # 检查是否有多样性
        unique_rewards = len(set(rewards))
        print(f"\n多样性分析:")
        print(f"  - 不同reward值的数量: {unique_rewards}")
        if unique_rewards <= 2:
            print(f"  ⚠️  Reward缺乏多样性！这会导致无法提取经验。")
            print(f"  原因可能是:")
            print(f"    1. 游戏太难，所有rollout都失败（reward=0）")
            print(f"    2. 游戏太简单，所有rollout都成功（reward=1）")
            print(f"    3. 评分逻辑有问题")
        else:
            print(f"  ✓ Reward有足够多样性，可以提取经验")
    else:
        print("  ⚠️  没有找到reward数据！")
    
    # 分析correct字段
    correct_count = sum(1 for s in samples if s.correct is True)
    incorrect_count = sum(1 for s in samples if s.correct is False)
    none_count = sum(1 for s in samples if s.correct is None)
    
    print(f"\nCorrect统计:")
    print(f"  - 正确: {correct_count} ({correct_count/len(samples)*100:.1f}%)")
    print(f"  - 错误: {incorrect_count} ({incorrect_count/len(samples)*100:.1f}%)")
    print(f"  - 未判断: {none_count} ({none_count/len(samples)*100:.1f}%)")
    
    # 显示前5个样本的详细信息
    print(f"\n前5个样本详情:")
    for i, sample in enumerate(samples[:5]):
        print(f"\n样本 {i+1}:")
        print(f"  - Question: {sample.raw_question[:60]}...")
        print(f"  - Reward: {sample.reward}")
        print(f"  - Correct: {sample.correct}")
        print(f"  - Response length: {len(sample.response) if sample.response else 0}")

print("\n" + "=" * 80)



