# 项目架构

## 运行链路

```text
数据准备 -> 数据库数据集 -> rollout / verifier -> 经验提取与更新
                                      |                 |
                                      v                 v
                                  评估记录          经验 Agent YAML
                                      |                 |
                                      +------ 对比 ------+
```

TF-LLM 保留上游 Youtu-Agent 的 Agent、工具和评估框架，在其上增加 Training-Free GRPO、分层经验、benchmark 适配与可靠性控制。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `utu/agents/` | Agent 运行时与工具调用 |
| `utu/eval/` | 数据加载、processor、benchmark 和结果写入 |
| `utu/practice/` | rollout、经验提取、分层管理和 Agent 生成 |
| `configs/agents/` | Agent、模型和工具配置 |
| `configs/env/` | Provider 专用的 `.env` 示例，不保存真实密钥 |
| `configs/eval/` | 各数据集评估协议 |
| `configs/practice/` | 各数据集经验学习协议 |
| `docs/research/` | 尚未完成系统验证的研究提案与人工审计材料 |
| `scripts/data/` | 下载、转换和划分数据集 |
| `scripts/experiments/` | 需要额外调度约束的正式实验 |
| `scripts/korgym/` | KORGym 服务与结果工具 |
| `scripts/utils/` | 通用结果查看和辅助工具 |
| `scripts/archive/` | 带旧路径或旧协议假设的历史脚本，不用于新实验 |
| `workspace/` | 生成经验、审计结果及其他运行产物 |
| `tests/` | 关键协议和可靠性测试 |

## 两类配置

评估配置位于 `configs/eval/<dataset>/`，决定数据集、采样次数、并发、processor、benchmark 和 Agent。经验学习配置位于 `configs/practice/<dataset>/`，决定训练数据、rollout 数量、奖励与经验更新方式。

生成的经验 Agent 位于 `configs/agents/practice/`。公平对比时应复用 baseline 的评估配置，只通过 `--agent_config` 替换 Agent，避免两个 YAML 在采样、超时或 verifier 上发生漂移。

## 数据与产物

默认 SQLite 数据库为仓库根目录的 `test.db`，连接由 `UTU_DB_URL` 控制。它可能非常大，不应作为源码提交。经验文件通常写入 `workspace/hierarchical_experiences/`；模型输出与评估结果按 `exp_id` 写入数据库。

外部任务仓库，如 `SkillsBench-repo/`，应固定 commit 并保持独立，不把第三方历史合入主仓库。

## 可靠性边界

评估结果包含两类失败：

- 任务失败：Agent 完成了有效试次，但 verifier 判定不通过，或真正耗尽任务时间。
- 基础设施失败：API 连接、429/5xx、Docker/Harbor 异常、缺失 reward 产物等导致试次无效。

基础设施失败必须单独记录并补跑。SkillsBench 使用专用成对调度器执行这一约束；其他数据集也应在分析时进行相同审计。

## 扩展新数据集

通常需要新增数据准备脚本、processor、benchmark、Agent 配置、practice 配置与 eval 配置，并为关键解析和奖励路径添加测试。完成后为该数据集建立独立文档，不把专用命令堆回 README。
