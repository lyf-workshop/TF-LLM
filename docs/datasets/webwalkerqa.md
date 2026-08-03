# WebWalkerQA 训练与评估

WebWalkerQA 评估网页搜索、页面读取、证据整合与答案生成。它同时依赖 Agent 模型、Judge 模型、搜索服务和网页内容服务，是当前最容易受外部网络变化影响的数据集。

## 额外配置

在 `.env` 中设置：

```dotenv
JUDGE_LLM_TYPE=chat.completions
JUDGE_LLM_MODEL=<固定 judge 模型>
JUDGE_LLM_BASE_URL=<judge endpoint>
JUDGE_LLM_API_KEY=<judge key>

SERPER_API_KEY=<serper key>
JINA_API_KEY=<jina key>
```

Agent 与 Judge 模型都应固定实际版本。

## 准备数据

```bash
uv run python scripts/data/process_training_free_GRPO_data.py \
  --datasets AFM_web_RL WebWalkerQA
```

`AFM_web_RL` 用于经验学习，`WebWalkerQA` 用于评估。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name web/web_search \
  --rollout_concurrency 8
```

默认 YAML 的并发较高。首次部署建议从 4 到 8 开始，根据 endpoint 限额逐步调整。当前配置生成 `configs/agents/practice/web_practice_agent.yaml`。

## 公平评估

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
BASE_ID="webwalker_baseline_${RUN_TAG}"
EXP_ID="webwalker_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name web/web \
  --exp_id "$BASE_ID" \
  --concurrency 8 \
  --judge_concurrency 8

uv run python scripts/run_eval.py \
  --config_name web/web \
  --agent_config practice/web_practice_agent \
  --exp_id "$EXP_ID" \
  --concurrency 8 \
  --judge_concurrency 8
```

两组必须使用相同的 Agent 模型、Judge 模型、并发和时间窗口，最好逐批交错运行。搜索索引和网页内容会变化，相隔较久的实验不能视为严格对照。

## 查看结果

```bash
uv run python scripts/utils/view_results.py \
  --compare \
  -e "$BASE_ID" "$EXP_ID" \
  --detailed
```

## 失败审计

将 429、5xx、连接失败、页面抓取失败和 Judge API 异常与答案错误分开统计。外部服务错误应在相同条件下补跑；网页确实不存在或 Agent 选择了错误来源则属于任务行为。报告中同时保存运行日期与外部服务版本。
