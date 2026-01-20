# 分层经验学习系统 - 完整运行指南

## 📋 目录

1. [系统概述](#系统概述)
2. [前置准备](#前置准备)
3. [快速开始](#快速开始)
4. [完整运行流程](#完整运行流程)
5. [配置说明](#配置说明)
6. [结果查看](#结果查看)
7. [常见问题](#常见问题)

---

## 系统概述

### 核心功能

本系统实现了三层分层经验学习机制：

- **L0（案例级）**：从单个问题的推理过程中提取具体教训
- **L1（模式级）**：从 5 个 L0 案例中抽象出通用策略
- **L2（元策略级）**：从 3 个 L1 模式 + 对应的所有 L0 案例中提炼跨任务原则

### 关键改进

**L2 生成基于 L1 + L0 双重输入**：
- 传统方法：L2 = LLM(L1_batch)
- 本系统：L2 = LLM(L1_batch + source_L0)
- 优势：避免过度抽象，保持原则的实用性和可解释性

---

## 前置准备

### 1. 环境要求

```bash
# WSL/Linux 环境
cd /mnt/f/youtu-agent

# 确保虚拟环境激活
source .venv/bin/activate

# 或使用 uv（推荐）
uv sync
```

### 2. 数据集准备

确保数据集已加载到数据库：

```bash
# 检查数据集是否存在
sqlite3 test.db "SELECT name, COUNT(*) FROM dataset GROUP BY name;"

# 应该看到：
# ZebraLogic-Medium-30|30
# ZebraLogic-Easy-30|30
```

如果数据集不存在，请先加载：

```bash
uv run python scripts/data/load_dataset.py --dataset ZebraLogic-Medium-30
uv run python scripts/data/load_dataset.py --dataset ZebraLogic-Easy-30
```

### 3. 配置文件检查

确保以下文件存在：

```bash
ls configs/practice/medium_reasoning_hierarchical_num1.yaml
ls configs/agents/practice/logic_agent_hierarchical_learning.yaml
ls configs/prompts/hierarchical_critique.yaml
ls configs/eval/logic/easy_base_hierarchical.yaml
ls configs/eval/logic/medium_base_hierarchical.yaml
```

---

## 快速开始

### 最简单的运行方式

```bash
cd /mnt/f/youtu-agent

# 1. 运行训练（生成分层经验）
uv run python scripts/run_training_free_GRPO.py \
  --config_name medium_reasoning_hierarchical_num1

# 2. 等待训练完成（约 30-60 分钟，取决于 LLM 速度）

# 3. 评估训练后的 agent
uv run python scripts/run_eval.py \
  --config_name logic/easy_practice_hierarchical_num1
```

---

## 完整运行流程

### Step 1: 基线评估（可选但推荐）

在训练前先评估基线性能，用于对比：

```bash
# 在 Easy 数据集上评估基线
uv run python scripts/run_eval.py \
  --config_name logic/easy_base_hierarchical

# 在 Medium 数据集上评估基线
uv run python scripts/run_eval.py \
  --config_name logic/medium_base_hierarchical
```

**预期结果**：
- 评估结果保存在数据库中
- exp_id: `qwen_baseline_hierarchical_easy` / `qwen_baseline_hierarchical_medium`
- Pass@1 约 30-40%

### Step 2: 训练（生成分层经验）

```bash
cd /mnt/f/youtu-agent

uv run python scripts/run_training_free_GRPO.py \
  --config_name medium_reasoning_hierarchical_num1
```

**训练过程日志**：

```
2025-12-23 10:00:00 [INFO] Starting experience generation...
2025-12-23 10:00:01 [INFO] Initializing hierarchical experience manager (L0/L1/L2)...
2025-12-23 10:00:01 [INFO] Hierarchical experience manager initialized
2025-12-23 10:00:01 [INFO] Training-free GRPO components built successfully

Epoch 1/3, Batch 1/1:
2025-12-23 10:05:00 [INFO] Step 0 completed. New experiences added: 9
2025-12-23 10:05:00 [INFO] Processing hierarchical experiences for step 0...
2025-12-23 10:05:01 [INFO] Added 9 L0 experiences (total: 9)
2025-12-23 10:05:01 [INFO] Hierarchical processing complete. L0=9, L1=0, L2=0

Epoch 2/3, Batch 1/1:
2025-12-23 10:15:00 [INFO] Step 1 completed. New experiences added: 14
2025-12-23 10:15:00 [INFO] Processing hierarchical experiences for step 1...
2025-12-23 10:15:01 [INFO] Added 14 L0 experiences (total: 23)
2025-12-23 10:15:02 [INFO] Generating L1 from 5 L0 experiences...
2025-12-23 10:15:05 [INFO] Generated L1_0: Use a structured tracking method...
2025-12-23 10:15:06 [INFO] Generating L1 from 5 L0 experiences...
2025-12-23 10:15:09 [INFO] Generated L1_1: Apply systematic constraint enforcement...
2025-12-23 10:15:09 [INFO] Hierarchical processing complete. L0=23, L1=2, L2=0

Epoch 3/3, Batch 1/1:
2025-12-23 10:25:00 [INFO] Step 2 completed. New experiences added: 15
2025-12-23 10:25:00 [INFO] Processing hierarchical experiences for step 2...
2025-12-23 10:25:01 [INFO] Added 15 L0 experiences (total: 38)
2025-12-23 10:25:02 [INFO] Generating L1 from 5 L0 experiences...
2025-12-23 10:25:05 [INFO] Generated L1_2: Use a grid to systematically track...
2025-12-23 10:25:06 [INFO] Generating L2 from 3 L1 + 15 L0 experiences...
2025-12-23 10:25:12 [INFO] Generated L2_0: Principle: Prioritize constraint validation...
2025-12-23 10:25:12 [INFO] Hierarchical processing complete. L0=38, L1=3, L2=1

2025-12-23 10:25:13 [INFO] Using hierarchical experiences (L0/L1/L2)
2025-12-23 10:25:13 [INFO] Added 14 hierarchical experiences (L2=1, L1=3, L0=10)
2025-12-23 10:25:13 [INFO] Agent configuration saved to: configs/agents/practice/medium_reasoning_hierarchical_num1_agent.yaml
2025-12-23 10:25:13 [INFO] Experience generation completed successfully
```

**生成的文件**：
- Agent 配置：`configs/agents/practice/medium_reasoning_hierarchical_num1_agent.yaml`
- 经验 JSON：`workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json`

### Step 3: 训练后评估

```bash
# 在 Easy 数据集上评估（测试跨难度迁移）
uv run python scripts/run_eval.py \
  --config_name logic/easy_practice_hierarchical_num1

# 在 Medium 数据集上评估（测试同难度提升）
uv run python scripts/run_eval.py \
  --config_name logic/medium_practice_hierarchical_num1
```

**预期结果**：
- Pass@1 提升 5-15%
- L2 经验应该带来更好的跨难度迁移

### Step 4: 结果对比

```bash
# 对比 Easy 数据集上的基线 vs 训练后
uv run python scripts/compare_eval_results.py \
  --exp1 qwen_baseline_hierarchical_easy \
  --exp2 qwen_practice_hierarchical_easy \
  --exp1_name "Baseline (Easy)" \
  --exp2_name "After Training (Easy)"

# 对比 Medium 数据集上的基线 vs 训练后
uv run python scripts/compare_eval_results.py \
  --exp1 qwen_baseline_hierarchical_medium \
  --exp2 qwen_practice_hierarchical_medium \
  --exp1_name "Baseline (Medium)" \
  --exp2_name "After Training (Medium)"
```

---

## 配置说明

### 训练配置：`configs/practice/medium_reasoning_hierarchical_num1.yaml`

```yaml
# @package _global_
defaults:
  - base
  - /model@: qwen
  - /agents@: practice/logic_agent_hierarchical_learning
  - /eval@: logic/easy_base_hierarchical
  - _self_

exp_id: medium_reasoning_hierarchical_num1

practice:
  # Rollout 配置
  epochs: 3
  batch_size: 20  # Medium-30 经 GRPO 过滤后约 20 题
  grpo_n: 5
  rollout_concurrency: 4
  rollout_temperature: 0.7
  rollout_data_truncate: null
  task_timeout: 3600
  shuffle_data: true
  restart_step: null

  # 经验生成配置
  agent_objective: "Solve logic puzzles by deducing the correct assignments..."
  learning_objective: "Improve logical reasoning and constraint satisfaction..."
  given_ground_truth: true
  num_experiences_per_query: 2
  verify_module: "utu.practice.verify.logic"

  # 分层学习配置（核心）
  hierarchical_learning:
    enabled: true                      # 启用分层学习
    l1_aggregation_threshold: 5        # 5 个 L0 → 1 个 L1
    l2_aggregation_threshold: 3        # 3 个 L1 → 1 个 L2
    max_l0_per_problem: 1
    max_l1_total: 50
    max_l2_total: 10
    include_l0_in_prompt: true         # 在 agent prompt 中包含 L0
    max_l0_recent: 10                  # 最多包含 10 个最近的 L0
    l1_confidence_threshold: 0.7
    l2_confidence_threshold: 0.8
    experience_save_path: "workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json"

  # 评估配置
  do_eval: false
  eval_strategy: "epoch"
  eval_steps: 1
  eval_data_truncate: null

data:
  practice_dataset_name: "ZebraLogic-Medium-30"
```

### Agent 基础配置：`configs/agents/practice/logic_agent_hierarchical_learning.yaml`

```yaml
# @package _global_
defaults:
  - _self_

agent:
  instructions: |
    You are a helpful assistant specializing in solving logic puzzle problems...
    
    **IMPORTANT**: Your final answer must follow this exact format:
    
    <answer>
    \boxed{{
      "solution": {
        "House 1": {"Color": "...", "Nationality": "...", ...},
        ...
      }
    }}
    </answer>
```

### Prompt 模板：`configs/prompts/hierarchical_critique.yaml`

包含 L1 和 L2 生成的 prompt 模板（已在前面创建）。

---

## 结果查看

### 1. 查看生成的经验（JSON）

```bash
# 完整查看
cat workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json

# 只看统计
cat workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json | grep -A 5 '"stats"'

# 只看 L2
cat workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json | grep -A 3 '"l2_experiences"'
```

**JSON 结构**：

```json
{
  "l0_experiences": [
    {
      "id": "L0_0",
      "content": "Constraint validation: Validate interdependent positional clues immediately...",
      "original_id": "G0",
      "step": 0,
      "problem_count": 30
    },
    ...
  ],
  "l1_experiences": [
    {
      "id": "L1_0",
      "content": "Use a structured tracking method (grid/table) to enforce constraints...",
      "source_l0_ids": ["L0_0", "L0_1", "L0_2", "L0_3", "L0_4"],
      "step": 1
    },
    ...
  ],
  "l2_experiences": [
    {
      "id": "L2_0",
      "content": "Principle: Prioritize constraint validation through structured, real-time tracking...",
      "source_l1_ids": ["L1_0", "L1_1", "L1_2"],
      "step": 2
    }
  ],
  "stats": {
    "total_l0": 38,
    "total_l1": 3,
    "total_l2": 1
  }
}
```

### 2. 查看生成的 Agent 配置（YAML）

```bash
cat configs/agents/practice/medium_reasoning_hierarchical_num1_agent.yaml
```

**关键部分**：

```yaml
agent:
  instructions: "...\n\nWhen solving problems, you MUST first carefully read and understand\
    \ the helpful instructions and experiences:\n\
    [G0]. [L2-Meta] Principle: Prioritize constraint validation through structured,\
    \ real-time tracking to maintain logical coherence...\n\
    [G1]. [L1-Pattern] Use a structured tracking method, such as a grid or table...\n\
    [G2]. [L1-Pattern] Apply systematic constraint enforcement during each assignment...\n\
    [G3]. [L1-Pattern] Use a grid to systematically track and cross-check constraints...\n\
    [G4]. [L0-Case] Constraint validation: Validate interdependent positional clues...\n\
    [G5]. [L0-Case] Grid initialization: Use a grid/table starting with deterministic...\n\
    ..."
```

### 3. 查看评估结果

```bash
# 查询数据库
sqlite3 test.db "
SELECT exp_id, dataset_name, pass_1, pass_5, total_samples
FROM eval_summary
WHERE exp_id LIKE '%hierarchical%'
ORDER BY created_at DESC;
"
```

---

## 常见问题

### Q1: 训练时出现 "batch size 小于数据集大小" 错误

**原因**：GRPO 会过滤掉"全对"或"全错"的问题，导致有效问题数减少。

**解决**：
```yaml
# 在 medium_reasoning_hierarchical_num1.yaml 中调整
practice:
  batch_size: 20  # 从 30 改为 20
```

### Q2: L1/L2 没有生成

**检查点**：
1. 是否启用了分层学习：
   ```yaml
   hierarchical_learning:
     enabled: true
   ```

2. 是否达到阈值：
   - L1 需要至少 5 个 L0
   - L2 需要至少 3 个 L1

3. 查看日志中的 "Hierarchical processing complete" 行

### Q3: LLM 调用失败

**常见原因**：
- API key 未设置或过期
- 网络问题
- Rate limiting

**检查**：
```bash
# 检查 .env 文件
cat .env | grep API_KEY

# 测试 LLM 连接
uv run python scripts/test_llm_connection.py
```

### Q4: 如何只测试分层经验生成而不完整训练？

```bash
# 使用测试脚本
uv run python scripts/test_hierarchical_experience.py

# 或缩短训练（只跑 1 个 epoch，10 道题）
uv run python scripts/run_training_free_GRPO.py \
  --config_name medium_reasoning_hierarchical_num1 \
  practice.epochs=1 \
  practice.rollout_data_truncate=10
```

### Q5: 如何清理缓存重新训练？

```bash
# 清理经验缓存
sqlite3 test.db "DELETE FROM cache_experience WHERE experiment_name='medium_reasoning_hierarchical_num1';"

# 清理 JSON 文件
rm workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json

# 清理生成的 agent 配置
rm configs/agents/practice/medium_reasoning_hierarchical_num1_agent.yaml

# 重新训练
uv run python scripts/run_training_free_GRPO.py \
  --config_name medium_reasoning_hierarchical_num1
```

---

## 性能优化

### 加速训练

```yaml
# 增加并发度
practice:
  rollout_concurrency: 8  # 默认 4

# 减少 rollout 数量
practice:
  grpo_n: 3  # 默认 5

# 使用更快的模型
defaults:
  - /model@: gpt-4o-mini  # 代替 qwen
```

### 调整经验质量 vs 数量

```yaml
hierarchical_learning:
  # 更严格的阈值 → 更少但更高质量的经验
  l1_aggregation_threshold: 10  # 默认 5
  l2_aggregation_threshold: 5   # 默认 3
  
  # 更宽松的阈值 → 更多但可能更噪音的经验
  l1_aggregation_threshold: 3
  l2_aggregation_threshold: 2
```

---

## 实验建议

### 对照实验组

| 实验组 | 配置 | 目的 |
|--------|------|------|
| 基线 | 无经验学习 | 建立基准性能 |
| 传统 GRPO | 只有扁平经验 | 对比分层的价值 |
| L0+L1 | 只用 L0 和 L1 | 评估 L2 的额外贡献 |
| L1+L2 | 只用 L1 和 L2 | 评估 L0 的具体案例价值 |
| 完整分层 | L0+L1+L2 | 最佳性能 |

### 跨难度实验

训练在 Medium，评估在 Easy/Hard：
```bash
# 训练
uv run python scripts/run_training_free_GRPO.py \
  --config_name medium_reasoning_hierarchical_num1

# 评估 Easy（下难度迁移）
uv run python scripts/run_eval.py \
  --config_name logic/easy_practice_hierarchical_num1

# 评估 Hard（上难度迁移）
uv run python scripts/run_eval.py \
  --config_name logic/hard_practice_hierarchical_num1
```

---

## 总结

✅ **系统已完成**：
- 分层经验生成（L0/L1/L2）
- L2 基于 L1+L0 双重输入
- 自动触发和持久化
- 完整的评估流程

🎯 **关键命令**：
```bash
# 1. 训练
uv run python scripts/run_training_free_GRPO.py --config_name medium_reasoning_hierarchical_num1

# 2. 评估
uv run python scripts/run_eval.py --config_name logic/easy_practice_hierarchical_num1

# 3. 对比
uv run python scripts/compare_eval_results.py --exp1 baseline --exp2 after_training
```

📚 **参考文档**：
- 实现说明：`分层经验学习-实现说明.md`
- 系统文档：`分层经验学习系统-完整文档.md`（如果存在）

---

**祝实验顺利！** 🚀

如有问题，请查看日志文件或联系开发者。




























