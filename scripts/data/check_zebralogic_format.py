"""
检查 ZebraLogic 数据集的格式和结构

用法:
    python scripts/data/check_zebralogic_format.py
"""

import json
from datasets import load_dataset


def check_zebralogic_format():
    """检查 ZebraLogic 数据集的格式"""
    
    print("=" * 70)
    print("ZebraLogic 数据集格式检查")
    print("=" * 70)
    print()
    
    try:
        # 尝试加载数据集
        import os
        
        # 支持多种路径格式（Windows 和 WSL）
        local_paths = [
            "ZebraLogic/grid_mode/test-00000-of-00001.parquet",  # 相对路径
            "F:\\youtu-agent\\ZebraLogic\\grid_mode\\test-00000-of-00001.parquet",  # Windows 绝对路径
            "/mnt/f/youtu-agent/ZebraLogic/grid_mode/test-00000-of-00001.parquet",  # WSL 路径
        ]
        
        local_file_found = None
        for path in local_paths:
            if os.path.exists(path):
                local_file_found = path
                break
        
        if not local_file_found:
            print("Error: Local ZebraLogic file not found!")
            print("Tried paths:")
            for path in local_paths:
                print(f"  - {path}")
            print("\nPlease ensure ZebraLogic dataset is downloaded to the project directory.")
            return False
        
        print(f"Loading ZebraLogic dataset from local file: {local_file_found}")
        dataset = load_dataset(
            "parquet",
            data_files=local_file_found,
            split="train"  # 直接指定 split
        )
        
        print(f"✓ Successfully loaded dataset")
        print(f"Total samples: {len(dataset)}")
        print()
        
        # 显示可用字段
        print("=" * 70)
        print("Available fields:")
        print("=" * 70)
        for field in dataset.column_names:
            print(f"  - {field}")
        print()
        
        # 显示前3个样本
        print("=" * 70)
        print("Sample data (first 3 samples):")
        print("=" * 70)
        
        for i in range(min(3, len(dataset))):
            print(f"\n--- Sample {i+1} ---")
            sample = dataset[i]
            print(json.dumps(sample, indent=2, ensure_ascii=False))
        
        print()
        print("=" * 70)
        print("Field mapping suggestions:")
        print("=" * 70)
        
        # 分析字段并给出映射建议
        sample = dataset[0]
        
        # 查找问题字段
        question_candidates = []
        for field in ["question", "problem", "puzzle", "input", "text"]:
            if field in sample and sample[field]:
                question_candidates.append(field)
        
        if question_candidates:
            print(f"\n问题字段 (problem) 可能的候选:")
            for field in question_candidates:
                value = str(sample[field])[:100]
                print(f"  ✓ {field}: {value}...")
        else:
            print(f"\n⚠ 未找到明显的问题字段，请手动检查")
        
        # 查找答案字段
        answer_candidates = []
        for field in ["answer", "solution", "output", "label", "target"]:
            if field in sample and sample[field] is not None:
                answer_candidates.append(field)
        
        if answer_candidates:
            print(f"\n答案字段 (groundtruth) 可能的候选:")
            for field in answer_candidates:
                value = str(sample[field])[:100]
                print(f"  ✓ {field}: {value}...")
        else:
            print(f"\n⚠ 未找到明显的答案字段，请手动检查")
        
        # 其他有用的字段
        other_fields = []
        for field in ["difficulty", "level", "category", "topic", "type"]:
            if field in sample:
                other_fields.append(field)
        
        if other_fields:
            print(f"\n其他有用字段:")
            for field in other_fields:
                value = sample[field]
                print(f"  • {field}: {value}")
        
        print()
        print("=" * 70)
        print("建议的代码映射:")
        print("=" * 70)
        
        # 生成建议代码
        question_field = question_candidates[0] if question_candidates else "question"
        answer_field = answer_candidates[0] if answer_candidates else "answer"
        
        suggested_code = f'''
# 在 load_zebralogic.py 中使用:

problem = row.get("{question_field}", "")
groundtruth = row.get("{answer_field}", "")

sample = DatasetSample(
    dataset="ZebraLogic",
    index=idx,
    source="training_free_grpo",
    question=str(problem),
    answer=str(groundtruth),
'''
        
        if "difficulty" in sample or "level" in sample:
            level_field = "difficulty" if "difficulty" in sample else "level"
            suggested_code += f'    level=row.get("{level_field}", 0),\n'
        
        if "category" in sample or "topic" in sample:
            topic_field = "category" if "category" in sample else "topic"
            suggested_code += f'    topic=row.get("{topic_field}", ""),\n'
        
        suggested_code += ')'
        
        print(suggested_code)
        print()
        
    except Exception as e:
        print(f"✗ Error loading dataset: {e}")
        print()
        print("可能的原因:")
        print("  1. 数据集不存在或名称错误")
        print("  2. 网络连接问题")
        print("  3. 需要登录 HuggingFace (某些数据集需要)")
        print()
        print("解决方案:")
        print("  1. 检查数据集地址: https://huggingface.co/datasets/WildEval/ZebraLogic")
        print("  2. 如果需要登录: huggingface-cli login")
        print("  3. 尝试手动下载: git clone https://huggingface.co/datasets/WildEval/ZebraLogic")
        print()
        return False
    
    return True


if __name__ == "__main__":
    check_zebralogic_format()

