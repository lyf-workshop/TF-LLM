# SkillsBench 训练与论文对齐评估

SkillsBench 评估 Agent 在隔离 Linux 环境中完成软件、办公、科学等专业任务的能力。每个试次可能构建 Docker 环境并由 Harbor verifier 读取产物，因此基础设施可靠性是协议的一部分。

## 环境

推荐 Linux x86_64。WSL2 需要 Docker Desktop 的 WSL integration。

```bash
bash scripts/setup/deploy.sh --profile skillsbench
uv run python scripts/setup/check_environment.py \
  --profile skillsbench \
  --check-api
```

部署脚本固定外部仓库到 `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`，并安装适配器当前要求的 `harbor==0.3.0`。

## 准备数据

论文 Table 19 的 87 个任务：

```bash
uv run python scripts/data/prepare_skillsbench_data.py \
  --repo_path ./SkillsBench-repo \
  --paper_87 \
  --force
```

结果数据集为 `SkillsBench-Paper-87`。经验学习所用的工程划分：

`--paper_87` 会按论文清单保留需要外部 API 的任务。正式对齐时必须补齐这些任务要求的凭据；不能因缺少凭据静默删题，也不能把凭据缺失计为 Agent 失败。

```bash
uv run python scripts/data/prepare_skillsbench_data.py \
  --repo_path ./SkillsBench-repo \
  --eval_dataset_name SkillsBench-Eval-77 \
  --train_dataset_name SkillsBench-Train-40 \
  --train_ratio 0.5 \
  --force
```

正式研究必须额外检查 `SkillsBench-Train-40` 与 `SkillsBench-Paper-87` 的任务 ID 是否重叠。若有重叠，这一结果只能说明同分布经验复用，不能作为独立测试集泛化结论。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name skillsbench/skillsbench_practice
```

当前配置使用 `SkillsBench-Train-40`、每题 5 条 rollout、低并发 Docker 调度，并写入：

- 经验池：`workspace/hierarchical_experiences/skillsbench_practice.json`
- 生成 Agent：`configs/agents/practice/skillsbench_practice_2_ds_agent.yaml`

训练 temperature 用于制造轨迹差异，可以高于零；正式评估 temperature 必须保持为 0。

## 论文对齐成对评估

不要分别手工启动两个 `run_eval.py` 作为正式 SkillsBench 结果。专用调度器会交错 baseline 与经验组、分类基础设施错误、补跑无效试次，并检查发布条件。

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
MODEL='<固定模型版本>'
BASE_ID="skillsbench_paper_baseline_${RUN_TAG}_v4"
EXP_ID="skillsbench_paper_tf_grpo_${RUN_TAG}_v4"

uv run python scripts/experiments/run_skillsbench_paired_eval.py \
  --baseline-config skillsbench/skillsbench_paper_baseline_eval \
  --experience-config skillsbench/skillsbench_paper_tf_grpo_eval \
  --baseline-exp-id "$BASE_ID" \
  --experience-exp-id "$EXP_ID" \
  --agent-model "$MODEL" \
  --pair-concurrency 2 \
  --seed 20260730 \
  --step run
```

两个配置都使用 `SkillsBench-Paper-87`、`pass_k=3` 和 `temperature=0.0`。完整实验应得到每组 `87 x 3 = 261` 个有效试次。

## 补跑基础设施错误

```bash
uv run python scripts/experiments/run_skillsbench_paired_eval.py \
  --baseline-config skillsbench/skillsbench_paper_baseline_eval \
  --experience-config skillsbench/skillsbench_paper_tf_grpo_eval \
  --baseline-exp-id "$BASE_ID" \
  --experience-exp-id "$EXP_ID" \
  --agent-model "$MODEL" \
  --pair-concurrency 2 \
  --seed 20260730 \
  --step retry-infra
```

API 连接、API timeout、429/5xx、Harbor 异常和 `RewardFileNotFoundError` 属于 `infra_error`。模型请求按 2 到 30 秒的指数退避最多额外尝试 4 次；连续 3 次故障后，调度器固定暂停 60 秒再探测，暂停时间不会继续增长。超过次数后试次保持无效，只补跑这些无效试次。真正耗尽 900 秒任务时间仍算 Agent 失败。

## 查看与发布

```bash
uv run python scripts/experiments/run_skillsbench_paired_eval.py \
  --baseline-exp-id "$BASE_ID" \
  --experience-exp-id "$EXP_ID" \
  --step stat

uv run python scripts/utils/view_benchmark_results.py \
  -b skillsbench \
  -e "$BASE_ID" "$EXP_ID"
```

只有两组都达到 261 个有效试次、无待补跑 infra error，且模型与协议一致时才发布对比。报告总通过率、平均 reward、领域分项、难度分项、增益/退化任务以及置信区间；不要继续向旧 `_v3` 实验 ID 混入新日期数据。
