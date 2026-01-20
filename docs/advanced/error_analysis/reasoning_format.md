# 逻辑推理格式要求说明

## 概述

为了支持自动化的错误检测和经验提取，逻辑推理agent必须遵循标准化的推理过程格式。这些格式要求使得错误检测器能够：

1. **准确提取推理步骤**：识别每个推理步骤
2. **检测逻辑冲突**：发现矛盾、约束违反等问题
3. **提取断言**：识别实体-属性关系
4. **生成经验总结**：从错误中学习改进策略

## 格式要求详解

### 1. 步骤编号 (Step Numbering)

**要求**：
- 使用清晰的步骤编号：`1.`, `2.`, `3.`（推荐）或 `步骤1`, `步骤2`, `步骤3`
- 每个步骤独立一行

**示例**：
```
1. From clue 1, we know that Peter is in house 1.
2. From clue 2, Alice is in house 2.
3. From clue 3, the person in house 1 has a bird.
```

**为什么重要**：
- 错误检测器通过步骤编号提取推理步骤
- 便于定位具体错误位置
- 支持步骤级别的错误分析

### 2. 断言格式 (Assertion Format)

**要求**：
- 使用明确的断言格式：
  - `"X is in house Y"` 或 `"X is located in house Y"`
  - `"House X has Y"` 或 `"House X contains Y"`
  - `"X has attribute Y"` 或 `"X owns Y"`
- 保持实体和属性名称的一致性

**示例**：
```
1. Peter is in house 1.
2. House 1 has color red.
3. Peter has pet bird.
```

**为什么重要**：
- 错误检测器通过正则表达式提取断言
- 格式不一致会导致断言提取失败
- 支持矛盾检测（如 "Peter in house 1" vs "Peter in house 2"）

### 3. 线索引用 (Clue Reference)

**要求**：
- **必须**明确引用线索：
  - `"From clue 1"`, `"According to clue 2"`, `"Based on clue 3"`
  - `"根据线索1"`, `"从线索2可知"`, `"根据线索3"`
- 不要在没有引用线索的情况下进行推理

**示例**：
```
1. From clue 1, Peter is in house 1.
2. From clue 3, the person in house 1 has a bird.
3. Therefore, Peter has a bird (combining clues 1 and 3).
```

**为什么重要**：
- 错误检测器检查是否所有线索都被使用
- 支持约束违反检测
- 帮助识别不完整的推理

### 4. 逻辑连接词 (Logical Connections)

**要求**：
- 使用明确的逻辑连接词：
  - `"Therefore"`, `"Thus"`, `"Hence"`, `"So"`, `"Because"`, `"Since"`
  - `"因此"`, `"所以"`, `"从而"`, `"因为"`, `"由于"`
- 展示步骤之间的逻辑流程

**示例**：
```
1. From clue 1, Peter is in house 1.
2. From clue 2, Alice is in house 2.
3. Therefore, Peter and Alice are in different houses.
```

**为什么重要**：
- 错误检测器评估推理质量
- 缺少逻辑连接词会被标记为推理质量问题
- 帮助理解推理流程

### 5. 排除和约束 (Elimination and Constraints)

**要求**：
- 明确说明排除的可能性：
  - `"We can eliminate X because..."`
  - `"X cannot be Y because..."`
  - `"排除X，因为..."`
- 明确跟踪约束

**示例**：
```
1. From clue 1, Peter is in house 1.
2. From clue 4, the person in house 1 has color red.
3. Therefore, Peter has color red.
4. We can eliminate red for other houses (uniqueness constraint).
```

**为什么重要**：
- 支持循环推理检测（使用已排除的可能性）
- 帮助识别约束处理问题
- 支持不一致赋值检测

### 6. 验证步骤 (Verification Step)

**要求**：
- **必须**在最终答案前包含验证步骤：
  - `"Let me verify the solution against all constraints:"`
  - `"验证解决方案是否符合所有约束："`
- 明确检查每个线索/约束

**示例**：
```
Verification:
- Clue 1: Peter is in house 1. ✓
- Clue 2: Alice is in house 2. ✓
- Clue 3: House 1 has color red. ✓
- All constraints satisfied.
```

**为什么重要**：
- 错误检测器检查是否有验证步骤
- 缺少验证会被标记为推理质量问题
- 帮助确保解决方案的正确性

### 7. 答案格式 (Answer Format)

**要求**：
- 最终答案必须使用以下格式：
```xml
<answer>
\boxed{'The final answer goes here.'}
</answer>
```

**为什么重要**：
- 验证器通过 `<answer>` 标签提取答案
- 支持多种答案格式的解析
- 区分推理过程和最终答案

## 完整示例

```
1. From clue 1, Peter is in house 1.
2. From clue 2, Alice is in house 2.
3. From clue 3, the person in house 1 has a bird.
4. Therefore, Peter has a bird (combining clues 1 and 3).
5. From clue 4, House 1 has color red.
6. Therefore, Peter is in house 1 with color red and has a bird.
7. We can eliminate red for other houses (uniqueness constraint).

Verification:
- Clue 1: Peter is in house 1. ✓
- Clue 2: Alice is in house 2. ✓
- Clue 3: House 1 has bird. ✓
- Clue 4: House 1 has color red. ✓
- All constraints satisfied.

<answer>
\boxed{'The final answer goes here.'}
</answer>
```

## 错误检测器如何利用这些格式

### 步骤提取
```python
# 错误检测器会查找步骤编号
step_pattern = r'(?:^|\n)\s*(?:\d+[\.\)]|步骤\s*\d+|Step\s+\d+)'
```

### 断言提取
```python
# 错误检测器会查找断言格式
patterns = [
    r"([A-Z][a-z]+)\s+in\s+(?:house|position)\s+(\d+)",
    r"House\s+(\d+)\s+has\s+([a-z]+)",
    # ...
]
```

### 线索检查
```python
# 错误检测器会检查线索引用
clue_pattern = r"(?:clue|线索|constraint|约束)\s+(\d+)"
```

### 验证检查
```python
# 错误检测器会检查验证步骤
verification_keywords = ['verify', 'check', 'validate', '验证', '检查']
```

## 常见问题

**Q: 如果我不遵循这些格式会怎样？**  
A: 错误检测器可能无法准确提取推理步骤和断言，导致错误检测不准确，影响经验生成质量。

**Q: 可以使用其他格式吗？**  
A: 建议严格遵循这些格式。如果必须使用其他格式，需要相应更新错误检测器的正则表达式。

**Q: 格式要求是否适用于所有逻辑推理任务？**  
A: 这些格式主要针对ZebraLogic类型的逻辑谜题。其他任务可能需要调整格式要求。

## 相关文件

- **Agent配置**: `configs/agents/practice/logic_agent_zebralogic.yaml`
- **错误检测器**: `scripts/logic_conflict_detector.py`
- **验证器**: `utu/practice/verify/logic_with_error_analysis_v2.py`
























































