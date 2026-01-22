# 📊 查看数据库中的数据集 - 使用指南

## 🎯 功能概述

`scripts/utils/view_datasets.py` 是一个强大的数据集查看工具，提供以下功能：

1. ✅ 列出所有数据集及统计信息
2. ✅ 查看特定数据集的详细信息
3. ✅ 显示数据集样本内容
4. ✅ 过滤和搜索数据集
5. ✅ 对比多个数据集
6. ✅ 根据游戏名称搜索数据集
7. ✅ 导出数据集信息到 JSON

---

## 📚 使用方法

### 1️⃣ 列出所有数据集

```bash
# 列出数据库中的所有数据集
uv run python scripts/utils/view_datasets.py --list
```

**示例输出**:
```
================================================================================
📊 数据集列表 (Datasets)
================================================================================

📦 KORGym-Wordle-Eval-50
   样本数量: 50
   游戏名称: 33-wordle
   数据集类型: eval
   种子范围: 1 - 50

📦 KORGym-Wordle-Train-20
   样本数量: 20
   游戏名称: 33-wordle
   数据集类型: train
   种子范围: 51 - 70

📦 KORGym-Wordle-Train-100
   样本数量: 100
   游戏名称: 33-wordle
   数据集类型: train
   种子范围: 51 - 150

================================================================================
📊 总计: 3 个数据集, 170 个样本
================================================================================
```

---

### 2️⃣ 过滤数据集

```bash
# 只显示包含 "Wordle" 的数据集
uv run python scripts/utils/view_datasets.py --list --filter Wordle

# 只显示包含 "Train" 的数据集
uv run python scripts/utils/view_datasets.py --list --filter Train

# 只显示 KORGym 相关数据集
uv run python scripts/utils/view_datasets.py --list --filter KORGym
```

---

### 3️⃣ 查看特定数据集详情

```bash
# 查看 20 题训练集的详细信息
uv run python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20"
```

**示例输出**:
```
================================================================================
📦 数据集详情: KORGym-Wordle-Train-20
================================================================================

📊 基本信息:
   总样本数: 20

🎮 游戏信息:
   游戏名称: 33-wordle
   数据集类型: train
   难度级别: 4

🌱 种子信息:
   种子范围: 51 - 70
   种子数量: 20

🔬 关联的评估实验:
   - wordle_practice_20_eval (50 样本)
   - wordle_practice_eval_20_1 (50 样本)

================================================================================
```

---

### 4️⃣ 查看数据集样本

```bash
# 查看数据集并显示前 5 个样本
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Train-20" \
  --samples 5
```

**示例输出**:
```
📝 样本示例 (前 5 个):
--------------------------------------------------------------------------------

样本 #1 (ID: 123)
  数据集索引: 0
  元数据:
    - seed: 51
    - game_name: 33-wordle
    - dataset_type: train
    - level: 4
    - game_prompt: Guess the hidden word...
  问题: You are playing Wordle. The goal is to guess a hidden 4-letter word...
  答案: cake

样本 #2 (ID: 124)
  数据集索引: 1
  ...
```

---

### 5️⃣ 对比多个数据集

```bash
# 对比 20 题和 100 题训练集
uv run python scripts/utils/view_datasets.py --compare \
  "KORGym-Wordle-Train-20" \
  "KORGym-Wordle-Train-100"
```

**示例输出**:
```
================================================================================
📊 数据集对比
================================================================================

📦 KORGym-Wordle-Train-20
   样本数: 20
   种子范围: 51 - 70
   游戏: 33-wordle
   类型: train

📦 KORGym-Wordle-Train-100
   样本数: 100
   种子范围: 51 - 150
   游戏: 33-wordle
   类型: train

================================================================================
```

---

### 6️⃣ 根据游戏名称搜索

```bash
# 搜索所有 Wordle 游戏的数据集
uv run python scripts/utils/view_datasets.py --game "33-wordle"

# 搜索 Word Puzzle 游戏的数据集
uv run python scripts/utils/view_datasets.py --game "8-word_puzzle"
```

**示例输出**:
```
================================================================================
🎮 游戏 '33-wordle' 的数据集
================================================================================

📦 KORGym-Wordle-Eval-50
   样本数: 50
   种子范围: 1 - 50
   类型: eval

📦 KORGym-Wordle-Train-20
   样本数: 20
   种子范围: 51 - 70
   类型: train

📦 KORGym-Wordle-Train-100
   样本数: 100
   种子范围: 51 - 150
   类型: train

================================================================================
```

---

### 7️⃣ 导出数据集到 JSON

```bash
# 导出数据集信息（包含所有样本）
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Train-20" \
  --export wordle_train_20.json
```

**生成的 JSON 文件结构**:
```json
{
  "dataset_name": "KORGym-Wordle-Train-20",
  "total_samples": 20,
  "seeds": [51, 52, 53, ..., 70],
  "meta": {
    "game_name": "33-wordle",
    "dataset_type": "train",
    "level": 4
  },
  "related_experiments": ["wordle_practice_20_eval"],
  "samples": [
    {
      "id": 123,
      "dataset_index": 0,
      "question": "...",
      "answer": "...",
      "meta": {...}
    },
    ...
  ]
}
```

---

## 🎯 常见使用场景

### 场景 1：检查数据集是否创建成功

```bash
# 创建数据集后检查
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --train_seeds_start 51 \
  --train_seeds_end 70

# 验证数据集
uv run python scripts/utils/view_datasets.py --list --filter Wordle
```

### 场景 2：调试数据集问题

```bash
# 查看详细信息和样本内容
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Train-20" \
  --samples 3
```

### 场景 3：清理前确认数据

```bash
# 1. 先查看所有数据集
uv run python scripts/utils/view_datasets.py --list

# 2. 查看要删除的数据集详情
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Train-20"

# 3. 确认后删除
uv run python scripts/utils/clean_experiment_data.py \
  --dataset "KORGym-Wordle-Train-20"
```

### 场景 4：对比不同配置的数据集

```bash
# 对比不同题量的训练集
uv run python scripts/utils/view_datasets.py --compare \
  "KORGym-Wordle-Train-20" \
  "KORGym-Wordle-Train-50" \
  "KORGym-Wordle-Train-100"
```

### 场景 5：检查所有 KORGym 游戏数据

```bash
# 查看所有 KORGym 数据集
uv run python scripts/utils/view_datasets.py --list --filter KORGym

# 或者分别查看每个游戏
uv run python scripts/utils/view_datasets.py --game "8-word_puzzle"
uv run python scripts/utils/view_datasets.py --game "22-alphabetical_sorting"
uv run python scripts/utils/view_datasets.py --game "33-wordle"
```

---

## 🔄 与清理脚本配合使用

### 完整工作流

```bash
# 1. 查看当前所有数据集
uv run python scripts/utils/view_datasets.py --list

# 2. 查看特定数据集详情
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Train-20"

# 3. 删除不需要的数据集
uv run python scripts/utils/clean_experiment_data.py \
  --dataset "KORGym-Wordle-Train-20"

# 4. 验证删除成功
uv run python scripts/utils/view_datasets.py --list
```

---

## 📊 参数速查表

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--list` | `-l` | 列出所有数据集 | `--list` |
| `--dataset` | `-d` | 查看特定数据集 | `--dataset "KORGym-Wordle-Train-20"` |
| `--samples` | `-s` | 显示样本数量 | `--samples 5` |
| `--filter` | `-f` | 过滤数据集名称 | `--filter Wordle` |
| `--export` | `-e` | 导出到 JSON | `--export output.json` |
| `--compare` | `-c` | 对比多个数据集 | `--compare "dataset1" "dataset2"` |
| `--game` | `-g` | 按游戏名搜索 | `--game "33-wordle"` |

---

## 🛠️ 高级用法

### 批量导出所有 Wordle 数据集

```bash
# 先列出所有 Wordle 数据集
uv run python scripts/utils/view_datasets.py --list --filter Wordle

# 分别导出
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Eval-50" \
  --export wordle_eval_50.json

uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Train-20" \
  --export wordle_train_20.json
```

### 检查数据集完整性

```bash
# 检查评估集（应该是 50 题，种子 1-50）
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Eval-50"

# 检查训练集（应该是 20 题，种子 51-70）
uv run python scripts/utils/view_datasets.py \
  --dataset "KORGym-Wordle-Train-20"
```

---

## 🎯 一键命令速查

```bash
# === 列出所有数据集 ===
uv run python scripts/utils/view_datasets.py --list

# === 查看 Wordle 数据集 ===
uv run python scripts/utils/view_datasets.py --list --filter Wordle

# === 查看 20 题训练集详情 ===
uv run python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20"

# === 查看样本内容 ===
uv run python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20" --samples 3

# === 对比数据集 ===
uv run python scripts/utils/view_datasets.py --compare "KORGym-Wordle-Train-20" "KORGym-Wordle-Train-100"

# === 搜索游戏数据集 ===
uv run python scripts/utils/view_datasets.py --game "33-wordle"

# === 导出到 JSON ===
uv run python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20" --export dataset.json
```

---

## 📚 相关脚本

- **清理数据**: `scripts/utils/clean_experiment_data.py` - 删除数据集和实验
- **创建数据**: `scripts/data/prepare_korgym_data.py` - 创建 KORGym 数据集
- **查看结果**: `scripts/korgym/view_korgym_results.py` - 查看评估结果

---

## 🔍 故障排除

### Q1: 数据库为空

```bash
# 检查数据库文件是否存在
ls -l test.db

# 如果数据库为空，创建数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
```

### Q2: 找不到特定数据集

```bash
# 先列出所有数据集，检查名称是否正确
uv run python scripts/utils/view_datasets.py --list

# 注意名称大小写和格式
# 正确: "KORGym-Wordle-Train-20"
# 错误: "wordle-train-20", "Wordle Train 20"
```

### Q3: 导出的 JSON 文件太大

```bash
# 如果数据集很大，只查看信息不导出样本
uv run python scripts/utils/view_datasets.py \
  --dataset "large-dataset"
  # 不加 --export 参数
```

---

*脚本位置: `scripts/utils/view_datasets.py`*  
*最后更新: 2026-01-21*


