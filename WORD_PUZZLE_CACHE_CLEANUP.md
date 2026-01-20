# Word Puzzle 评估缓存清理指南

## 问题诊断

✅ 找到问题：评估结果被缓存在数据库的 `evaluation_data` 表中，使用相同的 `exp_id` 会直接读取缓存结果。

## 解决方案

### 1️⃣ 列出所有实验（查看缓存）

```bash
cd /mnt/f/youtu-agent
uv run python scripts/clean_experiment_data.py --list
```

应该会看到：
```
评估实验列表 (Evaluation Experiments)
======================================================================
  - word_puzzle_baseline_eval (50 samples)
  - word_puzzle_practice_eval (50 samples)
  ...
```

### 2️⃣ 删除评估缓存（正确语法）

```bash
# 方法1: 删除多个实验（正确语法，用空格分隔）
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval

# 方法2: 分别删除
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_practice_eval
```

### 3️⃣ 重新运行评估

```bash
# 确保游戏服务器在运行
# 在另一个终端: cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle && python game_lib.py -p 8775

# 基线评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

### 4️⃣ 查看新结果

```bash
uv run python scripts/view_training_results.py --exp_ids word_puzzle_baseline_eval word_puzzle_practice_eval --detailed
```

---

## 一键清理并重新评估

```bash
#!/bin/bash
cd /mnt/f/youtu-agent

echo "=== 第1步：删除旧的评估缓存 ==="
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval

echo ""
echo "=== 第2步：重新运行基线评估 ==="
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

echo ""
echo "=== 第3步：重新运行训练后评估 ==="
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval

echo ""
echo "=== 第4步：查看对比结果 ==="
uv run python scripts/view_training_results.py --exp_ids word_puzzle_baseline_eval word_puzzle_practice_eval --detailed
```

---

## 为什么之前的命令没用？

你之前的命令语法是正确的：
```bash
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_practice_eval word_puzzle_baseline_eval
```

可能的原因：
1. ❌ **exp_id 名称不匹配** - 数据库中的名称可能不同
2. ❌ **没有commit** - 虽然不太可能，脚本有commit
3. ❌ **多个数据库文件** - 可能读写了不同的数据库

### 验证方法：

```bash
# 删除前先列出
uv run python scripts/clean_experiment_data.py --list

# 删除
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval

# 删除后再列出，确认已删除
uv run python scripts/clean_experiment_data.py --list
```

---

## 快速验证脚本

如果还是不行，运行这个验证脚本：

```python
# scripts/verify_clean.py
from utu.utils import SQLModelUtils
from utu.db import EvaluationSample
from sqlmodel import select, delete

with SQLModelUtils.create_session() as session:
    # 查找
    samples = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id.in_(["word_puzzle_baseline_eval", "word_puzzle_practice_eval"])
        )
    ).all()
    
    print(f"找到 {len(samples)} 条记录")
    
    if samples:
        # 删除
        session.exec(
            delete(EvaluationSample).where(
                EvaluationSample.exp_id.in_(["word_puzzle_baseline_eval", "word_puzzle_practice_eval"])
            )
        )
        session.commit()
        print("✓ 已强制删除")
    else:
        print("✓ 数据已清空")
```

运行：
```bash
uv run python scripts/verify_clean.py
```

---

**请在WSL中按顺序执行上面的命令，特别是先 `--list` 查看，再删除，再确认！** 🔍

















