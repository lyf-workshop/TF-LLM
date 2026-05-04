# 自博弈 Agent 学习系统设计方案

## 背景与问题

TF-LLM 现有的 Training-Free GRPO 通过对比同一任务的 N 次 rollout（BEST vs WORST）来提取经验，但存在两个关键盲区：

1. **全部失败时无信号**：当所有 N 个 rollout 都失败（reward=0），没有对比，系统直接跳过，这道任务不产生任何经验
2. **跨 Epoch 无学习**：每个 epoch 独立提取经验，不感知自己相比上一版本是进步还是退步

此外，还有一个**阻塞 SkillsBench 训练流程的关键 Bug**：`training_free_grpo.py` 中 `skillsbench` 配置没有透传给子配置，导致训练时 harbor 根本不启动。

本方案在现有 L0/L1/L2 三层架构上叠加**自博弈机制**，让模型通过批判自身历史行为产生额外学习信号，不破坏现有代码路径。

---

## 整体架构

### 现有流程

```
for epoch in epochs:
  for batch in batches:
    1. Rollout: 每道任务生成 N=5 个 rollout（同一 agent）
    2. Experience Extraction:
       - 按任务分组，找 BEST(reward=1) vs WORST(reward=0) rollout
       - LLM 对比"为什么 BEST 成功，WORST 失败" → L0 经验
       - L0 积累 → 聚合为 L1（模式）→ L2（元策略）
    3. 经验注入 prompt: [L2-Meta][L1-Pattern][L0-Case] 格式
```

### 新增自博弈流程

```
[每 batch]
rollout × N → experience_updater.run()
                  ↓ (new_experiences, step_summaries)  ← 新增第二返回值
              hierarchical_experience_manager.process_step_experiences()
                  ↓ L0→L1→L2 聚合（原有逻辑）
              _detect_all_fail_groups(rollouts)
                  ↓ 找出所有 rollout 均为 0 的任务
              self_play_reflector.reflect_on_failures()   ← 【机制1】LLM 推断成功路径
                  ↓ SyntheticExperience(source="reflection")
              hierarchical_experience_manager.add_synthetic_l0()

[每 epoch 结束]
record_epoch_results(epoch, step_summaries)      ← 存储本epoch每个任务的结果
cross_epoch_contrast(epoch)                       ← 【机制2】与上epoch对比
    ↓ 改进任务 → LLM 提取"为什么这次比上次好"
    ↓ 回归任务 → LLM 提取"WARNING: 这次比上次差在哪"
    ↓ _maybe_update_champion()                   ← win_rate 提升才更新 champion
hierarchical_experience_manager.add_synthetic_l0()
```

---

## 两个自博弈机制

### 机制 1：反思型自博弈（Reflective Self-Play）

**触发条件**：一个任务的所有 N 个 rollout 全部失败（reward=0）

**做法**：
- 现有系统：跳过，无法提取经验
- 自博弈：让 LLM 读取这些失败的 trajectory，推断"什么样的做法应该能成功"
- 生成合成的正向经验，标注为 `[Synthetic]`，注入 L0

**意义**：把"全失败"这个最难的情况也转化为学习信号，而不是丢失信息。

**示例 prompt**：
```
Task: <任务描述>

以下是所有失败的尝试轨迹：
[Failed Attempt 1] ...
[Failed Attempt 2] ...

基于这些失败，推断成功需要采取哪些具体行动？
输出一条可转移的经验：<SyntheticExperience>...</SyntheticExperience>
```

---

### 机制 2：跨 Epoch Champion-Challenger 对比

**触发条件**：每个 epoch 结束时（epoch ≥ 1）

**做法**：
- 保存每个 epoch 每道任务的 best/worst rollout summary
- 与上一个 epoch 的结果对比：
  - **进步任务**（本 epoch 成功，上 epoch 失败）→ LLM 提取"本 epoch 多了哪些经验使得成功了"
  - **回归任务**（本 epoch 失败，上 epoch 成功）→ LLM 提取 `WARNING:` 警告经验
- 记录 champion（历史最优 win_rate），只有本 epoch win_rate 提升超过阈值才更新

**意义**：让系统感知到自身的纵向进步/退步，而不只是每 batch 的横向对比。

---

## 实现步骤

### Step 1 — Bug Fix（最优先）

**文件**：`utu/practice/training_free_grpo.py`

在 `build()` 方法中，korgym 透传之后紧接着加（约第 95 行）：

```python
# 修复：透传 skillsbench 配置
if hasattr(self.config, 'skillsbench') and self.config.skillsbench and self.config.skillsbench.enabled:
    practice_eval_config.skillsbench = self.config.skillsbench
    logger.info(f"✓ Passed skillsbench config to practice_eval_config")
```

eval_rollout_manager 构建处（约第 111 行）同样补充：

```python
if hasattr(self.config, 'skillsbench') and self.config.skillsbench:
    eval_eval_config.skillsbench = self.config.skillsbench
```

---

### Step 2 — Config 扩展

**文件**：`utu/config/practice_config.py`

在 `HierarchicalLearningConfig` 之后新增：

```python
class SelfPlayConfig(ConfigBaseModel):
    enabled: bool = False
    """总开关，False 时不初始化 SelfPlayReflector"""

    reflect_on_failures: bool = True
    """机制1：全失败反思"""

    cross_epoch_contrast: bool = True
    """机制2：跨epoch对比"""

    champion_update_threshold: float = 0.02
    """win_rate 需提升至少 2% 才更新 champion"""

    synthetic_experience_weight: float = 0.5
    """合成经验在 L1 batch 中最多占 50%"""

    max_reflect_per_step: int = 5
    """每 step 最多对几个全失败任务做反思（防止早期大量失败时 LLM 调用爆炸）"""

    reflection_concurrency: int = 4
    """反思 LLM 调用的并发数"""
```

在 `PracticeArguments` 中（`hierarchical_learning` 字段后）添加：

```python
self_play: SelfPlayConfig = Field(default_factory=SelfPlayConfig)
```

**新文件**：`configs/practice/skillsbench/skillsbench_self_play.yaml`

```yaml
# @package _global_
defaults:
  - skillsbench_practice
  - _self_

exp_id: "skillsbench_self_play"

practice:
  epochs: 5
  self_play:
    enabled: true
    reflect_on_failures: true
    cross_epoch_contrast: true
    champion_update_threshold: 0.02
    synthetic_experience_weight: 0.5
    max_reflect_per_step: 5
    reflection_concurrency: 4

skillsbench:
  enabled: true
  inject_curated_skills: false
  task_timeout_sec: 900
  max_agent_iterations: 30
```

---

### Step 3 — 新文件 `utu/practice/self_play_reflector.py`

#### 数据结构

```python
@dataclass
class EpochTaskRecord:
    """某个 epoch 某道任务的 rollout 快照"""
    task_id: str
    epoch: int
    rewards: list[float]
    best_reward: float
    best_trajectory_summary: str
    worst_trajectory_summary: str

@dataclass
class SyntheticExperience:
    """自博弈生成的合成 L0 经验"""
    content: str          # 带 [Synthetic] 前缀
    source: str           # "reflection" | "cross_epoch_improvement" | "cross_epoch_regression"
    task_id: str
    epoch: int
    weight: float = 0.5
```

#### 核心类接口

```python
class SelfPlayReflector:

    def __init__(self, config, self_play_config, agent_objective, learning_objective):
        # 初始化 LLM client，存储 _epoch_records 和 _champion

    async def reflect_on_failures(
        self, task_instruction: str, failed_rollouts: list[dict], epoch: int
    ) -> list[SyntheticExperience]:
        """机制1：从全失败 rollout 推断成功路径，生成合成 L0"""

    def record_epoch_results(
        self, epoch: int, problem_to_summarized_rollouts: dict[str, list[dict]]
    ) -> None:
        """存储本 epoch 每道任务的 rollout 结果，供跨 epoch 对比使用"""

    async def cross_epoch_contrast(
        self, epoch: int, concurrency: int = 4
    ) -> list[SyntheticExperience]:
        """机制2：对比 epoch t 与 epoch t-1，提取进步/回归经验"""

    def _maybe_update_champion(self, epoch, win_rate, epoch_records) -> bool:
        """win_rate 提升超过阈值才更新 champion"""
```

#### LLM Prompt 模板

| 模板 | 用途 | 输出格式 |
|------|------|---------|
| `REFLECT_ON_FAILURES_SP/UP` | 从失败推断成功做法 | `<SyntheticExperience>...</SyntheticExperience>` |
| `CROSS_EPOCH_IMPROVEMENT_SP/UP` | 分析进步原因 | 1-2 句可转移经验 |
| `CROSS_EPOCH_REGRESSION_SP/UP` | 分析回归原因 | 以 `WARNING:` 开头的警告 |

---

### Step 4 — `hierarchical_experience_manager.py` 扩展

**新增两个方法**，不修改现有方法签名：

```python
def add_synthetic_l0(self, synthetic_experiences: list, step: int) -> int:
    """
    注入合成 L0，使用宽松去重阈值 0.65（真实 L0 是 0.72-0.80）
    每个合成经验标记 synthetic=True, weight=float
    返回实际添加数量
    """

def _is_too_similar_synthetic(self, content: str) -> bool:
    """检查近 100 条经验（含合成），阈值 0.65"""
```

**修改 `_try_generate_l1` 内 l0_batch 选取**（约 5 行改动）：

```python
# 原：l0_batch = recent_l0[:threshold]

# 改为：按 weight 控制合成经验占比
real_l0 = [e for e in recent_l0 if not e.get("synthetic", False)]
synth_l0 = [e for e in recent_l0 if e.get("synthetic", False)]
sp_weight = synth_l0[0].get("synthetic_weight", 0.5) if synth_l0 else 0.5
max_synth = max(1, int(threshold * sp_weight))
l0_batch = (real_l0[:threshold] + synth_l0[:min(max_synth, threshold - len(real_l0[:threshold]))])[:threshold]
```

---

### Step 5 — `experience_updater.py` 返回值扩展（1 行）

`run()` 方法末尾修改：

```python
# 原：return new_experiences
# 改：
return new_experiences, problem_to_summarized_rollouts
```

`problem_to_summarized_rollouts` 是 `_single_rollout_summary()` 的已有输出，无需新计算。

---

### Step 6 — `training_free_grpo.py` 集成

#### 6.1 初始化（在 `build()` 中）

```python
self.self_play_reflector = None
if self.config.practice.self_play.enabled:
    from .self_play_reflector import SelfPlayReflector
    self.self_play_reflector = SelfPlayReflector(
        config=self.config.evaluation.agent,
        self_play_config=self.config.practice.self_play,
        agent_objective=self.config.practice.agent_objective,
        learning_objective=self.config.practice.learning_objective,
    )
    logger.info("SelfPlayReflector initialized")
```

#### 6.2 接收 experience_updater 第二返回值

```python
new_experiences, step_summaries = await self.experience_updater.run(...)
```

#### 6.3 每 batch 后触发机制 1（在 process_step_experiences 之后）

```python
if self.self_play_reflector is not None:
    all_fail_groups = self._detect_all_fail_groups(rollouts)
    if all_fail_groups:
        sp_config = self.config.practice.self_play
        tasks_to_reflect = list(all_fail_groups.items())[:sp_config.max_reflect_per_step]
        reflect_results = await asyncio.gather(*[
            self.self_play_reflector.reflect_on_failures(instr, rollout_list, epoch)
            for instr, rollout_list in tasks_to_reflect
        ])
        all_synthetic = [exp for batch in reflect_results for exp in batch]
        if all_synthetic and self.hierarchical_experience_manager:
            self.hierarchical_experience_manager.add_synthetic_l0(all_synthetic, step)
```

#### 6.4 每 epoch 结束触发机制 2

```python
if self.self_play_reflector is not None and batch_idx == num_batches - 1 and epoch >= 1:
    self.self_play_reflector.record_epoch_results(epoch, step_summaries)
    cross_exps = await self.self_play_reflector.cross_epoch_contrast(epoch)
    if cross_exps and self.hierarchical_experience_manager:
        self.hierarchical_experience_manager.add_synthetic_l0(cross_exps, step)
```

#### 6.5 新增辅助方法

```python
def _detect_all_fail_groups(self, rollouts: list) -> dict[str, list]:
    """
    按 raw_question 分组，返回所有 rollout 均为 reward=0 的任务
    {task_instruction: [rollout_dict, ...]}
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rollouts:
        if r.raw_question:
            groups[r.raw_question].append({
                "raw_question": r.raw_question,
                "reward": float(r.reward or 0.0),
                "trajectory_summary": r.trajectories or "",
            })
    return {
        task: rollout_list
        for task, rollout_list in groups.items()
        if all(rv["reward"] <= 0.0 for rv in rollout_list)
    }
```

---

## 改动文件汇总

| 文件 | 改动类型 | 改动量 |
|------|---------|-------|
| `utu/practice/training_free_grpo.py` | 修改 | ~60 行（bug fix + 集成） |
| `utu/practice/hierarchical_experience_manager.py` | 修改 | ~40 行（新增 2 方法 + L1 选取） |
| `utu/practice/experience_updater.py` | 修改 | 1 行（返回值） |
| `utu/config/practice_config.py` | 修改 | ~25 行（新增 SelfPlayConfig） |
| `utu/practice/self_play_reflector.py` | **新文件** | ~280 行 |
| `configs/practice/skillsbench/skillsbench_self_play.yaml` | **新文件** | ~25 行 |

---

## 关键设计决策

### 为什么合成经验用 `[Synthetic]` 前缀？

利用现有 `_extract_scope_key` 的词法匹配逻辑，`[Synthetic]` 成为 scope 前缀，与真实经验自然隔离，无需修改 L1/L2 聚合路径。同时 `synthetic=True` 标记允许精确权重控制。

### 为什么合成经验去重阈值宽松（0.65 vs 0.80）？

合成经验是推断出来的，而非直接观测，本身就允许一定冗余。过严的去重会丢失有价值的合成信号。

### 为什么 `champion_update_threshold` 默认 0.02？

SkillsBench 的 0/1 稀疏奖励下，20 个任务里 1 个任务变化就带来 5% 的 win rate 波动。2% 阈值允许 2-3 个任务的随机波动不触发 champion 替换，同时不会过于保守。

### 为什么 `max_reflect_per_step` 限制为 5？

早期 epoch 大量任务全部失败是正常现象。不加限制会在信息最稀少时反而产生大量质量低的合成经验，带来噪声。随着 epoch 推进，all-fail 比率自然下降，限制也逐渐不再起作用。

---

## 验证方法

```bash
# Step 1: 验证 Bug Fix
uv run python scripts/run_training_free_GRPO.py --config_name skillsbench/skillsbench_practice
# 检查日志：应看到 "✓ Passed skillsbench config to practice_eval_config"
# 检查日志：应看到 harbor 实际启动

# Step 2: 验证机制 1（反思型自博弈）
uv run python scripts/run_training_free_GRPO.py --config_name skillsbench/skillsbench_self_play
# 检查日志（早期 epoch）：
#   "N all-fail tasks detected, triggering reflective self-play..."
#   "Added N synthetic L0 from reflection"

# Step 3: 验证机制 2（跨 epoch 对比）
# 检查日志（epoch >= 1）：
#   "Cross-epoch contrast epoch X→Y: N improvements, M regressions → K synthetic experiences"

# Step 4: 端到端验证
cat workspace/hierarchical_experiences/skillsbench_self_play.json | python -c "
import json, sys
data = json.load(sys.stdin)
synth = [e for e in data.get('L0', []) if '[Synthetic]' in e.get('content', '')]
print(f'Total L0: {len(data[\"L0\"])}, Synthetic: {len(synth)}')
"
# 预期：Synthetic 数量 > 0，说明自博弈机制正常工作
```

---

## 运行命令

```bash
# 完整自博弈训练流程

# 1. 准备数据
uv run python scripts/data/prepare_skillsbench_data.py --repo_path ./SkillsBench-repo

# 2. Baseline 评估（无经验）
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_baseline_eval

# 3. 自博弈训练（生成 L0/L1/L2 + 合成经验）
uv run python scripts/run_training_free_GRPO.py --config_name skillsbench/skillsbench_self_play

# 4. 带自博弈经验的评估
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_practice_eval

# 5. 对比结果
uv run python scripts/view_skillsbench_results.py skillsbench_baseline_eval skillsbench_practice_eval
```
