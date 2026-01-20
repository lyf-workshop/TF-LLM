# Wordle游戏 - Training-Free GRPO 实验指南

本文档提供了在Wordle游戏上运行Training-Free GRPO实验的完整流程。

## 📋 实验概述

- **游戏类型**: Wordle（猜单词游戏）
- **训练数据**: 100道题目
- **评估数据**: 120道题目
- **训练方法**: Training-Free GRPO（Group Relative Policy Optimization）
- **模型**: Qwen/Qwen2.5-7B-Instruct

## 🎮 游戏规则

Wordle是一个猜单词游戏：
- 最多10次尝试机会
- 每次猜测后会获得反馈：
  - ✅ **正确位置**: 字母在单词中且位置正确
  - 🟨 **错误位置**: 字母在单词中但位置错误
  - ⬜ **不在单词中**: 字母不在单词中
- 单词长度: 4-12个字母（随机）

## 🚀 快速开始

### 方式一：一键运行（推荐）

```bash
cd /mnt/f/youtu-agent

# 转换行尾（如果在WSL中）
sed -i 's/\r$//' scripts/run_wordle_full_experiment.sh
sed -i 's/\r$//' scripts/clean_wordle_data.sh

# 添加执行权限
chmod +x scripts/run_wordle_full_experiment.sh
chmod +x scripts/clean_wordle_data.sh

# 在一个终端启动游戏服务器
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8765

# 在另一个终端运行完整实验
bash scripts/run_wordle_full_experiment.sh
```

### 方式二：手动执行（分步控制）

#### 步骤0：启动游戏服务器

**在一个独立终端中运行：**
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8765
```

保持这个终端运行！

#### 步骤1：创建数据集

```bash
cd /mnt/f/youtu-agent

# 创建训练数据集（100题）
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-Wordle-Train-100" \
    --num_samples 100

# 创建评估数据集（120题）
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-Wordle-Eval-120" \
    --num_samples 120

# 验证数据集
uv run python scripts/view_dataset.py \
    --dataset_name "KORGym-Wordle-Eval-120" \
    --limit 5
```

#### 步骤2：基线评估（未学习经验）

```bash
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/wordle_agent \
    --dataset_name "KORGym-Wordle-Eval-120" \
    --exp_id wordle_baseline_120 \
    --game_port 8765
```

**查看基线结果：**
```bash
cat workspace/korgym_eval/wordle_baseline_120.json | python -m json.tool | grep -E "average_score|success_rate"
```

#### 步骤3：GRPO训练（总结经验）

```bash
uv run python scripts/run_training_free_GRPO.py \
    --config_name wordle_qwen_grpo
```

训练完成后会生成：
- `configs/agents/practice/wordle_qwen_grpo_agent.yaml` （包含学到的经验）

**查看学到的经验：**
```bash
cat configs/agents/practice/wordle_qwen_grpo_agent.yaml | grep -A 5 "experiences:"
```

#### 步骤4：增强评估（使用学到的经验）

```bash
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/wordle_qwen_grpo_agent \
    --dataset_name "KORGym-Wordle-Eval-120" \
    --exp_id wordle_enhanced_120 \
    --game_port 8765
```

**查看增强结果：**
```bash
cat workspace/korgym_eval/wordle_enhanced_120.json | python -m json.tool | grep -E "average_score|success_rate"
```

#### 步骤5：对比结果

```bash
python scripts/compare_korgym_scores.py \
    workspace/korgym_eval/wordle_baseline_120.json \
    workspace/korgym_eval/wordle_enhanced_120.json
```

## 🧹 清理数据

如果需要重新开始实验：

```bash
# 清理所有Wordle相关数据
bash scripts/clean_wordle_data.sh

# 或者手动清理
rm -f workspace/korgym_eval/wordle_*.json
rm -f configs/agents/practice/wordle_qwen_grpo_agent.yaml
# 还需要从数据库中删除数据集（使用clean脚本）
```

## 📊 配置文件说明

### Agent配置：`configs/agents/practice/wordle_agent.yaml`

定义了agent的基本行为：
- **Instructions**: Wordle游戏策略指导
- **Temperature**: 0.7（平衡探索与利用）
- **Max turns**: 15（允许多轮交互）

### Practice配置：`configs/practice/wordle_qwen_grpo.yaml`

定义了训练参数：
- **Epochs**: 2（2个训练周期）
- **Batch size**: 50（每批50个样本）
- **GRPO n**: 5（每个样本生成5个rollout）
- **Rollout concurrency**: 16（并发处理）
- **Task timeout**: 300秒（每局游戏超时）

## 🔧 常见问题

### Q1: 游戏服务器连接失败

**错误**: `Connection refused` 或 `Failed to connect to game server`

**解决**:
```bash
# 确保游戏服务器正在运行
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8765

# 检查端口是否被占用
lsof -i :8765  # Linux/WSL
netstat -ano | findstr :8765  # Windows
```

### Q2: 数据集已存在

**错误**: `Dataset already exists`

**解决**:
```bash
# 删除旧数据集
bash scripts/clean_wordle_data.sh

# 或使用不同的数据集名称
--dataset_name "KORGym-Wordle-Train-100-v2"
```

### Q3: 训练进度缓慢

**原因**: Wordle是多轮交互游戏，每局可能需要多次猜测

**优化**:
- 减少 `rollout_concurrency`（如果内存不足）
- 增加 `rollout_concurrency`（如果CPU/GPU充足）
- 调整 `task_timeout`

### Q4: 行尾格式错误（WSL）

**错误**: `$'\r': command not found`

**解决**:
```bash
# 转换所有脚本的行尾
sed -i 's/\r$//' scripts/run_wordle_full_experiment.sh
sed -i 's/\r$//' scripts/clean_wordle_data.sh
```

## 📈 预期结果

基于KORGym论文和类似任务的经验：

| 指标 | 基线（无经验） | 增强（有经验） | 期望提升 |
|-----|--------------|--------------|---------|
| 平均分 | 30-50% | 40-60% | +10-20% |
| 成功率 | 30-50% | 40-60% | +10-20% |

**注意**: Wordle是多轮交互游戏，成功率取决于：
- 初始猜测策略
- 反馈利用能力
- 词汇量和模式识别

## 🎯 优化建议

如果基线分数较低（<30%），可以尝试：

1. **调整Prompt**
   - 添加更多示例
   - 强调常见字母（e, a, r, i, o, t）
   - 提供字母频率表

2. **调整Temperature**
   ```yaml
   temperature: 0.3  # 更确定性的策略
   ```

3. **增加训练数据**
   ```bash
   --num_samples 200  # 增加到200题
   ```

4. **调整GRPO参数**
   ```yaml
   grpo_n: 8  # 增加rollout数量
   epochs: 3  # 增加训练轮数
   ```

## 📚 参考资料

- [KORGym项目主页](https://razor233.github.io/KORGYM_HomePage/)
- [KORGym论文](https://arxiv.org/abs/2505.14552)
- [Wordle游戏规则](https://www.nytimes.com/games/wordle/index.html)

## 🆘 获取帮助

如遇到问题：
1. 查看终端输出的错误信息
2. 检查 `logs/` 目录下的日志文件
3. 使用 `--help` 查看命令参数
4. 参考其他游戏的配置文件（如 `alphabetical_sorting`）



