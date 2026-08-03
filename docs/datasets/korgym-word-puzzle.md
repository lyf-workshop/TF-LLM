# KORGym Word Puzzle 训练与评估

Word Puzzle 是单轮文字线索任务。当前游戏 ID 为 `8-word_puzzle`，固定端口 8775。

## 启动服务

在终端 A：

```bash
uv run python scripts/korgym/start_korgym_server.py \
  8-word_puzzle \
  --host 127.0.0.1 \
  --port 8775
```

## 准备数据

在终端 B：

```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name 8-word_puzzle
```

默认创建 `KORGym-WordPuzzle-Train-100`（seed 51-150）和 `KORGym-WordPuzzle-Eval-50`（seed 1-50）。

## 学习经验

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/word_puzzle_practice
```

经验写入 `workspace/hierarchical_experiences/word_puzzle_practice.json`，生成 Agent 为 `configs/agents/practice/word_puzzle_practice_agent.yaml`。当前 practice 使用 level 3，而 eval 配置使用 level 1；这属于跨难度迁移，报告中必须明确，或在正式实验前统一难度并对两组共同重跑。

## 公平评估

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
MODEL='<固定模型版本>'
BASE_ID="word_puzzle_baseline_${RUN_TAG}"
EXP_ID="word_puzzle_experience_${RUN_TAG}"

uv run python scripts/run_eval.py \
  --config_name korgym/word_puzzle_eval \
  --agent_model "$MODEL" \
  --concurrency 4 \
  --exp_id "$BASE_ID"

uv run python scripts/run_eval.py \
  --config_name korgym/word_puzzle_eval \
  --agent_config practice/word_puzzle_practice_agent \
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

重点审计答案顺序、词形、解析失败和服务错误。若修改 verifier 或输出模板，baseline 与经验组都必须重新评估。
