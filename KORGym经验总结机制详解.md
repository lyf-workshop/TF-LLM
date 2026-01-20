# KORGym 经验总结机制详解 🎮📚

## 📋 概述

KORGym 使用**三层分层经验学习（Hierarchical Experience Learning, HEL）**系统，从游戏对局中自动提取和聚合经验，逐步形成从具体到抽象的知识层次。

```
游戏对局 → L0 经验（案例级） → L1 经验（模式级） → L2 经验（元策略级） → 增强 Agent
```

---

## 🎯 三层经验架构

### L0：Case-Specific Experiences（案例级经验）
- **来源**：单次游戏对局
- **内容**：具体的成功/失败案例
- **特点**：高度具体，包含游戏状态和决策细节
- **标签**：`[L0-Case]`

### L1：Pattern-Level Experiences（模式级经验）  
- **来源**：聚合 5 个 L0 经验
- **内容**：通用的策略模式和战术
- **特点**：跨案例的共性，更抽象
- **标签**：`[L1-Pattern]`

### L2：Meta-Strategy Experiences（元策略级经验）
- **来源**：聚合 3 个 L1 经验 + 对应的 L0 经验
- **内容**：高层次的思维原则和元认知策略
- **特点**：跨游戏的通用原则
- **标签**：`[L2-Meta]`

---

## 🔄 完整的经验生成流程

### 阶段 1：游戏对局（Game Playing）

```python
# 1. Agent 玩游戏
KORGymAdapter.play_game(agent, seed)
  ├─ 单回合游戏: play_single_round()
  └─ 多回合游戏: play_multiple_rounds()
      ├─ 生成游戏实例 (generate_game_instance)
      ├─ Agent 做决策
      ├─ 验证动作 (verify_action)
      └─ 更新游戏状态
```

**输出**：游戏轨迹（Trajectory）
```json
{
  "game_name": "3-2048",
  "seed": 42,
  "success": true,
  "final_score": 2048,
  "rounds": 25,
  "trajectory": [
    {"action": "up", "score": 0, "board": "..."},
    {"action": "right", "score": 4, "board": "..."},
    ...
  ],
  "response_time": 15.3
}
```

---

### 阶段 2：L0 经验提取（Experience Extraction）

```python
# 2. 从游戏轨迹提取 L0 经验
KORGymExperienceExtractor.extract_l0_from_round(round_result)
```

**使用 LLM 分析游戏轨迹**：

```
输入到 LLM：
├─ 游戏信息（名称、分类、结果）
├─ 最终得分和成功状态
└─ 完整的游戏轨迹
   ├─ 每一步的动作
   ├─ 每一步的得分
   └─ 棋盘状态变化

LLM 任务：
1. 识别关键错误或成功策略
2. 提供具体、可操作的建议
3. 关注游戏状态和决策上下文
4. 总结可改进的地方
```

**Prompt 模板**（核心部分）：

```jinja2
Analyze the following game round and extract a concrete, actionable experience.

Game Information:
- Game Name: {{ game_name }}
- Success: {{ success }}
- Final Score: {{ final_score }}

Multi-Round Game Trajectory:
{% for i, step in enumerate(trajectory) %}
Round {{ i + 1 }}:
  Action: {{ step.action }}
  Score: {{ step.score }}
  State: {{ step.board }}
{% endfor %}

Extract ONE specific experience that:
1. Identifies a key mistake OR successful strategy
2. Provides concrete, actionable advice
3. Is specific to the game state/context
4. Helps improve future performance

Format: [L0-Case] Experience Title: Detailed description...
```

**L0 经验示例**：

```
[L0-Case] Early Corner Strategy: In 2048, prioritizing moves that keep 
the highest tile in a corner (preferably bottom-right) and building tiles 
in descending order along the edge significantly improves the chance of 
reaching 2048. Avoid moves that break this structure early in the game.
```

**存储结构**：

```json
{
  "id": "L0_0",
  "content": "Early Corner Strategy: In 2048, prioritizing...",
  "level": "L0-Case",
  "game_name": "3-2048",
  "seed": 42,
  "success": true,
  "score": 2048,
  "timestamp": "2026-01-10T12:30:45"
}
```

---

### 阶段 3：L1 经验聚合（Pattern Aggregation）

```python
# 3. 每积累 5 个 L0，自动生成 1 个 L1
HierarchicalExperienceManager._try_generate_l1()
```

**触发条件**：
- ✅ 积累了 5 个未聚合的 L0 经验（可配置：`l1_aggregation_threshold: 5`）

**聚合过程**：

```
选择 5 个最新的未聚合 L0 经验
    ↓
送入 LLM 分析
    ↓
提取跨案例的共性模式
    ↓
生成 L1 模式级经验
    ↓
标记这 5 个 L0 已被聚合
```

**Prompt 模板**（L1 生成）：

```jinja2
System Prompt:
You are analyzing game-playing experiences to extract general patterns.

Agent Objective: {{ agent_objective }}
Learning Objective: {{ learning_objective }}

User Prompt:
Below are {{ l0_experiences|length }} case-specific experiences (L0) 
from game rounds:

{% for exp in l0_experiences %}
{{ loop.index }}. {{ exp.content }}
{% endfor %}

Extract ONE general strategy pattern (L1) that:
1. Identifies common successful/unsuccessful approaches
2. Abstracts away game-specific details
3. Provides a tactical principle applicable across similar cases
4. Bridges concrete cases to strategic thinking

Format: [L1-Pattern] Pattern Name: Description with tactical advice.
```

**L1 经验示例**：

```
[L1-Pattern] Structural Preservation Strategy: When playing spatial puzzle 
games, maintain a consistent organizational structure (e.g., sorted order, 
corner anchoring) throughout the game. Breaking structure prematurely leads 
to chaos and limits future options. Apply this by: (1) establishing structure 
early, (2) only making moves that preserve or enhance it, (3) avoiding 
opportunistic moves that compromise structure.
```

**存储结构**：

```json
{
  "id": "L1_0",
  "content": "Structural Preservation Strategy: When playing...",
  "level": "L1-Pattern",
  "source_l0_ids": ["L0_0", "L0_1", "L0_2", "L0_3", "L0_4"],
  "timestamp": "2026-01-10T12:35:20"
}
```

---

### 阶段 4：L2 经验聚合（Meta-Strategy Synthesis）

```python
# 4. 每积累 3 个 L1，自动生成 1 个 L2
HierarchicalExperienceManager._try_generate_l2()
```

**触发条件**：
- ✅ 积累了 3 个 L1 经验（可配置：`l2_aggregation_threshold: 3`）

**关键创新：双重输入**

```
选择 3 个最新的 L1 经验
    ↓
找到这 3 个 L1 对应的所有 L0 经验（15 个）
    ↓
同时送入 LLM: L1 (模式) + L0 (案例)
    ↓
提取元认知策略和思维原则
    ↓
生成 L2 元策略级经验
```

**为什么需要 L0 + L1 双重输入？**

| 只用 L1 | L1 + L0 双重输入 |
|---------|------------------|
| ❌ 可能过度抽象 | ✅ 保持实践基础 |
| ❌ 脱离具体案例 | ✅ 原则有具体支撑 |
| ❌ 难以验证 | ✅ 可回溯到案例 |

**Prompt 模板**（L2 生成）：

```jinja2
System Prompt:
You are extracting meta-cognitive principles from game-playing patterns.

Agent Objective: {{ agent_objective }}
Learning Objective: {{ learning_objective }}

User Prompt:
L1 Pattern-Level Experiences:
{% for l1 in l1_experiences %}
- {{ l1.content }}
{% endfor %}

L0 Case-Specific Experiences (supporting the above L1 patterns):
{% for l0 in l0_experiences %}
- {{ l0.content }}
{% endfor %}

Extract ONE meta-strategy (L2) that:
1. Captures the fundamental principle behind these patterns
2. Considers both L1 patterns AND their source L0 cases
3. Provides high-level thinking framework
4. Is applicable across different game types

Format: "Principle: [principle]. [explanation]. [benefits]."
```

**L2 经验示例**：

```
[L2-Meta] Principle: Prioritize maintaining systematic structure over 
opportunistic gains in complex decision spaces. Establishing and preserving 
organizational frameworks (spatial, logical, or temporal) reduces cognitive 
load, prevents error accumulation, and creates predictable patterns that 
enable strategic planning. Benefits: clearer decision-making, reduced 
backtracking, and improved long-term outcomes across diverse problem domains.
```

**存储结构**：

```json
{
  "id": "L2_0",
  "content": "Principle: Prioritize maintaining systematic...",
  "level": "L2-Meta",
  "source_l1_ids": ["L1_0", "L1_1", "L1_2"],
  "source_l0_ids": ["L0_0", ..., "L0_14"],
  "timestamp": "2026-01-10T12:40:15"
}
```

---

## 🚀 Agent 配置集成

### 阶段 5：经验整合到 Agent（Agent Enhancement）

```python
# 5. 将分层经验注入到 Agent 配置中
training_free_grpo._create_agent_config_with_experiences()
```

**整合顺序**：从高到低（L2 → L1 → L0）

```yaml
agent:
  name: korgym_enhanced_agent
  instructions: |
    Solve the following game strategically.
    
    When playing, you MUST first carefully read and understand 
    the helpful instructions and experiences:
    
    [G0]. [L2-Meta] Principle: Prioritize maintaining systematic...
    
    [G1]. [L1-Pattern] Structural Preservation Strategy: When playing...
    [G2]. [L1-Pattern] Adaptive Planning: Continuously evaluate...
    [G3]. [L1-Pattern] Risk-Reward Analysis: Before making moves...
    
    [G4]. [L0-Case] Early Corner Strategy: In 2048, prioritizing...
    [G5]. [L0-Case] Merge Sequencing: When multiple merge options...
    [G6]. [L0-Case] Edge Building: Maintain tiles along one edge...
    ...
```

**配置参数**：

```yaml
hierarchical_learning:
  enabled: true
  l1_aggregation_threshold: 5    # 5 L0 → 1 L1
  l2_aggregation_threshold: 3     # 3 L1 → 1 L2
  max_l0_per_game: 3             # 每个游戏最多提取 3 个 L0
  max_l0_recent: 30              # Prompt 中只包含最近 30 个 L0
  include_l0_in_prompt: true     # 是否在 Prompt 中包含 L0
  
  experience_save_path: workspace/hierarchical_experiences/korgym_2048.json
  agent_save_path: configs/agents/practice/korgym_2048_agent.yaml
```

---

## 📊 完整示例：2048 游戏

### 游戏对局 → L0 提取

```
对局 1-5:
├─ 对局 1: 失败 (score: 512)
│   └─ L0_0: "避免破坏角落结构"
├─ 对局 2: 成功 (score: 2048)
│   └─ L0_1: "保持最大瓦片在角落"
├─ 对局 3: 失败 (score: 1024)
│   └─ L0_2: "提前规划合并序列"
├─ 对局 4: 成功 (score: 2048)
│   └─ L0_3: "沿边缘构建递减序列"
└─ 对局 5: 失败 (score: 256)
    └─ L0_4: "避免早期随机移动"

触发 L1 生成 ✓
```

### L0 聚合 → L1 生成

```
L0_0 + L0_1 + L0_2 + L0_3 + L0_4
         ↓ LLM 分析
    L1_0: "Structural Preservation Strategy"
    (结构保持策略)
```

### 继续积累更多经验

```
对局 6-10:
├─ L0_5: "中期避免填满棋盘"
├─ L0_6: "保留移动灵活性"
├─ L0_7: "识别死局模式"
├─ L0_8: "优先合并大瓦片"
└─ L0_9: "动态调整策略"

触发 L1 生成 ✓
    L1_1: "Adaptive Planning Strategy"
    (自适应规划策略)

对局 11-15:
├─ L0_10: "评估风险-收益权衡"
├─ L0_11: "短期vs长期目标平衡"
├─ L0_12: "避免贪婪决策"
├─ L0_13: "为未来留出空间"
└─ L0_14: "持续评估局面"

触发 L1 生成 ✓
    L1_2: "Risk-Reward Analysis Strategy"
    (风险-收益分析策略)
```

### L1 聚合 → L2 生成

```
L1_0 + L1_1 + L1_2  (3 个 L1)
    +
L0_0 ~ L0_14        (15 个对应的 L0)
         ↓ LLM 分析 (双重输入)
    L2_0: "Principle: Prioritize systematic structure 
           over opportunistic gains"
    (元原则：系统化结构优于机会主义收益)
```

---

## 🎮 训练流程示例

```bash
# 启动分层经验学习训练
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym_hierarchical_test

# 训练过程
Epoch 1/3, Batch 1/2:
  ├─ 玩 5 个游戏 (seeds 0-4)
  ├─ 提取 5 个 L0 → 生成 L1_0
  └─ 保存: workspace/hierarchical_experiences/korgym_2048.json

Epoch 1/3, Batch 2/2:
  ├─ 玩 5 个游戏 (seeds 5-9)
  ├─ 提取 5 个 L0 → 生成 L1_1
  └─ 更新经验库

Epoch 2/3, Batch 1/2:
  ├─ 玩 5 个游戏 (seeds 10-14)
  ├─ 提取 5 个 L0 → 生成 L1_2
  ├─ 触发 L2 生成: L1_0 + L1_1 + L1_2 + L0_0~L0_14 → L2_0
  └─ 更新 Agent 配置 (包含 L2)

Epoch 3/3:
  ├─ 使用增强的 Agent (包含 L2/L1/L0 经验)
  └─ 性能提升 ↑

最终输出:
├─ workspace/hierarchical_experiences/korgym_2048.json (经验库)
└─ configs/agents/practice/korgym_2048_agent.yaml (增强 Agent)
```

---

## 🔍 关键设计亮点

### 1. **渐进式抽象**
```
具体案例 (L0) → 战术模式 (L1) → 思维原则 (L2)
```

### 2. **双重输入机制** (L2 生成)
```
L1 (抽象模式) + L0 (具体案例) → L2 (有根基的元策略)
```

### 3. **自动化流程**
- ✅ 无需人工标注
- ✅ 基于阈值自动触发
- ✅ 增量式学习

### 4. **实时反馈**
```
训练 → 提取经验 → 更新 Agent → 再训练 → 性能提升
```

### 5. **可配置性**
```yaml
l1_aggregation_threshold: 5   # 调整 L1 生成频率
l2_aggregation_threshold: 3   # 调整 L2 生成频率
max_l0_recent: 30             # 控制 Prompt 长度
```

---

## 📈 经验数量示例

假设玩 50 个游戏：

```
50 个游戏
  ↓ (每个游戏 1 个 L0)
50 个 L0 经验
  ↓ (每 5 个 L0 → 1 个 L1)
10 个 L1 经验
  ↓ (每 3 个 L1 → 1 个 L2)
3 个 L2 经验

最终 Agent Prompt 包含:
- 3 个 L2 (元策略)
- 10 个 L1 (战术模式)
- 30 个 L0 (最近的案例，可配置)
= 43 条经验
```

---

## 🎯 与传统方法对比

| 维度 | 传统单层经验 | KORGym 分层经验 |
|------|-------------|----------------|
| **结构** | 扁平列表 | L0 → L1 → L2 层次 |
| **抽象** | 混合不同抽象级别 | 明确分层 |
| **溯源** | 无法追溯来源 | 完整追溯链 |
| **适用性** | 单任务 | 跨任务迁移 |
| **Prompt 长度** | 随经验线性增长 | 控制在合理范围 |
| **知识重用** | 低 | 高（L2/L1 可跨游戏） |

---

## 📚 相关文件

### 核心代码
- `utu/practice/korgym_adapter.py` - 游戏交互适配器
- `utu/practice/korgym_experience_extractor.py` - L0 经验提取器
- `utu/practice/hierarchical_experience_manager.py` - 分层经验管理器
- `utu/practice/training_free_grpo.py` - 训练主流程

### 配置文件
- `configs/practice/korgym_hierarchical_test.yaml` - 训练配置
- `configs/prompts/hierarchical_critique.yaml` - Prompt 模板
- `configs/agents/practice/logic_agent_hierarchical_learning_clean.yaml` - Agent 基础配置

### 工具脚本
- `scripts/test_korgym_adapter.py` - 测试适配器
- `scripts/debug_game_server.py` - 调试服务器
- `scripts/check_korgym_env.py` - 环境检查

---

## ✅ 总结

KORGym 的经验总结机制实现了：

1. **自动化**：从游戏对局到经验生成，全程自动
2. **分层化**：L0/L1/L2 三层结构，由具体到抽象
3. **智能化**：使用 LLM 进行经验提取和聚合
4. **可追溯**：每个经验都有明确的来源链
5. **可配置**：灵活的阈值和参数设置

**核心价值**：让 Agent 能够从游戏实践中**自主学习**，形成从具体案例到通用原则的**知识金字塔** 🎯

---

## 🚀 快速上手

```bash
# 1. 安装依赖
curl -LsSf https://astral.sh/uv/install.sh | sh
uv pip install fastapi gymnasium pygame

# 2. 检查环境
python scripts/check_korgym_env.py

# 3. 测试适配器
uv run python scripts/test_korgym_adapter.py

# 4. 开始训练
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym_hierarchical_test

# 5. 查看生成的经验
cat workspace/hierarchical_experiences/korgym_2048.json
```

🎮 开始你的 KORGym 经验学习之旅！











