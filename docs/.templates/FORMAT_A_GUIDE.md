# [游戏/功能名] 使用指南

> 适用版本：2026-03  
> 前置条件：已完成环境配置，参考 [安装指南](../guides/installation.md)

## 概述

本文档介绍 [游戏/功能名] 的完整使用流程，包括：
- 快速开始（5分钟体验）
- 完整实验流程（数据准备→训练→评估）
- 配置说明
- 常见问题处理

## 快速开始（5分钟）

最短路径体验，仅包含必要命令：

```bash
# 1. 启动游戏服务器（独立终端）
cd KORGym/game_lib/XX-game_name
python game_lib.py -p 8777

# 2. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "XX-game_name"

# 3. 运行基线评估
uv run python scripts/run_eval.py --config_name korgym/game_eval

# 4. 训练（生成经验）
uv run python scripts/run_training_free_GRPO.py --config_name korgym/game_practice

# 5. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/game_practice_eval
```

## 完整流程

### Step 1: 环境准备

[详细步骤...]

### Step 2: 数据集准备

[详细步骤...]

### Step 3: 基线评估

[详细步骤...]

### Step 4: 训练（经验学习）

[详细步骤...]

### Step 5: 增强评估

[详细步骤...]

### Step 6: 结果分析

[详细步骤...]

## 配置说明

### 评估配置

关键配置项说明：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `game_port` | 8777 | 游戏服务器端口 |
| `level` | 3 | 游戏难度/参数 |
| `max_rounds` | 10 | 最大交互轮数 |
| `concurrency` | 4 | 并发评估数 |

### 训练配置

[配置说明...]

## 常见问题

遇到问题请参考 [故障排除指南](../troubleshooting/index.md)：

- [API 限流（429错误）](../troubleshooting/index.md#api-rate-limit-429)
- [服务器500错误](../troubleshooting/index.md#server-500-error)
- [准确率为0%](../troubleshooting/index.md#zero-accuracy)

## 相关文档

- [Training-Free GRPO 原理](../concepts/training_free_grpo.md)
- [分层经验学习机制](../concepts/hierarchical_experience.md)
- [命令速查参考](../reference/commands.md)
- [KORGym 游戏总览](../korgym/index.md)
