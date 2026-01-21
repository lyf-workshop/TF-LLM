# KORGym评分机制与结果查看指南 📊

## 📋 评分机制详解

### 1. Word Puzzle (Crossword) - 8-word_puzzle

**游戏类型**: 填字游戏（单轮）

**评分公式**:
```python
score = correct_count / total_words
```

**示例**:
- 游戏有5个单词需要填写
- Agent答对了3个
- Score = 3/5 = 0.6
- Success = True (因为 score > 0)

**论文指标**:
- **Average Score** (平均得分): 所有样本的平均score
- **Accuracy** (准确率): success_count / total_count

**特点**:
- ✅ 支持部分正确（partial credit）
- ✅ 答对1个就算成功
- ✅ 适合评估推理能力

---

### 2. Alphabetical Sorting (Word Path Puzzle) - 22-alphabetical_sorting

**游戏类型**: 单词路径查找（单轮）

**评分公式**:
```python
score = 1.0 if path_correct else 0.0
```

**示例**:
- 在3x3网格中找到目标单词的路径
- 路径必须完全正确才得分
- Score = 1 (完全正确) 或 0 (错误)
- Success = (score > 0)

**论文指标**:
- **Accuracy** (准确率): 完全答对的样本数 / 总样本数

**特点**:
- ❌ 不支持部分正确（all-or-nothing）
- ✅ 必须找到完整的相邻路径
- ✅ 适合评估空间推理

---

### 3. Wordle - 33-wordle

**游戏类型**: 单词猜测游戏（多轮，最多6次）

**评分公式**:
```python
if guessed_correctly_within_6_attempts:
    score = 1.0
else:
    score = 0.0
```

**示例**:
- 6次机会猜测一个5字母单词
- 猜中了：Score = 1, Success = True
- 失败了：Score = 0, Success = False

**论文指标**:
- **Accuracy** (准确率): 成功猜中的样本数 / 总样本数

**特点**:
- ❌ 不支持部分正确（all-or-nothing）
- ✅ 多轮交互，有反馈机制
- ✅ 适合评估迭代推理能力

---

## 🔍 如何查看结果

### 推荐方式：使用专用脚本

```bash
cd /mnt/f/youtu-agent

# 🎯 查看所有游戏的对比结果（最推荐）
uv run python scripts/view_korgym_results.py --game all

# 输出示例：
# ================================================================================
# 对比分析: 基线 vs 训练后
# ================================================================================
# 
# 实验结果: word_puzzle_baseline_eval
# 游戏: 8-word_puzzle
# 总样本数: 50
# 成功数: 12
# 准确率 (Accuracy): 24.00%
# 平均得分 (Avg Score): 0.3240
# ...
# 提升统计
# ================================================================================
# 准确率提升: +15.00% (从 24.00% 到 39.00%)
# 平均得分提升: +0.1200 (从 0.3240 到 0.4440)
```

### 单个游戏查看

```bash
# Word Puzzle
uv run python scripts/view_korgym_results.py --game word_puzzle

# Alphabetical Sorting
uv run python scripts/view_korgym_results.py --game alphabetical_sorting

# Wordle
uv run python scripts/view_korgym_results.py --game wordle
```

### 查看单个实验的详细信息

```bash
# 基线评估详情
uv run python scripts/view_korgym_results.py --exp_id word_puzzle_baseline_eval --detailed

# 训练后评估详情
uv run python scripts/view_korgym_results.py --exp_id word_puzzle_practice_eval --detailed

# 输出示例：
# 详细样本信息 (前10个)
# ================================================================================
# 样本 1:
#   Seed: 1
#   Correct: True
#   Score: 0.6000
#   Action: ["happy", "world", "music"]...
```

### 对比两个实验

```bash
# 自定义对比
uv run python scripts/view_korgym_results.py --compare \
    word_puzzle_baseline_eval \
    word_puzzle_practice_eval
```

---

## 📈 理解输出指标

### 关键指标说明

| 指标 | 说明 | 适用游戏 | 论文中的用法 |
|------|------|----------|--------------|
| **Accuracy** | 成功样本数 / 总样本数 | All | 主要评价指标 |
| **Average Score** | 平均得分 (0-1) | Word Puzzle主要 | 细粒度评价 |
| **Success Count** | 成功的样本数 (score > 0) | All | 辅助指标 |
| **Total Score** | 所有样本得分之和 | - | 计算用 |

### Word Puzzle 特殊说明

对于Word Puzzle，有两个重要指标：

1. **Accuracy** (准确率):
   - 定义: 至少答对1个单词的样本比例
   - 计算: success_count / total_count
   - 示例: 50个样本中30个至少答对1个单词 = 60%

2. **Average Score** (平均得分):
   - 定义: 所有样本的平均得分
   - 计算: sum(all_scores) / total_count
   - 示例: 50个样本总分18分 = 平均0.36分

**两者的区别**:
```
样本1: 5个单词答对3个 → score=0.6, success=True
样本2: 5个单词答对0个 → score=0.0, success=False
样本3: 5个单词答对1个 → score=0.2, success=True

Accuracy = 2/3 = 66.67%  (2个成功)
Avg Score = (0.6+0.0+0.2)/3 = 0.267  (平均得分)
```

---

## 🐛 常见问题

### 问题1: 准确率显示0%但有样本correct=True

**原因**: 可能是统计脚本的bug或数据库中有混合数据

**解决**:
```bash
# 使用分析脚本查看详情
uv run python scripts/analyze_word_puzzle_results.py --exp_id word_puzzle_baseline_eval

# 清理缓存后重新评估
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

### 问题2: 评估结果被缓存

**症状**: 多次运行评估结果完全一样

**原因**: 数据库中存在旧的评估结果，系统直接读取

**解决**:
```bash
# 查看所有实验
uv run python scripts/clean_experiment_data.py --list

# 清理特定实验
uv run python scripts/clean_experiment_data.py --exp_id \
    word_puzzle_baseline_eval \
    word_puzzle_practice_eval

# 重新评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

### 问题3: Average Score和Accuracy差异很大

**这是正常的！** 对于Word Puzzle：

```
场景A: 大部分样本答对1-2个单词
  → Accuracy: 80% (大部分至少答对1个)
  → Avg Score: 0.30 (平均每道题答对30%)

场景B: 少数样本全对，大部分全错
  → Accuracy: 20% (只有20%至少答对1个)
  → Avg Score: 0.20 (平均得分也是20%)
```

**建议**: 对Word Puzzle同时关注两个指标

---

## 📊 论文中的报告方式

根据论文标准，应该这样报告结果：

### 格式1: 表格形式

| Game | Baseline Acc | Practice Acc | Improvement |
|------|--------------|--------------|-------------|
| Word Puzzle | 24.0% (0.324) | 39.0% (0.444) | +15.0% (+0.120) |
| Alphabetical Sorting | 18.0% | 32.0% | +14.0% |
| Wordle | 12.0% | 20.0% | +8.0% |

注: Word Puzzle括号内为Average Score

### 格式2: 文本描述

```
在Word Puzzle游戏中，基线Agent的准确率为24.0%，平均得分为0.324。
经过分层经验学习后，准确率提升至39.0%，平均得分提升至0.444，
相对提升62.5%（绝对提升15.0%）。
```

---

## 🔗 相关文档

- **完整命令参考**: `KORGYM_THREE_GAMES_COMMANDS.md`
- **清理缓存指南**: `WORD_PUZZLE_CACHE_CLEANUP.md`
- **故障排查**: `WORD_PUZZLE_DIAGNOSIS.md`
- **Zero Accuracy修复**: `WORD_PUZZLE_ZERO_ACCURACY_FIX.md`

---

**记住**: 
1. Word Puzzle关注**Average Score**
2. 其他游戏关注**Accuracy**
3. 评估前一定要**清理缓存**！

















