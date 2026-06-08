#!/usr/bin/env python3
"""清理 ZebraLogic Training-Free GRPO 训练数据，保留基线评估

用法:
    uv run python scripts/clean_zebralogic_training_data.py
"""

import sys
from pathlib import Path
from sqlmodel import select, delete

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.db.experience_cache_model import ExperienceCacheModel
from utu.utils.sqlmodel_utils import SQLModelUtils
from utu.utils.experience_cache import ExperienceCache


def clean_training_data(force: bool = False):
    """清理训练相关数据，保留基线评估"""
    
    # 基线评估的 exp_id（保留）
    baseline_exp_id = "logic_zebralogic_test_eval"
    
    # 训练相关的 exp_id（删除）
    training_exp_id = "logic_practice_zebralogic"
    training_eval_exp_id = "logic_practice_zebralogic_test_eval"
    
    print("\n" + "=" * 80)
    print("🧹 清理 ZebraLogic Training-Free GRPO 训练数据")
    print("=" * 80)
    print()
    print("将删除以下数据:")
    print(f"  ❌ 训练经验缓存: {training_exp_id}")
    print(f"  ❌ 训练后评估: {training_eval_exp_id}")
    print()
    print("将保留以下数据:")
    print(f"  ✅ 基线评估: {baseline_exp_id}")
    print()
    
    if not force:
        response = input("确认删除？输入 'yes' 继续: ")
        if response.lower() != 'yes':
            print("取消删除。")
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
        
        # 2. 删除训练后的评估数据
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
        
        # 3. 验证基线评估是否保留
        print("\n✅ 验证基线评估...")
        baseline_samples = list(session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == baseline_exp_id
            )
        ))
        
        if baseline_samples:
            print(f"  ✓ 基线评估已保留 ({len(baseline_samples)} 条记录)")
        else:
            print("  ⚠️  警告: 未找到基线评估数据")
    
    print("\n" + "=" * 80)
    print(f"✅ 清理完成！共删除 {total_deleted} 条记录")
    print("=" * 80)
    print()
    print("现在可以重新运行 Training-Free GRPO:")
    print("  uv run python scripts/run_training_free_GRPO.py --config practice/logic_reasoning_zebralogic.yaml")
    print()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="清理 ZebraLogic Training-Free GRPO 训练数据，保留基线评估"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="跳过确认提示"
    )
    
    args = parser.parse_args()
    clean_training_data(force=args.force)


if __name__ == "__main__":
    main()






