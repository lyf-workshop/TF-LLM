# TF-LLM DAPO-100 经验学习项目分析上下文

> 用途：将本文连同仓库交给其他大模型或研究者，对当前 Training-Free GRPO、分层经验学习和 AIME24 评估方案进行独立审查。
>
> 分析日期：2026-09-17
>
> 当前分支：`slim-research-baseline`
>
> 当前提交：`d540e08ac6d88007540a0055a1f47861f70ae7f9`
>
> 工作区状态：存在大量尚未提交的代码修改和实验产物。本文描述的是当前工作区，而不只是上述 Git 提交。

## 1. 阅读约定

本文使用三种结论标签，避免把观察、推断和建议混在一起：

- **已验证事实**：直接来自当前代码、解析后的 Hydra 配置、层级快照或聚类审计文件。
- **分析判断**：基于已验证事实作出的工程或研究判断，仍应通过实验验证。
- **建议**：下一步可执行方案，不代表已经实现或已经验证有效。

## 2. 执行摘要

### 2.1 项目目标

TF-LLM 当前研究的是一种不更新模型权重的经验学习流程。它借用 GRPO 的组内采样和奖励比较结构，对同一问题生成多条 rollout，经 verifier 判断后提取自然语言经验，再将经验注入后续任务提示词。

当前 DAPO/AIME 路线的目标是：

1. 从固定的 100 道 DAPO 数学题中学习经验。
2. 将经验维护为 L0、L1、L2 三层结构。
3. 将经验注入 Agent。
4. 在与训练集隔离的 AIME24 上，与无经验 baseline 做公平比较。

这里的“训练”是经验库学习，不是梯度训练，也不会修改基础模型权重。

### 2.2 当前最重要结论

1. **已验证事实**：L0 学习、候选评审、原子快照、缓存恢复和独立聚合入口已经能够工作。当前快照有 107 条活跃 L0、19 条归档 L0、328 条 L0 候选。
2. **已验证事实**：当前没有任何 L1 或 L2。107 条活跃 L0 全部仍为 `pending`。
3. **已验证事实**：最新 L1 聚合并没有使用最小支持数 3。WSL 配置继承后的有效值仍是 `min_l0_per_l1: 5`。
4. **已验证事实**：最新聚类在阈值 0.60 下得到 89 个簇，大小分布为 74 个单元素簇、12 个双元素簇、3 个三元素簇，没有簇达到 5，因此没有调用 L1 聚合模型，也没有生成 L1 候选。
5. **分析判断**：直接把最小支持数降到 3，技术上会让现有 3 个三元素簇进入聚合，但这 3 个簇人工观察都存在明显主题不一致，当前不适合直接生成可信 L1。
6. **已验证事实**：当前生成的 Agent YAML 只注入最近 20 条 L0，因为 L1/L2 均为空。它不是 107 条 L0 的完整注入。
7. **分析判断**：当前 L0 的单条内容通常包含方法、边界和校验步骤，局部质量尚可；但整体存在中英文近义重复、任务答案残留、工具故障模板重复和抽象粒度不一致，尚不足以证明能提高 AIME24。
8. **已验证事实**：尚未提供同模型、同温度、同 pass-k、同任务顺序的 baseline 与 learned-agent 配对评估结果，因此目前不能声称经验提高了 AIME24 表现。

## 3. 仓库与实验对象

### 3.1 主要目录

| 路径 | 作用 |
| --- | --- |
| `scripts/run_training_free_GRPO.py` | 完整经验学习入口 |
| `scripts/experiments/aggregate_hierarchical_experiences.py` | 从已有快照继续做 L1/L2 聚合，不执行 rollout |
| `scripts/run_eval.py` | 基线或经验 Agent 的评估入口 |
| `scripts/regen_practice_agent_yaml.py` | 当前是 SkillsBench 硬编码脚本，不是通用数学 Agent 再生成器 |
| `configs/practice/` | 经验学习配置和模板 |
| `configs/eval/` | 评估配置 |
| `configs/agents/practice/` | 基础 Agent 和生成的经验 Agent |
| `configs/data/math/` | DAPO-100 冻结数据清单 |
| `utu/practice/` | 经验学习核心实现 |
| `utu/eval/` | rollout、judge 和评估处理流程 |
| `workspace/hierarchical_experiences/` | L0/L1/L2 快照、备份和聚类审计 |
| `workspace/cache/` | embedding 和生成缓存 |

### 3.2 当前研究实例

| 项目 | 当前值 |
| --- | --- |
| 训练数据 | `DAPO-Math-17k-Random-100-Seed42-No-AIME24-v2` |
| 训练题数 | 100 |
| 抽样种子 | 42 |
| 评估数据 | `AIME24` |
| AIME24 题数 | 30 |
| 基础模型 | `deepseek-v4-flash` |
| API 类型 | `chat.completions` |
| 每题 rollout 数 | `grpo_n: 5` |
| 当前 rollout 并发 | 32 |
| 经验输出语言 | `same_as_input` |
| 层级快照 | `workspace/hierarchical_experiences/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.json` |
| 聚类审计 | `workspace/hierarchical_experiences/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.clusters.jsonl` |
| 当前经验 Agent | `configs/agents/practice/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915_agent.yaml` |

## 4. 配置继承与有效参数

### 4.1 继承链

当前 WSL 配置不是完整独立配置，而是逐层覆盖：

```text
configs/practice/math/math_dapo_100_full_hierarchy_wsl.yaml
  -> configs/practice/math/math_dapo_100_full_hierarchy.yaml
    -> configs/practice/math/TEMPLATE_math_practice.yaml
      -> configs/eval/math/math_AIME24.yaml
```

只查看最上层 WSL 文件会漏掉模板中的大量有效参数。

### 4.2 当前解析后的关键值

以下值已经通过 `ConfigLoader.load_training_free_grpo_config(...)` 实际解析确认：

| 参数 | 有效值 | 说明 |
| --- | ---: | --- |
| `practice.epochs` | 1 | 当前配置每次命令只循环一个 epoch |
| `practice.batch_size` | 100 | 100 道题组成一个 batch |
| `practice.grpo_n` | 5 | 每题生成 5 条 rollout |
| `practice.rollout_concurrency` | 32 | rollout 并发 |
| `evaluation.concurrency` | 32 | RolloutManager 实际使用的信号量并发 |
| `rollout_data_truncate` | 100 | 每个 epoch 使用 100 道题 |
| `shuffle_data` | false | 任务顺序固定 |
| `experience_output_language` | `same_as_input` | 只提供提示约束，不做实际同语种检测 |
| `embedding_model_name` | `sentence-transformers/all-MiniLM-L6-v2` | 本地 sentence-transformer |
| `embedding_dimensions` | 384 | embedding 维数 |
| `embedding_local_files_only` | true | 禁止运行时下载模型 |
| `l0_similarity_threshold` | 0.60 | L0 聚成 L1 的停止阈值 |
| `l1_similarity_threshold` | 0.55 | L1 聚成 L2 的停止阈值 |
| `min_l0_per_l1` | **5** | 最新命令实际使用的最小 L0 数 |
| `min_l1_per_l2` | 3 | 最小 L1 数 |
| `max_cluster_size` | 20 | 单簇上限 |
| `allow_provisional_aggregation` | true | 当前实验允许使用暂定阈值 |
| `l0_candidate_review_enabled` | true | L0 入池前评审 |
| `l1_candidate_review_enabled` | true | L1 入池前评审 |
| `l2_candidate_review_enabled` | true | L2 入池前评审 |
| `l0_review_full_pool_limit` | 50 | 活跃池不超过 50 时展示全池 |
| `l0_review_top_k` | 12 | 大池评审只检索最相关 12 条 |
| `max_l0_per_problem` | 0 | 关闭同任务 L0 数量限制 |
| `l0_injection_top_k` | 5 | 训练 rollout 每题最多检索 5 条 L0 |
| `include_l0_in_prompt` | true | 最终 Agent 允许加入 L0 |
| `max_l0_recent` | 20 | 最终 Agent 只加入最近 20 条 L0 |
| `require_practice_manifest` | false | 当前没有强制运行时验证冻结数据清单 |

### 4.3 配置与快照的时间含义

当前 YAML 写着 `epochs: 1`，但快照中的候选来源包含 epoch 0、1、2，说明历史上已经向同一快照写入了三轮学习结果：

| 候选来源 epoch | L0 候选数 |
| ---: | ---: |
| 0 | 125 |
| 1 | 95 |
| 2 | 108 |

独立聚合命令中的 `--epoch 3` 只是在审计记录中写入 epoch 标签，不会执行第四轮 rollout，也不会自动把 `practice.epochs` 改成 4。

## 5. 完整 Training-Free GRPO 流程

当前每个学习 epoch 的实际流程如下：

```text
读取 100 道 DAPO 题
  -> 每题复制为 5 个 trial
  -> 为每个 trial 检索并注入已有经验
  -> 最多形成 500 条 rollout
  -> verifier / judge 得到 reward
  -> 对每条 rollout 生成 trajectory summary
  -> 每题选取最多 4 条有代表性的成功/失败 summary
  -> 组内比较并生成原始 L0 candidates
  -> 按顺序评审每条 candidate
  -> 执行 ADD / UPDATE / DELETE / KEEP
  -> 原子保存层级快照
  -> epoch 末聚合 pending L0 -> L1
  -> 再聚合 pending L1 -> L2
  -> 将活跃经验写入新的 Agent YAML
```

### 5.1 数据展开

`TrainingFreeGRPODataManager` 按 `pass_k/grpo_n` 复制样本，并让同一问题的 trial 相邻。当前单 epoch 理论上是：

```text
100 tasks x 5 rollouts = 500 EvaluationSample rows
```

数据库实验 ID 使用 `<exp_id>_epoch_<N>`。日志中的：

```text
exp_id ... already exists in db
```

通常表示发现可恢复的已有记录，不等于执行失败。

### 5.2 Rollout 与 judge

`RolloutManager` 以数据库阶段恢复：

```text
init -> rollout -> judged
```

中断后，正常恢复只处理未完成阶段；已经 judged 的记录会复用。rollout 使用 `evaluation.concurrency`，judge 使用 `judge_concurrency`。

### 5.3 L0 候选生成

`ExperienceUpdater.generate_l0_candidates()` 分两阶段：

1. 为每条 rollout 生成详细 trajectory summary。
2. 按题目分组，比较组内 rollout，生成 `<Experiences>...</Experiences>`。

当前实现并不只从“有胜有负”的组学习。全成功、全失败和混合结果组都可进入经验生成。组内会优先选取有反事实价值的 summary，每题最多使用 4 条。

可靠性策略是 fail-closed：任何一条 summary 或 group-advantage 请求在重试后失败，整个 candidate batch 会报错，不接受部分成功结果。这可以避免悄悄缺失部分题目，但会让少数格式错误导致整批重跑。

### 5.4 L0 候选评审

原始 candidate 不会直接成为活跃经验。`HierarchicalExperienceManager` 会把 candidate 与当前活跃 L0 池比较，要求模型给出四选一决策，然后校验目标 ID、证据 ID、元数据和新内容。

评审是顺序执行的：前一条 candidate 的决策会改变后一条 candidate 看到的活跃池，因此结果可能具有顺序依赖。

### 5.5 epoch 末层级聚合

每个 epoch 的所有 batch 完成后才执行：

```text
aggregate_epoch(epoch)
  -> L0 -> L1
  -> L1 -> L2
```

未达到最小簇大小的经验不会被丢弃，会保持 `pending`，以后可在积累更多经验后重新聚类。

## 6. L0、L1、L2 的定义和生命周期

### 6.1 L0

L0 是从一个具体任务的一组 rollout 中提取出的可复用经验。合理的 L0 应包含：

- 可观察的适用条件。
- 具体解法或操作步骤。
- 常见失败模式。
- 至少一种校验方法。
- 明确的不适用边界。

L0 可以保留一定任务细节，但不应退化为该题答案复述，也不应只有“认真检查”“回代验证”之类空泛建议。

### 6.2 L1

L1 由同一语义簇内的多条 L0 支持，应表达跨题可复用的操作模式。例如：

```text
触发条件 -> 适用方法 -> 操作顺序 -> 失败边界 -> 验证方式
```

L1 不是简单拼接多个 L0，也不应把主题不同、仅共享通用校验措辞的 L0 合并。

### 6.3 L2

L2 由多个 L1 支持，目标是形成更高层的条件化策略或元策略。它应能指导“何时选择哪类方法”，而不是继续重复具体题型公式。

### 6.4 记录状态

活跃经验使用两个主要状态轴：

- `lifecycle_status`: `active`、`needs_review` 或归档相关状态。
- `aggregation_status`: `pending`、`aggregated` 或终端状态。

候选记录另有 `status`、`review_decision`、`resolution`、`result_experience_id` 和错误信息。被 UPDATE/DELETE 替代的旧版本进入 archive，保留 lineage 和来源证据。

## 7. 四种评审动作

### 7.1 动作语义

| 动作 | 当前语义 | 对经验池的影响 |
| --- | --- | --- |
| `ADD` | candidate 是独立、可复用且未被已有经验覆盖的知识 | 新增一条活跃经验 |
| `UPDATE` | candidate 应修正或扩展一条已展示的活跃经验 | 归档目标，创建替代版本 |
| `DELETE` | 已展示目标被证据证明错误、过时、有害或完全被替代 | 归档目标，不新增 candidate 内容 |
| `KEEP` | candidate 没有提供足以改变池子的增量 | 池保持不变 |

### 7.2 结构校验

当前实现对变更动作做了较严格的校验：

- ADD、UPDATE、DELETE 必须引用展示给评审模型的证据 ID。
- UPDATE、DELETE 只能指向展示过的活跃目标。
- UPDATE 必须实际改变规范化内容。
- ADD 不能与活跃池或 archive 中的规范化内容完全相同。
- L1/L2 的 ADD 或 UPDATE 必须包含有效结构化内容。
- 元数据硬约束不一致时拒绝提交。

L1/L2 聚合内容的结构包括：

```text
decision
title
principle
applicable_when
not_applicable_when
recommended_actions
evidence_summary
confidence
```

聚合模型也可以返回 `decision: conflict`，明确拒绝不相容的父经验。

### 7.3 合理性评价

**分析判断**：四动作集合本身是合理的，覆盖了经验池维护的主要情况，比只有 ADD/DELETE 更适合多轮学习。当前主要问题不在动作名称，而在候选召回、证据展示和顺序依赖：

1. 活跃池超过 50 后，评审只看到语义 top-12，真正重复项可能没有被召回。
2. `KEEP` 同时承担“候选重复”“候选太弱”“证据不足”等多种含义，后续统计不易区分。
3. UPDATE 只允许替换一个目标，无法直接处理一个 candidate 同时合并两条近义经验的情况。
4. 顺序评审缺少 epoch 末全局 consolidation，跨批次重复可能长期保留。
5. 模型决策有重试上限，失败 candidate 会持久化为 `review_failed`，但当前没有自动后处理队列。

## 8. 聚类算法与阈值门控

### 8.1 当前算法

`ExperienceClusterer` 实现未知簇数的凝聚式聚类：

1. 每条 pending 经验开始时是独立簇。
2. 计算两个簇之间所有跨簇样本对的 adjusted similarity。
3. 使用跨样本对平均值作为 linkage。
4. 合并平均值最高且不低于阈值的两个簇。
5. 达不到阈值时停止。
6. 不允许合并后超过 `max_cluster_size: 20`。

阈值判断使用：

```text
hard_compatible and adjusted_similarity >= threshold
```

### 8.2 元数据约束

硬约束字段：

```text
task_stage, failure_mode
```

双方都有值且值不同，就禁止合并。

软约束字段：

```text
domain, task_family, tool_type, strategy_type
```

软字段匹配会小幅加分，不匹配会减分。当前实现中的典型调整是匹配 `+0.02`、不匹配 `-0.10`。

### 8.3 当前元数据覆盖率

107 条活跃 L0 的实际情况：

| 字段 | 覆盖情况 |
| --- | --- |
| `failure_mode` | 107/107 |
| `failure_mode=none` | 91 |
| `failure_mode=mixed_outcome` | 12 |
| `failure_mode=verifier_failure` | 4 |
| `task_stage` | 107/107，但全部为 `unknown` |
| `domain` | 0/107 |
| `task_family` | 0/107 |
| `strategy_type` | 0/107 |
| `tool_type` | 0/107 |

**分析判断**：实际聚类几乎完全由文本 embedding 和 `failure_mode` 主导。配置了多种元数据约束，但绝大多数没有提供有效信息。

### 8.4 Embedding 风险

当前模型是 `all-MiniLM-L6-v2`。它体积小、速度快、适合英文句向量，但当前活跃 L0 中存在大量中文和中英混合内容。

基于字符分布的只读统计得到：

| 启发式语言类别 | 活跃 L0 数 |
| --- | ---: |
| 拉丁字母主导 | 79 |
| CJK 主导 | 28 |

这不是项目内置语言分类器的结果，只用于揭示当前经验池确实是混合语言。`same_as_input` 在当前代码中只生成提示语，验证函数不会检查输出是否真的与输入同语种。因此同一任务在不同轮次产生英文和中文近义经验是可能的。

### 8.5 离线阈值扫描

对当前 107 条 pending L0 使用生产聚类器和固定 embedding 做过离线扫描：

| L0 阈值 | 簇数 | 最大簇 | 大小至少 3 的簇 | 这些簇覆盖记录数 |
| ---: | ---: | ---: | ---: | ---: |
| 0.60 | 89 | 3 | 3 | 9 |
| 0.58 | 83 | 3 | 4 | 12 |
| 0.56 | 78 | 6 | 4 | 16 |
| 0.55 | 77 | 6 | 4 | 16 |
| 0.54 | 73 | 6 | 7 | 26 |
| 0.52 | 69 | 6 | 8 | 29 |
| 0.50 | 63 | 6 | 10 | 38 |
| 0.48 | 60 | 8 | 11 | 45 |
| 0.45 | 51 | 9 | 10 | 51 |

**分析判断**：不能只根据“产生更多大簇”选择阈值。人工检查发现，即使在 0.60 下也有明显假阳性，常由“回代验证”“检查边界”“工具失败后改用手算”等通用措辞驱动。

## 9. 当前快照的定量状态

快照：

```text
workspace/hierarchical_experiences/
  math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.json
```

### 9.1 层级计数

| 层级 | 活跃 | 归档 | 候选 | pending aggregation |
| --- | ---: | ---: | ---: | ---: |
| L0 | 107 | 19 | 328 | 107 |
| L1 | 0 | 0 | 0 | 0 |
| L2 | 0 | 0 | 0 | 0 |

快照 schema 是版本 4。

### 9.2 L0 候选状态

| candidate status | 数量 |
| --- | ---: |
| `committed` | 324 |
| `review_failed` | 4 |

### 9.3 评审动作

| 动作 | 数量 |
| --- | ---: |
| ADD | 107 |
| UPDATE | 19 |
| KEEP | 198 |
| 无决策，评审失败 | 4 |

这组数字与活跃和归档数量一致：UPDATE 会产生新版本并归档旧版本，因此 19 条归档记录不代表 19 条错误经验。

### 9.4 四条评审失败

| candidate | epoch | 原因 |
| --- | ---: | --- |
| `C0_e13430517bd7a2073fb5` | 1 | UPDATE 没有引用至少一个已展示 rollout evidence ID |
| `C0_25233c13c7061a393744` | 2 | `failure_mode: none` 与目标 `mixed_outcome` 硬冲突 |
| `C0_91fb2ee2db43bd19ee4b` | 2 | `failure_mode: mixed_outcome` 与目标 `none` 硬冲突 |
| `C0_ed65b11548c28326996f` | 2 | `failure_mode: mixed_outcome` 与目标 `none` 硬冲突 |

这些不是整次训练失败。系统把它们持久化为可审计的 `review_failed`，其余 324 条候选已经提交决策。

## 10. 最新 L1 聚合命令的精确诊断

用户执行了：

```bash
.venv/bin/python scripts/experiments/aggregate_hierarchical_experiences.py \
  --config-name math/math_dapo_100_full_hierarchy_wsl \
  --level l1 \
  --epoch 3 \
  --execute
```

### 10.1 该命令会做什么

- 读取配置指定的已有层级快照。
- 读取 pending L0。
- 本地计算 embedding 并聚类。
- 只对达到最小大小的簇调用 L1 聚合和 L1 candidate review 模型。
- 原子更新同一个快照。
- 在 JSONL 审计中写入一次聚合报告。

### 10.2 该命令不会做什么

- 不读取 DAPO 数据集生成新 rollout。
- 不执行 verifier/judge。
- 不生成新的 L0。
- `--epoch 3` 不会创建第四个训练 epoch，只是审计标签。
- 不自动重新生成 Agent YAML。

### 10.3 实际结果

最新审计记录为：

```text
source_level: L0
target_level: L1
epoch: 3
pending_count: 107
minimum_size: 5
cluster_count / attempt_count: 89
status: 89 x pending_below_minimum
cluster sizes: 74 x 1, 12 x 2, 3 x 3
```

因此：

- 没有一个簇达到 5。
- 没有生成 L1 candidate。
- 没有执行 L1 candidate review。
- 没有活跃 L1。
- 快照 SHA-256 前后都为 `5b0118e779bf7ba58e1f27877877116c1aa5d70fd8bdf99c29b3983b90fd0969`。
- `snapshot_changed: false` 是正确结果，不是保存失败。

### 10.4 为什么没有使用 3

用户创建了备份：

```text
math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.before_l1_min3.json
```

但文件名不会改变配置。WSL YAML 没有覆盖 `min_l0_per_l1`，所以继续继承实验配置中的 5。

**结论**：当前尚未实际测试 `min_l0_per_l1: 3`。

## 11. 把最小支持数从 5 降到 3 的影响

### 11.1 技术上是否能直接基于现有 L0 聚合

可以。独立聚合脚本就是为已有快照设计的，不需要重新跑 DAPO rollout。只要配置实际解析为 3，再执行同一 L1 聚合命令，就会对当前大小为 3 的簇尝试生成 L1。

### 11.2 当前是否应该直接执行

**分析判断**：不建议不经检查就执行。当前阈值 0.60 下恰好有 3 个三元素簇，其主题分别为：

1. 四次多项式完全平方数、复数模最值、圆盘包含最值。
2. 等差数列存在性、红蓝点直线分割、数位阶乘方程。
3. 平面图三角剖分、三角恒等式参数、正棱锥异面直线夹角。

这些成员不是同一数学模式。它们主要共享“检查边界、回代验证、工具失败后转手算”等表面措辞。若把最小支持数改成 3，这 3 个假阳性簇会首先进入 L1 聚合。

### 11.3 更稳妥的顺序

建议按以下顺序推进：

1. 保持 `l0_similarity_threshold: 0.60`，不要同时降低相似度阈值。
2. 先改进用于 embedding 的表示，去除重复的工具故障、答案格式和通用校验尾句。
3. 补齐 `domain`、`task_family`、`strategy_type` 和 `tool_type`。
4. 对现有三个三元素簇做人工或独立 LLM 兼容性判定。
5. 再用 `min_l0_per_l1: 3` 运行小规模聚合。
6. 检查 L1 candidate 的结构化字段和父证据，再决定是否接受。

不建议现在把阈值直接降到 0.52。它会让更多记录进入大簇，但在当前表示受通用模板措辞支配的情况下，召回增加很可能伴随明显精度下降。

## 12. L0 抽象质量分析

### 12.1 优点

当前不少 L0 已经包含：

- 明确题型触发条件。
- 可执行的数学变换或建模步骤。
- 定义域、端点、符号和分支检查。
- 适用边界与失效条件。
- 回代、小样例或独立公式验证。

这比只存“本题应该怎么做”更有迁移价值，也比只有一句泛化原则更可执行。

### 12.2 主要问题

1. **粒度不一致**：有些记录接近具体题解，有些已经接近 L1 级别的通用模式。
2. **答案泄漏式细节**：部分 L0 保留本题最终参数或数值答案，不利于纯粹迁移。
3. **模板尾句重复**：大量记录都包含工具报错后停止重试、回代验证、检查边界，影响 embedding。
4. **中英文重复**：同一源任务可存在英文和中文的近义活跃记录。
5. **过长**：若把多条长 L0 全量注入，会增加提示词噪声和注意力竞争。
6. **缺少结构化标签**：数学领域、题型、策略类型等字段几乎为空，难以可靠检索与聚类。

### 12.3 总体评价

**分析判断**：当前 L0 单条质量为“中等到较好，但不均匀”。经验生成模型已经能抽取方法、边界和校验，但池级质量控制还不足。部分 L0 实际上过于抽象，部分又过于题目化，当前不宜仅凭数量继续扩大池子。

## 13. 去重机制分析

### 13.1 当前结果

- 对内容只做空白折叠后，没有完全相同的活跃 L0。
- 至少有 8 个源任务各自保留了 2 条活跃 L0。
- 人工检查可见明显的中英文近义对和同题改写对。

因此“没有精确重复”不能说明语义去重有效。

### 13.2 根本原因

`normalise_content()` 当前只做：

```text
连续空白折叠 + 首尾去空白
```

稳定 ID 的输入还包含来源任务、rollout、父节点和 identity context。两条语义相同但来源不同或语言不同的经验可以得到不同 ID，这是 provenance 正确性与去重目标之间的冲突。

候选评审召回策略是：

- 活跃池不超过 50：展示全部活跃经验。
- 活跃池超过 50：只展示语义 top-12。

当前活跃池为 107，因此评审模型看不到全池。同任务配额 `max_l0_per_problem` 又是 0，即关闭状态。

### 13.3 建议的分层去重方案

1. 候选生成后先做质量门控，拒绝纯答案复述、过短空话和工具故障模板。
2. 使用 Unicode NFKC、标点和 LaTeX 感知的 canonicalization。
3. 增加不含 provenance 的 canonical-content fingerprint，仅用于重复检测，不替代现有稳定 ID。
4. 召回集合使用并集：精确指纹、同任务、lineage 邻居、semantic top-k、lexical top-k。
5. 默认限制同一任务最多保留约 2 条活跃 L0，除非 `strategy_type` 明确不同。
6. 每个 epoch 末增加一次全局 consolidation review。
7. embedding 相似只能触发复核，不能单独自动删除经验。

## 14. 经验注入机制

### 14.1 训练期间按题检索

训练 rollout 的注入逻辑位于 `TrainingFreeGRPOProcesser`：

- 所有非 L0 经验，即所有活跃 L1/L2，被视为全局经验并注入。
- L0 使用轻量词袋加 IDF 检索。
- 每题最多选择 `l0_injection_top_k: 5`。
- 最低分数为 `1e-12`，无词项重合时不强行注入。
- 被注入的经验 ID 写入 sample metadata，供质量追踪。

### 14.2 当前检索的中文问题

检索器的 tokenizer 将连续字母数字保留，并按空格切词。中文文本通常没有词间空格，整段中文容易成为一个超长 token。不同中文问题与中文经验几乎不会有完全相同的整段 token。

**分析判断**：当前词法检索对英文尚可，对中文经验很弱。当前又没有 L1/L2 全局经验，因此中文题在后续 epoch 中可能检索不到任何 L0，实际“经验学习闭环”会弱于配置表面显示的 top-5。

### 14.3 最终 Agent YAML 的三段式注入

完整训练完成后，Agent YAML 使用三段：

1. Zone 1：全部 L2，放在系统提示词顶部。
2. Zone 2：全部 L1，追加为操作模式。
3. Zone 3：最近的 L0，最多 `max_l0_recent` 条。

当前 L1/L2 都为空，所以生成的数学 Agent 只有 Zone 3。对 YAML 解码后确认其中有 20 条 `•` 开头的 L0，不是 107 条。

训练期间的 top-5 检索与最终 Agent 的最近 20 条注入是两套不同机制，不应混为一谈。

### 14.4 Agent 再生成缺口

独立聚合脚本明确不会生成 Agent YAML。仓库中的 `scripts/regen_practice_agent_yaml.py` 目前把输入、基础 Agent、输出文件和 `MAX_L0_RECENT` 硬编码为 SkillsBench，不能安全地直接用于当前数学快照。

**建议**：在正式产生 L1/L2 前，增加一个通用再生成 CLI，至少接受：

```text
--config-name
--snapshot
--output-agent
```

并复用 `TrainingFreeGRPO._create_agent_config_with_experiences()` 的同一套 zone 逻辑，避免训练入口和独立脚本出现行为漂移。

## 15. 持久化、中断与恢复

### 15.1 快照写入

层级快照使用原子替换：

```text
写入 .tmp
  -> flush
  -> fsync
  -> os.replace
```

这可以避免进程中断后留下半个 JSON 文件。

### 15.2 候选缓存

候选缓存由 experiment、epoch、batch 和 batch fingerprint 绑定。fingerprint 包含 rollout 和候选生成配置，用于防止改了输入或配置后错误复用旧 candidate。

层级快照中的已暂存 candidate 是权威状态，辅助数据库缓存不是权威来源。

### 15.3 正常恢复方式

`restart_step=None` 表示所有步骤都允许使用缓存，是正常崩溃恢复方式。

显式 `restart_step=N` 表示 N 之前用缓存，N 开始重新执行。但对已经存在内容的层级快照，当前代码会拒绝显式 rewind，因为不能证明快照中没有 N 之后产生的状态。

因此，中断后的首选操作是用原 experiment name 和原配置直接重跑，不传 `--restart_step`。程序会复用数据库 rollout、judge、candidate cache 和快照状态。

### 15.4 常见非致命告警

```text
PHOENIX_ENDPOINT or PHOENIX_PROJECT_NAME is not set
OPENAI_API_KEY is not set, skipping trace export
```

这些表示 tracing 未导出，不代表 rollout、经验学习或快照保存失败。

## 16. 已出现过的生成错误

### 16.1 英文语言校验失败

旧配置要求 `experience_output_language: english` 时，多次出现：

```text
generated L0 candidate violates experience_output_language='english'
(cjk_characters=0, latin_letters=0)
```

这表示模型返回了空内容、符号内容或无法识别为英文正文的 candidate。系统重试三次后仍失败，会拒绝整个部分 candidate batch。

当前 WSL 配置改为 `same_as_input`，避免了强制英文校验，但该模式目前不验证“是否真的与输入同语种”，因此经验池变成中英文混合。

### 16.2 无法解析 `<Experiences>`

```text
group advantage returned no parseable <Experiences> items
```

表示模型输出没有满足约定标签或标签内没有可分割经验。该错误也会重试，最终仍失败则整批拒绝。

### 16.3 API 断连

```text
RemoteProtocolError: Server disconnected without sending a response
```

这是上游 API 或网络瞬时错误。生成恢复层会按退避策略重试。若最终成功，不影响该批结果。

## 17. 数据隔离与 manifest

`configs/data/math/dapo_random_100_seed42_no_aime24_v2.json` 记录了：

- DAPO 源数据清单。
- AIME24 排除集，共 30 道题。
- seed 42。
- 基于 token 5-gram Jaccard 的近重复排除。
- 近重复阈值 0.90。
- 目标数据集与 manifest 的 SHA-256。

但当前 WSL 配置是：

```yaml
require_practice_manifest: false
```

**分析判断**：数据集本身有冻结证据，但当前 measured run 没有在启动时 fail-closed 验证数据库快照与 manifest 完全一致。正式实验应打开严格校验，并记录解析后配置、任务顺序和 Agent prompt hash。

## 18. AIME24 评估设计

### 18.1 当前默认协议

`configs/eval/math/math_AIME24.yaml`：

```yaml
data:
  dataset: AIME24
concurrency: 128
pass_k: 32
```

共 30 道题，每个条件最多产生：

```text
30 tasks x 32 trials = 960 rollouts
```

建议实际运行时把并发统一覆盖为 32，降低 API 瞬时错误并与当前可用吞吐一致。

### 18.2 baseline 命令

```bash
cd /mnt/d/Users/Administrator/Documents/GitHub/TF-LLM
export UTU_SKIP_AUTO_SETUP=1

.venv/bin/python scripts/run_eval.py \
  --config_name math/math_AIME24 \
  --exp_id aime24_dapo100_baseline_20260917 \
  --concurrency 32
```

### 18.3 当前 learned-agent 命令

```bash
cd /mnt/d/Users/Administrator/Documents/GitHub/TF-LLM
export UTU_SKIP_AUTO_SETUP=1

.venv/bin/python scripts/run_eval.py \
  --config_name math/math_AIME24 \
  --agent_config practice/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915_agent \
  --exp_id aime24_dapo100_l0_recent20_20260917 \
  --concurrency 32
```

这个 learned-agent 条件实际测试的是“最近 20 条 L0 的静态全局注入”，不是完整 107 条 L0，也不是 L0/L1/L2 层级 Agent。

### 18.4 公平比较要求

baseline 和经验组至少应保持以下条件一致：

- 同一个模型和提供商端点。
- 同一个模型版本。
- 同 temperature、top-p 和 timeout。
- 同 `pass_k`。
- 同 concurrency 和 judge concurrency。
- 同一批 30 道 AIME24。
- 同任务顺序。
- 同 verifier。
- 同工具配置。
- 唯一差异是经验 prompt。

建议保存每题每 trial 结果，做配对分析，而不只比较一个总平均分。

## 19. 当前过程能否提高评估效果

### 19.1 有利因素

- L0 通常包含明确的数学方法、边界和验证步骤。
- 多 rollout 提供了成功/失败对照，而不是只总结单条正确答案。
- candidate review 能阻止大量候选直接进入活跃池，当前 198/328 被 KEEP。
- 训练集已尝试排除 AIME24 重复题。
- 经验有 provenance 和可恢复快照，便于审计。

### 19.2 不利因素

- 当前最终 Agent 只用最近 20 条 L0，覆盖面有限且选择标准只是“最近”。
- L0 很长，可能挤占问题推理上下文并造成注意力干扰。
- 中英文近义重复会浪费 prompt token。
- 中文词法检索效果弱，多轮学习时经验不一定真正被注入。
- 当前聚类假阳性明显，错误 L1 可能比没有 L1 更有害。
- `all-MiniLM-L6-v2` 对当前混合语言经验不理想。
- 工具基础设施故障被反复写进数学经验，可能让 Agent 在正常工具环境中过早放弃工具。
- 当前没有 AIME24 baseline/learned 配对结果。

### 19.3 客观结论

**分析判断**：当前流程有提高 AIME24 的可能，但证据不足，且也存在降低效果的现实风险。工程流程“能完整跑通”与研究结论“经验有效”是两件事。只有完成严格配对评估并分析退化题目后，才能判断经验注入是否有效。

## 20. 建议的受控实验计划

### 阶段 A：固定当前 L0 基线

1. 冻结当前快照和 Agent YAML 的 SHA-256。
2. 运行无经验 baseline。
3. 运行当前最近 20 条 L0 Agent。
4. 比较逐题 pass@1、平均 reward、pass@32 和退化题。

### 阶段 B：验证检索，而不是扩大静态 prompt

1. 对 AIME24 每题动态检索 L0。
2. 使用支持中文的 multilingual embedding 或字符 n-gram/BM25。
3. 比较静态 recent-20 与 query top-k。
4. 记录每题实际注入 ID，检查相关性。

### 阶段 C：修复聚类表示

1. 将 L0 拆成核心策略和附加 provenance/工具备注。
2. embedding 只编码核心策略、适用条件和数学题型。
3. 补齐结构化元数据。
4. 人工标注一小批正负样本对，校准阈值。

### 阶段 D：小规模 L1

1. 固定阈值 0.60。
2. 最小支持数试验 3 与 5。
3. 只允许人工确认的兼容簇进入 L1 聚合。
4. 比较 L0-only 与 L0+L1，不同时修改检索器和 prompt 长度。

### 阶段 E：L2

只有在 L1 数量和质量足够、且 L1 已显示下游收益后，才开始 L2。当前没有任何 L1，讨论 L2 阈值还为时过早。

## 21. WSL 诊断与复现命令

### 21.1 环境与配置解析

```bash
cd /mnt/d/Users/Administrator/Documents/GitHub/TF-LLM
export UTU_SKIP_AUTO_SETUP=1

.venv/bin/python - <<'PY'
from utu.config import ConfigLoader

config = ConfigLoader.load_training_free_grpo_config(
    "math/math_dapo_100_full_hierarchy_wsl"
)
h = config.practice.hierarchical_learning
print("epochs=", config.practice.epochs)
print("grpo_n=", config.practice.grpo_n)
print("rollout_concurrency=", config.practice.rollout_concurrency)
print("l0_similarity_threshold=", h.l0_similarity_threshold)
print("min_l0_per_l1=", h.min_l0_per_l1)
print("min_l1_per_l2=", h.min_l1_per_l2)
print("snapshot=", h.experience_save_path)
PY
```

当前应打印 `min_l0_per_l1= 5`。

### 21.2 备份快照

```bash
cp \
  workspace/hierarchical_experiences/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.json \
  workspace/hierarchical_experiences/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.backup_$(date +%Y%m%d_%H%M%S).json
```

### 21.3 独立 L1 聚合

```bash
.venv/bin/python scripts/experiments/aggregate_hierarchical_experiences.py \
  --config-name math/math_dapo_100_full_hierarchy_wsl \
  --level l1 \
  --epoch 3 \
  --execute
```

在真正修改配置前重复这条命令仍会使用 5，不会测试 3。

若要测试 3，应先在一个新的实验覆盖配置中明确写入：

```yaml
practice:
  hierarchical_learning:
    min_l0_per_l1: 3
```

然后先用 21.1 的解析脚本确认输出确实为 3，再执行聚合。不要只通过备份文件名推断参数已经生效。

### 21.4 查看快照摘要

```bash
.venv/bin/python - <<'PY'
import json
from collections import Counter
from pathlib import Path

path = Path(
    "workspace/hierarchical_experiences/"
    "math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.json"
)
data = json.loads(path.read_text(encoding="utf-8"))
for level in ("l0", "l1", "l2"):
    active = data.get(f"{level}_experiences", [])
    archive = data.get(f"{level}_archive", [])
    candidates = data.get(f"{level}_candidates", [])
    print(level.upper(), len(active), len(archive), len(candidates))
print("L0 candidate status:", Counter(x.get("status") for x in data["l0_candidates"]))
PY
```

### 21.5 完整经验学习命令

```bash
cd /mnt/d/Users/Administrator/Documents/GitHub/TF-LLM
export UTU_SKIP_AUTO_SETUP=1

.venv/bin/python scripts/run_training_free_GRPO.py \
  --config_name math/math_dapo_100_full_hierarchy_wsl \
  --experiment_name math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915 \
  --epochs 1 \
  --rollout_concurrency 32
```

注意：对同一个 experiment name 重跑会优先恢复 epoch 0 的缓存。它不是“从 epoch 3 自动继续一轮”的命令。若目标是严格的第四轮学习，应先明确 epoch 编号、数据库 exp_id、candidate fingerprint 和快照来源的连续性，不要仅把 `--epochs` 改为 1 并假设它会从 3 开始。

### 21.6 建议的针对性测试

```bash
.venv/bin/python -m pytest \
  tests/practice/test_hierarchical_clustering.py \
  tests/practice/test_l0_candidate_review.py \
  tests/practice/test_hierarchical_aggregation_cli.py \
  tests/practice/test_experience_injection.py \
  tests/practice/test_generation_recovery.py
```

这些命令是建议验证项，本文档编写过程中没有重新执行完整测试套件。

## 22. 关键设计缺陷与风险清单

按优先级排序：

1. **聚类表示污染**：通用验证语句和工具故障语句主导相似度，产生跨题型假阳性。
2. **元数据缺失**：除 `failure_mode` 外几乎没有有效聚类标签。
3. **多语言不一致**：`same_as_input` 没有实际语言验证，同任务出现中英文近义记录。
4. **中文检索弱**：当前词法 tokenizer 不适合无空格中文。
5. **全局语义去重不足**：top-12 召回与空白归一化无法稳定发现跨语言和跨来源重复。
6. **静态 Agent 选择策略弱**：最终只取最近 20 条 L0，不考虑与 AIME24 问题的相关性或质量。
7. **聚合后 Agent 再生成缺口**：没有适用于任意数学快照的通用 CLI。
8. **manifest 未强制**：当前实验配置允许数据库内容变化后继续运行。
9. **评审失败积压**：4 条 `review_failed` 没有独立修复工作流。
10. **文档漂移**：旧层级文档仍描述 schema 2、hashing embedding 和旧阈值，而当前快照是 schema 4、sentence-transformer 和 0.60/0.55。

## 23. 建议优先修改的模块

| 优先级 | 文件 | 建议 |
| ---: | --- | --- |
| P0 | `utu/practice/experience_retriever.py` | 更换为中文可用的 tokenizer/embedding 检索，并保留可解释分数 |
| P0 | `utu/practice/experience_clusterer.py` | 支持“核心策略表示”而不是直接编码完整长文本 |
| P0 | L0 生成 prompt 与 schema | 把数学策略、题型、适用边界、工具故障分别结构化 |
| P1 | `utu/practice/hierarchy/review_context.py` | 扩展同任务、lineage、exact fingerprint 和双路检索召回 |
| P1 | `utu/practice/domain/identity.py` | 增加仅用于查重的 canonical-content fingerprint |
| P1 | `utu/practice/hierarchical_experience_manager.py` | 增加 epoch 末 consolidation 和 review_failed 重试入口 |
| P1 | `scripts/regen_practice_agent_yaml.py` | 改为通用、配置驱动的 Agent 再生成 CLI |
| P2 | `configs/practice/math/` | 为 min3、min5 和检索消融建立独立、可追踪配置 |
| P2 | `docs/concepts/hierarchical_experience.md` | 更新 schema、embedding、阈值和 candidate review 说明 |

## 24. 需要外部模型重点回答的问题

请独立分析以下问题，不要默认当前实现方向正确：

1. 当前 L0 的合理抽象边界是什么？哪些样本应拆分、压缩或上移到 L1？
2. 如何去除工具故障和通用验证尾句对 embedding 的支配，同时保留这些信息供执行时使用？
3. 当前 107 条 L0 应采用什么 multilingual embedding、检索器和 reranker？
4. L0 聚类应该基于完整文本、结构字段，还是单独生成的 canonical strategy representation？
5. `failure_mode` 是否应该作为硬约束？`none` 与 `mixed_outcome` 是否可能支持同一策略？
6. `task_family` 应作为硬约束、软约束，还是只用于候选生成前分桶？
7. 对 100 道题、107 条活跃 L0，`min_l0_per_l1=3` 是否统计上合理？还需要哪些多样性约束？
8. 是否应该要求 L1 的父 L0 来自至少 3 个不同 source task，而不只是 3 条记录？
9. 如何设计跨语言语义去重，既合并中英文近义项，又保留 provenance 和版本 lineage？
10. ADD/UPDATE/DELETE/KEEP 是否足够？是否需要 MERGE、REJECT_LOW_QUALITY 或 DEFER？
11. 如何消除顺序评审带来的结果依赖，并保持可恢复和确定性？
12. 最终 Agent 应静态注入多少经验，还是应完全改为逐题检索？
13. 如何构造 AIME24 baseline、L0-only、retrieval-L0、L0+L1 的最小有效消融矩阵？
14. 30 道 AIME24、pass-k 32 下，应使用哪些统计检验和置信区间？
15. 当前系统中哪些机制最可能造成负迁移？应记录哪些逐题证据来定位？

## 25. 可直接交给其他大模型的提示词

```text
你是一名负责 LLM Agent、经验记忆、检索、聚类和严谨评估的研究工程师。

请阅读仓库中的：
docs/research/DAPO100_PROJECT_ANALYSIS_CONTEXT.md

并重点检查以下源文件和实验产物：
- utu/practice/training_free_grpo.py
- utu/practice/experience_updater.py
- utu/practice/hierarchical_experience_manager.py
- utu/practice/experience_clusterer.py
- utu/practice/hierarchy/review_context.py
- utu/practice/domain/identity.py
- utu/practice/experience_retriever.py
- utu/eval/processer/training_free_grpo_processor.py
- configs/practice/math/TEMPLATE_math_practice.yaml
- configs/practice/math/math_dapo_100_full_hierarchy.yaml
- configs/practice/math/math_dapo_100_full_hierarchy_wsl.yaml
- workspace/hierarchical_experiences/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.json
- workspace/hierarchical_experiences/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.clusters.jsonl
- configs/agents/practice/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915_agent.yaml

请不要只复述文档。请独立验证关键结论，并输出：
1. 按严重程度排序的代码和研究设计问题。
2. 对 L0 抽象质量的样本级评价。
3. 对去重、检索、聚类和 L1 生成的重构方案。
4. 是否应该把 min_l0_per_l1 从 5 降到 3，以及必要前置条件。
5. 一个能证明或否定 AIME24 收益的配对实验设计。
6. 最小修改方案与理想长期方案，分别列出涉及文件、数据迁移和测试。
7. 明确区分已验证事实、推断和建议。

特别注意：最新 epoch 3 独立聚合仍使用 minimum_size=5，并没有测试 3；
当前三个大小为 3 的簇人工观察存在明显跨题型假阳性。
```

## 26. 最终状态判断

当前系统已经超过“概念原型”阶段：L0 候选、证据、四动作评审、版本 lineage、原子快照、恢复和审计都具备较完整的工程骨架。

但它还没有达到“可直接相信层级经验能提高 AIME24”的阶段。当前最关键的问题不是继续增加 epoch 数或简单降低阈值，而是先提高经验表示、中文检索、语义去重和聚类精度，并完成严格 baseline 对照。

对最新命令的最终结论是：执行过程没有程序错误，但由于实际最小支持数仍为 5，所有簇都低于门槛，所以快照按设计保持不变。下一步不应把 `snapshot_changed: false` 当成故障，也不应把备份文件名中的 `min3` 当成参数已经生效。
