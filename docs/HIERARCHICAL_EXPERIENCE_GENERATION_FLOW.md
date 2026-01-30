# 分层经验生成流程详解

## 📋 目录

1. [概述](#概述)
2. [完整流程图](#完整流程图)
3. [各阶段详细说明](#各阶段详细说明)
4. [L0/L1/L2 生成逻辑](#l0l1l2-生成逻辑)
5. [关键配置参数](#关键配置参数)
6. [实际示例](#实际示例)

---

## 概述

### 🎯 分层经验架构

```
L2（元策略级 Meta-Strategy）
  ↑ 聚合自 3 个 L1 + 源 L0
L1（模式级 Pattern-Level）
  ↑ 聚合自 5 个 L0
L0（案例级 Case-Specific）
  ↑ 来自单个问题的经验总结
```

### 📍 生成阶段

**分层经验在 Training-Free GRPO 训练阶段生成**，具体在每个 step（epoch）的经验更新后进行。

---

## 完整流程图

```
┌─────────────────────────────────────────────────────────────────┐
│ Training-Free GRPO 主流程 (training_free_grpo.py)               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Rollout (每个 epoch 的推理过程)                          │
│   - 对每个训练样本生成多个候选答案                                  │
│   - rollout_manager.rollout_epoch()                            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Experience Update (提取经验)                            │
│   - 基于 rollout 结果提取高质量经验                               │
│   - experience_updater.run()                                   │
│   - 生成 new_experiences = {G0: "...", G1: "...", ...}         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Hierarchical Processing (分层经验处理) ⭐                │
│   - hierarchical_experience_manager.process_step_experiences() │
│   │                                                             │
│   ├─ 3.1: 转换为 L0 经验                                        │
│   │   - 将每个 new_experience 转换为 L0                        │
│   │   - 添加 scope_key、step、problem_count 等元数据            │
│   │   - 谨慎去重（Jaccard 相似度 >= 0.95）                      │
│   │                                                             │
│   ├─ 3.2: 尝试生成 L1 经验                                      │
│   │   - 检查未聚合的 L0 数量 >= l1_aggregation_threshold (默认 5) │
│   │   - 如果满足，调用 _generate_l1_from_l0()                   │
│   │   - 使用 LLM 从 5 个 L0 案例中抽象出 L1 模式                │
│   │                                                             │
│   └─ 3.3: 尝试生成 L2 经验                                      │
│       - 检查未聚合的 L1 数量 >= l2_aggregation_threshold (默认 3) │
│       - 如果满足，调用 _generate_l2_from_l1_and_l0()            │
│       - 使用 LLM 从 3 个 L1 + 源 L0 中提炼 L2 元策略            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Save Experiences (保存经验)                             │
│   - 保存到 workspace/hierarchical_experiences/<exp_id>.json    │
│   - 包含 l0_experiences、l1_experiences、l2_experiences         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Update Agent Config (更新 Agent 配置)                   │
│   - 将 L0/L1/L2 经验注入到 Agent 的 instructions 中              │
│   - 保存到 configs/agents/practice/<agent>_practice_agent.yaml │
└─────────────────────────────────────────────────────────────────┘
```

---

## 各阶段详细说明

### 阶段 1：经验提取（Experience Update）

**位置**：`utu/practice/experience_updater.py`

**输入**：
- Rollout 结果（每个问题的多个候选答案 + reward）

**输出**：
- 传统经验字典：`{G0: "经验内容1", G1: "经验内容2", ...}`

**示例**：
```python
new_experiences = {
    "G0": "在 Wordle 中，优先使用包含常见元音字母（a, e, i, o, u）的单词作为第一次猜测",
    "G1": "根据绿色反馈（正确位置）固定字母，根据黄色反馈（错误位置）排除可能性",
    "G2": "避免重复使用已经标记为灰色（不在单词中）的字母"
}
```

---

### 阶段 2：L0 转换（Case-Specific Experiences）

**位置**：`hierarchical_experience_manager.py` → `process_step_experiences()`

**逻辑**：
```python
async def process_step_experiences(
    self, 
    step_experiences: Dict[str, str],  # 传统经验 {G0: "...", G1: "..."}
    step: int,                         # 当前 step（epoch）
    problem_count: int                 # 本 step 中的问题数量
):
    # 1. 将每个传统经验转换为 L0
    for exp_id, content in step_experiences.items():
        # 提取 scope_key（游戏名称、问题标识等）
        scope_key = self._extract_scope_key(content)
        
        # 谨慎去重：只在同 scope 内且相似度 >= 0.95 时跳过
        if self._is_too_similar_to_recent_l0(content, scope_key, threshold=0.95):
            continue
        
        # 创建 L0 经验
        l0_exp = {
            'id': f"L0_{len(self.l0_experiences)}",
            'content': content,
            'original_id': exp_id,
            'scope_key': scope_key,
            'step': step,
            'problem_count': problem_count
        }
        self.l0_experiences.append(l0_exp)
    
    # 2. 尝试生成 L1
    await self._try_generate_l1(step)
    
    # 3. 尝试生成 L2
    await self._try_generate_l2(step)
    
    # 4. 保存所有经验
    self.save_experiences()
```

**示例 L0 经验**：
```json
{
  "id": "L0_15",
  "content": "在 Wordle 中，第一次猜测使用 'crane' 可以覆盖常见元音和辅音",
  "original_id": "G3",
  "scope_key": "33-wordle",
  "step": 2,
  "problem_count": 10
}
```

---

### 阶段 3：L1 生成（Pattern-Level Experiences）

**位置**：`hierarchical_experience_manager.py` → `_try_generate_l1()`

**触发条件**：
```python
未聚合的 L0 数量 >= l1_aggregation_threshold (默认 5)
```

**生成流程**：
```python
async def _try_generate_l1(self, step: int):
    # 1. 获取未聚合的 L0
    recent_l0 = self._get_unaggregated_l0()
    
    # 2. 检查是否达到阈值（默认 5 个）
    if len(recent_l0) >= self.h_config.l1_aggregation_threshold:
        # 3. 取前 5 个 L0
        l0_batch = recent_l0[:5]
        
        # 4. 调用 LLM 生成 L1 模式
        l1_content = await self._generate_l1_from_l0(l0_batch)
        
        # 5. 保存 L1 经验
        l1_exp = {
            'id': f"L1_{len(self.l1_experiences)}",
            'content': l1_content,
            'source_l0_ids': [exp['id'] for exp in l0_batch],
            'step': step
        }
        self.l1_experiences.append(l1_exp)
```

**LLM Prompt**（简化版）：
```
System: 你是专家，从多个具体案例（L0）中提取通用策略模式（L1）。

User:
L0 案例 1: "第一次猜测用 'crane' 覆盖常见字母"
L0 案例 2: "第一次用 'soare' 测试高频元音"
L0 案例 3: "起始词选择 'audio' 包含多个元音"
L0 案例 4: "首次猜测 'stare' 平衡元音辅音"
L0 案例 5: "开局使用 'arise' 最大化信息量"

任务：提取一个通用的模式级策略（L1）。

Assistant 生成:
"使用预定义的高熵起始词（如 crane、soare、audio）来最大化第一轮的信息增益，
快速缩小解空间并为后续推理提供有效约束。"
```

**示例 L1 经验**：
```json
{
  "id": "L1_3",
  "content": "使用预定义的高熵起始词来最大化第一轮信息增益",
  "source_l0_ids": ["L0_15", "L0_16", "L0_17", "L0_18", "L0_19"],
  "step": 2
}
```

---

### 阶段 4：L2 生成（Meta-Strategy Experiences）

**位置**：`hierarchical_experience_manager.py` → `_try_generate_l2()`

**触发条件**：
```python
未聚合的 L1 数量 >= l2_aggregation_threshold (默认 3)
```

**生成流程**：
```python
async def _try_generate_l2(self, step: int):
    # 1. 获取未聚合的 L1
    recent_l1 = self._get_unaggregated_l1()
    
    # 2. 检查是否达到阈值（默认 3 个）
    if len(recent_l1) >= self.h_config.l2_aggregation_threshold:
        # 3. 取前 3 个 L1
        l1_batch = recent_l1[:3]
        
        # 4. 获取所有源 L0（关键！避免过度抽象）
        source_l0_ids = set()
        for l1 in l1_batch:
            source_l0_ids.update(l1['source_l0_ids'])
        source_l0 = [exp for exp in self.l0_experiences if exp['id'] in source_l0_ids]
        
        # 5. 调用 LLM 生成 L2 元策略（基于 L1 + 源 L0）
        l2_content = await self._generate_l2_from_l1_and_l0(l1_batch, source_l0)
        
        # 6. 保存 L2 经验
        l2_exp = {
            'id': f"L2_{len(self.l2_experiences)}",
            'content': l2_content,
            'source_l1_ids': [exp['id'] for exp in l1_batch],
            'step': step
        }
        self.l2_experiences.append(l2_exp)
```

**关键创新**：
- ✅ **L2 基于 L1 + 源 L0 双重输入**，而非仅基于 L1
- ✅ 避免过度抽象（传统方法：`L2 = LLM(L1_batch)`）
- ✅ 保持原则的实用性和可解释性

**LLM Prompt**（简化版）：
```
System: 你是专家，从多个模式（L1）及其源案例（L0）中提炼跨任务元策略（L2）。

User:
L1 模式 1: "使用高熵起始词最大化信息增益"
L1 模式 2: "系统性验证约束防止逻辑矛盾"
L1 模式 3: "构建显式结构（表格/图）外化复杂度"

源 L0 案例（15 个）:
- "第一次用 crane 覆盖常见字母"
- "验证 clue 3 与 clue 5 的依赖关系"
- "为问题 7 构建约束表格"
- ...

任务：提炼一个跨任务的元策略原则（L2）。

Assistant 生成:
"Principle: 在搜索空间不确定时，优先投资于信息获取和结构化表示。
早期的结构投资（高熵探索、显式约束建模）能够指数级降低后续搜索成本，
将问题从试错驱动转化为约束驱动的系统推理。"
```

**示例 L2 经验**：
```json
{
  "id": "L2_1",
  "content": "Principle: 在搜索空间不确定时，优先投资于信息获取和结构化表示...",
  "source_l1_ids": ["L1_3", "L1_4", "L1_5"],
  "step": 3
}
```

---

## L0/L1/L2 生成逻辑

### L0 生成逻辑

**方法**：直接转换传统经验

**核心代码**：
```python
# utu/practice/hierarchical_experience_manager.py

for exp_id, content in step_experiences.items():
    scope_key = self._extract_scope_key(content)
    
    # 谨慎去重（同 scope 内，相似度 >= 0.95）
    if self._is_too_similar_to_recent_l0(content, scope_key, threshold=0.95):
        continue
    
    l0_exp = {
        'id': f"L0_{len(self.l0_experiences)}",
        'content': content,
        'original_id': exp_id,
        'scope_key': scope_key,
        'step': step,
        'problem_count': problem_count
    }
    self.l0_experiences.append(l0_exp)
```

**去重策略**：
- 只在同一 `scope_key`（游戏/任务）内去重
- 高阈值 0.95（只去除几乎完全相同的经验）
- 没有 `scope_key` 时不去重（避免跨任务误杀）

---

### L1 生成逻辑

**方法**：LLM 从 5 个 L0 案例中抽象模式

**核心代码**：
```python
# utu/practice/hierarchical_experience_manager.py

async def _generate_l1_from_l0(self, l0_batch: List[Dict]) -> str:
    # 1. 加载 prompt 模板
    l1_prompt = self.prompts["L1_AGGREGATION_PROMPT"]
    
    # 2. 渲染 system prompt
    system_prompt = Template(l1_prompt["system"]).render(
        agent_objective=self.agent_objective,
        learning_objective=self.learning_objective,
    )
    
    # 3. 渲染 user prompt（包含 5 个 L0 案例）
    user_prompt = Template(l1_prompt["user"]).render(
        l0_experiences=l0_batch
    )
    
    # 4. 调用 LLM 生成 L1
    response = await self.llm.query_one(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # 较低温度，确保稳定输出
    )
    
    return response.strip()
```

**Prompt 模板**：`configs/prompts/hierarchical_critique.yaml`

---

### L2 生成逻辑

**方法**：LLM 从 3 个 L1 + 源 L0 中提炼元策略

**核心代码**：
```python
# utu/practice/hierarchical_experience_manager.py

async def _generate_l2_from_l1_and_l0(
    self, 
    l1_batch: List[Dict],      # 3 个 L1
    source_l0: List[Dict]       # 约 15 个源 L0（3×5）
) -> str:
    # 1. 加载 prompt 模板
    l2_prompt = self.prompts["L2_AGGREGATION_PROMPT"]
    
    # 2. 渲染 system prompt
    system_prompt = Template(l2_prompt["system"]).render(
        agent_objective=self.agent_objective,
        learning_objective=self.learning_objective,
    )
    
    # 3. 渲染 user prompt（包含 3 个 L1 + 源 L0）
    user_prompt = Template(l2_prompt["user"]).render(
        l1_experiences=l1_batch,
        l0_experiences=source_l0,  # ✅ 关键：提供源 L0
    )
    
    # 4. 调用 LLM 生成 L2
    response = await self.llm.query_one(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    
    return response.strip()
```

**关键设计**：
- ✅ L2 基于 **L1 + 源 L0** 双重输入
- ✅ 避免过度抽象，保持实用性
- ✅ 源 L0 提供具体上下文，防止泛泛而谈

---

## 关键配置参数

### 分层学习配置

**位置**：`configs/practice/<experiment>.yaml`

```yaml
hierarchical_learning:
  enabled: true                      # 是否启用分层学习
  
  # L1 聚合阈值（多少个 L0 → 1 个 L1）
  l1_aggregation_threshold: 5
  
  # L2 聚合阈值（多少个 L1 → 1 个 L2）
  l2_aggregation_threshold: 3
  
  # 每个问题最多生成多少个 L0
  max_l0_per_problem: 1
  
  # L1 最大数量
  max_l1_total: 50
  
  # L2 最大数量
  max_l2_total: 10
  
  # 是否在 Agent prompt 中包含 L0
  include_l0_in_prompt: true
  
  # Agent prompt 中最多包含多少个最近的 L0
  max_l0_recent: 10
  
  # 经验保存路径
  experience_save_path: workspace/hierarchical_experiences/${exp_id}.json
```

---

## 实际示例

### 完整流程示例（Wordle）

#### Step 1：训练开始

```bash
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20
```

#### Step 2：第一个 Epoch 的 Rollout

```
Epoch 1/3:
- 处理 20 个 Wordle 问题
- 每个问题生成 3 个候选答案
- 总计 60 个 rollout
```

#### Step 3：经验提取

```
Experience Update:
- 从 60 个 rollout 中提取经验
- 生成 10 个传统经验 (G0-G9)
```

**示例经验**：
```python
new_experiences = {
    "G0": "第一次猜测使用 crane 来覆盖常见元音和辅音",
    "G1": "根据绿色反馈固定字母位置",
    "G2": "根据黄色反馈排除错误位置",
    "G3": "避免使用灰色字母",
    "G4": "注意双字母单词的可能性",
    ...
}
```

#### Step 4：分层处理

```
Hierarchical Processing (Step 1):

1. L0 转换:
   ✅ 添加 10 个 L0 经验 (L0_0 - L0_9)
   - scope_key: "33-wordle"
   - step: 1
   - problem_count: 20

2. L1 生成:
   ⏸️  未聚合的 L0 数量: 10
   ⏸️  需要: 5 个（已满足）
   ⏸️  但只在第一次满足阈值时生成
   ✅ 生成 L1_0 和 L1_1（从前 10 个 L0 中生成 2 个 L1）

3. L2 生成:
   ⏸️  未聚合的 L1 数量: 2
   ❌ 需要: 3 个（未满足）
   ⏸️  等待更多 L1
```

#### Step 5：第二个 Epoch

```
Epoch 2/3:
- 处理 20 个问题
- 生成 10 个新经验 (G10-G19)

Hierarchical Processing (Step 2):
1. L0 转换: +10 (L0_10 - L0_19)
2. L1 生成: +2 (L1_2 - L1_3)
3. L2 生成:
   ✅ 未聚合的 L1 数量: 4（满足阈值 3）
   ✅ 生成 L2_0（从 L1_0, L1_1, L1_2 + 源 L0）
```

#### Step 6：第三个 Epoch

```
Epoch 3/3:
- 处理 20 个问题
- 生成 10 个新经验 (G20-G29)

Hierarchical Processing (Step 3):
1. L0 转换: +10 (L0_20 - L0_29)
2. L1 生成: +2 (L1_4 - L1_5)
3. L2 生成: +1 (L2_1)
```

#### Step 7：最终结果

```
✅ Training completed!

Hierarchical Experiences Generated:
- L0: 30 case-specific experiences
- L1: 6 pattern-level strategies
- L2: 2 meta-strategy principles

Saved to: workspace/hierarchical_experiences/wordle_practice_20.json
```

#### Step 8：查看生成的经验

```bash
cat workspace/hierarchical_experiences/wordle_practice_20.json
```

**输出示例**：
```json
{
  "l0_experiences": [
    {
      "id": "L0_0",
      "content": "第一次猜测使用 crane 来覆盖常见元音和辅音",
      "original_id": "G0",
      "scope_key": "33-wordle",
      "step": 1,
      "problem_count": 20
    },
    ...
  ],
  "l1_experiences": [
    {
      "id": "L1_0",
      "content": "使用预定义的高熵起始词（crane, soare, audio）来最大化第一轮信息增益",
      "source_l0_ids": ["L0_0", "L0_1", "L0_2", "L0_3", "L0_4"],
      "step": 1
    },
    ...
  ],
  "l2_experiences": [
    {
      "id": "L2_0",
      "content": "Principle: 在搜索空间不确定时，优先投资于信息获取和结构化表示...",
      "source_l1_ids": ["L1_0", "L1_1", "L1_2"],
      "step": 2
    }
  ],
  "stats": {
    "total_l0": 30,
    "total_l1": 6,
    "total_l2": 2
  }
}
```

---

## 🎯 总结

### 回答你的问题

#### 1. **分层经验在哪个阶段得到？**

✅ **在 Training-Free GRPO 训练阶段**，具体在每个 epoch 的经验更新后：

```
训练流程:
1. Rollout（生成候选答案）
2. Experience Update（提取传统经验）
3. ⭐ Hierarchical Processing（生成 L0/L1/L2）← 这里！
4. Save Experiences
5. Update Agent Config
```

#### 2. **通过什么总结出来的？**

✅ **通过 LLM 的多层抽象**：

| 层级 | 输入 | 方法 | 输出 |
|------|------|------|------|
| **L0** | 传统经验 | 直接转换 + 去重 | 案例级经验 |
| **L1** | 5 个 L0 | LLM 抽象模式 | 模式级策略 |
| **L2** | 3 个 L1 + 源 L0 | LLM 提炼原则 | 元策略原则 |

**关键创新**：
- ✅ L2 基于 **L1 + 源 L0** 双重输入（避免过度抽象）
- ✅ 谨慎去重（高阈值 0.95，同 scope 限制）
- ✅ 增量生成（每个 epoch 后自动触发）

---

## 📚 相关文件

- **核心代码**：`utu/practice/hierarchical_experience_manager.py`
- **调用入口**：`utu/practice/training_free_grpo.py` (Line 222-234)
- **Prompt 模板**：`configs/prompts/hierarchical_critique.yaml`
- **配置示例**：`configs/practice/korgym/wordle_practice_20.yaml`

---

**文档创建时间**：2026-01-22  
**作者**：Claude Sonnet 4.5
