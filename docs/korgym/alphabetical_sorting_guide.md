# Alphabetical Sorting 游戏实验指南

本文档提供了 Alphabetical Sorting 游戏的 Training-Free GRPO 实验完整流程。

## 📋 实验概述

- **游戏类型**: Alphabetical Sorting（字母顺序排序）
- **训练数据**: 100道题目
- **评估数据**: 50道题目
- **训练方法**: Training-Free GRPO（Group Relative Policy Optimization）
- **模型**: Qwen/Qwen2.5-7B-Instruct

## 🎮 游戏规则

Alphabetical Sorting 是一个排序任务：

- **目标**: 将给定的单词列表按字母顺序排序
- **排序规则**: 标准的字典序（lexicographic order）
  - 逐字母比较
  - 大小写不敏感（通常）
  - 相同前缀时，较短的单词排在前面
- **难度级别**: 1-10（单词数量和复杂度递增）

**示例**:
```
输入: ["dog", "cat", "apple", "banana"]
输出: ["apple", "banana", "cat", "dog"]
```

## 🚀 快速开始

### 步骤 0: 启动游戏服务器

**在独立终端中运行：**
```bash
cd KORGym/game_lib/2-alphabetical_sorting
python game_lib.py -p 8780
```

保持这个终端运行！

### 步骤 1: 准备数据集

```bash
cd /mnt/f/youtu-agent

# 创建数据集
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "2-alphabetical_sorting" \
    --train_count 100 \
    --eval_count 50 \
    --level 5
```

这将创建：
- `KORGym-AlphabeticalSorting-Train-100`（训练集）
- `KORGym-AlphabeticalSorting-Eval-50`（评估集）

### 步骤 2: 基线评估

```bash
uv run python scripts/run_eval.py \
    --config_name korgym/alphabetical_sorting_eval
```

### 步骤 3: Training-Free GRPO 训练

```bash
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym/alphabetical_sorting_practice
```

训练完成后会生成：
- `configs/agents/practice/alphabetical_sorting_practice_agent.yaml`（包含学到的经验）

### 步骤 4: 增强评估

```bash
uv run python scripts/run_eval.py \
    --config_name korgym/alphabetical_sorting_practice_eval
```

### 步骤 5: 查看结果

```bash
# 使用专用的结果查看脚本
uv run python scripts/view_korgym_results.py

# 或手动查看
uv run python scripts/view_experiment_results.py \
    --exp_id alphabetical_sorting_baseline_eval alphabetical_sorting_practice_eval
```

## 📊 配置文件说明

### Agent 配置: `configs/agents/practice/alphabetical_sorting_agent.yaml`

定义了 agent 的基本行为：
- **Instructions**: 字母排序策略和规则
- **Temperature**: 0.0（完全确定性，因为排序有唯一正确答案）
- **Max turns**: 30（允许多步思考）

### Practice 配置: `configs/practice/korgym/alphabetical_sorting_practice.yaml`

定义了训练参数：
- **Epochs**: 2
- **Batch size**: 22（通常设为数据集大小的约1/5）
- **GRPO n**: 5（每题生成5个候选答案）
- **Rollout concurrency**: 4（并发执行数，避免 API 限流）
- **Hierarchical learning**: 启用三层经验学习

### Evaluation 配置: `configs/eval/korgym/alphabetical_sorting_eval.yaml`

定义了评估参数：
- **Dataset**: `KORGym-AlphabeticalSorting-Eval-50`
- **Level**: 5
- **Game port**: 8780

## 🔧 常见问题

### Q1: API 限流（Error 429）

**错误**: `Error code: 429 - TPM limit reached`

这是 Alphabetical Sorting 最常见的问题，因为：
- 任务简单，模型响应快
- 高并发容易触发 API 限流

**解决方案**:

```yaml
# 在 configs/practice/korgym/alphabetical_sorting_practice.yaml 中
practice:
  rollout_concurrency: 4  # 降低并发（从 16 降到 4）
```

```yaml
# 在 configs/agents/practice/alphabetical_sorting_agent.yaml 中
model:
  model: Qwen/Qwen2.5-7B-Instruct  # 使用较小模型（从 72B 降到 7B）
```

### Q2: 经验提取失败或数量少

**现象**: 训练后只生成了很少的经验（如 3 条而不是预期的 6-7 条）

**原因**: 
1. 大部分 rollout 失败（API 限流）
2. 层次经验学习未正确启用

**解决方案**:

```yaml
# 确保 hierarchical_learning 在 practice: 块下，而不是顶层
practice:
  # ... 其他参数 ...
  hierarchical_learning:
    enabled: true
    levels:
      - name: "L0"
        description: "案例级别：具体排序错误和成功案例"
      - name: "L1"  
        description: "模式级别：字母比较规则和排序策略"
      - name: "L2"
        description: "元认知级别：通用比较和排序原理"
```

### Q3: 缓存问题

**现象**: 修改配置后结果没有变化

**解决方案**:
```bash
# 清理旧的经验和评估结果
uv run python scripts/clean_experiment_data.py \
    --exp_id alphabetical_sorting_baseline_eval alphabetical_sorting_practice_eval

# 删除旧的 agent 配置
rm configs/agents/practice/alphabetical_sorting_practice_agent.yaml

# 重新运行训练
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym/alphabetical_sorting_practice
```

### Q4: 游戏服务器崩溃

**解决方案**:
```bash
# 重启服务器
cd KORGym/game_lib/2-alphabetical_sorting
python game_lib.py -p 8780
```

## 📈 预期结果

基于实验经验：

| 指标 | 基线（无经验） | 增强（有经验） | 期望提升 |
|-----|--------------|--------------|---------|
| 准确率 | 60-80% | 70-90% | +10-15% |
| 平均分 | 0.7-0.9 | 0.8-0.95 | +0.1-0.15 |

**注意**: 
- Alphabetical Sorting 相对简单，基线准确率通常较高
- 主要改进在于处理边界情况（相同前缀、特殊字符等）
- 层次经验学习可以提取通用的字母比较原理

## 🎯 优化建议

### 1. 避免 API 限流（最重要！）

```yaml
# configs/practice/korgym/alphabetical_sorting_practice.yaml
practice:
  rollout_concurrency: 2  # 进一步降低并发
  
model:
  model: Qwen/Qwen2.5-7B-Instruct  # 使用小模型
  model_settings:
    timeout: 60  # 增加超时时间
```

### 2. 优化 Agent Prompt

强调关键规则：
```yaml
agent:
  instructions: |-
    You are an expert at alphabetical sorting.
    
    Rules:
    1. Compare words letter by letter from left to right
    2. Earlier letters in the alphabet come first (a < b < c ... < z)
    3. If one word is a prefix of another, the shorter word comes first
    4. Case-insensitive comparison (A = a)
    
    Output format: ["word1", "word2", ...]
```

### 3. 调整训练参数

```yaml
practice:
  grpo_n: 3  # 降低候选数（排序任务不需要太多探索）
  batch_size: 30  # 增加批次大小
  epochs: 1  # 可能只需要1个epoch
```

### 4. 层次经验学习配置

Alphabetical Sorting 非常适合层次经验学习：

- **L0 (案例级)**:
  - "在排序 ['dog', 'cat'] 时，发现 'cat' 的首字母 'c' < 'd'，因此应放在前面"
  
- **L1 (模式级)**:
  - "当两个单词有相同前缀时，比较后续字母"
  - "字母表顺序: a < b < c < ... < z"
  
- **L2 (元认知级)**:
  - "排序本质是建立全序关系"
  - "传递性: 如果 A < B 且 B < C，则 A < C"

## 📚 评分机制

Alphabetical Sorting 的评分方式：

```python
# 完全正确才算成功
if sorted_result == expected_result:
    score = 1.0
else:
    score = 0.0
```

- 这是一个"全或无"的任务
- 只有完全正确才得分
- 部分正确不计分

## 🧪 调试技巧

### 查看具体的排序错误

```bash
# 查看评估详情
uv run python scripts/view_experiment_results.py \
    --exp_id alphabetical_sorting_practice_eval \
    --show_details
```

### 查看学到的经验

```bash
# 查看生成的 agent 配置
cat configs/agents/practice/alphabetical_sorting_practice_agent.yaml

# 提取经验部分
cat configs/agents/practice/alphabetical_sorting_practice_agent.yaml | \
    sed -n '/experiences:/,/^[^ ]/p'
```

### 测试单个样本

```python
# 使用 Python 交互式测试
from utu.agents import SimpleAgent

async with SimpleAgent(config="practice/alphabetical_sorting_practice_agent") as agent:
    result = await agent.chat("Sort these words: ['zebra', 'apple', 'monkey']")
    print(result)
```

## 🔗 相关资源

- [KORGym 主页](https://razor233.github.io/KORGYM_HomePage/)
- [Training-Free GRPO 论文](../advanced/papers/training_free_grpo.pdf)
- [实验命令汇总](../../KORGYM_THREE_GAMES_COMMANDS.md)
- [KORGym 集成指南](index.md)
- [API 限流问题详解](../../ALPHABETICAL_SORTING_CACHE_ISSUE.md)

## 📝 相关文档

- [Hierarchical Learning Fix](../../HIERARCHICAL_LEARNING_FIX.md) - 层次学习配置修复
- [Three Games Config Fix](../../THREE_GAMES_CONFIG_FIX_SUMMARY.md) - 三个游戏的配置修复总结

## 🆘 获取帮助

如遇到问题：
1. **首先检查**: 是否遇到 API 限流（429 错误）
2. **查看日志**: `logs/utu.log`
3. **验证配置**: 确保 `hierarchical_learning` 在正确位置
4. **检查服务器**: 确保游戏服务器正常运行
5. **参考修复文档**: 查看根目录的 `ALPHABETICAL_SORTING_*` 文档











