# Training-Free GRPO

## 核心思想

Training-Free GRPO 借用 GRPO 的“同一问题生成一组候选并比较奖励”结构，但不做梯度更新，也不修改基础模型权重。系统从候选轨迹的成功与失败差异中提取自然语言经验，再把经验写入 Agent 提示词。

```text
问题 -> N 条 rollout -> verifier 奖励 -> 组内对比
                                      -> 经验候选
                                      -> 合并经验池
                                      -> 生成经验 Agent
```

仓库沿用 `training`、`practice` 等工程命名，但这里的“训练”指经验学习，不是参数训练。

## 实现入口

- `scripts/run_training_free_GRPO.py`：命令行入口。
- `utu/practice/training_free_grpo.py`：主流程。
- `utu/practice/rollout_manager.py`：候选轨迹生成。
- `utu/practice/experience_updater.py`：从奖励差异提取并更新经验。
- `configs/practice/`：数据、rollout 数量、温度与经验目标。

## 与普通评估的区别

经验学习阶段通常使用非零 temperature 和多条 rollout，以形成可比较的成功/失败轨迹。评估阶段应使用固定协议，并比较无经验 Agent 与经验 Agent。学习阶段的奖励不能直接当作泛化结果。

## 有效性条件

经验方法只有在以下条件同时满足时才可认为有效：

1. 训练任务与正式测试任务隔离。
2. baseline 与经验组除经验外保持一致。
3. 基础设施错误没有被计入任务失败。
4. 增益在多次运行或足够多任务上稳定出现。
5. 对退化任务进行了逐例分析。

当前仓库已经实现流程，但尚未证明经验在所有数据集上稳定优于 baseline。
