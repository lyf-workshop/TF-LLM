import json

# 读取原始文件
with open('workspace/hierarchical_experiences/word_puzzle_practice_less.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 统计信息
print(f"原始经验数量:")
print(f"  L0: {len(data.get('l0_experiences', []))} 条")
print(f"  L1: {len(data.get('l1_experiences', []))} 条")
print(f"  L2: {len(data.get('l2_experiences', []))} 条")

# 删除 L0 经验
data['l0_experiences'] = []

# 更新统计信息
if 'stats' in data:
    data['stats']['total_l0'] = 0

# 保存修改后的文件
with open('workspace/hierarchical_experiences/word_puzzle_practice_less.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\n[OK] 修改后经验数量:")
print(f"  L0: {len(data.get('l0_experiences', []))} 条")
print(f"  L1: {len(data.get('l1_experiences', []))} 条")
print(f"  L2: {len(data.get('l2_experiences', []))} 条")
print(f"\n文件已保存！")
