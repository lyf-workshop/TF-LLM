# ✅ Word Puzzle评估准确率为0的问题修复

## 🔍 问题分析

### 症状
```
word_puzzle_practice_eval:
  准确率: 0.00%
  Pass@1: 0.00%
```

所有样本都失败了。

### 根本原因

**评估配置文件缺少 `level` 参数！**

```yaml
# ❌ 错误配置（缺少level参数）
korgym:
  enabled: true
  game_name: "8-word_puzzle"
  game_host: "localhost"
  game_port: 8775
  max_rounds: 1
  timeout_per_game: 600
  # ❌ 缺少 level: 3
```

### 影响

当KORGym processor初始化adapter时，没有level参数会导致：
1. 游戏生成使用默认level（可能是level 4或5，非常难）
2. 与训练时使用的level 3不匹配
3. 导致所有题目都无法正确回答

---

## ✅ 修复内容

### **已修复的配置文件**

1. ✅ `configs/eval/korgym/word_puzzle_eval.yaml`
2. ✅ `configs/eval/korgym/word_puzzle_practice_eval.yaml`

### **修复后的配置**

```yaml
# ✅ 正确配置
korgym:
  enabled: true
  game_name: "8-word_puzzle"
  game_host: "localhost"
  game_port: 8775
  level: 3  # ✅ 添加level参数，与训练配置一致
  max_rounds: 1
  timeout_per_game: 600
```

---

## 📊 对比

| 配置项 | 训练配置 | 评估配置（修复前） | 评估配置（修复后） |
|--------|---------|------------------|------------------|
| level | 3 | ❌ 缺失 | ✅ 3 |
| 难度 | 中等 | 未知（可能很高） | 中等 |
| 一致性 | - | ❌ 不匹配 | ✅ 匹配 |

---

## 🚀 重新评估

### **1. 清理旧的评估数据**

```bash
cd /mnt/f/youtu-agent

# 使用数据库清理脚本
uv run python -c "
from utu.utils import SQLModelUtils
from utu.db import EvaluationSample
from sqlmodel import delete

with SQLModelUtils.create_session() as session:
    # 删除旧的评估数据
    session.exec(delete(EvaluationSample).where(
        EvaluationSample.exp_id == 'word_puzzle_practice_eval'
    ))
    session.exec(delete(EvaluationSample).where(
        EvaluationSample.exp_id == 'word_puzzle_baseline_eval'
    ))
    session.commit()
    print('✓ 已删除旧的评估数据')
"
```

### **2. 重新运行基线评估**

```bash
# 确保游戏服务器运行在8775端口
# WSL终端: cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle && python game_lib.py -p 8775

# 重新评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

### **3. 重新运行训练后评估**

```bash
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

### **4. 查看结果**

```bash
uv run python scripts/view_training_results.py --exp_ids word_puzzle_baseline_eval word_puzzle_practice_eval --detailed
```

---

## 📈 预期结果

修复后应该看到：

```
word_puzzle_baseline_eval:
  准确率: 30-50%  # 基线（无经验）
  
word_puzzle_practice_eval:
  准确率: 40-65%  # 训练后（有经验）
  提升: +10-15%
```

---

## ✅ 检查其他游戏

已确认其他游戏的配置**正确包含level参数**：

| 游戏 | 基线评估 | 训练后评估 | 状态 |
|------|---------|-----------|------|
| **Word Puzzle** | ✅ 已修复 | ✅ 已修复 | 修复 |
| **Alphabetical Sorting** | ✅ 有level:3 | ✅ 有level:3 | 正常 |
| **Wordle** | ✅ 有level:3 | ✅ 有level:3 | 正常 |

---

## 🎯 关键经验

### **配置完整性检查清单**

对于KORGym评估，配置文件必须包含：

```yaml
korgym:
  enabled: true         # ✅ 必须
  game_name: "..."      # ✅ 必须
  game_host: "..."      # ✅ 必须
  game_port: 8775       # ✅ 必须
  level: 3              # ✅ 必须！容易遗漏
  max_rounds: 1         # ✅ 必须
  timeout_per_game: 600 # ✅ 推荐
```

### **训练与评估一致性**

| 配置项 | 要求 |
|--------|------|
| `level` | ✅ 训练和评估必须一致 |
| `game_port` | ✅ 必须指向正确的游戏服务器 |
| `max_rounds` | ✅ 必须与游戏类型匹配 |

---

## 🔧 故障排查

如果评估准确率异常低（0%或接近0%）：

1. **检查level参数是否存在**
2. **检查level是否与训练一致**
3. **检查游戏服务器是否运行正确端口**
4. **检查数据集名称是否匹配**
5. **查看详细样本了解失败原因**

---

## 📝 快速修复脚本

创建检查脚本：

```python
# scripts/check_korgym_configs.py
import yaml
from pathlib import Path

eval_configs = Path("configs/eval/korgym")

for config_file in eval_configs.glob("*.yaml"):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    
    if "korgym" in config:
        korgym = config["korgym"]
        has_level = "level" in korgym
        
        status = "✅" if has_level else "❌"
        level_val = korgym.get("level", "MISSING")
        
        print(f"{status} {config_file.name}: level={level_val}")
```

---

## 🎉 总结

- ✅ 发现问题：评估配置缺少 `level: 3`
- ✅ 修复配置：添加 `level: 3` 到两个word_puzzle评估配置
- ✅ 验证其他游戏：alphabetical_sorting和wordle配置正常
- ⏳ 下一步：重新运行评估，查看正确的准确率

**修复完成！现在重新运行评估应该能看到正确的准确率了。** 🚀

---

**创建时间**: 2026-01-17  
**问题**: Word Puzzle评估准确率为0  
**原因**: 配置缺少level参数  
**影响**: 两个word_puzzle评估配置文件

















