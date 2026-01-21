# Training-Free GRPO 经验生成机制详解 📚

本文档通过具体例子详细讲解经验生成的完整流程。

## 🎯 核心思想

**GRPO (Group Relative Policy Optimization)** 的核心思想是：
- 为每个问题生成多个不同的解答（rollouts）
- 通过对比成功和失败的解答，提取可学习的经验
- 将经验整合到 agent 的 instructions 中，用于指导未来的解答

---

## 📋 完整流程概览

```
输入：一个 batch 的问题（每个问题有 5 个 rollouts）
  ↓
步骤 1: 单 Rollout 摘要 (Single Rollout Summary)
  ↓
步骤 2: 组优势分析 (Group Advantage)
  ↓
步骤 3: 组更新 (Group Update)
  ↓
步骤 4: 批量更新 (Batch Update)
  ↓
输出：更新后的经验库
```

---

## 🔍 详细例子：ZebraLogic 问题

### 初始状态

假设我们有一个 ZebraLogic 问题，GRPO 为它生成了 5 个不同的解答：

**问题**：
```
有5个房子，每个房子住一个人，养一只宠物，用一种颜色，开一辆车。
已知：
1. Peter 住在第1个房子
2. 养鸟的人住在白色房子旁边
3. 第3个房子是 Craftsman 风格
...
请找出每个房子的完整信息。
```

**5 个 Rollouts 及其结果**：

| Rollout | 解答过程 | Reward | 是否正确 |
|---------|---------|--------|---------|
| Rollout 1 | 尝试了约束推理，但遗漏了关键约束 | 0.0 | ❌ 错误 |
| Rollout 2 | 正确使用了所有约束，得到正确答案 | 1.0 | ✅ 正确 |
| Rollout 3 | 推理过程正确，但最后答案格式错误 | 0.0 | ❌ 错误 |
| Rollout 4 | 部分约束理解错误 | 0.0 | ❌ 错误 |
| Rollout 5 | 正确解答，但推理过程不够清晰 | 1.0 | ✅ 正确 |

**筛选条件检查**：
- 平均分数 = (0 + 1 + 0 + 0 + 1) / 5 = 0.4
- 0 < 0.4 < 1 ✅ **满足条件，会被用于经验生成**

---

## 步骤 1: 单 Rollout 摘要 (Single Rollout Summary)

### 目的
为每个 rollout 生成详细的摘要，分析其推理过程、成功/失败原因。

### 输入
- 问题文本
- Ground Truth 答案
- Rollout 的完整轨迹（trajectory）
- Critique（如果有）

### 处理过程

**对 Rollout 1（失败的）**：
```python
# 调用 LLM 进行分析
prompt = """
分析这个失败的解答：
- 问题：{question}
- 正确答案：{ground_truth}
- 轨迹：{trajectory}
- 错误原因：遗漏了关键约束

请详细分析：
1. 每一步做了什么
2. 哪里出错了
3. 如何改进
"""
```

**LLM 输出摘要**：
```
Execution Summary:
1. Step 1: 
   - Action: 开始分析约束条件
   - Reasoning: 尝试列出所有已知信息
   - Missed: 没有注意到"养鸟的人住在白色房子旁边"这个约束需要同时考虑两个属性

2. Step 2:
   - Action: 尝试分配第1个房子（Peter）
   - Reasoning: 从已知信息开始
   - Missed: 没有考虑这个分配对其他约束的影响

Key Findings:
- 错误地孤立地处理约束，没有考虑约束之间的相互影响
- 遗漏了需要同时满足多个条件的约束

Overall Strategies:
- 采用了顺序分配策略，但没有全局视角
- 需要建立约束网络，同时考虑所有约束
```

**对 Rollout 2（成功的）**：
```
Execution Summary:
1. Step 1:
   - Action: 建立约束表
   - Reasoning: 将所有约束可视化，便于全局分析
   - Success: 正确识别了所有约束类型

2. Step 2:
   - Action: 识别强约束（唯一确定的）
   - Reasoning: Peter 住在第1个房子是强约束
   - Success: 从强约束开始推理

Key Findings:
- 使用约束表帮助全局思考
- 优先处理强约束，然后逐步推理
- 每步都验证是否违反已有约束

Overall Strategies:
- 系统化的约束推理方法
- 全局视角 + 局部验证
```

### 输出
每个 rollout 得到一个详细的摘要，包含：
- 执行步骤分析
- 关键发现
- 整体策略

---

## 步骤 2: 组优势分析 (Group Advantage)

### 目的
对比同一问题的多个 rollouts，找出成功和失败的关键差异，提取初步经验。

### 输入
- 问题文本
- Ground Truth 答案
- 所有 rollouts 的摘要（来自步骤 1）

### 处理过程

```python
# 将所有 rollouts 的摘要组合
formatted_trajectories = """
Attempt 1 (Reward 0.0):
[Rollout 1 的摘要]

Attempt 2 (Reward 1.0):
[Rollout 2 的摘要]

Attempt 3 (Reward 0.0):
[Rollout 3 的摘要]

Attempt 4 (Reward 0.0):
[Rollout 4 的摘要]

Attempt 5 (Reward 1.0):
[Rollout 5 的摘要]
"""

# 调用 LLM 进行对比分析
prompt = """
对比这5个解答，找出：
1. 成功的解答（Reward 1.0）的共同特点
2. 失败的解答（Reward 0.0）的共同问题
3. 成功 vs 失败的关键差异
4. 提取可复用的经验
"""
```

### LLM 输出

```
<Learning Objective Focus>
提高逻辑推理能力，特别是约束满足问题的系统化解决方法
</Learning Objective Focus>

<Performance Assessment>
- Good Responses: 
  - Rollout 2: 使用约束表，系统化推理，全局视角
  - Rollout 5: 虽然推理不够清晰，但最终答案正确
- Bad Responses:
  - Rollout 1: 孤立处理约束，遗漏关键约束
  - Rollout 3: 推理正确但格式错误
  - Rollout 4: 约束理解错误
</Performance Assessment>

<Comparative Analysis>
成功解答的关键因素：
1. **约束可视化**：Rollout 2 使用约束表，将所有信息可视化
2. **全局视角**：同时考虑所有约束，而不是孤立处理
3. **系统化方法**：从强约束开始，逐步推理

失败解答的共同问题：
1. **局部思维**：只关注单个约束，忽略约束间的相互影响
2. **缺乏验证**：没有在每步验证是否违反已有约束
3. **格式问题**：即使推理正确，格式错误也会导致失败
</Comparative Analysis>

<Pattern Identification>
成功模式：
- 建立约束网络/表格
- 优先处理强约束（唯一确定的）
- 每步验证约束一致性

失败模式：
- 孤立处理约束
- 忽略约束间的相互影响
- 缺乏系统性方法
</Pattern Identification>

<Experiences>
1. Constraint visualization: When solving constraint satisfaction problems, create a visual representation (table or network) of all constraints to maintain a global perspective and identify relationships between constraints.

2. Strong constraint prioritization: Start reasoning from strongly determined constraints (those with unique values) and use them as anchors for further deduction.

3. Consistency verification: After each assignment, verify that it doesn't violate any existing constraints before proceeding to the next step.
</Experiences>
```

### 输出
从这个问题中提取的初步经验（3条）

---

## 步骤 3: 组更新 (Group Update)

### 目的
将新提取的经验与现有经验库进行整合，决定是添加、更新还是忽略。

### 输入
- 现有经验库（可能为空，或包含之前提取的经验）
- 新提取的经验（来自步骤 2）

### 处理过程

**假设现有经验库**：
```
[G0]. Constraint handling: Always consider all constraints simultaneously when solving logic puzzles.
[G1]. Systematic approach: Use a step-by-step method to solve complex problems.
```

**新提取的经验**：
```
1. Constraint visualization: Create a visual representation of all constraints...
2. Strong constraint prioritization: Start from strongly determined constraints...
3. Consistency verification: Verify constraints after each assignment...
```

**调用 LLM 进行整合**：
```python
prompt = """
现有经验：
[G0]. Constraint handling: Always consider all constraints simultaneously...
[G1]. Systematic approach: Use a step-by-step method...

新经验：
1. Constraint visualization: Create a visual representation...
2. Strong constraint prioritization: Start from strongly determined constraints...
3. Consistency verification: Verify constraints after each assignment...

请决定每个新经验的操作：
- ADD: 如果完全是新的
- UPDATE: 如果是对现有经验的改进
- DELETE: 如果与现有经验冲突
- NONE: 如果已经包含在现有经验中
"""
```

### LLM 输出

```json
[
  {
    "operation": "UPDATE",
    "id": "G0",
    "content": "Constraint visualization: Create a visual representation (table or network) of all constraints to maintain a global perspective and consider all constraints simultaneously when solving logic puzzles."
  },
  {
    "operation": "ADD",
    "id": null,
    "content": "Strong constraint prioritization: Start reasoning from strongly determined constraints (those with unique values) and use them as anchors for further deduction."
  },
  {
    "operation": "ADD",
    "id": null,
    "content": "Consistency verification: After each assignment in constraint satisfaction problems, verify that it doesn't violate any existing constraints before proceeding to the next step."
  }
]
```

### 输出
操作列表，指示如何更新经验库

---

## 步骤 4: 批量更新 (Batch Update)

### 目的
处理一个 batch 中所有问题的经验更新操作，合并冲突，生成最终的经验库。

### 输入
- 当前经验库
- 来自多个问题的所有更新操作

### 处理过程

**假设这个 batch 有 3 个问题，每个都产生了更新操作**：

问题 A 的操作：
```json
[
  {"operation": "UPDATE", "id": "G0", "content": "..."},
  {"operation": "ADD", "id": null, "content": "Strong constraint prioritization: ..."}
]
```

问题 B 的操作：
```json
[
  {"operation": "ADD", "id": null, "content": "Strong constraint prioritization: ..."},
  {"operation": "ADD", "id": null, "content": "Pattern recognition: Look for patterns in constraints..."}
]
```

问题 C 的操作：
```json
[
  {"operation": "UPDATE", "id": "G0", "content": "..."},
  {"operation": "ADD", "id": null, "content": "Error checking: Always verify the final answer format..."}
]
```

**调用 LLM 进行批量整合**：
```python
prompt = """
现有经验：
[G0]. Constraint handling: ...
[G1]. Systematic approach: ...

所有更新操作：
- 问题 A: UPDATE G0, ADD "Strong constraint prioritization"
- 问题 B: ADD "Strong constraint prioritization", ADD "Pattern recognition"
- 问题 C: UPDATE G0, ADD "Error checking"

请合并这些操作：
1. 如果多个 UPDATE 针对同一个 ID，合并它们
2. 如果多个 ADD 内容相似，合并为一个
3. 处理冲突
"""
```

### LLM 输出

```json
[
  {
    "operation": "UPDATE",
    "id": "G0",
    "content": "Constraint visualization: Create a visual representation of all constraints to maintain a global perspective, consider all constraints simultaneously, and use them as anchors for deduction."
  },
  {
    "operation": "ADD",
    "id": null,
    "content": "Strong constraint prioritization: Start reasoning from strongly determined constraints (those with unique values) and use them as anchors for further deduction."
  },
  {
    "operation": "ADD",
    "id": null,
    "content": "Pattern recognition: Look for patterns and relationships in constraints to identify logical connections."
  },
  {
    "operation": "ADD",
    "id": null,
    "content": "Error checking: Always verify the final answer format matches the expected output structure."
  }
]
```

### 输出
最终的经验库更新操作

---

## 步骤 5: 应用更新

### 处理更新操作

```python
# 应用更新操作
experiences = {
    "G0": "Constraint handling: Always consider all constraints simultaneously...",
    "G1": "Systematic approach: Use a step-by-step method..."
}

# 执行操作
for operation in operations:
    if operation["operation"] == "UPDATE":
        experiences[operation["id"]] = operation["content"]
    elif operation["operation"] == "ADD":
        new_id = f"G{len(experiences)}"
        experiences[new_id] = operation["content"]
    elif operation["operation"] == "DELETE":
        del experiences[operation["id"]]
```

### 最终经验库

```
{
    "G0": "Constraint visualization: Create a visual representation of all constraints to maintain a global perspective, consider all constraints simultaneously, and use them as anchors for deduction.",
    "G1": "Systematic approach: Use a step-by-step method to solve complex problems.",
    "G2": "Strong constraint prioritization: Start reasoning from strongly determined constraints (those with unique values) and use them as anchors for further deduction.",
    "G3": "Pattern recognition: Look for patterns and relationships in constraints to identify logical connections.",
    "G4": "Error checking: Always verify the final answer format matches the expected output structure."
}
```

---

## 🎯 经验如何被使用

### 在训练过程中

每个 step 都会：
1. 处理新的 rollouts
2. 提取经验
3. 更新经验库
4. 经验库会累积，越来越丰富

### 在评估/测试时

经验会被插入到 agent 的 instructions 中：

```yaml
agent:
  instructions: |
    You are a helpful assistant for solving logic puzzles.
    
    When solving problems, you MUST first carefully read and understand 
    the helpful instructions and experiences:
    
    [G0]. Constraint visualization: Create a visual representation of all constraints...
    [G1]. Systematic approach: Use a step-by-step method...
    [G2]. Strong constraint prioritization: Start reasoning from strongly determined constraints...
    [G3]. Pattern recognition: Look for patterns and relationships...
    [G4]. Error checking: Always verify the final answer format...
    
    Now solve the following problem:
    {question}
```

这样，agent 在每次解答时都能参考这些积累的经验。

---

## 🔑 关键要点总结

1. **多 Rollout 策略**：每个问题生成多个解答（grpo_n=5），确保有成功和失败的对比

2. **筛选机制**：只处理平均分数在 0-1 之间的问题（既有成功也有失败）

3. **四步提取流程**：
   - 单 Rollout 摘要：分析每个解答的细节
   - 组优势分析：对比成功和失败，提取经验
   - 组更新：与现有经验整合
   - 批量更新：处理整个 batch，合并冲突

4. **经验累积**：每个 step 都会更新经验库，经验越来越丰富

5. **In-Context Learning**：经验通过 instructions 传递给模型，而不是参数更新

---

## 📊 数据流示例

```
Batch 输入 (Step 0):
- 问题 A: 5 个 rollouts (2 成功, 3 失败) → 平均 0.4 ✅
- 问题 B: 5 个 rollouts (0 成功, 5 失败) → 平均 0.0 ❌ (跳过)
- 问题 C: 5 个 rollouts (5 成功, 0 失败) → 平均 1.0 ❌ (跳过)

处理问题 A:
  步骤 1 → 5 个摘要
  步骤 2 → 3 条初步经验
  步骤 3 → 3 个更新操作
  步骤 4 → 合并到经验库

经验库更新:
  {} → {"G0": "...", "G1": "...", "G2": "..."}

下一个 Step (Step 1):
- 使用更新后的经验库
- 处理新的 batch
- 继续累积经验

最终 (Step N):
- 经验库包含 50+ 条经验
- 保存到 agent 配置文件
- 用于评估和测试
```

---

这就是 Training-Free GRPO 经验生成的完整机制！🎉


