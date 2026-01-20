# 增强验证器错误信息使用流程详解

## 概述

本文档详细说明增强验证器 (`logic_with_error_analysis.py`) 返回的错误信息是如何在 Training-Free GRPO 流程中被使用的。

## 完整流程

### 阶段 1: 验证阶段 (Judging Phase)

**位置**: `utu/eval/processer/training_free_grpo_processor.py`

```python
async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
    # 调用 verify_func
    res = self.verify_func(sample=data, llm=self.judge_client)
    
    reward = res.get("reward", 0.0)
    reasoning = res.get("reasoning", None)  # ← 这里获取错误信息
    
    # 保存到数据库
    data.update(
        reward=reward,
        reasoning=reasoning,  # ← 错误信息被保存到 EvaluationSample.reasoning
    )
    return data
```

**关键点**:
- `verify_func` 返回的 `reasoning` 字段被保存到 `EvaluationSample.reasoning`
- 如果使用增强验证器，`reasoning` 包含详细的错误分析
- 如果使用基本验证器，`reasoning` 通常为 `None`

---

### 阶段 2: 经验生成阶段 (Experience Generation Phase)

**位置**: `utu/practice/experience_updater.py`

#### 步骤 2.1: 单 Rollout 摘要 (Single Rollout Summary)

**函数**: `_single_rollout_summary()`

**关键代码**:

```python
async def summarize_with_semaphore(item: EvaluationSample):
    # 构建 prompt
    up = FileUtils.get_jinja_template_str(
        self.prompts["SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP"]
    ).render(
        question=item.raw_question,
        trajectory=json.loads(item.trajectories)[0]["trajectory"],
        answer=item.correct_answer if given_ground_truth else "[REDACTED]",
        critique=item.reasoning or "[No critique provided]",  # ← 这里使用 reasoning！
    )
    
    # 调用 LLM 生成摘要
    response = await self.llm.query_one(
        messages=[
            {"role": "system", "content": sp},
            {"role": "user", "content": up},
        ],
    )
```

**Prompt 模板** (`utu/prompts/practice/experience.yaml`):

```yaml
SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP: |
  <Working Agent Input>
  {{ question }}
  </Working Agent Input>

  <Ground Truth>
  {{ answer }}
  </Ground Truth>

  <Critique>                    # ← 错误信息在这里！
  {{ critique }}                # ← 这就是 item.reasoning
  </Critique>

  <Trajectory>
  {{ trajectory }}
  </Trajectory>
```

**System Prompt 说明**:

```
<Your Input>
- Critique: [If available, provide the critique of the agent's response 
             to help identify shortcomings]  # ← 明确说明使用 critique
</Your Input>

<Task Instructions>
2. **Extract Step-by-Step Details**: For each step in the trajectory, 
   describing how it can be improved towards the learning objective. 
   When the critique is available, use it to inform your analysis 
   and provide details.  # ← 要求使用 critique 来指导分析
</Task Instructions>
```

**作用**:
- LLM 使用 `critique`（即 `reasoning` 字段）来分析轨迹
- 帮助识别错误原因和改进方向
- 生成详细的轨迹摘要，包含：
  - 每一步的执行情况
  - 错失的机会
  - 关键发现
  - 整体策略

---

#### 步骤 2.2: 组优势分析 (Group Advantage)

**函数**: `_group_advantage()`

在这个阶段，多个 rollouts 的摘要被一起分析，但**不再直接使用 critique**。

**输入**:
- 多个 rollouts 的轨迹摘要（来自步骤 2.1）
- 这些摘要已经包含了基于 critique 的分析

**输出**:
- 提取的经验（Experiences）
- 性能评估
- 对比分析

---

#### 步骤 2.3: 组更新和批量更新

**函数**: `_group_update()` 和 `_batch_update()`

这些阶段进一步优化经验，但**不再直接使用 critique**。

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│ 阶段 1: 验证阶段 (Judging Phase)                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  verify_func(sample)                                         │
│    ↓                                                         │
│  {                                                           │
│    "reward": 0.0,                                           │
│    "reasoning": "Found 3 logical errors: ..."  ← 错误分析    │
│  }                                                           │
│    ↓                                                         │
│  EvaluationSample.reasoning = reasoning  ← 保存到数据库     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 阶段 2: 经验生成阶段 (Experience Generation Phase)           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  步骤 2.1: 单 Rollout 摘要                                   │
│  ────────────────────────────────────────                   │
│                                                              │
│  SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP                         │
│    critique = sample.reasoning  ← 使用错误信息！            │
│    ↓                                                         │
│  LLM 分析轨迹，使用 critique 指导分析                       │
│    ↓                                                         │
│  生成轨迹摘要（包含错误分析和改进建议）                      │
│                                                              │
│  步骤 2.2: 组优势分析                                        │
│  ────────────────────────────────────────                   │
│                                                              │
│  使用多个 rollouts 的摘要（已包含 critique 分析）           │
│    ↓                                                         │
│  提取经验和模式                                              │
│                                                              │
│  步骤 2.3: 经验更新                                          │
│  ────────────────────────────────────────                   │
│                                                              │
│  优化和整合经验                                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 关键发现

### 1. 错误信息的使用位置

**只在步骤 2.1（单 Rollout 摘要）中使用**

- ✅ **使用**: `_single_rollout_summary()` 函数中，作为 `critique` 传递给 LLM
- ❌ **不使用**: 后续的组优势分析和经验更新阶段

### 2. 错误信息的作用

1. **指导 LLM 分析**: 帮助 LLM 理解错误原因
2. **识别改进点**: 指出轨迹中的具体问题
3. **生成详细摘要**: 基于错误信息生成更准确的轨迹摘要

### 3. 错误信息的格式要求

从 prompt 模板可以看出，错误信息应该：
- 清晰描述错误类型
- 指出具体问题
- 帮助 LLM 理解失败原因

**示例（好的错误信息）**:
```
Found 3 logical errors in reasoning:

• Constraint Violations (2): 
  1. Attribute 'Color:Red' assigned to multiple entities: House 1, House 2
  2. Entity 'House 2' is missing attributes: PhoneModel

• Contradictions (1): 
  1. Contradiction found between step 1 and step 3
```

**示例（不好的错误信息）**:
- 太长或太复杂
- 格式不清晰
- 包含太多技术细节

## 为什么可能影响训练效果

### 可能的问题

1. **错误信息太长**: 
   - 占用太多 token
   - 可能干扰 LLM 对轨迹的分析

2. **错误信息格式不合适**:
   - LLM 无法有效利用
   - 可能产生误导

3. **错误信息不准确**:
   - LogicErrorAnalyzer 误判
   - 导致 LLM 基于错误信息生成摘要

4. **错误信息与学习目标不匹配**:
   - 错误信息关注技术细节
   - 但学习目标关注推理策略

### 建议

1. **检查错误信息长度**: 使用 `scripts/view_actual_error_analysis.py` 查看实际长度
2. **简化错误信息**: 修改 `_format_error_reasoning()` 函数
3. **禁用错误分析**: 如果效果不好，设置 `enable_error_analysis=False`
4. **改进错误分析**: 提高 LogicErrorAnalyzer 的准确性

## 相关文件

- **验证函数**: `utu/practice/verify/logic_with_error_analysis.py`
- **验证处理器**: `utu/eval/processer/training_free_grpo_processor.py`
- **经验更新器**: `utu/practice/experience_updater.py`
- **Prompt 模板**: `utu/prompts/practice/experience.yaml`
- **错误分析器**: `scripts/logic_error_analyzer.py`

## 调试工具

1. **查看错误信息**: `scripts/view_actual_error_analysis.py`
2. **诊断错误格式**: `scripts/inspect_error_analysis_output.py`
3. **测试验证函数**: `scripts/test_logic_verify.py`







































































