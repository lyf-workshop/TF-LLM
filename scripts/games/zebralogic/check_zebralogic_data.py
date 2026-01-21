#!/usr/bin/env python3
"""检查 ZebraLogic 数据集是否准备好"""

from sqlmodel import select
from utu.db.eval_datapoint import DatasetSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def check_datasets():
    """检查训练和测试数据集"""
    
    datasets_to_check = [
        "ZebraLogic-Train-100",
        "ZebraLogic-Test-30"
    ]
    
    print("\n" + "="*70)
    print("ZebraLogic 数据集检查")
    print("="*70 + "\n")
    
    with SQLModelUtils.create_session() as session:
        all_ready = True
        
        for dataset_name in datasets_to_check:
            statement = select(DatasetSample).where(
                DatasetSample.dataset == dataset_name
            )
            samples = list(session.exec(statement))
            
            if samples:
                print(f"✅ {dataset_name}: {len(samples)} 个样本")
            else:
                print(f"❌ {dataset_name}: 未找到数据！")
                all_ready = False
        
        print("\n" + "="*70)
        if all_ready:
            print("✅ 所有数据集已准备好！可以开始 Training-Free GRPO")
        else:
            print("❌ 数据集未准备好，请先运行数据准备脚本")
            print("\n运行以下命令准备数据:")
            print("  uv run python scripts/data/prepare_zebralogic_samples.py \\")
            print("    --train_size 100 --test_size 30 \\")
            print("    --train_name 'ZebraLogic-Train-100' \\")
            print("    --test_name 'ZebraLogic-Test-30'")
        print("="*70 + "\n")


if __name__ == "__main__":
    check_datasets()

