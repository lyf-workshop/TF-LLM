# 逻辑冲突检测器使用指南

## 概述

`logic_conflict_detector.py` 是一个用于检测逻辑推理过程中冲突并生成经验总结的工具。它可以帮助大模型从错误中学习，改进推理能力。

## 功能特性

### 1. 冲突检测类型

脚本可以检测以下类型的逻辑冲突：

- **直接矛盾**: 同一实体被赋予不同的值
  - 例如: "Peter is in house 1" 和 "Peter is in house 2"
  
- **约束违反**: 违反了问题中的约束条件
  - 例如: 没有考虑所有线索，或违反了约束规则
  
- **循环推理**: 使用已排除的可能性
  - 例如: 先排除 "Alice has bird"，后续又使用 "Alice has bird"
  
- **不一致赋值**: 在推理过程中多次改变同一实体的属性
  - 例如: House 1 被多次赋值且值不一致
  
- **重复分配**: 同一属性被分配给多个实体
  - 例如: "Red" 被同时分配给 House 1 和 House 2

### 2. 经验生成

如果配置了LLM，脚本可以从检测到的冲突中自动生成经验总结，帮助模型改进推理策略。

## 安装和配置

### 前置要求

- Python 3.12+
- 已安装项目依赖 (`uv sync`)

### LLM配置（可选）

如果要使用经验生成功能，需要配置LLM。可以通过以下方式：

1. **使用配置文件**:
```bash
python scripts/logic_conflict_detector.py \
    --config agents/simple/base.yaml \
    --sample sample.json
```

2. **环境变量**: 确保 `.env` 文件中配置了LLM API密钥

## 使用方法

### 1. 分析单个样本

```bash
# 创建样本JSON文件 (sample.json)
{
  "dataset": "ZebraLogic-Test",
  "raw_question": "Logic puzzle with clues...",
  "response": "Reasoning steps...",
  "correct_answer": "{\"header\": [...], \"rows\": [...]}"
}

# 运行检测
python scripts/logic_conflict_detector.py \
    --sample sample.json \
    --config agents/simple/base.yaml \
    --output results.json
```

### 2. 批量分析

```bash
# 创建批量样本JSON文件 (samples.json)
[
  {
    "dataset": "ZebraLogic-Test",
    "raw_question": "...",
    "response": "...",
    "correct_answer": "..."
  },
  ...
]

# 运行批量检测
python scripts/logic_conflict_detector.py \
    --batch samples.json \
    --limit 100 \
    --config agents/simple/base.yaml \
    --output batch_results.json
```

### 3. 仅检测冲突（不生成经验）

```bash
python scripts/logic_conflict_detector.py \
    --sample sample.json \
    --no-experience \
    --output results.json
```

## 输出格式

脚本会输出JSON格式的结果：

```json
[
  {
    "sample_id": null,
    "has_conflicts": true,
    "total_conflicts": 2,
    "conflicts_by_type": {
      "contradictions": [
        {
          "type": "contradiction",
          "step1": 1,
          "step2": 3,
          "assertion1": "Peter -> house 1",
          "assertion2": "Peter -> house 2",
          "description": "步骤 1 和步骤 3 存在矛盾"
        }
      ],
      "constraint_violations": [],
      "circular_reasoning": [],
      "inconsistent_assignments": [],
      "duplicate_assignments": []
    },
    "summary": "检测到以下冲突类型: contradictions: 1 个",
    "experience": "从冲突中生成的经验总结..."
  }
]
```

## 集成到现有系统

### 与 Training-Free GRPO 集成

可以将冲突检测集成到训练流程中：

```python
from scripts.logic_conflict_detector import LogicConflictDetector
from utu.db import EvaluationSample

# 在训练循环中
detector = LogicConflictDetector(llm=your_llm)

for rollout in rollouts:
    conflict_analysis = detector.detect_conflicts(rollout)
    
    if conflict_analysis["has_conflicts"]:
        # 生成经验
        experience = await detector.generate_experience(
            conflict_analysis,
            rollout.raw_question,
            rollout.response
        )
        # 将经验添加到经验库
        # ...
```

### 与验证器集成

可以扩展现有的验证器，添加冲突检测：

```python
from utu.practice.verify.logic_with_error_analysis_v2 import verify_func
from scripts.logic_conflict_detector import LogicConflictDetector

def enhanced_verify_func(sample, **kwargs):
    # 基础验证
    result = verify_func(sample, **kwargs)
    
    # 如果答案错误，检测冲突
    if result["reward"] < 1.0:
        detector = LogicConflictDetector()
        conflict_analysis = detector.detect_conflicts(sample)
        
        if conflict_analysis["has_conflicts"]:
            result["conflict_analysis"] = conflict_analysis
    
    return result
```

## 示例

查看 `scripts/logic_conflict_detector_example.py` 了解详细的使用示例。

运行示例：

```bash
python scripts/logic_conflict_detector_example.py
```

## 高级用法

### 自定义冲突检测

可以继承 `LogicConflictDetector` 类并添加自定义检测逻辑：

```python
class CustomConflictDetector(LogicConflictDetector):
    def _detect_custom_conflicts(self, response: str) -> List[Dict]:
        # 自定义检测逻辑
        conflicts = []
        # ...
        return conflicts
    
    def detect_conflicts(self, sample: EvaluationSample) -> Dict[str, Any]:
        result = super().detect_conflicts(sample)
        # 添加自定义检测
        result["conflicts_by_type"]["custom"] = self._detect_custom_conflicts(sample.response)
        return result
```

### 批量处理优化

对于大量样本，可以使用异步处理：

```python
import asyncio

async def batch_analyze(samples, detector):
    tasks = [analyze_sample(s, detector) for s in samples]
    results = await asyncio.gather(*tasks)
    return results
```

## 故障排除

### 问题: LLM配置失败

**解决方案**: 
- 检查配置文件路径是否正确
- 确认 `.env` 文件中配置了API密钥
- 使用 `--no-experience` 跳过经验生成

### 问题: 检测不到冲突

**可能原因**:
- 推理文本格式不符合预期
- 断言提取模式不匹配

**解决方案**:
- 检查推理文本是否包含步骤标记（如 "1.", "步骤1"）
- 查看 `_extract_assertions` 方法，确认模式匹配

### 问题: 误报过多

**解决方案**:
- 调整 `_are_contradicting` 方法的判断逻辑
- 添加更严格的上下文检查

## 贡献

欢迎提交Issue和Pull Request来改进冲突检测算法和经验生成质量。

## 相关文档

- [逻辑错误检测快速开始](逻辑错误检测快速开始.md)
- [经验生成机制详解](经验生成机制详解.md)
- [Training-Free GRPO 完整流程详解](Training-Free_GRPO完整流程详解.md)
























































