# Wordle 使用指南

> 适用版本：2026-03  
> 前置条件：已完成环境配置，参考 [安装指南](../installation.md)  
> 游戏类型：多轮交互猜词游戏

## 概述

本文档介绍 **Wordle** 游戏的完整实验流程，包括：
- 游戏规则和评分机制
- 快速开始（5分钟体验）
- 完整实验流程（数据准备→训练→评估）
- 不同数据集规模的配置（20题/50题/100题）
- 性能优化和故障排除

**核心特点**：
- **多轮交互**：最多10次猜测机会
- **结构化反馈**：绿色（正确位置）、黄色（错误位置）、灰色（不在单词中）
- **分层经验学习**：提取L0/L1/L2三层经验，提升性能10-20%

---

## 游戏规则

### 基本机制

- **目标**：在10次尝试内猜出隐藏单词
- **单词长度**：4-12个字母（可配置，推荐5字母）
- **游戏端口**：8777
- **单词库**：16,922个英文单词

### 反馈系统

每次猜测后会收到反馈：

| 反馈 | 含义 | 示例 |
|------|------|------|
| ✅ **绿色** | 字母在单词中且位置正确 | `a@0` → 字母a在位置0正确 |
| 🟨 **黄色** | 字母在单词中但位置错误 | `p@1` → 字母p存在但不在位置1 |
| ⬜ **灰色** | 字母不在单词中 | `x@2` → 字母x不存在 |

**反馈格式**（简洁版）：
```
apple → G:a@0 Y:p@1 N:p@2 N:l@3 N:e@4
```

### 评分规则

```
猜中单词: score = 1.0 (100%)
10次用尽未猜中: score = 0.0 (0%)
```

**特点**：All-or-nothing（全对或全错），无部分分数。

---

## 快速开始（5分钟）

最短路径体验 Wordle 实验：

### 步骤1：启动游戏服务器

**打开终端1**，启动 Wordle 游戏服务器：

```bash
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

**成功标志**：
```
 * Running on http://127.0.0.1:8777
 * Running on http://0.0.0.0:8777
```

**保持此终端运行！**

### 步骤2：准备数据集

**打开终端2**，准备数据集：

```bash
cd /path/to/youtu-agent
source .venv/bin/activate  # Linux/WSL/macOS
# 或 .venv\Scripts\activate  # Windows

# 创建50题评估集 + 100题训练集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
```

**预期输出**：
```
✓ 创建评估数据集: KORGym-Wordle-Eval-50 (50题)
✓ 创建训练数据集: KORGym-Wordle-Train-100 (100题)
```

### 步骤3：基线评估

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

**评估时间**：5-10分钟

### 步骤4：训练（生成经验）

```bash
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
```

**训练时间**：15-30分钟

**完成后看到**：
```
✓ Training completed
  Generated experiences: 
    L0: 45-50 case-level experiences
    L1: 9-10 pattern-level experiences  
    L2: 3 meta-strategy experiences
```

**生成的文件**：
- `workspace/hierarchical_experiences/wordle_practice.json` - 经验库
- `configs/agents/practice/wordle_practice_agent.yaml` - 带经验的Agent配置

### 步骤5：训练后评估

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
```

### 步骤6：对比结果

```bash
uv run python scripts/games/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_eval
```

**预期输出**：
```
=== KORGym 结果对比 ===

wordle_baseline_eval:
  准确率: 35.2%
  平均分: 0.352

wordle_practice_eval:  
  准确率: 45.8%  ✓ 提升 +10.6%
  平均分: 0.458

🎉 训练后性能提升明显！
```

---

## 完整流程

### Step 1: 环境准备

#### 1.1 检查Python环境

```bash
python --version  # 需要 Python 3.12+
```

#### 1.2 激活虚拟环境

```bash
source .venv/bin/activate  # Linux/WSL/macOS
# 或
.venv\Scripts\activate  # Windows
```

#### 1.3 验证API配置

确保 `.env` 文件中已配置LLM API：

```bash
UTU_LLM_TYPE=chat.completions
UTU_LLM_MODEL=deepseek-chat
UTU_LLM_BASE_URL=https://api.deepseek.com/v1
UTU_LLM_API_KEY=your-api-key-here
```

---

### Step 2: 数据集准备

#### 2.1 创建标准数据集（100题训练）

```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 150
```

**生成数据集**：
- `KORGym-Wordle-Eval-50`：50题评估集
- `KORGym-Wordle-Train-100`：100题训练集

#### 2.2 验证数据集

```bash
# 查看所有数据集
uv run python scripts/data/list_datasets.py | grep Wordle

# 查看数据集详情
uv run python scripts/utils/view_dataset.py \
  --dataset_name "KORGym-Wordle-Eval-50" \
  --limit 5
```

---

### Step 3: 基线评估

运行基线评估，测试未经训练的Agent性能：

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

**配置文件**：`configs/eval/korgym/wordle_eval.yaml`

**关键参数**：
```yaml
exp_id: "wordle_baseline_eval"
data:
  dataset: "KORGym-Wordle-Eval-50"
concurrency: 2  # 多轮游戏必须低并发，避免API限流
korgym:
  game_name: "33-wordle"
  game_port: 8777
  level: 5  # 单词长度（5字母）
  max_rounds: 10  # 最多10次猜测
```

**评估时间**：约10-15分钟（50题）

**查看结果**：
```bash
uv run python scripts/games/view_korgym_results.py wordle_baseline_eval
```

---

### Step 4: 训练（经验学习）

运行 Training-Free GRPO 训练，生成分层经验：

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/wordle_practice
```

**配置文件**：`configs/practice/korgym/wordle_practice.yaml`

**关键参数**：
```yaml
exp_id: "wordle_practice"
practice:
  epochs: 2  # 训练轮数
  batch_size: 100  # 批次大小
  grpo_n: 3  # 每题生成3个候选
  rollout_concurrency: 4  # 低并发避免API限流
  rollout_temperature: 0.7
  
  hierarchical_learning:
    enabled: true
    l1_aggregation_threshold: 5  # 5个L0→1个L1
    l2_aggregation_threshold: 3  # 3个L1→1个L2
    max_l0_recent: 50
    include_l0_in_prompt: true
    experience_save_path: workspace/hierarchical_experiences/wordle_practice.json
    agent_save_path: configs/agents/practice/wordle_practice_agent.yaml

data:
  practice_dataset_name: "KORGym-Wordle-Train-100"
```

**训练过程**：
1. **Rollout生成**：对每题生成3个候选答案（100题 × 3 = 300次游戏）
2. **相对优势计算**：比较同组候选的相对表现
3. **经验提取**：从高分rollout提取L0经验
4. **分层聚合**：自动生成L1、L2经验
5. **Agent更新**：将经验注入Agent配置

**训练时间**：15-30分钟（取决于模型和API速度）

**完成标志**：
```
✓ Training completed
✓ Generated agent config: configs/agents/practice/wordle_practice_agent.yaml
✓ Generated experiences: workspace/hierarchical_experiences/wordle_practice.json
```

**查看生成的经验**：
```bash
cat workspace/hierarchical_experiences/wordle_practice.json | python -m json.tool
```

---

### Step 5: 增强评估

使用训练后生成的Agent（包含经验）重新评估：

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
```

**配置文件**：`configs/eval/korgym/wordle_practice_eval.yaml`

**关键区别**：
```yaml
exp_id: "wordle_practice_eval"
agent:
  config_name: "practice/wordle_practice_agent"  # 使用训练后的Agent
data:
  dataset: "KORGym-Wordle-Eval-50"  # 相同的评估集
```

---

### Step 6: 结果分析

#### 6.1 对比评估结果

```bash
uv run python scripts/games/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_eval
```

**示例输出**：
```
=== KORGym 结果对比 ===

wordle_baseline_eval:
  准确率: 35.2%
  平均分: 0.352
  成功: 17/50
  失败: 33/50

wordle_practice_eval:  
  准确率: 45.8%  ✓ 提升 +10.6%
  平均分: 0.458
  成功: 23/50
  失败: 27/50

提升分析：
- 绝对提升：+10.6%
- 相对提升：+30.1%
- 新增成功：6题
```

#### 6.2 详细分析（可选）

```bash
# 分析前20题的详细表现
uv run python scripts/games/wordle/analyze_wordle_results.py \
  --exp_id wordle_practice_eval \
  --top_n 20
```

---

## 不同数据集规模

根据实验需求和预算，可以选择不同规模的训练集：

### 20题训练（快速测试）

**适用场景**：
- ✅ 快速验证想法
- ✅ 调试代码流程
- ✅ 预算有限
- ✅ 初次尝试

**创建数据集**：
```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 70  # 70-51+1 = 20题
```

**运行训练**：
```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/wordle_practice_20
```

**配置调整**：
```yaml
# configs/practice/korgym/wordle_practice_20.yaml
practice:
  batch_size: 20  # 匹配数据集大小
  rollout_concurrency: 8  # 可稍高
  hierarchical_learning:
    l1_aggregation_threshold: 4  # 降低阈值
    l2_aggregation_threshold: 2
    max_l0_recent: 20
data:
  practice_dataset_name: "KORGym-Wordle-Train-20"
```

**预期效果**：

| 指标 | 100题训练 | 20题训练 |
|------|-----------|----------|
| **训练时间** | 15-30分钟 | **5-10分钟** |
| **API成本** | ~$2-3 | **~$0.5** |
| **L0经验数** | 45-50个 | 15-18个 |
| **L1经验数** | 9-10个 | 3-4个 |
| **L2经验数** | 3个 | 1-2个 |
| **准确率提升** | +8-12% | **+5-8%** |

---

### 50题训练（平衡选择）

**适用场景**：
- ⚖️ 平衡时间和效果
- ⚖️ 中等预算
- ⚖️ 验证性实验

**创建数据集**：
```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --train_seeds_start 51 \
  --train_seeds_end 100  # 100-51+1 = 50题
```

**配置调整**：
```yaml
practice:
  batch_size: 50
  rollout_concurrency: 16
  hierarchical_learning:
    max_l0_recent: 50
data:
  practice_dataset_name: "KORGym-Wordle-Train-50"
```

---

### 100题训练（正式实验）

**适用场景**：
- ✅ 最终实验结果
- ✅ 论文/报告数据
- ✅ 充分测试分层学习效果

**详见完整流程章节**。

---

## 配置说明

### Agent配置

**基线版**：`configs/agents/practice/wordle_agent.yaml`

```yaml
agent:
  name: "wordle_agent"
  model:
    model_settings:
      model: "deepseek-chat"
      temperature: 0.7
      max_tokens: 500
  instructions: |
    You are playing Wordle game...
    
    CRITICAL WORD VALIDATION:
    - Your answer MUST be a real, existing English word
    - NEVER submit made-up words
    - Prefer common/familiar words
    
    Output: Answer: word (lowercase, exact length)
```

**关键优化**：
- ✅ **单词有效性验证**：强制要求真实英文单词
- ✅ **简洁历史格式**：减少token消耗87%
- ✅ **温度0.7**：平衡探索与利用

---

### 评估配置

**关键参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| `concurrency` | **2** | 多轮游戏必须低并发，避免429错误 |
| `game_port` | 8777 | Wordle默认端口 |
| `level` | 5 | 单词长度（4-12可配置） |
| `max_rounds` | 10 | 最大猜测次数，必须与`game_lib.py`一致 |
| `timeout_per_game` | 600 | 每局超时（秒） |

**并发数选择**：

| 并发数 | 最大API调用 | 429风险 | 评估时间（50题） | 推荐度 |
|-------|------------|---------|----------------|--------|
| 8 | 80 | 🔴 高 | ~10分钟 | ❌ 不推荐 |
| 4 | 40 | 🟡 中 | ~20分钟 | ⚠️ 可能有风险 |
| **2** | **20** | **🟢 低** | **~40分钟** | **✅ 推荐** |
| 1 | 10 | 🟢 极低 | ~80分钟 | ⚠️ 太慢 |

---

### 训练配置

**关键参数**：

```yaml
practice:
  epochs: 2  # 训练轮数
  batch_size: 100  # 必须匹配训练集大小
  grpo_n: 3  # 每题候选数（3-5推荐）
  rollout_concurrency: 4  # 多轮游戏必须低并发
  rollout_temperature: 0.7
  task_timeout: 600
  
  agent_objective: |
    input: Wordle game state with previous guesses and feedback
    output: A strategic word guess
  
  learning_objective: |
    Help the agent improve Wordle gameplay by extracting:
    - L0: Specific guess sequences and feedback interpretation
    - L1: Opening strategies and constraint satisfaction
    - L2: Deductive reasoning principles
  
  hierarchical_learning:
    enabled: true
    l1_aggregation_threshold: 5
    l2_aggregation_threshold: 3
    max_l0_per_game: 1
    max_l0_recent: 50
    include_l0_in_prompt: true
```

---

## 性能优化

### 优化1：简洁历史格式

**问题**：Prompt长度指数增长，10轮后达5000+字符

**解决方案**：简洁历史格式（已自动应用）

```
❌ 旧格式（冗长）：
The letter a located at idx=0 is in the word and in the correct spot,
The letter p located at idx=1 is in the word but in the wrong spot,
...
(~400字符/轮)

✅ 新格式（简洁）：
apple → G:a@0 Y:p@1 N:p@2 N:l@3 N:e@4
(~50字符/轮)
```

**效果**：

| 指标 | 优化前 | 优化后 | 提升 |
|------|-------|-------|------|
| Token消耗 | ~3000 | ~400 | **87% ↓** |
| 成本（100局） | ¥1.20 | ¥0.16 | **87% ↓** |
| Prompt长度 | 8750字符 | 275字符 | **97% ↓** |

---

### 优化2：单词有效性验证

**问题**：LLM猜测无效单词（如teelle, forestor）

**解决方案**：在Agent prompt中强调单词有效性

```yaml
instructions: |
  CRITICAL WORD VALIDATION:
  - Your answer MUST be a real, existing English word
  - NEVER submit made-up words
  - Prefer common/familiar words
  - Examples: crane, stare, table, house, world
```

**效果**：减少50-70%的无效单词猜测，准确率提升5-15%

---

### 优化3：固定单词长度

**推荐配置**：
```yaml
korgym:
  level: 5  # 固定5字母（标准Wordle）
```

**原因**：
- ✅ 5字母单词最常见，LLM词汇量最丰富
- ✅ 避免4-12字母随机变化导致的不稳定
- ✅ 便于对比不同实验结果

---

### 优化4：降低并发数

**多轮游戏特性**：
- 每个样本需要10次API调用（10轮交互）
- 高并发 = 80-100次并发API调用
- 触发429 Rate Limit错误

**解决方案**：
```yaml
# 评估配置
concurrency: 2  # 从8降到2

# 训练配置
practice:
  rollout_concurrency: 4  # 保持低并发
```

---

## 常见问题

### Q1: 游戏服务器连接失败

**错误**：`Connection refused to http://localhost:8777`

**解决**：

1. 检查服务器是否启动：
```bash
# Windows
netstat -an | findstr 8777

# Linux/WSL
netstat -tuln | grep 8777
```

2. 重启服务器：
```bash
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

3. 检查端口占用：
```bash
# 如果端口被占用，更换端口
python game_lib.py -p 8778
# 同时修改配置文件中的 game_port
```

---

### Q2: API Rate Limit (429错误)

**错误**：
```
Error code: 429 - Rate limit exceeded
```

**解决**：

1. **降低并发数**（最有效）：
```yaml
# configs/eval/korgym/wordle_eval.yaml
concurrency: 2  # 从8改为2
```

2. **增加重试延迟**：
```yaml
practice:
  task_timeout: 900  # 增加超时
  rollout_concurrency: 2  # 进一步降低
```

3. **使用更小的模型**：
```yaml
agent:
  model:
    model_settings:
      model: "Qwen2.5-7B-Instruct"  # 从72B降级
```

---

### Q3: 准确率为0%或很低

**可能原因**：

1. **Prompt历史格式问题** → 已修复（简洁格式）
2. **单词长度不固定** → 修改`level: 5`固定5字母
3. **LLM猜无效单词** → 已添加单词验证提示
4. **模型能力不足** → 换用更大模型（72B）

**诊断步骤**：

```bash
# 查看失败样本的详细信息
sqlite3 test.db "SELECT response, correct_answer FROM evaluation_data WHERE exp_id='wordle_baseline_eval' AND correct=0 LIMIT 5"
```

---

### Q4: 训练后准确率没有提升

**可能原因**：

1. **训练集太小**（如20题）→ 增加到50或100题
2. **经验质量不高** → 检查生成的经验文件
3. **L1/L2经验太少** → 降低聚合阈值

**检查经验生成**：
```bash
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.L0 | length'
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.L1 | length'
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.L2 | length'
```

**预期数量**（100题训练）：
- L0: 45-50个
- L1: 9-10个
- L2: 3个

如果数量不足，调整配置：
```yaml
hierarchical_learning:
  l1_aggregation_threshold: 4  # 从5降到4
  l2_aggregation_threshold: 2  # 从3降到2
```

---

### Q5: 数据集已存在错误

**错误**：`Dataset already exists: KORGym-Wordle-Train-100`

**解决**：

```bash
# 方案1：删除旧数据集
uv run python -c "
from utu.db import DBService, DatasetSample
from sqlmodel import select
db = DBService()
with db.session() as session:
    stmt = select(DatasetSample).where(
        DatasetSample.dataset == 'KORGym-Wordle-Train-100'
    )
    for sample in session.exec(stmt):
        session.delete(sample)
    session.commit()
print('✓ 删除成功')
"

# 方案2：使用不同名称
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --dataset_suffix "_v2"  # 生成 KORGym-Wordle-Train-100_v2
```

---

### Q6: 生成的经验质量不高

**检查方法**：

```bash
# 查看经验内容
cat workspace/hierarchical_experiences/wordle_practice.json | python -m json.tool | less
```

**常见问题**：

1. **L0经验过于重复**：
   - 原因：样本多样性不足
   - 解决：增加训练集，或调整`num_experiences_per_query: 2`

2. **L1经验过于抽象**：
   - 原因：聚合阈值过高
   - 解决：降低`l1_aggregation_threshold`

3. **L2经验太少**：
   - 原因：L1数量不足
   - 解决：增加训练数据或降低阈值

---

## 清理和维护

### 清理实验数据

```bash
# 清理特定实验的数据库记录
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id wordle_baseline_eval

# 清理所有Wordle实验
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id_pattern "wordle%"
```

### 清理生成的文件

```bash
# 删除生成的经验文件
rm workspace/hierarchical_experiences/wordle_practice*.json

# 删除生成的Agent配置
rm configs/agents/practice/wordle_practice*_agent.yaml
```

### 完全重置

```bash
# 使用清理脚本（WSL/Linux）
bash scripts/cleanup_and_rerun_wordle.sh

# 或手动执行：
# 1. 清理数据库
# 2. 删除生成文件
# 3. 重新准备数据集
# 4. 重新运行实验
```

---

## 预期结果

### 性能基准

| 指标 | 基线（无经验） | 增强（有经验） | 提升 |
|------|--------------|--------------|------|
| **准确率** | 30-50% | 40-65% | **+10-20%** |
| **平均分** | 0.30-0.50 | 0.40-0.65 | **+0.10-0.20** |
| **成功率** | 15-25/50 | 20-32/50 | **+5-10题** |

### 模型对比

| 模型 | 基线准确率 | 增强准确率 | 提升 |
|------|----------|----------|------|
| **Qwen2.5-7B** | 25-35% | 35-45% | +10% |
| **Qwen2.5-72B** | 50-65% | 60-75% | +10-15% |
| **DeepSeek-Chat** | 40-55% | 50-65% | +10% |

**建议**：
- 开发/测试：使用7B模型（快速、成本低）
- 正式实验：使用72B模型（准确率高）

---

## 进阶技巧

### 技巧1：手动优化经验

如果自动生成的经验质量不佳，可以手动编辑：

```bash
code workspace/hierarchical_experiences/wordle_practice.json
```

**优化方向**：
- 删除重复/低质量的L0经验
- 合并相似的L1经验
- 强化L2元策略的通用性

### 技巧2：混合经验策略

结合自动生成和手动优化：

```yaml
# 使用手动优化的经验
agent:
  experience_file: "workspace/hierarchical_experiences/wordle_manual_optimized.json"
```

### 技巧3：不同level的对比实验

测试不同单词长度的性能：

```bash
# Level 4 (4字母)
uv run python scripts/run_eval.py --config_name korgym/wordle_eval_l4

# Level 5 (5字母) - 推荐
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# Level 6 (6字母)
uv run python scripts/run_eval.py --config_name korgym/wordle_eval_l6
```

### 技巧4：经验检索过滤

启用经验检索，动态选择最相关的经验：

```yaml
# configs/agents/practice/wordle_agent.yaml
experience_filter:
  enabled: true
  strategy: "retrieval"
  retrieval_top_k: 10  # 只选择top-10相关经验
```

参考：[经验过滤指南](../concepts/experience_filtering.md)

---

## 相关文档

- [Training-Free GRPO 原理](../concepts/training_free_grpo.md)
- [分层经验学习机制](../concepts/hierarchical_experience.md)
- [命令速查参考](../reference/commands.md)
- [故障排除指南](../troubleshooting/index.md)
- [KORGym 游戏总览](../korgym/index.md)
- [Word Puzzle 指南](./word_puzzle.md)
- [Alphabetical Sorting 指南](./alphabetical_sorting.md)

---

## 参考资料

- [KORGym项目主页](https://razor233.github.io/KORGYM_HomePage/)
- [KORGym论文](https://arxiv.org/abs/2505.14552)
- [Wordle游戏规则](https://www.nytimes.com/games/wordle/index.html)
- [Training-Free GRPO论文](https://arxiv.org/abs/2510.08191)

---

*最后更新：2026-03-16*  
*适用配置版本：v1.0*
