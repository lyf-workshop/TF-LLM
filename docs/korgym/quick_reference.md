# KORGym 快速参考

本文档提供 KORGym 实验的快速命令和配置参考。

## 🎮 游戏端口和基本信息

| 游戏 | 目录 | 端口 | 推荐难度 | 数据集前缀 |
|------|------|------|---------|----------|
| Wordle | `33-wordle` | 8765 | 5 | `KORGym-Wordle` |
| Word Puzzle | `8-word_puzzle` | 8775 | 3 | `KORGym-WordPuzzle` |
| Alphabetical Sorting | `2-alphabetical_sorting` | 8780 | 5 | `KORGym-AlphabeticalSorting` |

## ⚡ 快速命令

### 游戏服务器

```bash
# Wordle
cd KORGym/game_lib/33-wordle && python game_lib.py -p 8765

# Word Puzzle
cd KORGym/game_lib/8-word_puzzle && python game_lib.py -p 8775

# Alphabetical Sorting
cd KORGym/game_lib/2-alphabetical_sorting && python game_lib.py -p 8780
```

### 数据集准备

```bash
# Wordle
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "33-wordle" --train_count 100 --eval_count 50 --level 5

# Word Puzzle
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "8-word_puzzle" --train_count 100 --eval_count 50 --level 3

# Alphabetical Sorting
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "2-alphabetical_sorting" --train_count 100 --eval_count 50 --level 5
```

### 基线评估

```bash
# Wordle
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# Word Puzzle
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# Alphabetical Sorting
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval
```

### Training-Free GRPO 训练

```bash
# Wordle
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# Word Puzzle
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice

# Alphabetical Sorting
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice
```

### 增强评估（训练后）

```bash
# Wordle
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# Word Puzzle
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval

# Alphabetical Sorting
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
```

### 查看结果

```bash
# 使用专用的 KORGym 结果查看器
uv run python scripts/view_korgym_results.py

# 查看特定实验对比
uv run python scripts/view_experiment_results.py \
    --exp_id wordle_baseline_eval wordle_practice_eval

# 分析前N题（Wordle示例）
uv run python scripts/analyze_wordle_top20.py \
    --exp_id wordle_practice_eval --top_n 20
```

## 📋 关键配置参数

### Practice 配置（`configs/practice/korgym/*_practice.yaml`）

```yaml
practice:
  epochs: 2                    # 训练轮数
  batch_size: 20               # 每批样本数
  grpo_n: 5                    # 每题生成的候选解数量
  rollout_concurrency: 4       # 并发数（重要！避免 API 限流）
  task_timeout: 300            # 每个任务超时时间（秒）
  
  # 层次经验学习（必须在 practice 块内！）
  hierarchical_learning:
    enabled: true
    levels:
      - name: "L0"
        description: "案例级别经验"
      - name: "L1"
        description: "模式级别经验"
      - name: "L2"
        description: "元认知级别经验"

data:
  dataset: "KORGym-Wordle-Train-100"  # 训练数据集
  level: 5                     # 难度级别（必须与评估一致！）
  game_port: 8765              # 游戏服务器端口
```

### Agent 配置（`configs/agents/practice/*_agent.yaml`）

```yaml
agent:
  name: wordle_agent
  instructions: |
    [游戏规则和策略提示]
  
max_turns: 100                 # 最大交互轮数

model:
  model: Qwen/Qwen2.5-7B-Instruct  # 推荐使用 7B 而非 72B
  model_settings:
    temperature: 0.5           # Wordle: 0.5, Word Puzzle: 0.3, Sorting: 0.0
    top_p: 0.95
    extra_args:
      timeout: 3000
```

### Eval 配置（`configs/eval/korgym/*_eval.yaml`）

```yaml
exp_id: wordle_baseline_eval   # 实验 ID

data:
  dataset: "KORGym-Wordle-Eval-50"  # 评估数据集
  type: "single"
  level: 5                     # 必须与训练一致！
  game_port: 8765              # 游戏服务器端口

agent_config: "practice/wordle_agent"  # Agent 配置路径
```

## 🔧 常见调优参数

### 避免 API 限流（Alphabetical Sorting 最需要）

```yaml
# configs/practice/korgym/alphabetical_sorting_practice.yaml
practice:
  rollout_concurrency: 4  # 从 16 降到 4
  
model:
  model: Qwen/Qwen2.5-7B-Instruct  # 从 72B 降到 7B
```

### 提高训练质量

```yaml
practice:
  epochs: 3              # 增加训练轮数
  grpo_n: 8             # 增加候选解数量
  batch_size: 30        # 增加批次大小
```

### 调整 Agent 确定性

```yaml
model:
  model_settings:
    temperature: 0.0   # 完全确定性（适合 Sorting）
    temperature: 0.3   # 较低探索（适合 Word Puzzle）
    temperature: 0.5   # 平衡（适合 Wordle）
    temperature: 0.7   # 较高探索
```

## 🧹 清理命令

### 清理数据集

```bash
# 清理并重新创建所有 KORGym 数据集
uv run python scripts/clean_and_recreate_datasets.py

# 手动删除特定数据集（需要数据库操作）
```

### 清理评估结果

```bash
# 删除特定实验结果
uv run python scripts/clean_experiment_data.py \
    --exp_id wordle_baseline_eval wordle_practice_eval

# 验证清理
uv run python scripts/verify_clean.py \
    --exp_id wordle_baseline_eval
```

### 清理训练产物

```bash
# 删除训练生成的 agent 配置
rm configs/agents/practice/wordle_practice_agent.yaml
rm configs/agents/practice/word_puzzle_practice_agent.yaml
rm configs/agents/practice/alphabetical_sorting_practice_agent.yaml
```

### 完全重置

```bash
# 1. 停止游戏服务器（Ctrl+C）

# 2. 清理数据
uv run python scripts/clean_and_recreate_datasets.py
uv run python scripts/clean_experiment_data.py --exp_id \
    wordle_baseline_eval wordle_practice_eval \
    word_puzzle_baseline_eval word_puzzle_practice_eval \
    alphabetical_sorting_baseline_eval alphabetical_sorting_practice_eval

# 3. 删除训练产物
rm configs/agents/practice/*_practice_agent.yaml

# 4. 重新开始实验
```

## 🔍 调试命令

### 检查游戏服务器

```bash
# Linux/WSL
lsof -i :8765
lsof -i :8775
lsof -i :8780

# Windows
netstat -ano | findstr :8765
netstat -ano | findstr :8775
netstat -ano | findstr :8780
```

### 测试服务器连接

```bash
# Wordle
curl http://localhost:8765/generate -X POST \
    -H "Content-Type: application/json" \
    -d '{"seed": 1}'

# Word Puzzle
curl http://localhost:8775/generate -X POST \
    -H "Content-Type: application/json" \
    -d '{"seed": 1}'

# Alphabetical Sorting
curl http://localhost:8780/generate -X POST \
    -H "Content-Type: application/json" \
    -d '{"seed": 1}'
```

### 查看日志

```bash
# 查看最新日志
tail -100 logs/utu.log

# 搜索错误
cat logs/utu.log | grep -i "error\|exception\|failed"

# 查看特定实验日志
cat logs/utu.log | grep "wordle_practice"

# 查看 API 限流
cat logs/utu.log | grep "429\|rate limit"
```

### 列出数据集

```bash
# 列出所有数据集
uv run python scripts/list_datasets.py

# 只看 KORGym
uv run python scripts/list_datasets.py | grep KORGym
```

### 查看数据集内容

```bash
# 查看前5个样本
uv run python scripts/view_dataset.py \
    --dataset_name "KORGym-Wordle-Eval-50" \
    --limit 5

# 查看特定样本
uv run python scripts/view_dataset.py \
    --dataset_name "KORGym-Wordle-Eval-50" \
    --index 0
```

## 📊 预期结果参考

| 游戏 | 基线准确率 | 增强准确率 | 期望提升 | 基线平均分 | 增强平均分 |
|------|-----------|-----------|---------|-----------|-----------|
| Wordle | 30-50% | 40-60% | +10-20% | 0.35-0.55 | 0.45-0.65 |
| Word Puzzle | 20-40% | 30-50% | +10-15% | 0.3-0.5 | 0.4-0.6 |
| Alphabetical Sorting | 60-80% | 70-90% | +10-15% | 0.7-0.9 | 0.8-0.95 |

## 🚦 运行前检查清单

在运行实验前，确保：

- [ ] 游戏服务器正在运行且端口正确
- [ ] `.env` 文件已配置 API keys
- [ ] 虚拟环境已激活：`source .venv/bin/activate` 或 `uv` 前缀
- [ ] 依赖已安装：`uv sync --all-extras`
- [ ] 配置文件中的 `level` 参数在训练和评估中一致
- [ ] `rollout_concurrency` 已设置为合理值（推荐 4）
- [ ] `hierarchical_learning` 在 `practice:` 块内（如需要）
- [ ] 模型配置合理（推荐 7B 而非 72B）

## 🔗 完整文档

- [Wordle 完整指南](wordle_guide.md)
- [Word Puzzle 完整指南](word_puzzle_guide.md)
- [Alphabetical Sorting 完整指南](alphabetical_sorting_guide.md)
- [常见问题排查](troubleshooting.md)
- [完整命令参考](../../KORGYM_THREE_GAMES_COMMANDS.md)

## ⚠️ 最常见的三个问题

1. **Alphabetical Sorting 遇到 API 限流（429）**
   - 解决：降低 `rollout_concurrency` 到 4，使用 7B 模型

2. **Word Puzzle 评估准确率 0%**
   - 解决：检查训练和评估的 `level` 是否一致，清理缓存结果

3. **经验数量少（只有 3 条而不是 6-7 条）**
   - 解决：确保 `hierarchical_learning` 在 `practice:` 块内，不在顶层






