# 研究提案

本目录保存尚未完成系统实验验证的研究设计，不作为当前运行协议或已证实结论。

- [Self-Evolving Agent](self_evolving_agent_design.md)：经验质量反馈、策略更新与多轮演化设想。
- [Self-Play](self_play_design.md)：在 rollout 全失败等弱监督场景中补充学习信号的设想。

两个方案均建立在当前 Training-Free GRPO 与分层经验实现之上。实施前应以[项目当前状态](../PROJECT_STATUS.md)和各[数据集手册](../datasets/index.md)为准；提案中的旧命令和预期数字仅用于保留设计背景。

`artifacts/skillsbench_practice_2_experience_inventory.txt` 是已有 SkillsBench 经验 Agent 的静态清单，用于人工审计，不是评估结果。
