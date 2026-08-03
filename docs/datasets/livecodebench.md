# LiveCodeBench 训练与评估

LiveCodeBench 用于评估竞争编程题的代码生成能力。当前适配从 `release_v5` 固定抽取 30 道训练题和 50 道评估题，并使用公开测试与隐藏测试执行结果计算奖励。

## 准备数据

```bash
uv run python scripts/data/prepare_livecodebench_data.py \
  --version_tag release_v5 \
  --train_count 30 \
  --eval_count 50 \
  --seed 42
```

生成 `LiveCodeBench-Train-30` 与 `LiveCodeBench-Eval-50`。修改版本、数量或 seed 后应使用新的实验 ID，并重新审计训练/评估题目是否重叠。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name livecodebench/lcb_practice
```

当前配置对 30 道训练题进行 3 个 epoch、每题 5 条 rollout，生成：

- `workspace/hierarchical_experiences/lcb_practice.json`
- `configs/agents/practice/lcb_practice_30_agent.yaml`

## 公平评估

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
BASE_ID="lcb_baseline_${RUN_TAG}"
EXP_ID="lcb_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name livecodebench/lcb_baseline_eval \
  --exp_id "$BASE_ID"

uv run python scripts/run_eval.py \
  --config_name livecodebench/lcb_baseline_eval \
  --agent_config practice/lcb_practice_30_agent \
  --exp_id "$EXP_ID"
```

两组共享 `LiveCodeBench-Eval-50`、`pass_k=1` 与执行 verifier。需要固定模型时，两条命令添加相同的 `--agent_model '<model-id>'`。

## 查看结果

```bash
uv run python scripts/utils/view_benchmark_results.py \
  -b lcb \
  -e "$BASE_ID" "$EXP_ID" \
  --detailed
```

除总 Pass@1 外，应报告经验组新增通过和丢失通过的题目，并检查错误是算法、输出格式、超时还是执行环境导致。

## 安全与复现

该 benchmark 会执行模型生成的代码。只在隔离的、无敏感凭据的运行环境中评估，不要在个人主机或生产服务器上直接执行不受信任代码。固定数据版本、Python 版本、资源限制和测试超时，否则结果不可直接比较。
