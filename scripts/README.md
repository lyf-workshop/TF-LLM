# Scripts 使用说明

本文档说明 `scripts/` 目录下所有脚本的用途与使用方法。

---

## 目录结构

```
scripts/
├── run_eval.py                    # 评估入口
├── run_training_free_GRPO.py      # 训练入口
├── regen_practice_agent_yaml.py   # 重新生成 practice agent YAML
│
├── utils/                         # 通用工具脚本
├── korgym/                        # KORGym 游戏环境脚本
│   └── games/                     # 各游戏专属脚本
│       ├── alphabetical_sorting/
│       ├── wordle/
│       └── word_puzzle/
├── logic/                         # 逻辑推理类 benchmark
│   └── zebralogic/
├── data/                          # 数据集准备脚本
├── setup/                         # 环境部署脚本
├── db/                            # 数据库工具
├── tracing/                       # Phoenix 链路追踪
├── analysis/                      # 工具使用分析
├── experiments/                   # 实验结果分析（ZebraLogic 相关）
├── error_analysis/                # 错误分析（ZebraLogic 相关）
└── archive/                       # 已废弃脚本（仅供参考）
```

---

## 核心入口脚本

### `run_eval.py` — 评估入口

对指定 benchmark 执行完整评估流程（preprocess → rollout → judge → stat）。

```bash
# 运行评估（config_name 对应 configs/eval/ 下的文件路径）
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_baseline_eval
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_with_skills_eval
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_practice_eval
uv run python scripts/run_eval.py --config_name livecodebench/lcb_baseline_eval
uv run python scripts/run_eval.py --config_name logic/zebralogic_test_eval
```

### `run_training_free_GRPO.py` — 训练入口

运行 Training-Free GRPO 流程，自动生成分层经验（L0/L1/L2）并输出 practice agent YAML。

```bash
# 运行训练（config_name 对应 configs/practice/ 下的文件路径）
uv run python scripts/run_training_free_GRPO.py --config_name skillsbench/skillsbench_practice
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice
```

### `regen_practice_agent_yaml.py` — 重新生成 practice agent YAML

从已有的 JSON 经验文件重新生成 agent YAML，无需重跑训练。当注入格式（三区注入策略）更新时使用。

```bash
# 默认从 skillsbench_practice.json 重新生成 skillsbench_practice_agent.yaml
uv run python scripts/regen_practice_agent_yaml.py

# 指定经验文件和输出路径
uv run python scripts/regen_practice_agent_yaml.py \
  --experiences workspace/hierarchical_experiences/skillsbench_practice.json \
  --output configs/agents/practice/skillsbench_practice_agent.yaml
```

---

## `utils/` — 通用工具脚本

### 结果查看

#### `view_results.py` — 通用评估结果查看

```bash
# 查看单个实验摘要
uv run python scripts/utils/view_results.py -e skillsbench_baseline_eval

# 同时查看多个实验
uv run python scripts/utils/view_results.py -e exp1 exp2 exp3

# 对比两个实验（baseline vs 训练后），显示 improved/regressed/unchanged 题数
uv run python scripts/utils/view_results.py -e skillsbench_baseline_eval skillsbench_practice_eval --compare

# 对比时显示 Pass@K 详情和变化题目列表
uv run python scripts/utils/view_results.py -e exp1 exp2 --compare --detailed

# 查看论文实验结果（AIME 2024/2025，hardcoded 对比）
uv run python scripts/utils/view_results.py --paper

# 显示每道题的详细输出（前5个模型答案）
uv run python scripts/utils/view_results.py -e exp_id --details

# 只看失败 / 只看正确的题目
uv run python scripts/utils/view_results.py -e exp_id --details --failed
uv run python scripts/utils/view_results.py -e exp_id --details --correct

# 限制显示题目数
uv run python scripts/utils/view_results.py -e exp_id --details --limit 20

# 列出数据库中所有实验
uv run python scripts/utils/view_results.py --list

# 导出结果为 JSON
uv run python scripts/utils/view_results.py -e exp_id --export results.json

# 调整正确判定阈值（默认 0.5）
uv run python scripts/utils/view_results.py -e exp_id --threshold 1.0
```

#### `view_benchmark_results.py` — Benchmark 专属结果查看（SkillsBench / LiveCodeBench）

自动从 `exp_id` 中推断 benchmark 类型（含 `lcb` → LiveCodeBench，其余默认 SkillsBench）。

```bash
# SkillsBench: 查看单个实验（含 domain/difficulty 分类统计）
uv run python scripts/utils/view_benchmark_results.py -e skillsbench_baseline_eval

# SkillsBench: 对比多个实验
uv run python scripts/utils/view_benchmark_results.py \
  -e skillsbench_baseline_eval skillsbench_with_skills_eval skillsbench_practice_eval

# SkillsBench: 对比官方榜单排名
uv run python scripts/utils/view_benchmark_results.py -e skillsbench_practice_eval --leaderboard

# SkillsBench: 只显示失败的任务
uv run python scripts/utils/view_benchmark_results.py -e exp_id --failed

# LiveCodeBench: 查看单个实验（含 difficulty/platform 分类统计）
uv run python scripts/utils/view_benchmark_results.py -e lcb_baseline_eval

# LiveCodeBench: 对比两个实验
uv run python scripts/utils/view_benchmark_results.py -e lcb_baseline_eval lcb_practice_eval

# 显式指定 benchmark 类型
uv run python scripts/utils/view_benchmark_results.py -e my_exp --benchmark skillsbench
uv run python scripts/utils/view_benchmark_results.py -e my_exp --benchmark lcb

# 导出为 JSON
uv run python scripts/utils/view_benchmark_results.py -e exp_id --export results.json
```

### 数据库 / 数据集管理

#### `check_experiments.py` — 列出数据库中所有实验

```bash
uv run python scripts/utils/check_experiments.py
```

#### `view_datasets.py` — 列出所有数据集

```bash
uv run python scripts/utils/view_datasets.py
```

#### `view_dataset.py` — 查看某个数据集的内容

```bash
uv run python scripts/utils/view_dataset.py --dataset SkillsBench-Eval-77
uv run python scripts/utils/view_dataset.py --dataset SkillsBench-Eval-77 --limit 10
```

#### `clean_experiment_data.py` — 清理实验数据

```bash
# 删除指定实验的所有样本
uv run python scripts/utils/clean_experiment_data.py --exp_id skillsbench_baseline_eval

# 列出所有实验（不删除）
uv run python scripts/utils/clean_experiment_data.py --list

# 删除所有数据（谨慎使用）
uv run python scripts/utils/clean_experiment_data.py --all
```

#### `clean_and_recreate_datasets.py` — 重建 KORGym 数据集

修复 meta 字段问题后重新创建数据集，通常在数据集格式变更后使用。

```bash
uv run python scripts/utils/clean_and_recreate_datasets.py
```

---

## `korgym/` — KORGym 游戏环境

### 环境管理

```bash
# 检查 KORGym 环境是否就绪（依赖、Docker、服务器连通性）
uv run python scripts/korgym/check_korgym_env.py

# 启动 KORGym 游戏服务器
uv run python scripts/korgym/start_korgym_server.py
bash scripts/korgym/start_korgym_server.sh

# 预览游戏状态
uv run python scripts/korgym/preview_korgym_game.py --game word_puzzle

# 清理临时数据
uv run python scripts/korgym/cleanup_korgym_temp_data.py
```

### 数据集初始化

```bash
# 初始化训练数据集
uv run python scripts/korgym/init_korgym_dataset.py

# 初始化评估数据集
uv run python scripts/korgym/init_korgym_eval_dataset.py
```

### 评估与结果

```bash
# 运行 KORGym 评估
uv run python scripts/korgym/run_korgym_eval.py --game word_puzzle
bash scripts/korgym/run_korgym_full_pipeline.sh

# 查看评估结果（含得分分布）
uv run python scripts/korgym/view_korgym_results.py -e word_puzzle_baseline_eval

# 对比两个实验
uv run python scripts/korgym/compare_korgym_results.py \
  -b word_puzzle_baseline_eval -p word_puzzle_practice_eval

# 对比论文分数
uv run python scripts/korgym/compare_korgym_scores.py
```

### `games/` — 各游戏专属脚本

每个游戏子目录（`wordle/`、`word_puzzle/`、`alphabetical_sorting/`）包含：

| 文件类型 | 说明 |
|---------|------|
| `run_*.sh` | 完整实验运行脚本（含训练+评估） |
| `analyze_*.py` | 分析该游戏的评估结果 |
| `clean_*.sh / .py` | 清理该游戏的缓存或训练数据 |
| `diagnose_*.py` | 诊断评估流程问题 |
| `check_*.py` | 快速检查数据集或配置 |

---

## `logic/zebralogic/` — ZebraLogic 逻辑谜题

```bash
# 分析 ZebraLogic 数据集分布
uv run python scripts/logic/zebralogic/analyze_zebra_dataset.py

# 查看评估结果
uv run python scripts/logic/zebralogic/view_zebralogic_results.py --exp_id logic_zebralogic_test_eval

# 对比训练前后结果
uv run python scripts/logic/zebralogic/compare_zebralogic_results.py \
  --baseline logic_zebralogic_test_eval \
  --practice logic_practice_zebralogic_test_eval

# 诊断评估问题
uv run python scripts/logic/zebralogic/diagnose_zebralogic_eval.py

# 清理训练数据（去重、格式修复）
uv run python scripts/logic/zebralogic/clean_zebralogic_training_data.py
```

---

## `data/` — 数据集准备

所有 benchmark 数据集的下载、处理、上传脚本。

```bash
# 下载数据集
uv run python scripts/data/download_dataset.py --dataset zebralogic

# 准备各 benchmark 数据
uv run python scripts/data/prepare_skillsbench_data.py
uv run python scripts/data/prepare_livecodebench_data.py
uv run python scripts/data/prepare_korgym_data.py
uv run python scripts/data/prepare_zebralogic_samples.py

# 处理 Training-Free GRPO 训练数据
uv run python scripts/data/process_training_free_GRPO_data.py

# 上传数据集到 Hugging Face
uv run python scripts/data/upload_dataset.py --dataset SkillsBench-Eval-77
```

---

## `setup/` — 环境部署

### `deploy.sh` — Linux 一键部署

在 Linux 服务器上全新部署或更新项目。

```bash
# 全新部署（交互式填写 API Key）
bash scripts/setup/deploy.sh

# 非交互式部署（CI/CD 友好）
bash scripts/setup/deploy.sh --api-key sk-xxxx

# 指定模型和 API 地址（适配国产模型，如阿里云百炼）
bash scripts/setup/deploy.sh \
  --api-key sk-xxxx \
  --model qwen-plus \
  --base-url https://dashscope.aliyuncs.com/compatible-mode/v1

# 跳过 KORGym 安装（只跑 SkillsBench / LiveCodeBench，无需 Docker 游戏服务器）
bash scripts/setup/deploy.sh --api-key sk-xxxx --no-korgym

# 更新已部署的项目（git pull + uv sync）
bash scripts/setup/deploy.sh --update-only
```

**脚本完成后会自动打印下一步操作指引。**

---

## `db/` — 数据库工具

```bash
# 清除评估缓存（不删除样本数据）
uv run python scripts/db/clear_cache.py

# 导出数据库内容为文件
uv run python scripts/db/dump_db.py --output backup.json
```

---

## `tracing/` — Phoenix 链路追踪

调试 LLM 调用链路，需先启动 Phoenix 服务。

```bash
# 测试 Phoenix 连通性
uv run python scripts/tracing/test_phoenix.py

# 搜索特定 span
uv run python scripts/tracing/search_phoenix_span.py --query "experience_updater"
```

---

## `experiments/` 与 `error_analysis/` — 实验与错误分析

这两个目录包含 ZebraLogic 相关的深度分析脚本，主要用于论文实验复现和错误归因。通常不需要日常使用，按需查阅目录内各文件的 docstring。

---

## `archive/` — 已废弃脚本

存放因功能重复或已被更完整脚本替代而废弃的旧脚本，**不建议直接使用**，仅供历史参考。

---

## 快速参考：常用工作流

### 1. 运行评估 → 查看结果

```bash
# 评估
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_baseline_eval

# 查看
uv run python scripts/utils/view_benchmark_results.py -e skillsbench_baseline_eval --leaderboard
```

### 2. 运行训练 → 对比结果

```bash
# 训练（生成经验，输出 practice agent YAML）
uv run python scripts/run_training_free_GRPO.py --config_name skillsbench/skillsbench_practice

# 用 practice agent 评估
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_practice_eval

# 对比 baseline vs practice
uv run python scripts/utils/view_results.py \
  -e skillsbench_baseline_eval skillsbench_practice_eval --compare --detailed
```

### 3. 更新经验注入格式后重新生成 YAML

```bash
# 直接从 JSON 重新生成，不用重跑训练
uv run python scripts/regen_practice_agent_yaml.py
```

### 4. 清理旧实验数据

```bash
# 查看所有实验
uv run python scripts/utils/check_experiments.py

# 删除指定实验
uv run python scripts/utils/clean_experiment_data.py --exp_id old_exp_id
```
