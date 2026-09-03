# 分层经验与簇内聚合

系统将经验分为三个层级：L0 是任务/rollout 产生的具体经验，L1 是多个相近 L0
支持的可执行模式，L2 是多个相近 L1 支持的条件化高层策略。上层经验只在同一簇内生成，
不再按经验生成顺序任意切块。

## 数据与状态

经验文件使用 `schema_version: 2`，每条记录至少包含稳定 `id`、`level`、`content`、
来源任务与 rollout、可用的分类元数据、真实 `parent_ids`、`cluster_id`、
`aggregation_status`、创建时间和版本。L1 的 `source_l0_ids` 是直接 L0 父级；L2 的
`source_l1_ids` 是直接 L1 父级，同时保存可传递追踪的 `source_l0_ids`。

旧的列表格式和 `id -> content` 字典格式会在读取时迁移。旧 L1 若已经存在 L2 但没有
状态字段，会被保守地视为已处理，以免程序重启后重复生成 L2。

`aggregation_status` 的含义：

- `pending`：尚未成功形成上层经验，可以在后续 epoch 重试；
- `aggregated`：已成功形成并保存上层经验；
- `terminal`：L2 终端记录。

L0 使用标准化内容和已知分类元数据的 SHA-256 摘要作为稳定 ID；相同内容但失败模式或阶段
不同的记录不会在入池时被错误折叠。L1/L2 的 ID 同时包含结构化内容和排序后的真实父级 ID，
因此经验重排不会改变 ID，不同来源也不会被错误折叠。

## 聚类流程

默认流程为：

```text
pending L0/L1
  -> 检查 task_stage、failure_mode 等硬约束
  -> 计算可替换的文本 embedding 与 cosine similarity
  -> 按相似度阈值执行未知簇数量的凝聚聚类
  -> 仅处理达到最小规模的簇
  -> 校验结构化 L1/L2 输出与置信度
  -> 原子保存子记录和父级状态
```

仓库没有既有 embedding 依赖，因此默认 `hashing` provider 是本地、无密钥、确定性的
哈希文本向量。它适合复现和离线运行，但语义能力有限。`ExperienceClusterer` 接受实现
`embed(texts)` 的 provider，可在不改聚类算法的情况下换成本地向量模型或托管 embedding。

硬约束字段在双方都有值且不同的情况下禁止合并；字段缺失时回退到语义聚类，并在审计记录
中写入元数据完整度。软约束一致会小幅提高得分，不一致会更明显地降低得分。

## 关键配置

```yaml
practice:
  hierarchical_learning:
    enabled: true
    clustering_enabled: true
    clustering_method: agglomerative
    embedding_provider: hashing
    l0_similarity_threshold: 0.80
    l1_similarity_threshold: 0.75
    min_l0_per_l1: 5
    min_l1_per_l2: 3
    max_cluster_size: 20
    use_metadata_constraints: true
    hard_constraint_fields: [task_stage, failure_mode]
    soft_constraint_fields: [domain, task_family, tool_type, strategy_type]
    random_seed: 42
    aggregation_temperature: 0.2
    experience_save_path: workspace/hierarchical_experiences/example.json
    clustering_audit_path: workspace/hierarchical_experiences/example.clusters.jsonl
```

默认的 `5/3` 沿用现有实验规模：L1 至少需要五个具体证据，L2 至少需要三个独立模式；
`0.80/0.75` 让具体 L0 更严格，而允许表述更抽象的 L1 有稍低阈值。SkillsBench 当前每轮
最多约 20 个任务，因此 `max_cluster_size: 20` 可避免一次聚合超过整轮规模。这些值是初始
假设，必须结合审计分布和下游成功率调整。

旧配置名 `l1_aggregation_threshold`、`l2_aggregation_threshold` 仍可读取，分别映射到新的
最小簇规模。设置 `clustering_enabled: false` 后使用原有的生成顺序分组，供消融实验使用；
不足最小规模的尾部仍保持 pending，不会生成无效单条经验。

## 审计与 A/B 消融

每次聚类在 JSONL 审计文件中记录输入数量、簇及成员 ID、质心和代表经验、簇内平均相似度、
元数据一致性/完整度、硬约束拆分、pending、成功子级、真实父级与失败原因。

使用同一个已有 L0 文件运行 A/B：

```bash
python scripts/experiments/run_hierarchical_ablation.py \
  --config-name skillsbench/skillsbench_practice \
  --source-experiences workspace/hierarchical_experiences/skillsbench_practice.json \
  --output-dir workspace/ablations/skillsbench_cluster_v1
```

入口会复制同一份 L0 为两个全新快照，A 使用顺序分组，B 使用簇内聚合；两者共享模型、提示词、
随机种子和零聚合温度。它不会覆盖已有输出，并会生成两个 Agent YAML 和 `report.json`。

若运行前已经有逐任务下游评估 JSON/JSONL，可在上述命令追加：

```bash
  --baseline-eval path/to/sequential_eval.json \
  --clustered-eval path/to/clustered_eval.json
```

报告包含 L0/L1/L2 数量、簇数与大小、相似度、元数据一致性、pending、重复/冲突比例、提示词
Token 数、成功率以及提升/退化任务数。没有下游结果时结论为
`downstream_evaluation_not_provided`；结果也可以是 `negative` 或 `no_improvement`。

通常需要先使用生成的两个 Agent YAML 完成评估，再单独生成带下游结论的报告：

```bash
python scripts/experiments/report_hierarchical_ablation.py \
  --baseline-hierarchy workspace/ablations/skillsbench_cluster_v1/sequential.json \
  --clustered-hierarchy workspace/ablations/skillsbench_cluster_v1/clustered.json \
  --baseline-audit workspace/ablations/skillsbench_cluster_v1/sequential.clusters.jsonl \
  --clustered-audit workspace/ablations/skillsbench_cluster_v1/clustered.clusters.jsonl \
  --baseline-eval path/to/sequential_eval.json \
  --clustered-eval path/to/clustered_eval.json \
  --output workspace/ablations/skillsbench_cluster_v1/report_with_eval.json
```

如果评估由 `scripts/run_eval.py` 写入默认数据库，则不需要导出文件，把两个评估实验 ID
替换为以下参数即可：

```bash
  --baseline-exp-id skillsbench_hierarchy_a_eval \
  --clustered-exp-id skillsbench_hierarchy_b_eval
```

同一任务有多个 pass-k trial 时，报告以该任务的最高 reward 作为任务结果。
