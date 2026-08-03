# TF-LLM 文档

TF-LLM 研究如何在不更新基础模型权重的前提下，从任务轨迹中学习、组织并复用经验。当前仓库处于基线复现与经验闭环验证阶段。

## 从这里开始

- [项目当前状态](PROJECT_STATUS.md)：已经实现、已经验证和仍待验证的边界。
- [部署指南](DEPLOYMENT.md)：Linux、WSL2 与 macOS 的首次安装流程。
- [项目架构](PROJECT_ARCHITECTURE.md)：代码、配置、数据和产物如何组织。
- [数据集索引](datasets/index.md)：每个 benchmark 的独立运行手册。
- [脚本参考](https://github.com/lyf-workshop/TF-LLM/blob/slim-research-baseline/scripts/README.md)：命令行入口及职责。
- [故障排查](TROUBLESHOOTING.md)：API、数据库、Docker 与评估异常。

## 方法说明

- [Training-Free GRPO](concepts/training_free_grpo.md)
- [分层经验机制](concepts/hierarchical_experience.md)
- [经验选择与检索](concepts/experience_selection.md)
- [误差分析](concepts/error_analysis.md)

## 研究提案

- [研究提案索引](research/index.md)
- [自进化 Agent 设计](research/self_evolving_agent_design.md)
- [Self-Play 设计](research/self_play_design.md)

提案用于描述后续研究方向，不代表相应闭环已经完成或取得正向结果。
