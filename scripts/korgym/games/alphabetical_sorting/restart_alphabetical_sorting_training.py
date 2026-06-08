#!/usr/bin/env python3
"""完整重启 Alphabetical Sorting 训练流程

这个脚本会：
1. 清理经验缓存
2. 清理旧的训练评估数据
3. 保留数据集（避免重新创建）

用法:
    uv run python scripts/restart_alphabetical_sorting_training.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import select, delete
from utu.db.eval_datapoint import EvaluationSample
from utu.db.experience_cache_model import ExperienceCacheModel
from utu.utils.sqlmodel_utils import SQLModelUtils
from utu.utils.experience_cache import ExperienceCache
from utu.utils import get_logger

logger = get_logger(__name__)


def main():
    # 配置
    training_exp_id = "alphabetical_sorting_practice"
    training_eval_exp_id = "alphabetical_sorting_practice_eval"
    baseline_exp_id = "alphabetical_sorting_baseline_eval"
    
    print("\n" + "=" * 80)
    print("🧹 完整重启 Alphabetical Sorting 训练流程")
    print("=" * 80)
    print()
    print("将删除以下数据:")
    print(f"  ❌ 训练经验缓存: {training_exp_id}")
    print(f"  ❌ 训练评估数据: {training_exp_id} (training rollout data)")
    print(f"  ❌ 训练后评估: {training_eval_exp_id}")
    print()
    print("将保留以下数据:")
    print(f"  ✅ 基线评估: {baseline_exp_id}")
    print(f"  ✅ 训练数据集: KORGym-AlphabeticalSorting-Train-100")
    print(f"  ✅ 评估数据集: KORGym-AlphabeticalSorting-Eval-50")
    print()
    
    # 确认删除
    response = input("确认删除？输入 'yes' 继续: ")
    if response.lower() != 'yes':
        print("❌ 取消操作")
        return
    
    total_deleted = 0
    
    with SQLModelUtils.create_session() as session:
        # 1. 删除训练经验缓存
        print("\n📦 清理经验缓存...")
        cache_records = list(session.exec(
            select(ExperienceCacheModel).where(
                ExperienceCacheModel.experiment_name == training_exp_id
            )
        ))
        
        if cache_records:
            for record in cache_records:
                session.delete(record)
            session.commit()
            print(f"  ✓ 已删除 {len(cache_records)} 条经验缓存记录")
            total_deleted += len(cache_records)
        else:
            print("  ℹ️  未找到经验缓存数据")
        
        # 2. 删除训练过程中的评估数据 (rollout data)
        print("\n📊 清理训练rollout数据...")
        training_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == training_exp_id
            )
        ))
        
        if training_samples:
            session.exec(
                delete(EvaluationSample).where(
                    EvaluationSample.exp_id == training_exp_id
                )
            )
            session.commit()
            print(f"  ✓ 已删除 {len(training_samples)} 条训练rollout记录")
            total_deleted += len(training_samples)
        else:
            print("  ℹ️  未找到训练rollout数据")
        
        # 3. 删除训练后的评估数据
        print("\n📊 清理训练后评估数据...")
        eval_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == training_eval_exp_id
            )
        ))
        
        if eval_samples:
            session.exec(
                delete(EvaluationSample).where(
                    EvaluationSample.exp_id == training_eval_exp_id
                )
            )
            session.commit()
            print(f"  ✓ 已删除 {len(eval_samples)} 条评估记录")
            total_deleted += len(eval_samples)
        else:
            print("  ℹ️  未找到训练后评估数据")
        
        # 4. 验证基线评估是否保留
        print("\n✅ 验证基线评估...")
        baseline_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == baseline_exp_id
            )
        ))
        
        if baseline_samples:
            print(f"  ✓ 基线评估已保留 ({len(baseline_samples)} 条记录)")
        else:
            print("  ⚠️  警告: 未找到基线评估数据（可能还没运行过）")
    
    print("\n" + "=" * 80)
    print(f"✅ 清理完成！共删除 {total_deleted} 条记录")
    print("=" * 80)
    print()
    print("现在可以重新运行 Training-Free GRPO:")
    print()
    print("1. 确保游戏服务器正在运行:")
    print("   cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting")
    print("   python game_lib.py -p 8776")
    print()
    print("2. 重新训练:")
    print("   uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice")
    print()
    print("3. 训练后评估:")
    print("   uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()













