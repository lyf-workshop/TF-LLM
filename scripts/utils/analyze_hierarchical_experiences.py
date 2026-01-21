#!/usr/bin/env python3
"""分析分层经验学习的结果"""

from pathlib import Path
import json

# 读取生成的经验 JSON
exp_file = Path("workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json")

if exp_file.exists():
    with open(exp_file) as f:
        data = json.load(f)
    
    print("\n" + "=" * 80)
    print("分层经验统计")
    print("=" * 80)
    print(f"\nL0 (案例级): {len(data['l0_experiences'])} 个")
    print(f"L1 (模式级): {len(data['l1_experiences'])} 个")
    print(f"L2 (元策略级): {len(data['l2_experiences'])} 个")
    
    print("\n" + "-" * 80)
    print("L2 元策略内容:")
    print("-" * 80)
    for i, l2 in enumerate(data['l2_experiences']):
        print(f"\n[L2-{i}] ({l2['id']}):")
        print(f"  {l2['content'][:200]}...")
        print(f"  来源 L1: {l2['source_l1_ids']}")
    
    print("\n" + "-" * 80)
    print("L1 模式内容:")
    print("-" * 80)
    for i, l1 in enumerate(data['l1_experiences'][:5]):  # 只显示前 5 个
        print(f"\n[L1-{i}] ({l1['id']}):")
        print(f"  {l1['content'][:200]}...")
        print(f"  来源 L0: {l1['source_l0_ids']}")
    
    if len(data['l1_experiences']) > 5:
        print(f"\n  ... 还有 {len(data['l1_experiences']) - 5} 个 L1 经验")
    
    print("\n" + "=" * 80)
else:
    print(f"❌ 未找到经验文件: {exp_file}")
    print("\n可用的经验文件:")
    for f in Path("workspace/hierarchical_experiences").glob("*.json"):
        print(f"  - {f}")


























