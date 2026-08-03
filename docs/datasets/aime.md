# AIME 2024/2025 训练与评估

AIME 用于测量数学推理与最终数值答案的正确性。经验从 DAPO-Math-17k 的训练样本中提取，AIME 2024 和 AIME 2025 作为独立评估集。

## 准备数据

```bash
uv run python scripts/data/process_training_free_GRPO_data.py \
  --datasets AIME24 AIME25 DAPO-Math-17k
```

数据默认写入 `UTU_DB_URL` 指向的数据库。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name math/math_reasoning
```

当前配置从 DAPO-Math-17k 取 100 条数据、每题 5 条 rollout，生成 `configs/agents/practice/math_practice_agent.yaml`。

## 评估 AIME 2024

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
BASE24="aime24_baseline_${RUN_TAG}"
EXP24="aime24_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name math/math_AIME24 \
  --exp_id "$BASE24"

uv run python scripts/run_eval.py \
  --config_name math/math_AIME24 \
  --agent_config practice/math_practice_agent \
  --exp_id "$EXP24"
```

## 评估 AIME 2025

```bash
BASE25="aime25_baseline_${RUN_TAG}"
EXP25="aime25_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name math/math_AIME25 \
  --exp_id "$BASE25"

uv run python scripts/run_eval.py \
  --config_name math/math_AIME25 \
  --agent_config practice/math_practice_agent \
  --exp_id "$EXP25"
```

## 查看结果

```bash
uv run python scripts/utils/view_results.py \
  --compare \
  -e "$BASE24" "$EXP24" \
  --detailed

uv run python scripts/utils/view_results.py \
  --compare \
  -e "$BASE25" "$EXP25" \
  --detailed
```

## 成本与报告

当前两个评估配置均为 `pass_k=32`。每道题会产生 32 条采样，增加并发只会缩短等待时间，不会减少调用量。首次运行可通过命令行临时降低并发，但 baseline 与经验组必须使用同一参数。

报告应同时给出单次采样准确率、Pass@K、题目级变化和跨运行方差。AIME 题量小，单次结果波动较大，不应根据一次运行下结论。
