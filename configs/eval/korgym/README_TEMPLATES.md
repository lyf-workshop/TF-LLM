# KORGym评估配置模板使用指南 📚

## 📋 模板文件

本目录包含以下模板文件：

1. **`TEMPLATE_korgym_game_eval.yaml`** - 基线评估配置模板
2. **`TEMPLATE_korgym_game_practice_eval.yaml`** - 训练后评估配置模板

配套的其他模板：
- **`configs/practice/TEMPLATE_korgym_game_practice.yaml`** - 训练配置模板
- **`configs/agents/practice/TEMPLATE_korgym_game_agent.yaml`** - Agent配置模板

---

## 🚀 快速开始：创建新游戏的评估配置

### 步骤1: 创建Agent配置

```bash
cd /mnt/f/youtu-agent/configs/agents/practice

# 复制模板
cp TEMPLATE_korgym_game_agent.yaml my_game_agent.yaml

# 编辑文件，修改：
# - agent.name
# - agent.instructions（游戏策略）
# - model.model_settings.temperature
```

### 步骤2: 创建基线评估配置

```bash
cd /mnt/f/youtu-agent/configs/eval/korgym

# 复制模板
cp TEMPLATE_korgym_game_eval.yaml my_game_eval.yaml

# 编辑文件，修改：
# - defaults: 引用你的Agent配置
# - exp_id
# - data.dataset
# - korgym.game_name
# - korgym.game_port
# - korgym.level
# - korgym.max_rounds
```

### 步骤3: 创建训练配置

```bash
cd /mnt/f/youtu-agent/configs/practice

# 如果没有korgym子目录，创建它
mkdir -p korgym

# 复制模板
cp TEMPLATE_korgym_game_practice.yaml korgym/my_game_practice.yaml

# 编辑文件，修改：
# - defaults: 引用你的baseline_eval配置
# - exp_id
# - practice.agent_objective
# - practice.learning_objective
# - practice.hierarchical_learning.experience_save_path
# - practice.hierarchical_learning.agent_save_path
# - data.practice_dataset_name
# - korgym部分（与eval一致）
```

### 步骤4: 创建训练后评估配置

```bash
cd /mnt/f/youtu-agent/configs/eval/korgym

# 复制模板
cp TEMPLATE_korgym_game_practice_eval.yaml my_game_practice_eval.yaml

# 编辑文件，修改：
# - defaults: 引用训练生成的practice_agent配置
# - exp_id
# - data.dataset（与baseline_eval相同）
# - korgym部分（与baseline_eval完全一致）
```

---

## 📝 完整示例：添加新游戏 "42-my_game"

### 假设游戏信息
- 游戏ID: `42-my_game`
- 端口: `8780`
- 类型: 单轮
- 难度: level 3
- max_rounds: 1

### 创建的文件

#### 1. Agent配置: `configs/agents/practice/my_game_agent.yaml`

```yaml
# @package _global_
defaults:
  - /model/base@model
  - _self_

agent:
  name: my_game_agent
  instructions: |-
    You are an expert at playing My Game for KORGym.
    Your goal is to [describe goal].
    
    Strategy:
    1. [Step 1]
    2. [Step 2]
    
    Output Format:
    - Answer: YOUR_ANSWER

max_turns: 50

model:
  model_settings:
    temperature: 0.3
    top_p: 0.95
    extra_args:
      timeout: 3000
```

#### 2. 基线评估: `configs/eval/korgym/my_game_eval.yaml`

```yaml
# @package _global_
defaults:
  - /agents/practice/my_game_agent@agent
  - _self_

exp_id: "my_game_baseline_eval"

data:
  dataset: "KORGym-MyGame-Eval-50"
  type: "single"

concurrency: 32
pass_k: 1

verify_filename: "korgym.py"
verify_func_name: "verify_func"

korgym:
  enabled: true
  game_name: "42-my_game"
  game_host: "localhost"
  game_port: 8780
  level: 3
  max_rounds: 1
  timeout_per_game: 600
```

#### 3. 训练配置: `configs/practice/korgym/my_game_practice.yaml`

```yaml
# @package _global_
defaults:
  - /eval/korgym/my_game_eval@evaluation
  - _self_

exp_id: "my_game_practice"

practice:
  epochs: 2
  batch_size: 50
  grpo_n: 3
  rollout_concurrency: 4
  rollout_temperature: 0.7
  task_timeout: 600
  do_eval: false
  eval_strategy: "epoch"
  
  agent_objective: |
    input: My game state
    output: Valid action
  
  learning_objective: |
    Help the agent improve by extracting:
    - L0: Specific strategies
    - L1: General patterns
    - L2: Universal principles
  
  num_experiences_per_query: 1
  
  hierarchical_learning:
    enabled: true
    l1_aggregation_threshold: 5
    l2_aggregation_threshold: 3
    max_l0_per_game: 1
    max_l0_recent: 50
    include_l0_in_prompt: true
    experience_save_path: workspace/hierarchical_experiences/my_game_practice.json
    agent_save_path: configs/agents/practice/my_game_practice_agent.yaml

data:
  practice_dataset_name: "KORGym-MyGame-Train-100"

korgym:
  enabled: true
  game_name: "42-my_game"
  game_host: "localhost"
  game_port: 8780
  level: 3
  num_train_seeds: 100
  eval_seeds_start: 1
  eval_seeds_end: 50
  train_seeds_start: 51
  train_seeds_end: 150
  max_rounds: 1
```

#### 4. 训练后评估: `configs/eval/korgym/my_game_practice_eval.yaml`

```yaml
# @package _global_
defaults:
  - /agents/practice/my_game_practice_agent@agent
  - _self_

exp_id: "my_game_practice_eval"

data:
  dataset: "KORGym-MyGame-Eval-50"  # 与baseline相同
  type: "single"

concurrency: 32
pass_k: 1

verify_filename: "korgym.py"
verify_func_name: "verify_func"

korgym:
  enabled: true
  game_name: "42-my_game"
  game_host: "localhost"
  game_port: 8780
  level: 3
  max_rounds: 1
  timeout_per_game: 600
```

---

## 🎯 运行流程

```bash
# 1. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "42-my_game"

# 2. 基线评估
uv run python scripts/run_eval.py --config_name korgym/my_game_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/my_game_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/my_game_practice_eval

# 5. 查看对比
uv run python scripts/view_korgym_results.py --compare \
  my_game_baseline_eval \
  my_game_practice_eval
```

---

## ✅ 配置检查清单

创建配置前确认：

### 游戏信息
- [ ] 游戏ID（例如：`42-my_game`）
- [ ] 游戏端口（例如：`8780`）
- [ ] 游戏类型（单轮 or 多轮）
- [ ] Level含义（难度 or 其他参数）
- [ ] Max_rounds值（查看game_lib.py）

### 配置一致性
- [ ] 所有配置文件的 `game_name` 一致
- [ ] 所有配置文件的 `game_port` 一致
- [ ] 所有配置文件的 `level` 一致
- [ ] 所有配置文件的 `max_rounds` 一致
- [ ] 训练和评估使用相同的评估数据集

### 命名规范
- [ ] Agent: `{game}_agent.yaml`
- [ ] 基线评估: `{game}_eval.yaml`, exp_id: `{game}_baseline_eval`
- [ ] 训练配置: `{game}_practice.yaml`, exp_id: `{game}_practice`
- [ ] 训练后评估: `{game}_practice_eval.yaml`, exp_id: `{game}_practice_eval`
- [ ] 数据集: `KORGym-{GameName}-Eval-50`, `KORGym-{GameName}-Train-100`

---

## 🔧 常见问题

### Q1: 如何确定max_rounds？

```bash
# 查看游戏代码
grep -n "attempts\|max_attempts\|max_rounds" KORGym/game_lib/X-game/game_lib.py

# 例如Wordle:
# 113:        "attempts": 10,
# 所以 max_rounds: 10
```

### Q2: level参数是什么意思？

不同游戏有不同含义，查看 `generate()` 函数：
- Word Puzzle: 难度等级（1-5）
- Wordle: 单词长度（4-12）
- 2048: 网格大小（3-5）
- 其他: 查看具体game_lib.py

### Q3: 如何知道游戏是单轮还是多轮？

```python
from utu.practice.korgym_adapter import KORGymGameClassifier
game_type = KORGymGameClassifier.get_game_type("42-my_game")
print(f"Game type: {game_type}")  # 'single' or 'multiple'
```

### Q4: hierarchical_learning应该放在哪里？

✅ 正确位置：
```yaml
practice:
  epochs: 2
  ...
  hierarchical_learning:  # 在practice下
    enabled: true
```

❌ 错误位置：
```yaml
practice:
  epochs: 2
  ...

hierarchical_learning:  # 在顶层（无效！）
  enabled: true
```

---

## 📚 相关文档

- **完整命令**: `KORGYM_THREE_GAMES_COMMANDS.md`
- **评分指南**: `KORGYM_SCORING_GUIDE.md`
- **多轮游戏**: `MULTI_ROUND_GAME_EVAL_GUIDE.md`
- **Wordle指南**: `WORDLE_GAME_ANALYSIS.md`

---

**使用模板可以快速为新游戏创建完整的配置！** 🎉




















