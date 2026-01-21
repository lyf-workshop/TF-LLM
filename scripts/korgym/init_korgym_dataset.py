#!/usr/bin/env python3
"""
初始化 KORGym 数据集

KORGym 游戏是实时生成的，不需要预先准备数据。
但 training_free_grpo 要求数据集存在于数据库中。
这个脚本创建一个虚拟数据集条目，实际数据在运行时生成。
"""

import argparse
from utu.utils import SQLModelUtils
from utu.db import DatasetSample


def create_korgym_dataset(dataset_name: str, num_samples: int = 50):
    """
    创建 KORGym 虚拟数据集
    
    Args:
        dataset_name: 数据集名称
        num_samples: 样本数量
    """
    print(f"Creating KORGym dataset: {dataset_name}")
    print(f"Number of samples: {num_samples}")
    
    # 创建虚拟样本
    samples = []
    for i in range(num_samples):
        sample = DatasetSample(
            dataset=dataset_name,
            index=i,
            source="KORGym",  # 关键：设置 source 为 "KORGym"，用于选择 processer
            question=f"KORGym game seed {i}",  # 占位符
            answer="",  # KORGym 游戏没有固定答案
            meta={
                "korgym": True,
                "seed": i,
                "note": "This is a placeholder. Actual game will be generated at runtime."
            }
        )
        samples.append(sample)
    
    # 保存到数据库
    from sqlmodel import select
    
    with SQLModelUtils.create_session() as session:
        # 检查是否已存在
        existing = session.exec(
            select(DatasetSample)
            .where(DatasetSample.dataset == dataset_name)
            .limit(1)
        ).first()
        
        if existing:
            # 计数
            count = session.exec(
                select(DatasetSample)
                .where(DatasetSample.dataset == dataset_name)
            ).all()
            print(f"✓ Dataset {dataset_name} already exists ({len(count)} samples)")
            print(f"  Skipping creation")
            return
        
        # 批量插入
        print(f"Inserting {len(samples)} samples...")
        for sample in samples:
            session.add(sample)
        
        session.commit()
        print(f"✓ Dataset {dataset_name} created successfully!")
        
        # 验证
        count = session.exec(
            select(DatasetSample)
            .where(DatasetSample.dataset == dataset_name)
        ).all()
        print(f"  Total samples in database: {len(count)}")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize KORGym dataset in database"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="Dataset name (e.g., KORGym-WordPuzzle-Train)"
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        default=50,
        help="Number of samples (default: 50)"
    )
    
    args = parser.parse_args()
    
    create_korgym_dataset(args.dataset, args.num_samples)


if __name__ == "__main__":
    main()

