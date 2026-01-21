# Word Puzzle 完整实验指南 📊

## 🎯 实验目标

对比**无经验 Agent** vs **有经验 Agent**在 Word Puzzle（填字游戏）上的成功率差异，并与 KORGym 论文结果对齐。

---

## 📋 实验流程

```
步骤 1: 基线评估 → 测试原始 Agent（无经验）
    ↓
步骤 2: 训练阶段 → Agent 玩游戏，提取 L0/L1/L2 经验
    ↓
步骤 3: 增强评估 → 测试增强 Agent（有经验）
    ↓
步骤 4: 对比分析 → 计算成功率提升，对比论文结果
```

---

## 🚀 快速开始

### 方式 1: 一键运行完整实验（推荐）

```bash
# 在 WSL 终端执行
cd /mnt/f/youtu-agent
bash scripts/run_complete_word_puzzle_experiment.sh
```

**执行内容：**
1. ✅ 启动游戏服务器
2. ✅ 评估基线 Agent（50 局，与论文对齐）
3. ✅ 训练生成经验
4. ✅ 评估增强 Agent（50 局）
5. ✅ 对比结果与论文

**预计时间：** 40-60 分钟

---

### 方式 2: 分步执行

#### Step 1: 启动游戏服务器

```bash
cd /mnt/f/youtu-agent
uv run python scripts/start_korgym_server.py \
    --game_name 8-word_puzzle \
    --port 8775 \
    --level 4 &
```

**检查服务器：**
```bash
curl http://localhost:8775/health
```

---

#### Step 2: 评估基线（无经验）

**标准评估（50 局，与论文对齐）：**
```bash
uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config practice/logic_agent_hierarchical_learning_clean \
    --exp_id baseline_clean \
    --num_seeds 50 \
    --level 4
```

**快速测试（20 局）：**
```bash
uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config practice/logic_agent_hierarchical_learning_clean \
    --exp_id baseline_quick \
    --num_seeds 20 \
    --level 4
```

**输出示例：**
```
📊 Paper Table Metrics:
  Average Score: 0.030
  → This is the value shown in the paper table!
```

---

#### Step 3: 训练 Agent（生成分层经验）

```bash
uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_hierarchical_experiment
```

**训练过程：**
```
Epoch 1/3, Batch 1/6:
  ├─ 玩 5 个游戏
  ├─ 提取 5 个 L0 → 生成 L1_0 ✨
  └─ 保存经验

Epoch 2/3, Batch 1/6:
  ├─ 玩 5 个游戏
  ├─ 提取 5 个 L0 → 生成 L1_2 ✨
  ├─ 触发 L2 生成 ✨✨
  └─ 更新 Agent 配置
```

**生成的文件：**
- `workspace/hierarchical_experiences/word_puzzle_exp.json` - 经验库
- `configs/agents/practice/word_puzzle_exp_agent.yaml` - 增强的 Agent

---

#### Step 4: 评估增强（有经验）

```bash
uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config word_puzzle_hierarchical_agent \
    --exp_id enhanced_hierarchical \
    --num_seeds 50 \
    --level 4
```

---

#### Step 5: 对比结果与论文

```bash
python scripts/compare_paper_scores.py \
    workspace/korgym_paper_aligned/baseline_clean_word_puzzle.json \
    workspace/korgym_paper_aligned/enhanced_hierarchical_word_puzzle.json
```

**输出示例：**
```
📊 Your Results:
Experiment                               Score     vs Paper
--------------------------------------------------------------------------------
baseline_clean                           0.030     ≈ DeepSeek-R1-Distill-Qwen-7B
enhanced_hierarchical                    0.150     ≈ Doubao-1.5-pro

📈 Improvement:
  Baseline:    0.030
  Enhanced:    0.150
  Improvement: +0.120 (+400.0%)

📖 Full Paper Ranking (Table 7 - Word Problem):
 1. O1-2024-12-17                        0.960
 2. Gemini-2.5-pro-03-25                 0.900
 ...
12. → enhanced_hierarchical              0.150 ⭐
13. Doubao-1.5-pro                       0.120
14. → baseline_clean                     0.030 ⭐
```

---

## 📊 论文对齐说明

### KORGym 论文设置（Table 7 - Word Problem）

| 参数 | 论文配置 | 你的配置 | 状态 |
|------|---------|---------|------|
| 游戏 | Word Problem (8-word_puzzle) | ✅ 相同 | ✅ |
| 难度 | Level 4 | ✅ Level 4 | ✅ |
| 游戏局数 | 50 seeds | ✅ 50 seeds | ✅ |
| 评分方式 | 填对单词比例 | ✅ 相同 | ✅ |

### 论文表格（参考）

**Table 7 - Word Problem:**

| Model | Score |
|-------|-------|
| O1-2024-12-17 | 0.960 |
| Gemini-2.5-pro | 0.900 |
| O3-mini | 0.880 |
| Claude-3.7-thinking | 0.820 |
| DeepSeek-R1 | 0.820 |
| Gemini-2.0-Flash-thinking | 0.620 |
| Doubao-1.5-thinking-pro | 0.600 |
| Claude-3.7 | 0.580 |
| Qwen-Max | 0.480 |
| DeepSeek-v3-0324 | 0.460 |
| GPT-4o | 0.420 |
| Gemini-2.0-Flash | 0.340 |
| Doubao-1.5-pro | 0.120 |
| DeepSeek-R1-Distill-Qwen-7B | 0.020 |

### 评分理解

**论文表格中的数值 = 平均得分 (Average Score)**

```
avg_score = Σ(每局 score) / 游戏总数
score = 填对的单词数 / 总单词数
```

**示例：**
- `0.030` = 平均填对 **3%** 的单词
- `0.120` = 平均填对 **12%** 的单词
- `0.960` = 平均填对 **96%** 的单词

---

## 📁 配置文件说明

### 训练配置
**文件**: `configs/practice/word_puzzle_hierarchical_experiment.yaml`

关键参数：
```yaml
exp_id: word_puzzle_hierarchical_exp

korgym:
  game_name: "8-word_puzzle"
  level: 3              # 难度：1-5（3=中等）
  num_seeds: 30         # 训练用 30 个游戏

data:
  batch_size: 5         # 每批 5 个游戏
  num_epochs: 3         # 3 轮训练

hierarchical_learning:
  enabled: true
  l1_aggregation_threshold: 5  # 每 5 个 L0 → 1 个 L1
  l2_aggregation_threshold: 3  # 每 3 个 L1 → 1 个 L2
  max_l0_per_game: 1          # 每个游戏 1 个 L0
```

### 基线评估配置
**文件**: `configs/eval/korgym/word_puzzle_baseline.yaml`

```yaml
exp_id: word_puzzle_baseline_eval
agent: practice/logic_agent_hierarchical_learning_clean  # 无经验
korgym:
  num_seeds: 20  # 评估 20 个游戏
```

### 增强评估配置
**文件**: `configs/eval/korgym/word_puzzle_enhanced.yaml`

```yaml
exp_id: word_puzzle_enhanced_eval
agent: practice/word_puzzle_exp_agent  # 有经验（训练后生成）
korgym:
  num_seeds: 20  # 相同的 20 个游戏
```

---

## 🔍 查看结果

### 查看评估结果

```bash
# 方法 1: 使用快速查看脚本（推荐）
python scripts/view_korgym_results.py word_puzzle_baseline_eval

# 方法 2: 查看分数汇总
cat workspace/korgym_paper_aligned/score.txt

# 方法 3: SQLite 快速查询
sqlite3 database.db "SELECT COUNT(*) as total, SUM(correct) as success, ROUND(AVG(CASE WHEN correct=1 THEN 100.0 ELSE 0 END), 1) as rate FROM evaluation_data WHERE exp_id='word_puzzle_baseline_eval';"
```

### 查看经验文件

```bash
# 查看经验统计
cat workspace/hierarchical_experiences/word_puzzle_exp.json | python -m json.tool | head -50

# 统计经验数量
echo "L0: $(cat workspace/hierarchical_experiences/word_puzzle_exp.json | grep -c '\"level\": \"L0-Case\"')"
echo "L1: $(cat workspace/hierarchical_experiences/word_puzzle_exp.json | grep -c '\"level\": \"L1-Pattern\"')"
echo "L2: $(cat workspace/hierarchical_experiences/word_puzzle_exp.json | grep -c '\"level\": \"L2-Meta\"')"
```

### 查看增强的 Agent

```bash
# 查看 Agent 配置
cat configs/agents/practice/word_puzzle_exp_agent.yaml | less

# 统计经验数量
grep -c '\[G[0-9]' configs/agents/practice/word_puzzle_exp_agent.yaml
```

---

## 🔧 调整参数

### 增加训练数据

```yaml
# configs/practice/word_puzzle_hierarchical_experiment.yaml
korgym:
  num_seeds: 50  # 从 30 增加到 50

data:
  num_epochs: 5  # 从 3 增加到 5
```

### 调整经验生成阈值

```yaml
hierarchical_learning:
  l1_aggregation_threshold: 3  # 更频繁生成 L1（每 3 个 L0）
  l2_aggregation_threshold: 2  # 更早生成 L2（每 2 个 L1）
```

### 改变游戏难度

```yaml
korgym:
  level: 2  # 1=最简单, 5=最难
```

---

## 🐛 故障排查

### 问题 1：游戏服务器连接失败

**错误**：`Connection refused to localhost:8775`

**解决**：
```bash
# 检查服务器是否运行
curl http://localhost:8775/docs

# 如果没有，启动服务器
python scripts/start_korgym_server.py 8-word_puzzle

# 等待 5 秒后再运行实验
```

### 问题 2：找不到实验结果

**错误**：`⚠ 未找到实验: word_puzzle_baseline_eval`

**解决**：
```bash
# 检查数据库中的实验 ID
sqlite3 database.db "SELECT DISTINCT exp_id FROM evaluation_data;"

# 使用正确的 exp_id
```

### 问题 3：经验文件不存在

**错误**：`⚠ 经验文件不存在`

**解决**：
```bash
# 检查文件是否生成
ls -lh workspace/hierarchical_experiences/word_puzzle_exp.json

# 如果不存在，重新运行训练
uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_hierarchical_experiment
```

### 问题 4：LLM API 超时

**错误**：`Timeout waiting for LLM response`

**解决**：
1. 检查网络连接
2. 检查 API key 是否有效
3. 增加超时时间（在配置文件中）:
```yaml
model:
  model_settings:
    timeout: 120  # 增加到 120 秒
```

---

## ✅ 实验检查清单

在运行实验前，确保：

- [ ] 已安装所有依赖（fastapi, gymnasium, pygame 等）
- [ ] 游戏服务器正常运行（http://localhost:8775/docs 可访问）
- [ ] LLM API 配置正确（.env 文件）
- [ ] 虚拟环境已激活
- [ ] 有足够的磁盘空间（至少 500MB）
- [ ] 配置文件存在且正确

运行检查：
```bash
python scripts/check_korgym_env.py
```

---

## 📚 相关文档

- [KORGym 经验总结机制详解](KORGym经验总结机制详解.md)
- [KORGym 快速使用指南](KORGym快速使用指南.md)
- [KORGym WSL 环境配置](KORGym_WSL环境配置指南.md)
- [Training-Free GRPO 完整流程详解](Training-Free_GRPO完整流程详解.md)

---

## 🎯 总结

这个实验将让你：

1. **量化评估**分层经验学习的效果
2. **可视化**经验的生成过程（L0 → L1 → L2）
3. **对比分析**有无经验的性能差异
4. **理解**经验如何改进 Agent 的决策
5. **对齐论文**结果，验证系统正确性

**预期成功率提升**: 15-30 百分点（取决于游戏难度和训练数据）

🚀 **立即开始实验！**








