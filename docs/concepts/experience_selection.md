# 经验选择与检索

当经验池增长后，将全部经验注入每个任务会增加 token、干扰和错误迁移。`utu/eval/experience_filter.py` 提供三种选择策略。

## 策略

| 策略 | 行为 | 额外成本 |
| --- | --- | --- |
| `static` | 按 L0/L1/L2 数量上限截取 | 无 |
| `retrieval` | 使用 BM25 按当前 query 召回 | 低 |
| `llm_rerank` | 先召回候选，再由 LLM 按相关性等标准排序 | 一次额外模型调用 |

示例 eval 配置：

```yaml
experience_filter:
  enabled: true
  experience_source: workspace/hierarchical_experiences/skillsbench_practice.json
  strategy: retrieval
  retrieval_top_k: 8
  retrieval_min_score: 0.0
```

LLM rerank 支持 `static`、`bm25` 或 `all` 召回，并可配置 `max_candidates`、`final_top_k`、temperature 与 timeout。

## 实验设计

选择器本身会改变提示词，应作为独立变量。推荐比较：全部经验、固定数量、BM25 与 BM25 加 rerank；各组控制总经验条数和近似 token 长度。

## 质量跟踪

`ExperienceQualityTracker` 可以记录经验注入次数、成功率、最近使用时间和质量分数。但质量记录与自动删除尚未形成经过验证的端到端闭环。现阶段应先离线审计低分经验，再决定是否删除，避免因相关性误判产生自我强化。
