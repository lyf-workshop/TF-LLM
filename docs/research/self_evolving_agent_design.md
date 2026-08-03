# Training-Free Self-Evolving Agent 设计方案

> 状态：研究提案，尚未完成系统实验验证。当前可运行流程和结论边界以[项目当前状态](../PROJECT_STATUS.md)及[数据集手册](../datasets/index.md)为准；本文中的旧命令与预期数字仅用于保留设计背景。

## 核心原则

**模型参数永远不变。进化发生在 agent 系统本身。**

```
传统方法：
  固定 Agent → 任务 → 结果
  （要提升就得训练模型）

Self-Evolving Agent：
  Agent_t → 任务 → 结果 → 进化 → Agent_{t+1} → 更难的任务 → 更好的结果 → ...
  （参数不动，agent 系统自主进化）
```

Agent 进化体现在 4 个维度，相互联动，形成闭环：

```
┌─────────────────────────────────────────────────────────┐
│                  Self-Evolving Agent                     │
│                                                         │
│  ① 经验进化          ② 策略进化                         │
│  L0/L1/L2 有质量评分  系统提示自动改写                   │
│  低质经验被淘汰        A/B 验证后提交                     │
│          ↑                 ↑                            │
│          └──────────┬──────┘                            │
│                     │ reward + trajectory                │
│          ┌──────────┴──────┐                            │
│          ↓                 ↓                            │
│  ③ 课程进化          ④ 工具模式进化                      │
│  任务难度自动调节      成功工具链被提炼复用                │
│  聚焦学习边界任务      形成工具策略库                     │
└─────────────────────────────────────────────────────────┘
```

---

## 四个进化维度

### 维度 1：经验进化（Experience Evolution）

**现状**：L0/L1/L2 只增不减，经验质量无差异对待。

**进化目标**：每条经验都有生命周期，好的经验越用越重要，无效经验自动淘汰。

**机制**：
- 每条 L0 经验记录"被注入 prompt 时的成功率"
- 若某条经验在注入后成功率持续低于平均水平 → 降权 → 最终淘汰
- 若某条经验注入后成功率显著高于平均 → 提升优先级，优先进入 L1 聚合
- L1/L2 经验同理：若其派生的任务成功率下降，触发重新聚合

```
经验生命周期：
  生成 → 积累使用次数 → 评分 → 晋升(提高rank) 或 降级(减少曝光) → 淘汰(移除)

评分公式：
  quality_score = 0.7 * success_rate_when_injected + 0.3 * recency_bonus
  （recency_bonus 随时间衰减，防止经验"过期"但仍占位置）
```

**数据结构扩展**（在 `hierarchical_experience_manager.py` 的经验字典中）：

```python
{
  "id": "L0_12",
  "content": "...",
  "step": 5,
  "quality": {
    "inject_count": 8,          # 被注入 prompt 的次数
    "success_count": 6,         # 注入后任务成功的次数
    "success_rate": 0.75,       # 注入成功率
    "rank": 2,                  # 当前排名（影响 L1 聚合优先级）
    "last_used_step": 23,       # 最近使用的 step
    "status": "active"          # active | deprecated | pruned
  }
}
```

---

### 维度 2：策略进化（Strategy Evolution）

**现状**：Agent 的 `instructions` 字段是写死的，经验只是追加在末尾。

**进化目标**：系统提示本身根据积累的经验自动改写，策略结构也会进化。

**机制**：
- 每 K 个 step，触发一次策略进化：
  1. **分析**：把当前 L2 元策略 + 高分 L1 模式 + 近期成功/失败案例喂给 LLM
  2. **生成**：让 LLM 提议一个改进版的 `instructions`（更紧凑、更有针对性）
  3. **验证**：在保留验证集（holdout）上用新旧 instructions 各跑一次
  4. **提交或回滚**：新版表现更好才替换，否则回滚并记录失败原因

```
策略版本管理：
  strategy_v0 (初始)
      ↓ [K steps 后触发进化]
  strategy_v1 (候选)
      ↓ [在 holdout set 验证]
  strategy_v1 胜出 → 正式替换 strategy_v0
  strategy_v1 失败 → 记录失败原因 → 继续用 strategy_v0
```

**保留 holdout 集**：从训练集中固定划分 10-15% 的任务作为策略验证集，不参与日常训练。

---

### 维度 3：课程进化（Curriculum Evolution）

**现状**：每个 epoch 从全部训练集随机采样，无难度感知。

**进化目标**：系统自动识别"学习边界"，把训练计算资源集中在最有价值的任务上。

**机制**：

```
任务状态（基于滑动窗口 pass_rate）：
  pass_rate > 0.7  → "已掌握(mastered)"：减少曝光，偶尔复习即可
  pass_rate < 0.1  → "暂时超出(too_hard)"：减少曝光，等整体能力提升后再尝试
  0.1 ≤ pass_rate ≤ 0.7 → "学习区(learning_zone)"：重点训练

采样策略（每个 batch）：
  60% 来自学习区任务
  20% 来自超出任务（持续挑战）
  20% 来自已掌握任务（防止遗忘）
```

**动态难度调节**：
- 如果学习区任务全部变为"已掌握" → 把部分"超出任务"重新纳入学习区
- 如果学习区任务长期无进展 → 分析共同失败原因，针对性生成反思经验（对接维度 1）

```python
class CurriculumEngine:
    def update_task_status(self, task_id, reward):
        """更新任务状态，基于最近5次的滑动平均"""
    
    def sample_batch(self, batch_size) -> list[str]:
        """按 60/20/20 策略采样任务 id"""
    
    def get_frontier_tasks(self) -> list[str]:
        """返回当前学习边界任务（供维度1的反思型经验提取优先处理）"""
    
    def get_progress_report(self) -> dict:
        """返回各状态任务数量，用于监控进化进度"""
```

---

### 维度 4：工具模式进化（Tool Pattern Evolution）

**现状**：agent 靠通用经验决定如何使用工具，无显式工具策略库。

**进化目标**：从成功 trajectory 中自动提炼可复用的工具调用链，形成工具策略库。

**机制**：
- 每次任务成功后，LLM 分析 trajectory 中的工具调用序列
- 识别关键工具模式，如：
  - `file → head → python3`（先识别文件类型，再采样，再处理）
  - `ls -la → cat → grep`（定位 → 查看 → 筛选）
  - `pip install → python → verify`（安装依赖 → 执行 → 验证）
- 提炼为结构化的工具链经验，标注领域标签（文件处理/数据分析/环境配置等）
- 注入 prompt 时，根据任务描述的关键词匹配相关工具模式

```
工具模式示例（注入 prompt 格式）：
  [ToolPattern][file-processing] 处理未知格式文件时：
    先用 file <input> 识别类型，再用 head -5 采样内容，
    确认格式后再写处理脚本。避免盲目运行导致错误。

  [ToolPattern][env-setup] 安装依赖前先检查已有环境：
    pip list | grep <package>，只安装缺失的包，
    安装后立即用 python -c "import <package>" 验证。
```

**与经验系统的关系**：工具模式作为特殊标记的 L0 经验（`tool_pattern=True`），参与 L1/L2 聚合但有独立的展示区域。

---

## 进化闭环

四个维度协同工作，形成完整的自进化闭环：

```
┌──────────────────────────────────────────────────────────────────┐
│                         进化闭环                                  │
│                                                                  │
│  任务输入                                                         │
│     ↓                                                            │
│  [课程引擎] 选择"学习边界"任务                                     │
│     ↓                                                            │
│  [Agent 执行] 使用当前 {策略 + 经验 + 工具模式} 生成 N 次 rollout   │
│     ↓                                                            │
│  [Reward] harbor verifier / LLM judge 给出 0~1 分                │
│     ↓                                                            │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                  四维进化信号提取                      │       │
│  │                                                      │       │
│  │  成功 rollout → [工具模式提取] → 工具策略库更新         │       │
│  │  失败 rollout → [反思经验生成] → L0 合成经验            │       │
│  │  任务 pass_rate → [课程引擎] 更新任务状态               │       │
│  │  经验注入后成功率 → [经验质量追踪] 更新 quality score   │       │
│  └──────────────────────────────────────────────────────┘       │
│     ↓                                                            │
│  [L0→L1→L2 聚合] + [经验淘汰] + [工具模式去重]                   │
│     ↓                                                            │
│  每 K steps: [策略进化] LLM 改写 instructions → holdout 验证      │
│     ↓                                                            │
│  Agent_{t+1} = {新策略 + 新经验 + 新工具模式} → 下一轮            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 实现方案

### 新增模块结构

```
utu/practice/self_evolving/
├── __init__.py
├── curriculum.py          # 维度3：课程引擎
├── strategy_evolver.py    # 维度2：策略进化
├── tool_pattern_library.py # 维度4：工具模式库
└── experience_quality.py  # 维度1：经验质量追踪
```

### 各模块核心接口

#### `curriculum.py`

```python
class CurriculumEngine:
    # 状态持久化到 SQLite（复用现有 DB）
    
    def update(self, task_id: str, reward: float, step: int) -> None:
        """每次 rollout 结束后调用，更新任务滑动 pass_rate"""
    
    def sample_batch(self, batch_size: int, all_task_ids: list[str]) -> list[str]:
        """按 60/20/20 策略采样，first-call 时随机初始化"""
    
    def get_frontier_tasks(self) -> list[str]:
        """返回学习区任务 id 列表"""
    
    def status_report(self) -> dict:
        """{"mastered": N, "learning_zone": N, "too_hard": N}"""
```

#### `strategy_evolver.py`

```python
class StrategyEvolver:
    
    def __init__(self, llm, holdout_task_ids: list[str], evolve_every_k_steps: int = 50):
        ...
    
    async def maybe_evolve(
        self,
        step: int,
        current_instructions: str,
        l2_experiences: list[dict],
        l1_experiences: list[dict],
        recent_failures: list[dict],
    ) -> str | None:
        """
        每 K steps 触发一次。返回新 instructions（已通过验证），
        或 None（未触发或验证失败）。
        """
    
    async def _propose_new_instructions(self, current, l2, l1, failures) -> str:
        """让 LLM 基于积累的经验改写系统提示"""
    
    async def _validate_on_holdout(self, old_instructions, new_instructions) -> bool:
        """在 holdout 集上对比新旧 instructions，返回新版是否更好"""
```

#### `tool_pattern_library.py`

```python
class ToolPatternLibrary:
    
    async def extract_from_trajectory(
        self,
        task_instruction: str,
        trajectory: str,   # JSON string from harbor
        reward: float,
    ) -> list[str]:
        """
        仅对成功 rollout (reward >= 0.5) 调用。
        让 LLM 从 trajectory 中提炼关键工具链模式。
        返回格式：["[ToolPattern][domain] 描述...", ...]
        """
    
    def get_relevant_patterns(self, task_instruction: str, top_k: int = 3) -> list[str]:
        """
        基于 BM25 或关键词匹配，从库中检索与当前任务最相关的工具模式。
        供注入 agent prompt 使用。
        """
    
    def deduplicate(self) -> int:
        """移除相似度 > 0.8 的重复工具模式，返回移除数量"""
```

#### `experience_quality.py`

```python
class ExperienceQualityTracker:
    
    def record_injection(
        self,
        experience_ids: list[str],   # 本次注入 prompt 的经验 id
        task_id: str,
        step: int,
    ) -> None:
        """记录哪些经验被注入了（在 rollout 前调用）"""
    
    def record_outcome(
        self,
        task_id: str,
        reward: float,
        step: int,
    ) -> None:
        """记录任务结果（在 rollout 后调用），更新相关经验的 success_rate"""
    
    def get_scores(self, experience_ids: list[str]) -> dict[str, float]:
        """返回 {exp_id: quality_score} 字典"""
    
    def get_deprecated_ids(self, threshold: float = 0.2) -> list[str]:
        """
        返回需要淘汰的经验 id：
        inject_count >= 5 且 success_rate < threshold
        """
    
    def update_l0_ranks(self, l0_experiences: list[dict]) -> list[dict]:
        """根据 quality_score 给 L0 经验重新排序，影响 L1 聚合优先级"""
```

---

### 现有文件修改点

#### `training_free_grpo.py`（主循环集成）

```python
# build() 中初始化所有进化模块
self.curriculum_engine = CurriculumEngine(config=...) if sp.enabled else None
self.strategy_evolver = StrategyEvolver(llm=..., holdout_ids=...) if sp.enabled else None
self.tool_pattern_library = ToolPatternLibrary(llm=...) if sp.enabled else None
self.experience_quality = ExperienceQualityTracker() if sp.enabled else None

# 主循环中的集成点：
# [1] batch 采样前：用课程引擎决定本次任务
batch_task_ids = self.curriculum_engine.sample_batch(batch_size, all_task_ids)

# [2] rollout 前：记录经验注入情况
injected_ids = self._get_current_experience_ids()
self.experience_quality.record_injection(injected_ids, task_id, step)

# [3] rollout 后：更新课程状态 + 提取工具模式 + 记录质量
for sample in rollouts:
    self.curriculum_engine.update(task_id, sample.reward, step)
    self.experience_quality.record_outcome(task_id, sample.reward, step)
    if sample.reward >= 0.5:  # 成功才提取工具模式
        patterns = await self.tool_pattern_library.extract_from_trajectory(
            sample.raw_question, sample.trajectories, sample.reward
        )
        # 工具模式作为特殊 L0 注入经验管理器

# [4] 每 K steps：经验质量清洗 + 策略进化
if step % self.config.practice.self_evolving.prune_every_k_steps == 0:
    deprecated = self.experience_quality.get_deprecated_ids()
    self.hierarchical_experience_manager.prune_experiences(deprecated)

new_instructions = await self.strategy_evolver.maybe_evolve(
    step, current_instructions, l2_exps, l1_exps, recent_failures
)
if new_instructions:
    self._update_agent_instructions(new_instructions)
```

#### `hierarchical_experience_manager.py`

新增两个方法：

```python
def prune_experiences(self, deprecated_ids: list[str]) -> int:
    """移除指定 id 的 L0 经验，返回移除数量"""

def get_quality_ranked_l0(self, quality_tracker) -> list[dict]:
    """按 quality_score 排序返回 L0，供 L1 聚合优先使用高质量经验"""
```

#### `experience_updater.py`

修改 `run()` 返回值，暴露 per-task summaries（供策略进化模块使用）：

```python
return new_experiences, problem_to_summarized_rollouts  # 原只返回 new_experiences
```

---

### 配置 Schema

```python
class SelfEvolvingConfig(ConfigBaseModel):
    enabled: bool = False

    # 维度 1：经验进化
    experience_prune_threshold: float = 0.2
    """注入成功率低于此值（且使用次数 >= 5）的经验被淘汰"""
    prune_every_k_steps: int = 30
    """每隔多少 step 执行一次经验淘汰"""
    experience_min_inject_count: int = 5
    """至少被注入几次才参与质量评估"""

    # 维度 2：策略进化
    strategy_evolve_enabled: bool = True
    strategy_evolve_every_k_steps: int = 50
    """每隔多少 step 尝试一次策略进化"""
    strategy_holdout_ratio: float = 0.15
    """训练集中保留多少比例作为策略验证集"""
    strategy_min_improvement: float = 0.03
    """新策略需比旧策略 win_rate 高出多少才提交"""

    # 维度 3：课程进化
    curriculum_enabled: bool = True
    curriculum_mastered_threshold: float = 0.7
    """pass_rate 超过此值认为任务已掌握"""
    curriculum_too_hard_threshold: float = 0.1
    """pass_rate 低于此值认为任务暂时超出能力"""
    curriculum_window_size: int = 5
    """计算 pass_rate 的滑动窗口大小"""
    curriculum_learning_zone_ratio: float = 0.6
    """每 batch 中学习区任务的比例"""

    # 维度 4：工具模式进化
    tool_pattern_enabled: bool = True
    tool_pattern_max_library_size: int = 50
    """工具模式库的最大容量"""
    tool_pattern_top_k_inject: int = 3
    """每次注入 prompt 时最多添加几条工具模式"""
    tool_pattern_similarity_threshold: float = 0.8
    """去重阈值"""
```

---

### 新配置文件

`configs/practice/skillsbench/skillsbench_self_evolving.yaml`

```yaml
# @package _global_
defaults:
  - skillsbench_practice
  - _self_

exp_id: "skillsbench_self_evolving"

practice:
  epochs: 10                  # 进化需要更多轮次
  batch_size: 10
  grpo_n: 5

  self_evolving:
    enabled: true

    # 经验进化
    experience_prune_threshold: 0.2
    prune_every_k_steps: 30
    experience_min_inject_count: 5

    # 策略进化
    strategy_evolve_enabled: true
    strategy_evolve_every_k_steps: 50
    strategy_holdout_ratio: 0.15
    strategy_min_improvement: 0.03

    # 课程进化
    curriculum_enabled: true
    curriculum_mastered_threshold: 0.7
    curriculum_too_hard_threshold: 0.1
    curriculum_window_size: 5
    curriculum_learning_zone_ratio: 0.6

    # 工具模式进化
    tool_pattern_enabled: true
    tool_pattern_max_library_size: 50
    tool_pattern_top_k_inject: 3

skillsbench:
  enabled: true
  inject_curated_skills: false
  task_timeout_sec: 900
  max_agent_iterations: 30
```

---

## Agent Prompt 的进化形态

随着训练进行，agent 的 system prompt 会从这样：

```
You are an expert software engineer...
[基础指令]
```

逐步进化成这样：

```
You are an expert software engineer...
[策略v3：根据实际失败模式改写的指令，更简洁、更有针对性]

--- Evolved Strategies ---
[L2-Meta] 在执行任何输出生成任务前，先建立 schema：...
[L2-Meta] 遇到依赖问题时，优先检查已安装版本再安装新版：...

--- Learned Patterns ---
[L1-Pattern] 数据处理任务的通用流程：inspect → sample → transform → verify
[L1-Pattern] 文件格式转换的关键步骤：...

--- Tool Chains ---
[ToolPattern][file-processing] 未知格式文件处理链：file → head → python3
[ToolPattern][env-setup] 环境配置验证链：pip list → pip install → python -c

--- Recent Cases ---
[L0-Case] PDF 表格提取：使用 pdfplumber 而非 PyPDF2，前者保留表格结构...
[L0-Case] Docker 环境检查：先 docker ps -a 确认容器状态再操作...
```

---

## 实现优先级

按照依赖关系和价值排序：

| 优先级 | 模块 | 价值 | 难度 |
|-------|------|------|------|
| P0 | Bug Fix（skillsbench 配置透传） | 阻塞整个流程 | 低 |
| P1 | 课程进化（Curriculum） | 直接影响训练效率 | 低 |
| P2 | 工具模式进化（Tool Patterns） | 直接提升任务成功率 | 中 |
| P3 | 经验质量追踪（Experience Quality） | 防止经验库退化 | 中 |
| P4 | 策略进化（Strategy Evolution） | 最高价值，也最复杂 | 高 |

建议按 P0→P1→P2→P3→P4 顺序实现，每个模块独立可测试。

---

## 改动文件汇总

| 文件 | 改动类型 | 主要内容 |
|------|---------|---------|
| `utu/practice/training_free_grpo.py` | 修改 | Bug Fix + 集成四个进化模块 |
| `utu/practice/experience_updater.py` | 修改 | 返回 step_summaries |
| `utu/practice/hierarchical_experience_manager.py` | 修改 | 新增 prune / quality_ranked_l0 方法 |
| `utu/config/practice_config.py` | 修改 | 新增 SelfEvolvingConfig |
| `utu/practice/self_evolving/__init__.py` | **新建** | 模块入口 |
| `utu/practice/self_evolving/curriculum.py` | **新建** | CurriculumEngine |
| `utu/practice/self_evolving/strategy_evolver.py` | **新建** | StrategyEvolver |
| `utu/practice/self_evolving/tool_pattern_library.py` | **新建** | ToolPatternLibrary |
| `utu/practice/self_evolving/experience_quality.py` | **新建** | ExperienceQualityTracker |
| `configs/practice/skillsbench/skillsbench_self_evolving.yaml` | **新建** | 配置文件 |

---

## 验证方法

```bash
# 运行自进化训练
uv run python scripts/run_training_free_GRPO.py \
    --config_name skillsbench/skillsbench_self_evolving

# 监控进化进度（每 epoch 输出）
# 预期日志：
#   [Curriculum] learning_zone: 28, mastered: 8, too_hard: 4
#   [ToolPattern] Extracted 2 new patterns, library size: 15
#   [ExperienceQuality] Pruned 3 low-quality L0 experiences
#   [StrategyEvolver] Step 50: New strategy validated (+4.2%), committed

# 查看工具模式库
cat workspace/self_evolving/tool_patterns.json

# 查看策略进化历史
cat workspace/self_evolving/strategy_history.json

# 对比基线 vs 自进化结果
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_baseline_eval
uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_practice_eval
```
