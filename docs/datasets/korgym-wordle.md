# KORGym Wordle 训练与评估

Wordle 是当前 KORGym 适配中的多轮任务。Agent 根据每轮绿、黄、灰反馈更新约束，最多进行 10 次猜测。当前游戏 ID 为 `33-wordle`，固定端口 8777。

## 启动服务

在终端 A：

```bash
uv run python scripts/korgym/start_korgym_server.py \
  33-wordle \
  --host 127.0.0.1 \
  --port 8777
```

服务启动后确认：

```bash
curl -f http://127.0.0.1:8777/docs >/dev/null
```

## 准备数据

在终端 B：

```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name 33-wordle
```

默认创建 `KORGym-Wordle-Train-100`（seed 51-150）和 `KORGym-Wordle-Eval-50`（seed 1-50）。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/wordle_practice \
  --rollout_concurrency 4
```

默认 YAML 中并发注释与实际值不一致，因此文档显式覆盖为 4。经验写入 `workspace/hierarchical_experiences/wordle_practice_2.json`，当前生成 Agent 为 `configs/agents/practice/wordle_practice_2_agent.yaml`。

practice 当前使用 4 字母单词，eval 使用 5 字母单词。这是跨长度迁移实验，不是同难度训练；正式报告必须明确，或先统一 level 并在同一协议下重跑。

## 公平评估

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
MODEL='<固定模型版本>'
BASE_ID="wordle_baseline_${RUN_TAG}"
EXP_ID="wordle_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name korgym/wordle_eval \
  --agent_model "$MODEL" \
  --concurrency 4 \
  --exp_id "$BASE_ID"

uv run python scripts/run_eval.py \
  --config_name korgym/wordle_eval \
  --agent_config practice/wordle_practice_2_agent \
  --agent_model "$MODEL" \
  --concurrency 4 \
  --exp_id "$EXP_ID"
```

两组都应保持 `max_rounds=10`、相同 level、模型和采样参数。不要把单轮 `run_eval.py` 输出解析逻辑替换成普通问答 verifier。

## 查看结果

```bash
uv run python scripts/korgym/view_korgym_results.py \
  --compare "$BASE_ID" "$EXP_ID" \
  --detailed
```

## 多轮审计

逐例检查以下内容：

- 每轮 session 是否连续，反馈是否属于当前 seed。
- 黄字是否保留但排除错误位置，灰字是否考虑重复字母规则。
- 非法单词和重复猜测如何计分。
- 失败是策略耗尽 10 轮，还是服务、session 或解析异常。

服务异常导致历史丢失时，该试次无效；Agent 在有效历史中耗尽轮数则属于真实失败。
