"""
合并多个游戏的 L1 和 L2 经验到 all_games.json
"""
import json
from pathlib import Path

# 定义文件路径
workspace_dir = Path("workspace/hierarchical_experiences")
source_files = [
    "alphabetical_sorting_practice.json",
    "word_puzzle_practice.json",
    "wordle_practice_2.json"
]
target_file = "all_games.json"

# 读取目标文件
target_path = workspace_dir / target_file
with open(target_path, 'r', encoding='utf-8') as f:
    all_games_data = json.load(f)

# 初始化合并后的经验列表
merged_l1 = []
merged_l2 = []

# 用于生成新的 ID
l1_counter = 0
l2_counter = 0

# 遍历源文件
for source_file in source_files:
    source_path = workspace_dir / source_file
    print(f"\n处理文件: {source_file}")
    
    with open(source_path, 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    
    # 提取 L1 经验
    if "l1_experiences" in source_data:
        l1_experiences = source_data["l1_experiences"]
        print(f"  找到 {len(l1_experiences)} 条 L1 经验")
        
        for exp in l1_experiences:
            # 创建新的经验对象，保持原有格式
            new_exp = {
                "id": f"L1_{l1_counter}",
                "content": exp["content"],
                "source_l0_ids": exp.get("source_l0_ids", []),
                "step": exp.get("step", 0),
                "source_game": source_file.replace(".json", "")  # 添加来源标记
            }
            merged_l1.append(new_exp)
            l1_counter += 1
    
    # 提取 L2 经验
    if "l2_experiences" in source_data:
        l2_experiences = source_data["l2_experiences"]
        print(f"  找到 {len(l2_experiences)} 条 L2 经验")
        
        for exp in l2_experiences:
            # 创建新的经验对象，保持原有格式
            new_exp = {
                "id": f"L2_{l2_counter}",
                "content": exp["content"],
                "source_l1_ids": exp.get("source_l1_ids", []),
                "step": exp.get("step", 0),
                "source_game": source_file.replace(".json", "")  # 添加来源标记
            }
            merged_l2.append(new_exp)
            l2_counter += 1

# 更新 all_games.json
all_games_data["l1_experiences"] = merged_l1
all_games_data["l2_experiences"] = merged_l2
all_games_data["stats"] = {
    "total_l1": len(merged_l1),
    "total_l2": len(merged_l2),
    "source_games": len(source_files)
}

# 写入目标文件
with open(target_path, 'w', encoding='utf-8') as f:
    json.dump(all_games_data, f, indent=2, ensure_ascii=False)

print(f"\n✅ 合并完成！")
print(f"  总共 L1 经验: {len(merged_l1)}")
print(f"  总共 L2 经验: {len(merged_l2)}")
print(f"  保存到: {target_file}")
