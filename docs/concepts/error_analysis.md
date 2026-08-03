# 误差分析

误差分析的目标不是为失败补一个故事，而是判断性能变化来自 Agent、经验、verifier 还是基础设施。

## 建议分类

1. `infra_error`：API、数据库、Docker、Harbor、游戏服务或缺失产物。
2. `format_error`：答案本身可能正确，但不满足 parser/verifier 格式。
3. `reasoning_error`：约束、计算、搜索或算法过程错误。
4. `tool_error`：工具选择、参数、路径或调用顺序错误。
5. `timeout`：区分模型请求异常与 Agent 在有效环境中真正耗尽任务时间。
6. `experience_regression`：baseline 通过而经验组失败，并能从轨迹观察到经验干扰。

## 分析顺序

先检查试次是否有效，再比较同一任务的 baseline 与经验组轨迹。只对有效的 gained/lost 任务归因，并记录使用了哪些经验、是否被检索、是否改变关键动作。

## 工具位置

- `scripts/utils/view_results.py`：通用任务级对比。
- `scripts/utils/view_benchmark_results.py`：SkillsBench 与 LiveCodeBench。
- `scripts/korgym/view_korgym_results.py`：KORGym。
- `scripts/error_analysis/`：逻辑 verifier、冲突与错误提取的研究脚本。
- `scripts/experiments/`：逐题统计和专项分析脚本。

后两类目录包含探索性脚本，不构成统一正式协议。使用前检查脚本中的默认实验 ID、数据路径和模型假设，并把实际命令随实验一起保存。
