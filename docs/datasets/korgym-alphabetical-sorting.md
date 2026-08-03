# KORGym Alphabetical Sorting 训练与评估

Alphabetical Sorting 是单轮字典序排序任务。当前游戏 ID 为 `22-alphabetical_sorting`，固定端口 8776。

## 启动服务

在终端 A：

```bash
uv run python scripts/korgym/start_korgym_server.py \
  22-alphabetical_sorting \
  --host 127.0.0.1 \
  --port 8776
```

## 准备数据

在终端 B：

```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name 22-alphabetical_sorting
```

默认创建 `KORGym-AlphabeticalSorting-Train-100` 与 `KORGym-AlphabeticalSorting-Eval-50`，训练和评估 seed 不重叠。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/alphabetical_sorting_practice
```

经验写入 `workspace/hierarchical_experiences/alphabetical_sorting_practice.json`，生成 Agent 为 `configs/agents/practice/alphabetical_sorting_practice_agent.yaml`。

## 公平评估

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
MODEL='<固定模型版本>'
BASE_ID="alphabetical_sorting_baseline_${RUN_TAG}"
EXP_ID="alphabetical_sorting_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name korgym/alphabetical_sorting_eval \
  --agent_model "$MODEL" \
  --concurrency 4 \
  --exp_id "$BASE_ID"

uv run python scripts/run_eval.py \
  --config_name korgym/alphabetical_sorting_eval \
  --agent_config practice/alphabetical_sorting_practice_agent \
  --agent_model "$MODEL" \
  --concurrency 4 \
  --exp_id "$EXP_ID"
```

## 查看结果

```bash
uv run python scripts/korgym/view_korgym_results.py \
  --compare "$BASE_ID" "$EXP_ID" \
  --detailed
```

分析时区分字典序策略错误、大小写或标点规则不一致、输出列表解析失败与服务故障。任何排序规范修正都要同时重跑两组。
