#!/usr/bin/env python3
"""检查Wordle数据集的实际情况"""
from utu.utils import SQLModelUtils
from utu.db.eval_datapoint import DatasetSample
from sqlmodel import select, func

print("=" * 80)
print("Wordle数据集检查")
print("=" * 80)

with SQLModelUtils.create_session() as session:
    # 检查训练数据集
    train_count = session.exec(
        select(func.count()).select_from(DatasetSample).where(
            DatasetSample.dataset == "KORGym-Wordle-Train-100"
        )
    ).one()
    
    print(f"\n训练数据集: KORGym-Wordle-Train-100")
    print(f"  实际数量: {train_count} 题")
    print(f"  预期数量: 100 题")
    if train_count != 100:
        print(f"  ⚠️  数量不匹配！")
    
    # 检查评估数据集
    eval_count = session.exec(
        select(func.count()).select_from(DatasetSample).where(
            DatasetSample.dataset == "KORGym-Wordle-Eval-120"
        )
    ).one()
    
    print(f"\n评估数据集: KORGym-Wordle-Eval-120")
    print(f"  实际数量: {eval_count} 题")
    print(f"  预期数量: 120 题")
    if eval_count != 120:
        print(f"  ⚠️  数量不匹配！")
    
    # 检查所有Wordle数据集
    print(f"\n所有Wordle数据集:")
    all_datasets = session.exec(
        select(DatasetSample.dataset, func.count()).where(
            DatasetSample.dataset.like("KORGym-Wordle%")
        ).group_by(DatasetSample.dataset)
    ).all()
    
    for dataset_name, count in all_datasets:
        print(f"  - {dataset_name}: {count} 题")

print("\n" + "=" * 80)



