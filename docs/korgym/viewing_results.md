# KORGym结果查看指南 📊

## 📋 概述

评估结果主要存储在**数据库**中，而不是文件系统。我创建了一个便捷脚本帮你查看结果。

---

## 🔍 查看评估结果

### 1. 列出所有实验

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 列出所有实验和数据集
uv run python scripts/view_eval_results.py --list
```

输出示例：
```
==================================================================
评估实验列表 (Evaluation Experiments)
==================================================================
  - word_puzzle_baseline_eval (50 samples)
  - word_puzzle_practice_eval (50 samples)
  - alphabetical_sorting_baseline_eval (50 samples)
  ...

==================================================================
数据集列表 (Datasets)
==================================================================
  - KORGym-WordPuzzle-Eval-50 (50 samples)
  - KORGym-WordPuzzle-Train-100 (100 samples)
  ...
```

---

### 2. 查看基线评估结果

```bash
# 查看Word Puzzle基线评估
uv run python scripts/view_eval_results.py --exp_id word_puzzle_baseline_eval
```

输出示例：
```
==================================================================
实验结果: word_puzzle_baseline_eval
==================================================================
总样本数: 50
已判断样本: 50
正确样本: 21
准确率: 42.00%
Pass@K: 0.4200 (42.00%)
平均Reward: 0.4200
唯一问题数: 50
==================================================================
```

---

### 3. 查看训练后评估结果

```bash
# 查看Word Puzzle训练后评估
uv run python scripts/view_eval_results.py --exp_id word_puzzle_practice_eval
```

---

### 4. 对比基线和训练后结果

```bash
# 对比两个实验
uv run python scripts/view_eval_results.py --compare \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval
```

输出示例：
```
==================================================================
实验对比
==================================================================

指标                 基线                 训练后               提升           
----------------------------------------------------------------------
总样本数             50                   50                   -
正确数               21                   28                   +7
准确率               42.00%               56.00%               +14.00%
平均Reward           0.4200               0.5600               +14.00%
==================================================================
```

---

### 5. 查看详细信息

```bash
# 查看详细信息（包含前10个样本的详细结果）
uv run python scripts/view_eval_results.py --exp_id word_puzzle_baseline_eval --detailed
```

---

## 🗑️ 删除训练相关数据

### 问题：训练数据在哪里？

训练过程的数据存储在：

1. **数据库** - 使用exp_id查询
2. **文件系统** - `workspace/hierarchical_experiences/`

### 完整清理命令

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 1. 先列出所有实验，找到相关的exp_id
uv run python scripts/view_eval_results.py --list

# 2. 删除数据库中的实验数据
uv run python scripts/clean_experiment_data.py --exp_id \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval

# 3. 删除文件系统中的训练数据
rm -f workspace/hierarchical_experiences/word_puzzle_practice.json
rm -f configs/agents/practice/word_puzzle_practice_agent.yaml
rm -rf workspace/word_puzzle_*

# 4. 验证清理结果
uv run python scripts/view_eval_results.py --list
```

---

## 📊 三个游戏的快速查看命令

### Word Puzzle

```bash
# 基线结果
uv run python scripts/view_eval_results.py --exp_id word_puzzle_baseline_eval

# 训练后结果
uv run python scripts/view_eval_results.py --exp_id word_puzzle_practice_eval

# 对比
uv run python scripts/view_eval_results.py --compare \
  word_puzzle_baseline_eval word_puzzle_practice_eval
```

### Alphabetical Sorting

```bash
# 基线结果
uv run python scripts/view_eval_results.py --exp_id alphabetical_sorting_baseline_eval

# 训练后结果
uv run python scripts/view_eval_results.py --exp_id alphabetical_sorting_practice_eval

# 对比
uv run python scripts/view_eval_results.py --compare \
  alphabetical_sorting_baseline_eval alphabetical_sorting_practice_eval
```

### Wordle

```bash
# 基线结果
uv run python scripts/view_eval_results.py --exp_id wordle_baseline_eval

# 训练后结果
uv run python scripts/view_eval_results.py --exp_id wordle_practice_eval

# 对比
uv run python scripts/view_eval_results.py --compare \
  wordle_baseline_eval wordle_practice_eval
```

---

## 🔄 完整的重新运行流程

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# === 步骤1: 完全清理 ===
echo "🗑️  清理旧数据..."

# 列出当前所有实验
uv run python scripts/view_eval_results.py --list

# 删除Word Puzzle相关实验
uv run python scripts/clean_experiment_data.py --exp_id \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval

# 删除文件系统数据
rm -f workspace/hierarchical_experiences/word_puzzle_practice.json
rm -f configs/agents/practice/word_puzzle_practice_agent.yaml

echo "✓ 清理完成"

# === 步骤2: 准备数据集 ===
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# === 步骤3: 基线评估 ===
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# === 步骤4: 查看基线结果 ===
uv run python scripts/view_eval_results.py --exp_id word_puzzle_baseline_eval

# === 步骤5: 训练 ===
uv run python scripts/run_training_free_GRPO.py --config_name word_puzzle_practice

# === 步骤6: 训练后评估 ===
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval

# === 步骤7: 查看训练后结果 ===
uv run python scripts/view_eval_results.py --exp_id word_puzzle_practice_eval

# === 步骤8: 对比结果 ===
uv run python scripts/view_eval_results.py --compare \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval
```

---

## 💡 常用命令速查

```bash
# 列出所有实验
uv run python scripts/view_eval_results.py --list

# 查看基线分数
uv run python scripts/view_eval_results.py --exp_id word_puzzle_baseline_eval

# 查看详细信息
uv run python scripts/view_eval_results.py --exp_id word_puzzle_baseline_eval --detailed

# 对比基线和训练后
uv run python scripts/view_eval_results.py --compare word_puzzle_baseline_eval word_puzzle_practice_eval

# 清理实验
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval
```

---

## 📁 结果存储位置

| 类型 | 存储位置 | 说明 |
|------|---------|------|
| **评估结果** | 数据库（EvaluationSample表） | 每个样本的详细结果 |
| **统计信息** | 日志输出 | 打印到控制台 |
| **经验数据** | `workspace/hierarchical_experiences/*.json` | L0/L1/L2经验 |
| **Agent配置** | `configs/agents/practice/*_practice_agent.yaml` | 训练后生成 |

---

**现在使用 `scripts/view_eval_results.py` 来查看所有评估结果！** 📊

