# KORGym 适配修改详细说明 🔧

## 📋 概述

为了将 **Training-Free GRPO** 系统适配到 **KORGym** 游戏平台，我们进行了以下核心修改：

---

## 🆕 一、新增核心模块

### 1. KORGym 游戏适配器

**文件**: `utu/practice/korgym_adapter.py`

**功能**：
- ✅ **游戏分类器** (`KORGymGameClassifier`)
  - 按 6 个推理维度分类游戏（math_logic, control_interaction, puzzle, spatial_geometric, strategic, multimodal）
  - 识别游戏类型（单轮 single / 多轮 multiple）
  - 检测多模态游戏

- ✅ **游戏适配器** (`KORGymAdapter`)
  - 与 KORGym 游戏服务器通信（FastAPI 接口）
  - 生成游戏实例（`generate_game_instance`）
  - 获取游戏提示（`get_game_prompt`）
  - 验证动作（`verify_action`）
  - 执行单轮游戏（`play_single_round`）
  - 执行多轮游戏（`play_multiple_rounds`）
  - 自动选择游戏类型（`play_game`）
  - 从 Agent 响应中提取动作（`_extract_action`）

**关键代码**：
```python
class KORGymAdapter:
    def __init__(self, game_name, game_host="localhost", game_port=8775, level=4):
        # 初始化适配器，自动分类游戏
        self.game_category = KORGymGameClassifier.get_category(game_name)
        self.game_type = KORGymGameClassifier.get_game_type(game_name)
    
    async def play_game(self, agent, seed: int) -> Dict:
        # 自动选择单轮或多轮游戏
        if self.game_type == 'single':
            return await self.play_single_round(agent, seed)
        else:
            return await self.play_multiple_rounds(agent, seed)
```

---

### 2. KORGym 经验提取器

**文件**: `utu/practice/korgym_experience_extractor.py`

**功能**：
- ✅ 从游戏轨迹提取 L0 经验
- ✅ 支持单轮和多轮游戏的不同提取策略
- ✅ 批量并发提取（`extract_batch_l0`）
- ✅ LLM 驱动的经验生成
- ✅ Fallback 机制（LLM 失败时生成简单经验）

**关键特性**：
- 使用 Jinja2 模板生成提取提示
- 针对单轮和多轮游戏使用不同的提示模板
- 支持并发提取以提高效率

**关键代码**：
```python
class KORGymExperienceExtractor:
    async def extract_l0_from_round(
        self, round_result: Dict, game_category: str, game_type: str
    ) -> str:
        # 根据游戏类型选择不同的上下文
        if game_type == 'single':
            # 单轮：使用 prompt, action, response
        else:
            # 多轮：使用完整轨迹 trajectory
```

---

## 🔧 二、配置系统修改

### 1. 新增 KORGymConfig 配置类

**文件**: `utu/config/eval_config.py`

**修改**：
```python
class KORGymConfig(ConfigBaseModel):
    """KORGym game configuration"""
    enabled: bool = False
    game_name: str = "3-2048"
    game_host: str = "localhost"
    game_port: int = 8775
    level: int = 3
    num_seeds: int = 20
    max_rounds: int = 50
```

**集成到 EvalConfig**：
```python
class EvalConfig(ConfigBaseModel):
    # ... 其他配置 ...
    korgym: KORGymConfig = Field(default_factory=KORGymConfig)
```

---

### 2. 集成到 TrainingFreeGRPOConfig

**文件**: `utu/config/practice_config.py`

**修改**：
```python
class TrainingFreeGRPOConfig(ConfigBaseModel):
    # ... 其他配置 ...
    korgym: KORGymConfig = Field(default_factory=KORGymConfig)
    """KORGym game evaluation configuration"""
```

---

## 🔄 三、GRPO 主流程修改

### 1. TrainingFreeGRPO.build() 方法

**文件**: `utu/practice/training_free_grpo.py`

**修改位置**: 第 89-95 行，第 109-111 行

**修改内容**：
```python
async def build(self):
    # ... 原有代码 ...
    
    # Pass KORGym configuration to practice eval config
    if hasattr(self.config, 'korgym'):
        if self.config.korgym:
            practice_eval_config.korgym = self.config.korgym
            logger.info(f"✓ Passed korgym config to practice_eval_config")
    
    # ... 创建 practice_rollout_manager ...
    
    # Pass KORGym configuration to eval eval config
    if hasattr(self.config, 'korgym') and self.config.korgym:
        eval_eval_config.korgym = self.config.korgym
```

**作用**：将 KORGym 配置传递给 RolloutManager，使其能够识别并使用 KORGym 游戏

---

### 2. RolloutManager 支持 KORGym

**文件**: `utu/practice/rollout_manager.py`

**修改**：虽然 RolloutManager 本身没有直接修改，但通过配置传递，它能够：
- 检测 `config.korgym.enabled`
- 使用 KORGymAdapter 执行游戏
- 使用 KORGymExperienceExtractor 提取经验

---

## 📊 四、数据处理修改

### 1. 数据管理器支持 KORGym

**文件**: `utu/practice/data_manager.py`

**修改**：`TrainingFreeGRPODataManager` 需要支持：
- 检测 KORGym 配置
- 生成游戏实例（通过 seed）
- 不依赖传统数据集，而是动态生成游戏

**关键变化**：
- 传统方式：从数据库加载预定义问题
- KORGym 方式：通过 seed 动态生成游戏实例

---

## 🎮 五、评估系统修改

### 1. 新增 KORGym 评估处理器

**文件**: `utu/eval/processer/korgym_processor.py` (新增)

**功能**：
- ✅ 专门处理 KORGym 游戏的评估流程
- ✅ 继承自 `BaseMatchProcesser`
- ✅ 在 `preprocess_one()` 中生成游戏实例
- ✅ 在 `judge_one()` 中验证动作并计算分数

**关键实现**：
```python
class KORGymProcesser(BaseMatchProcesser):
    def __init__(self, config: EvalConfig):
        # 检测并初始化 KORGym 适配器
        if config.korgym and config.korgym.enabled:
            self.adapter = KORGymAdapter(...)
    
    def preprocess_one(self, sample: EvaluationSample):
        # 1. 从 meta 获取 seed
        # 2. 生成游戏实例
        # 3. 获取游戏提示
        # 4. 设置 augmented_question
    
    async def judge_one(self, sample: EvaluationSample):
        # 1. 重新生成游戏（用 seed）
        # 2. 提取动作
        # 3. 验证动作
        # 4. 计算分数和成功状态
```

### 2. 处理器工厂注册

**文件**: `utu/eval/processer/__init__.py`

**修改**：
```python
from .korgym_processor import KORGymProcesser as KORGymProcesser

# 自动注册到 ProcesserFactory
# 可以通过 eval_method="KORGym" 使用
```

**使用方式**：
```yaml
evaluation:
  eval_method: "KORGym"  # 使用 KORGym 处理器
  korgym:
    enabled: true
    game_name: "8-word_puzzle"
```

---

## 🛠️ 六、辅助脚本和工具

### 1. 游戏服务器启动脚本

**文件**: `scripts/start_korgym_server.py`

**功能**：
- 自动启动 KORGym 游戏服务器
- 支持指定游戏名称、端口、难度级别
- 健康检查

---

### 2. 测试脚本

**文件**: `scripts/test_korgym_adapter.py`

**功能**：
- 测试 KORGym 适配器
- 验证游戏执行流程
- 验证经验提取

---

### 3. 评估脚本

**文件**: `scripts/run_korgym_eval.py`

**功能**：
- 专门用于 KORGym 游戏的评估
- 与传统的 `run_eval.py` 不同，不依赖数据库中的预定义问题
- 实时启动游戏服务器并执行评估

---

## 📝 七、配置文件示例

### KORGym 训练配置

**文件**: `configs/practice/word_puzzle_hierarchical_experiment.yaml`

```yaml
exp_id: word_puzzle_hierarchical_exp

# KORGym 配置
korgym:
  enabled: true
  game_name: "8-word_puzzle"
  game_host: "localhost"
  game_port: 8775
  level: 4
  num_seeds: 30
  max_rounds: 100

# 数据配置（KORGym 模式下，dataset 可能为空或用于其他目的）
data:
  practice_dataset_name: ""  # KORGym 不使用传统数据集

# 分层学习配置
hierarchical_learning:
  enabled: true
  l1_aggregation_threshold: 5
  l2_aggregation_threshold: 3
```

---

## 🔄 八、工作流程变化

### 传统 GRPO 流程

```
1. 从数据库加载问题
2. 为每个问题生成 N 个 rollouts
3. 验证答案
4. 提取经验
```

### KORGym GRPO 流程

```
1. 通过 seed 生成游戏实例（不依赖数据库）
2. Agent 与游戏服务器交互（多轮可能）
3. 收集游戏轨迹和结果
4. 从轨迹提取 L0 经验
5. 聚合 L1/L2 经验
```

---

## 🎯 九、关键设计决策

### 1. 游戏分类系统

**为什么**：KORGym 有 50+ 种游戏，需要按推理维度分类以便：
- 按游戏类型聚合 L1 经验
- 跨游戏类型生成 L2 元策略
- 选择合适的经验应用到新游戏

### 2. 单轮 vs 多轮游戏支持

**为什么**：不同游戏有不同的交互模式：
- **单轮游戏**（如 word_puzzle）：一次回答，直接验证
- **多轮游戏**（如 2048）：多轮交互，状态持续更新

需要不同的处理逻辑。

### 3. 动作提取机制

**为什么**：Agent 的输出是自然语言，需要提取结构化动作：
- 使用正则表达式提取 "Answer:" 后的内容
- 处理 LaTeX 格式（`\boxed{}` 等）
- 标准化响应格式

### 4. 配置传递机制

**为什么**：KORGym 配置需要在多个层级传递：
- `TrainingFreeGRPOConfig` → `EvalConfig` → `RolloutManager`
- 确保所有组件都能访问 KORGym 配置

---

## 📊 十、修改影响范围

### 核心模块（必须修改）

1. ✅ `utu/practice/training_free_grpo.py` - 主流程
2. ✅ `utu/config/practice_config.py` - 配置系统
3. ✅ `utu/config/eval_config.py` - 评估配置

### 新增模块（完全新增）

1. ✅ `utu/practice/korgym_adapter.py` - 游戏适配器
2. ✅ `utu/practice/korgym_experience_extractor.py` - 经验提取器

### 新增评估处理器（完全新增）

1. ✅ `utu/eval/processer/korgym_processor.py` - KORGym 评估处理器

### 可选修改（增强功能）

1. ⚠️ `utu/practice/data_manager.py` - 数据管理（可能需要支持动态生成）

### 辅助脚本（新增）

1. ✅ `scripts/start_korgym_server.py` - 服务器启动
2. ✅ `scripts/test_korgym_adapter.py` - 测试脚本
3. ✅ `scripts/run_korgym_eval.py` - 评估脚本

---

## 🔍 十一、代码示例对比

### 传统方式（ZebraLogic）

```python
# 从数据库加载问题
sample = EvaluationSample(
    dataset="ZebraLogic",
    raw_question="有5个房子...",
    correct_answer="..."
)

# Agent 回答
result = await agent.run(sample.raw_question)

# 验证答案
is_correct = verify_logic(result.final_output, sample.correct_answer)
```

### KORGym 方式

```python
# 生成游戏实例
adapter = KORGymAdapter(game_name="8-word_puzzle", level=4)
game_result = await adapter.play_game(agent, seed=42)

# 游戏结果包含：
# - prompt: 游戏提示
# - action: 提取的动作
# - score: 得分
# - success: 是否成功
# - trajectory: 完整轨迹（多轮游戏）

# 提取经验
extractor = KORGymExperienceExtractor(llm_config)
l0_experience = await extractor.extract_l0_from_round(
    game_result, 
    game_category="puzzle",
    game_type="single"
)
```

---

## ✅ 十二、总结

### 核心修改点

1. **新增适配器层**：`KORGymAdapter` 桥接游戏服务器和 GRPO 系统
2. **新增经验提取器**：`KORGymExperienceExtractor` 从游戏轨迹提取经验
3. **新增评估处理器**：`KORGymProcesser` 专门处理 KORGym 游戏的评估
4. **配置系统扩展**：添加 `KORGymConfig` 支持游戏配置
5. **主流程集成**：在 `TrainingFreeGRPO.build()` 中传递 KORGym 配置
6. **游戏分类系统**：支持 6 个推理维度和 50+ 种游戏

### 设计优势

1. **最小侵入**：通过配置传递，不破坏原有流程
2. **灵活扩展**：支持单轮和多轮游戏
3. **类型感知**：按游戏类型聚合经验，提升泛化能力
4. **向后兼容**：传统数据集方式仍然可用

### 使用方式

```bash
# 1. 启动游戏服务器
python scripts/start_korgym_server.py 8-word_puzzle

# 2. 运行 GRPO 训练（自动使用 KORGym）
uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_hierarchical_experiment
```

---

## 📚 相关文件

- `utu/practice/korgym_adapter.py` - 游戏适配器
- `utu/practice/korgym_experience_extractor.py` - 经验提取器
- `utu/practice/training_free_grpo.py` - GRPO 主流程
- `utu/config/practice_config.py` - 配置定义
- `KORGym集成指南.md` - 集成文档
- `KORGym分层经验学习适配方案.md` - 适配方案

