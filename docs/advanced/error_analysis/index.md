# 逻辑错误分析工具

高级逻辑错误分析工具集，用于检测、分析和改进智能体在逻辑推理任务中的表现。

## 📚 文档导航

### 🚀 快速开始

- **[快速入门指南](quickstart.md)** - 5分钟快速测试和使用
  - V1 vs V2 对比测试
  - 版本选择指南
  - 基本配置方法

### 📖 核心文档

#### 使用指南

- **[使用流程](usage_flow.md)** - 完整的使用流程和最佳实践
  - 工作流程说明
  - 配置方法
  - 常见问题解决

- **[对推理的影响](impact_on_reasoning.md)** - 错误分析如何影响推理质量
  - 影响机制分析
  - 效果评估
  - 优化建议

#### 工具详解

- **[分析器 V2 指南](analyzer_v2.md)** - 逻辑错误分析器 V2 详细说明
  - 功能特性
  - 使用方法
  - 与 V1 的区别

- **[冲突检测器](conflict_detector.md)** - 逻辑冲突检测工具
  - 检测算法
  - 配置参数
  - 使用示例

- **[提取器详解](extractor_guide.md)** - 逻辑错误提取器完整讲解
  - 架构设计
  - 四种错误类型
  - API 使用方法

#### 特殊功能

- **[不完整推理检测](incomplete_detection.md)** - 检测推理过程的完整性
  - 检测指标
  - 评分机制
  - 改进建议

- **[经验对比分析](experience_comparison.md)** - 对比不同经验的质量
  - 对比维度
  - 分析方法
  - 应用场景

### 📐 规范要求

- **[推理格式要求](reasoning_format.md)** - 标准化推理格式规范
  - 格式定义
  - 示例模板
  - 验证方法

## 🎯 核心功能

### 1. 逻辑错误检测

检测四种主要的逻辑错误类型：

- **矛盾断言** - 检测相互冲突的推理结论
- **无效消除** - 检测基于错误前提的排除
- **循环推理** - 检测推理过程中的循环依赖
- **不完整推理** - 检测缺失的必要推理步骤

### 2. 自动化分析

- 解析结构化推理过程
- 提取断言和推理链
- 生成详细的错误报告
- 提供改进建议

### 3. 质量评估

- 推理完整性评分
- 逻辑一致性检查
- 经验质量对比
- 影响分析报告

## 🔧 使用场景

### 场景 1: 逻辑推理任务评估

在 ZebraLogic、数独等逻辑谜题中：
```yaml
# configs/eval/logic/zebralogic_eval.yaml
verify_filename: "logic_with_error_analysis_v2.py"
verify_func_name: "verify_func"
```

### 场景 2: 推理过程调试

分析智能体为什么失败：
```python
from utu.practice.verify.logic_error_extractor import EnhancedLogicErrorAnalyzer

analyzer = EnhancedLogicErrorAnalyzer()
result = analyzer.analyze_reasoning(response_text, ground_truth)
print(result['errors'])  # 查看所有检测到的错误
```

### 场景 3: 经验质量提升

对比不同经验的效果：
- 分析哪些经验更有效
- 识别低质量经验
- 优化经验提取 prompt

## 📊 工具对比

| 特性 | V1 基础版本 | V2 增强版本 |
|------|------------|------------|
| 逻辑冲突检测 | ✅ | ✅ 增强 |
| 不完整推理检测 | ❌ | ✅ |
| 经验对比分析 | ❌ | ✅ |
| 详细错误报告 | 基础 | 详细 |
| 性能开销 | 低 | 中 |

## 🚀 快速示例

```python
# 1. 导入分析器
from utu.practice.verify.logic_with_error_analysis_v2 import verify_func

# 2. 准备数据
sample = EvaluationSample(
    question="逻辑推理问题...",
    correct_answer="正确答案",
    response="智能体的推理过程..."
)

# 3. 运行分析
result = await verify_func(sample)

# 4. 查看结果
print(f"是否正确: {result.correct}")
print(f"错误分析: {result.meta.get('error_analysis')}")
print(f"完整性评分: {result.meta.get('completeness_score')}")
```

## 🔗 相关资源

- [Agent Practice 文档](../../practice.md) - Training-Free GRPO 框架
- [评估框架](../../eval.md) - 评估系统文档
- [ZebraLogic 数据集](../../korgym/zebralogic_dataset.md) - 数据集准备

## 📞 支持

如有问题，请参考：
1. [FAQ](../../faq.md) - 常见问题解答
2. [GitHub Issues](https://github.com/TencentCloudADP/youtu-agent/issues) - 提交问题

