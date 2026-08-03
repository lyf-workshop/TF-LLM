# ZebraLogic 训练与评估

ZebraLogic 用于评估约束满足、排除推理和结构化答案能力。当前工程划分使用 100 条训练样本和 30 条测试样本。

## 准备数据

```bash
uv run python scripts/data/prepare_zebralogic_samples.py \
  --train_size 100 \
  --test_size 30 \
  --train_name ZebraLogic-Train-100 \
  --test_name ZebraLogic-Test-30
```

脚本会按稳定划分创建两个数据库数据集。正式运行前确认实际写入数量与配置名称一致。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name logic/logic_reasoning_zebralogic \
  --rollout_concurrency 16
```

默认 YAML 保留了早期高并发值。应按 endpoint 限额覆盖为可持续值，并记录最终参数。生成 Agent 为 `configs/agents/practice/logic_practice_zebralogic_agent.yaml`。

## 公平评估

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
BASE_ID="zebralogic_baseline_${RUN_TAG}"
EXP_ID="zebralogic_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name logic/logic_zebralogic_test \
  --exp_id "$BASE_ID" \
  --concurrency 16

uv run python scripts/run_eval.py \
  --config_name logic/logic_zebralogic_test \
  --agent_config practice/logic_practice_zebralogic_agent \
  --exp_id "$EXP_ID" \
  --concurrency 16
```

`logic_zebralogic_test` 当前使用 `pass_k=32`。两组必须复用该配置，只替换 Agent。

## 查看结果

```bash
uv run python scripts/utils/view_results.py \
  --compare \
  -e "$BASE_ID" "$EXP_ID" \
  --detailed
```

## 结果解释

除 Pass@K 外，应检查最终答案解析、字段顺序与 verifier 兼容性。若推理正确但输出格式无法解析，应单独记录为适配问题，再决定是否统一修正并重跑两组，不能只修经验组。

题量有限且 `pass_k` 高，推荐报告题目级成功次数与多个运行 seed，而不是只比较一个百分比。
