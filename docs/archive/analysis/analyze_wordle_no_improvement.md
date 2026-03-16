# 🔍 Wordle 经验学习无提升原因分析

## 📊 当前情况

查看 `wordle_practice_20_l4_agent.yaml`，我们发现：

1. **学习到的经验**（共7条）：
   - **1条 L1 Pattern-Level（模式级）**
   - **6条 L0 Case-Level（案例级）**

2. **经验内容分析**：

```yaml
[G0]. [L1-Pattern] **L1 Pattern-Level Strategy**: 
    选择高熵开局词，包含常见和独特字母混合，最大化信息增益。

[G1-G6]. [L0-Case] Initial Guess: 
    使用如 'crane', 'soare', 'cranes', 'audit' 等开局词。
```

---

## ⚠️ 问题诊断：经验学习的 7 大局限

### 🎯 核心问题：经验过于浅层和重复

#### 问题 1: **经验内容重复冗余** ❌

**现象**：
- 7条经验中有 **6条L0** 都在说"第一次猜测用好词"
- 内容几乎完全重复，信息量极低
- G1-G6 说的都是同一件事：`crane`, `soare` 等开局词

**影响**：
```
基线Agent: "我知道要用好的开局词"
学习后Agent: "我知道要用好的开局词（重复6遍）"
→ 实际提升 = 0
```

---

#### 问题 2: **只学到了开局，没学到推理过程** ❌

**现象**：
所有经验都在讲 "Initial Guess"（第一次猜测），但 Wordle 的关键在于：

1. ✅ **第1轮猜测** → 容易（选好词即可）
2. 🔥 **第2-10轮推理** → 困难（需要约束推理）
   - 如何利用 GREEN 反馈锁定位置
   - 如何用 YELLOW 反馈排除错误位置
   - 如何用 GRAY 反馈排除字母
   - 如何综合多轮反馈建立约束
   - 如何在约束下搜索候选词

**当前经验缺失的关键内容**：
```
❌ 没有学到：如何处理 GREEN/YELLOW/GRAY 反馈
❌ 没有学到：如何建立位置约束
❌ 没有学到：如何在约束下生成候选词
❌ 没有学到：如何避免重复已排除的字母
❌ 没有学到：如何在后续轮次快速收敛
```

---

#### 问题 3: **20题数据量太小，难以泛化** ❌

**数据集配置**：
```yaml
num_train_seeds: 20  # 只有 20 道题
train_seeds_end: 70  # Seeds: 51-70
```

**问题**：
- Wordle 每题的答案词不同，模式多样
- 20题覆盖的模式 < 10%（估计）
- 学到的经验可能只对这20题有效，无法泛化到评估集（50题，seeds 1-50）

**类比**：
```
训练集：apple, table, crane, house, ... (20个词)
评估集：phone, bread, smile, cloud, ... (50个词)

如果经验是 "crane 是好开局词"：
  → 对 crane 自己有效
  → 对其他所有词也许有效（如果够通用）
  → 但如果经验是 "crane的a在第2位很重要"（过拟合）
    → 对 phone, bread 就没用了
```

---

#### 问题 4: **L0 案例经验占比过高** ❌

**当前分布**：
```
L0 (案例级): 6 条 (85.7%)  ← 太多了！
L1 (模式级): 1 条 (14.3%)
L2 (元策略): 0 条 (0%)
```

**问题**：
- **L0 经验**：特定问题的解法，泛化能力弱
- **L1 经验**：通用模式，泛化能力中等
- **L2 经验**：元策略，泛化能力强

**理想分布**（对于小数据集）：
```
L0: 20-30%（提供具体示例）
L1: 40-50%（提供通用模式）
L2: 20-30%（提供高层策略）
```

---

#### 问题 5: **聚合阈值设置不当** ⚠️

你改回了原始配置：

```yaml
l1_aggregation_threshold: 5  # 需要5个L0才能聚合成1个L1
l2_aggregation_threshold: 3  # 需要3个L1才能聚合成1个L2
```

**问题**：
- 只有 20 道题 → 最多 20 个L0
- 20 ÷ 5 = 4个L1 (理论最大值)
- 4 ÷ 3 = 1个L2 (理论最大值)
- 但实际生成时可能更少（因为相似度不够高）

**建议配置**（20题）：
```yaml
l1_aggregation_threshold: 3  # 3个L0 → 1个L1
l2_aggregation_threshold: 2  # 2个L1 → 1个L2
max_l0_recent: 20
```

---

#### 问题 6: **Wordle 游戏本身的难度** ⚠️

**Wordle 特点**：
- **搜索空间巨大**：英文4字母词有几千个
- **约束推理复杂**：需要同时处理3种反馈（GREEN/YELLOW/GRAY）
- **需要词汇知识**：常见词、字母频率、词形模式
- **多轮交互**：每轮决策都影响后续

**对比其他游戏**：
```
Word Puzzle (填字游戏):
  - 单轮决策
  - 有明确上下文（交叉词提供线索）
  - 容易学习模式

Alphabetical Sorting (路径查找):
  - 单轮决策
  - 搜索空间小（3x3或4x4网格）
  - 规则明确

Wordle:
  - 10轮迭代决策
  - 搜索空间大（数千词）
  - 需要约束推理 + 词汇知识
```

---

#### 问题 7: **评估集与训练集不重叠** ⚠️

**Seeds 配置**：
```
训练集: seeds 51-70 (20题)
评估集: seeds 1-50  (50题)
```

**问题**：
- 不同 seed → 不同的隐藏单词
- 训练集和评估集的词**完全不重叠**
- 如果经验不够通用，就无法迁移

**举例**：
```
训练集学到：
  "对于 'crane' 这个词，如果第1轮猜 'soare'..."

评估集遇到：
  隐藏词是 'phone'

→ 训练时学到的 'crane' 的经验用不上
```

---

## 🎯 为什么没有提升？总结

### 根本原因

| 原因 | 影响程度 | 说明 |
|------|---------|------|
| **1. 经验内容重复冗余** | 🔴 极高 | 6条L0说同一件事，信息增益≈0 |
| **2. 只学到开局，未学推理** | 🔴 极高 | 开局容易，推理才是难点 |
| **3. 数据量太小 (20题)** | 🟠 高 | 难以覆盖足够多的模式 |
| **4. L0占比过高，L2缺失** | 🟠 高 | 案例化严重，缺乏泛化能力 |
| **5. 聚合阈值设置不当** | 🟡 中 | 限制了高层经验生成 |
| **6. Wordle 游戏本身难** | 🟡 中 | 需要复杂约束推理 |
| **7. 训练/评估不重叠** | 🟢 低 | 这是正确的实验设计 |

---

## 💡 改进建议

### 策略 1: **增加训练数据量** ⭐⭐⭐⭐⭐

**推荐配置**：
```yaml
num_train_seeds: 50-100  # 至少50题
```

**原因**：
- 更多数据 → 更多模式
- 更多模式 → 更通用的经验
- 更通用的经验 → 更好的泛化

---

### 策略 2: **调整聚合阈值（对于小数据集）** ⭐⭐⭐⭐

**20题配置**：
```yaml
hierarchical_learning:
  l1_aggregation_threshold: 3  # 降低
  l2_aggregation_threshold: 2  # 降低
  max_l0_recent: 20
```

**50题配置**：
```yaml
hierarchical_learning:
  l1_aggregation_threshold: 4
  l2_aggregation_threshold: 2
  max_l0_recent: 30
```

---

### 策略 3: **引导经验生成关注推理过程** ⭐⭐⭐⭐⭐

**问题**：当前 prompt 可能引导 LLM 只总结"第一次猜测"

**解决**：修改经验生成的 prompt，明确要求：
```
在总结 Wordle 经验时，请关注：
1. 如何选择第一个猜测词（信息增益最大化）
2. 如何处理 GREEN 反馈（锁定正确位置）
3. 如何处理 YELLOW 反馈（排除错误位置）
4. 如何处理 GRAY 反馈（排除字母）
5. 如何在第2-6轮根据反馈缩小候选范围
6. 如何避免重复已知错误的猜测
7. 如何在多个候选词中快速决策
```

**实现位置**：
- `utu/practice/experience_updater.py` 中的 prompt 模板
- 或者 `prompts/` 目录下的相关模板

---

### 策略 4: **可视化经验质量** ⭐⭐⭐

**创建分析脚本**：
```bash
# 查看学到的经验内容
uv run python scripts/korgym/inspect_wordle_experiences.py
```

**输出示例**：
```
=== Wordle 经验分析 ===
训练轮次: 4
总经验数: 7

L2 (元策略) - 0 条:
  (无)

L1 (模式级) - 1 条:
  1. 选择高熵开局词...

L0 (案例级) - 6 条:
  1. Initial Guess: crane
  2. Initial Guess: soare
  3. Initial Guess: crane (重复！)
  ...

⚠️ 问题：
  - L0 经验有重复
  - 缺少 L2 元策略
  - 所有经验都关于"第一次猜测"
  - 缺少"如何处理反馈"的经验
```

---

### 策略 5: **尝试不同的游戏** ⭐⭐⭐

如果 Wordle 确实太难，可以先在更简单的游戏上验证框架：

**推荐顺序**：
1. **Word Puzzle** (填字游戏)
   - 单轮决策
   - 部分得分
   - 较容易学习模式

2. **Alphabetical Sorting** (路径查找)
   - 单轮决策
   - 搜索空间小
   - 规则明确

3. **Wordle** (单词猜测)
   - 多轮迭代
   - 搜索空间大
   - 最具挑战

---

### 策略 6: **使用更强的基座模型** ⭐⭐⭐

当前模型：`Qwen/Qwen2.5-72B-Instruct`

**尝试**：
- `Qwen/Qwen2.5-110B` (如果可用)
- `deepseek-chat` 或 `deepseek-reasoner`
- 更强的推理能力 → 可能更好地利用经验

---

## 🔬 快速验证实验

### 实验 A: 增加数据量（推荐）

```bash
# 1. 创建 50 题训练集
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --train_seeds_start 51 \
  --train_seeds_end 100 \
  --level 4

# 2. 修改配置文件
# configs/practice/korgym/wordle_practice_50.yaml:
#   num_train_seeds: 50
#   batch_size: 50
#   l1_aggregation_threshold: 4
#   l2_aggregation_threshold: 2

# 3. 运行训练
uv run python scripts/run_practice.py \
  --config_name korgym/wordle_practice_50

# 4. 评估
uv run python scripts/run_eval.py \
  --config_name korgym/wordle_practice_50_eval
```

---

### 实验 B: 调整阈值（20题）

```yaml
# configs/practice/korgym/wordle_practice_20_optimized.yaml
hierarchical_learning:
  enabled: true
  l1_aggregation_threshold: 3  # 3个L0 → 1个L1
  l2_aggregation_threshold: 2  # 2个L1 → 1个L2
  max_l0_per_game: 1
  max_l0_recent: 20
```

---

### 实验 C: 先在 Word Puzzle 上验证

```bash
# Word Puzzle 更容易，先验证框架是否work
uv run python scripts/run_practice.py \
  --config_name korgym/word_puzzle_practice

uv run python scripts/run_eval.py \
  --config_name korgym/word_puzzle_practice_eval

# 对比结果
uv run python scripts/korgym/compare_korgym_results.py \
  --baseline word_puzzle_baseline_eval \
  --enhanced word_puzzle_practice_eval
```

---

## 📚 文献支持

根据 Training-Free GRPO 论文的实验：

1. **数据量影响**：
   - 训练集从 20 → 100，性能提升显著
   - 小数据集容易过拟合

2. **层次化经验的作用**：
   - L0 提供具体案例
   - L1 提取通用模式（**关键**）
   - L2 形成元策略（**最重要**）

3. **Wordle 的挑战**：
   - 论文中 Wordle 的提升幅度通常小于其他游戏
   - 需要更多训练数据

---

## 🎯 结论

**你的经验质量不差，但有几个关键问题**：

1. ✅ **经验生成成功了**（有7条）
2. ❌ **但内容重复冗余**（6条L0说同一件事）
3. ❌ **只学到了开局，没学到推理过程**（这是最大问题）
4. ⚠️ **数据量太小**（20题难以覆盖足够模式）
5. ⚠️ **缺少 L2 元策略**（最有泛化能力的经验）

**建议优先尝试**：
1. 🔥 **增加训练数据到 50-100 题**
2. 🔥 **修改经验生成 prompt，关注推理过程**
3. 🔥 **降低聚合阈值以生成更多 L1/L2**

---

*相关文件：*
- 配置: `configs/practice/korgym/wordle_practice_20.yaml`
- Agent: `configs/agents/practice/wordle_practice_20_l4_agent.yaml`
- 分析脚本: `scripts/korgym/compare_korgym_results.py`


