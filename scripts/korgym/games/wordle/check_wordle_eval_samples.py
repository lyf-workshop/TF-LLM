#!/usr/bin/env python3
"""检查Wordle训练过程中的评估样本"""
from utu.utils import SQLModelUtils
from utu.db.eval_datapoint import EvaluationSample
from sqlmodel import select, func

print("=" * 80)
print("Wordle训练评估样本检查")
print("=" * 80)

with SQLModelUtils.create_session() as session:
    # 检查所有wordle相关的exp_id
    exp_ids = session.exec(
        select(EvaluationSample.exp_id, func.count()).where(
            EvaluationSample.exp_id.like("wordle%")
        ).group_by(EvaluationSample.exp_id)
    ).all()
    
    print(f"\n所有Wordle实验:")
    for exp_id, count in exp_ids:
        print(f"  - {exp_id}: {count} 个样本")
    
    # 检查最新的训练epoch
    print(f"\n72B训练的详细信息:")
    epochs = session.exec(
        select(EvaluationSample.exp_id, func.count()).where(
            EvaluationSample.exp_id.like("wordle_qwen72b_grpo%")
        ).group_by(EvaluationSample.exp_id)
    ).all()
    
    for exp_id, count in epochs:
        print(f"  - {exp_id}: {count} 个样本")
        
        # 获取该epoch的详细信息
        samples = session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id
            ).limit(5)
        ).all()
        
        print(f"    前5个样本的ID: {[s.id for s in samples]}")

print("\n" + "=" * 80)
print("分析:")
print("- 如果每个epoch有100个样本，说明正常")
print("- 如果每个epoch有250个样本，可能是grpo_n导致的重复")
print("- grpo_n=5 意味着每个问题生成5个rollout，但不应该增加样本数")
print("=" * 80)



