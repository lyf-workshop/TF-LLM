# Word Puzzle 游戏实验指南

本文档提供了 Word Puzzle 游戏的 Training-Free GRPO 实验完整流程。

## 📋 实验概述

- **游戏类型**: Word Puzzle（单词填字游戏）
- **训练数据**: 100道题目
- **评估数据**: 50道题目
- **训练方法**: Training-Free GRPO（Group Relative Policy Optimization）
- **模型**: Qwen/Qwen2.5-7B-Instruct

## 🎮 游戏规则

Word Puzzle 是一个约束满足问题：

- **目标**: 在给定的字母网格中填入单词，使其满足所有约束
- **约束类型**:
  - 水平和垂直单词必须相互交叉
  - 填入的单词必须是有效的英文单词
  - 必须满足给定的线索
- **难度级别**: 1-5（数字越大，网格越大，约束越复杂）

## 🚀 快速开始

### 步骤 0: 启动游戏服务器

**在独立终端中运行：**
```bash
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

保持这个终端运行！

### 步骤 1: 准备数据集

```bash
cd /mnt/f/youtu-agent

# 创建数据集
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "8-word_puzzle" \
    --train_count 100 \
    --eval_count 50 \
    --level 3
```

这将创建：
- `KORGym-WordPuzzle-Train-100`（训练集）
- `KORGym-WordPuzzle-Eval-50`（评估集）

### 步骤 2: 基线评估

```bash
uv run python scripts/run_eval.py \
    --config_name korgym/word_puzzle_eval
```

### 步骤 3: Training-Free GRPO 训练

```bash
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym/word_puzzle_practice
```

训练完成后会生成：
- `configs/agents/practice/word_puzzle_practice_agent.yaml`（包含学到的经验）

### 步骤 4: 增强评估

```bash
uv run python scripts/run_eval.py \
    --config_name korgym/word_puzzle_practice_eval
```

### 步骤 5: 查看结果

```bash
# 使用专用的结果查看脚本
uv run python scripts/view_korgym_results.py

# 或手动查看
uv run python scripts/view_experiment_results.py \
    --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval
```

## 📊 配置文件说明

### Agent 配置: `configs/agents/practice/word_puzzle_agent.yaml`

定义了 agent 的基本行为：
- **Instructions**: Word Puzzle 解题策略
- **Temperature**: 0.3（较低温度，偏向确定性）
- **Max turns**: 50（允许多步推理）

### Practice 配置: `configs/practice/korgym/word_puzzle_practice.yaml`

定义了训练参数：
- **Epochs**: 2（训练周期）
- **Batch size**: 20（每批样本数）
- **GRPO n**: 5（每题生成5个候选解）
- **Rollout concurrency**: 4（并发数）
- **Hierarchical learning**: 启用三层经验学习（L0/L1/L2）

### Evaluation 配置: `configs/eval/korgym/word_puzzle_eval.yaml`

定义了评估参数：
- **Dataset**: `KORGym-WordPuzzle-Eval-50`
- **Level**: 3（难度级别）
- **Game port**: 8775

## 🔧 常见问题

### Q1: 游戏服务器连接失败

**错误**: `Failed to generate game instance: 500 Server Error`

**解决方案**:
```bash
# 重启游戏服务器
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# 检查端口占用
lsof -i :8775  # Linux/WSL
netstat -ano | findstr :8775  # Windows
```

### Q2: 评估准确率为 0%

**原因**: 可能的问题：
1. Level 配置不匹配（训练和评估使用不同难度）
2. 缓存了旧的评估结果

**解决方案**:
```bash
# 1. 检查配置文件中的 level 参数
# 训练: configs/practice/korgym/word_puzzle_practice.yaml
# 评估: configs/eval/korgym/word_puzzle_eval.yaml
# 确保两者的 level 相同

# 2. 清理缓存的评估结果
uv run python scripts/clean_experiment_data.py \
    --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval

# 3. 重新运行评估
uv run python scripts/run_eval.py \
    --config_name korgym/word_puzzle_practice_eval
```

### Q3: 数据集已存在

**解决方案**:
```bash
# 删除旧数据集并重新创建
uv run python scripts/clean_and_recreate_datasets.py
```

## 📈 预期结果

基于实验经验：

| 指标 | 基线（无经验） | 增强（有经验） | 期望提升 |
|-----|--------------|--------------|---------|
| 准确率 | 20-40% | 30-50% | +10-15% |
| 平均分 | 0.3-0.5 | 0.4-0.6 | +0.1-0.2 |

**注意**: 
- Word Puzzle 的分数计算基于填对的格子比例
- 难度越高（level 越大），基线准确率越低
- 层次经验学习（L0/L1/L2）可以提取不同抽象层次的解题策略

## 🎯 优化建议

如果结果不理想，可以尝试：

### 1. 调整难度级别

```yaml
# 在 configs/practice/korgym/word_puzzle_practice.yaml
data:
  level: 2  # 从 3 降低到 2
```

### 2. 调整 Agent Prompt

在 `configs/agents/practice/word_puzzle_agent.yaml` 中：
- 添加更多示例
- 强调约束检查
- 提供解题步骤

### 3. 调整 GRPO 参数

```yaml
# 在 configs/practice/korgym/word_puzzle_practice.yaml
practice:
  grpo_n: 8  # 增加候选解数量
  epochs: 3  # 增加训练轮数
  batch_size: 30  # 增加批次大小
```

### 4. 启用/调整层次经验学习

```yaml
practice:
  hierarchical_learning:
    enabled: true
    levels:
      - name: "L0"
        description: "具体案例级别的经验"
      - name: "L1"
        description: "模式级别的经验"
      - name: "L2"
        description: "元认知级别的经验"
```

## 📚 评分机制

Word Puzzle 的评分方式：

```python
score = correct_cells / total_cells
```

- `correct_cells`: 填对的格子数量
- `total_cells`: 总格子数量
- 分数范围: 0.0 - 1.0
- 完全正确时 `score = 1.0`

## 🔗 相关资源

- [KORGym 主页](https://razor233.github.io/KORGYM_HomePage/)
- [Training-Free GRPO 论文](../advanced/papers/training_free_grpo.pdf)
- [实验命令汇总](../../KORGYM_THREE_GAMES_COMMANDS.md)
- [KORGym 集成指南](index.md)

## 🆘 获取帮助

如遇到问题：
1. 查看日志文件：`logs/utu.log`
2. 使用 `--help` 查看命令参数
3. 参考其他游戏的配置（Wordle, Alphabetical Sorting）
4. 检查游戏服务器是否正常运行











