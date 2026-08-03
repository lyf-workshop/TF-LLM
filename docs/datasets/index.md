# 数据集索引

每个数据集都有独立手册，包含数据准备、经验学习、baseline、经验组评估和结果查看。README 只维护共用安装入口。

| 数据集 | 训练配置 | 评估配置 | 主要指标 |
| --- | --- | --- | --- |
| [SkillsBench](skillsbench.md) | `skillsbench/skillsbench_practice` | 专用成对评估 | 有效试次通过率、平均 reward |
| [LiveCodeBench](livecodebench.md) | `livecodebench/lcb_practice` | `livecodebench/lcb_baseline_eval` | Pass@1 |
| [AIME](aime.md) | `math/math_reasoning` | `math/math_AIME24`、`math/math_AIME25` | Pass@K |
| [WebWalkerQA](webwalkerqa.md) | `web/web_search` | `web/web` | Judge reward |
| [ZebraLogic](zebralogic.md) | `logic/logic_reasoning_zebralogic` | `logic/logic_zebralogic_test` | Pass@K |
| [KORGym Word Puzzle](korgym-word-puzzle.md) | `korgym/word_puzzle_practice` | `korgym/word_puzzle_eval` | 成功率、reward |
| [KORGym Alphabetical Sorting](korgym-alphabetical-sorting.md) | `korgym/alphabetical_sorting_practice` | `korgym/alphabetical_sorting_eval` | 成功率、reward |
| [KORGym Wordle](korgym-wordle.md) | `korgym/wordle_practice` | `korgym/wordle_eval` | 多轮成功率、reward |

KORGym 的共用服务约定见 [KORGym 总览](korgym.md)。

## 统一实验流程

1. 准备互不泄漏的训练集与评估集。
2. 在固定训练集上运行 Training-Free GRPO，生成经验 Agent。
3. 用一份 eval YAML 跑无经验 baseline。
4. 复用同一份 eval YAML，并通过 `--agent_config` 替换为经验 Agent。
5. 审计基础设施失败后比较结果，保存配置、commit 和模型 ID。

普通数据集的推荐命令形态：

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)

uv run python scripts/run_eval.py \
  --config_name <eval-config> \
  --exp_id <dataset>_baseline_${RUN_TAG}

uv run python scripts/run_eval.py \
  --config_name <same-eval-config> \
  --agent_config practice/<generated-agent> \
  --exp_id <dataset>_experience_${RUN_TAG}
```

`--agent_model` 可用于将两组固定到同一实际模型版本。不要直接采用内容已经漂移的 `*_practice_eval.yaml` 做正式对照。

## 结果有效性

- 训练和评估样本必须按稳定 ID 审计，不能只相信数据集名称。
- baseline 与经验组应同日交错运行，并共享 endpoint、模型、温度、并发策略、超时和 verifier。
- API、429/5xx、容器与缺失产物错误属于无效试次；真正的 Agent 超时和 verifier 不通过属于任务失败。
- 高 `pass_k` 会按题目成倍增加调用量，并发增加不会降低成本。
- 正式结果至少重复多个 seed 或运行批次，并报告均值、方差和任务级变化。
