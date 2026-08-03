# 脚本参考

本文只列出当前文档体系使用的稳定入口。数据集的完整命令与固定参数以 [`docs/datasets/`](../docs/datasets/index.md) 为准。

## 核心入口

### 评估

```bash
uv run python scripts/run_eval.py \
  --config_name <configs/eval 下的相对名称> \
  --exp_id <唯一实验 ID>
```

常用覆盖参数：

| 参数 | 作用 |
| --- | --- |
| `--agent_config` | 替换为 `configs/agents/` 下的 Agent |
| `--agent_model` | 固定实际模型 ID |
| `--dataset` | 临时覆盖数据集 |
| `--concurrency` | 覆盖 rollout 并发 |
| `--judge_concurrency` | 覆盖 judge 并发 |
| `--step` | `all`、`rollout`、`judge` 或 `retry-infra` |

### 经验学习

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name <configs/practice 下的相对名称>
```

该入口运行 rollout、奖励比较、经验更新并生成 Agent YAML。它不更新模型权重。

### 重建经验 Agent

```bash
uv run python scripts/regen_practice_agent_yaml.py \
  --experiences <experience.json> \
  --output <agent.yaml>
```

用于从已有经验 JSON 重新生成 Agent，不会重跑 rollout。

## 部署脚本

| 脚本 | 用途 |
| --- | --- |
| `setup/deploy.sh` | 安装 core、korgym、skillsbench 或 all profile |
| `setup/check_environment.py` | 检查 Python、依赖、API、Docker、Harbor 与外部仓库 |

首次安装见[部署指南](../docs/DEPLOYMENT.md)。

## 数据准备

当前主路径：

- `data/process_training_free_GRPO_data.py`：AIME、DAPO Math、WebWalkerQA 等内置数据。
- `data/prepare_livecodebench_data.py`：固定版本抽取 LiveCodeBench 训练/评估集。
- `data/prepare_zebralogic_samples.py`：创建 ZebraLogic 稳定划分。
- `data/prepare_korgym_data.py`：按游戏 ID 和 seed 创建 KORGym 数据。
- `data/prepare_skillsbench_data.py`：创建 SkillsBench 工程划分或论文 87 任务集。
- `data/move_dataset_tasks.py`、`data/prune_broken_train_tasks.py`：SkillsBench 数据维护工具，执行前先查看 `--help`。

`data/` 中其余脚本为专项转换或旧实验辅助，不应替代各数据集文档中的主命令。

## 正式实验调度

`experiments/run_skillsbench_paired_eval.py` 是 SkillsBench 论文对齐入口，负责交错运行两组、标记 infra error、补跑无效试次和检查 261/261 发布门禁。普通数据集继续使用 `run_eval.py`。

`experiments/` 中其他脚本多为逐题分析或历史实验驱动，使用前必须检查内置实验 ID 与路径。

## 结果查看

```bash
# AIME、WebWalkerQA、ZebraLogic 等
uv run python scripts/utils/view_results.py \
  --compare -e <baseline-id> <experience-id> --detailed

# SkillsBench 或 LiveCodeBench
uv run python scripts/utils/view_benchmark_results.py \
  -b <skillsbench|lcb> -e <baseline-id> <experience-id> --detailed

# KORGym
uv run python scripts/korgym/view_korgym_results.py \
  --compare <baseline-id> <experience-id> --detailed
```

其他通用工具：

- `utils/view_datasets.py`：列出数据集。
- `utils/view_dataset.py`：查看单个数据集样本。
- `utils/check_experiments.py`：列出实验。
- `utils/clean_experiment_data.py`：按实验 ID 清理记录，使用前先备份。
- `db/dump_db.py`、`db/clear_cache.py`：数据库导出与缓存维护。

## KORGym

- `korgym/start_korgym_server.py`：启动指定游戏服务。
- `korgym/view_korgym_results.py`：查看或对比结果。
- `korgym/check_korgym_env.py`：专项环境检查。
- `korgym/games/`：游戏诊断与历史实验脚本，不是统一正式入口。

## 分析与归档

- `error_analysis/`：逻辑 verifier、冲突检测和错误提取实验。
- `logic/zebralogic/`：ZebraLogic 专项诊断与统计。
- `analysis/`、`tracing/`：工具使用和 Phoenix tracing。
- `archive/setup/`：被 `scripts/setup/deploy.sh` 取代的旧安装脚本和模板。
- `archive/experiments/qwen/`：带旧路径与旧配置假设的 Qwen 实验脚本。
- `archive/` 其余内容：已废弃或仅用于追溯的脚本；新实验不得依赖其中命令。

任何脚本若与数据集文档冲突，以当前 Python 参数、YAML 和数据集文档为准。
