# 多轮交互游戏评估完整指南 🎮

## 📋 概述

本指南说明如何在youtu-agent框架中评估多轮交互游戏（如Wordle、2048、Minesweeper等）。

---

## ✅ 系统支持状态

### 已实现的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| **游戏分类** | ✅ | 自动识别single/multiple类型 |
| **多轮Rollout** | ✅ | BaseBenchmark自动调用adapter.play_game() |
| **完整交互** | ✅ | 支持最多max_rounds轮交互 |
| **Trajectory保存** | ✅ | 保存所有轮次的状态和动作 |
| **多轮Judge** | ✅ | KORGymProcesser识别并处理多轮结果 |
| **正确评分** | ✅ | 使用final_score，不重复验证 |
| **统计指标** | ✅ | 准确率、平均轮数等 |

---

## 🎮 支持的多轮游戏

根据 `KORGymGameClassifier`，以下游戏被识别为多轮游戏：

```python
'multiple': [
    '3-2048',                    # 2048游戏
    '10-minigrid',               # 网格导航
    '24-snake',                  # 贪吃蛇
    '25-Tetris',                 # 俄罗斯方块
    '26-TrustRovolution',        # 信任演化
    '27-NpointPlus',             # N点加法
    '30-Tower_of_Hanoi',         # 汉诺塔
    '31-ball_arrange',           # 球排列
    '33-wordle',                 # Wordle ⭐
    '36-CryptoWord',             # 密码词
    '37-SpiderSolitaire',        # 蜘蛛纸牌
    '38-minesweeper',            # 扫雷
    '39-Nullify',                # 归零游戏
    ...
]
```

---

## 🔄 多轮评估流程详解

### 阶段1: Preprocess

```python
# 生成初始游戏prompt
game_state = adapter.generate_game_instance(seed)
prompt = adapter.get_game_prompt(game_state)
sample.update(augmented_question=prompt, ...)
```

**输出**: 初始游戏状态的prompt

---

### 阶段2: Rollout（关键！）

```python
# 检测到多轮游戏
if self._should_use_korgym_multiround(sample):
    # 执行完整多轮交互
    game_result = await adapter.play_game(agent, seed)
    
    # game_result 包含：
    # - responses: 所有轮次的Agent响应
    # - trajectory: 所有轮次的游戏状态
    # - final_score: 最终得分（0或1）
    # - success: 是否成功
    # - rounds: 实际使用的轮数
```

**Wordle示例**:
```
Round 1: 
  prompt: "Wordle Game, Attempt: 1 of 10, Word length: 5"
  agent response: "Answer: arose"
  feedback: "a(yellow), r(gray), o(green), s(gray), e(yellow)"
  
Round 2:
  prompt: "Wordle Game, Attempt: 2 of 10, History: 1. arose (feedback...)"
  agent response: "Answer: phone"
  feedback: "p(green), h(green), o(green), n(green), e(green)"
  score: 1, is_end: True

Final result:
  rounds: 2
  final_score: 1
  success: True
```

---

### 阶段3: Judge

```python
# 识别多轮游戏结果
if adapter.game_type == 'multiple' and 'multiround_result' in meta:
    # 直接使用rollout阶段的结果
    score = multiround_result['final_score']
    success = multiround_result['success']
    rounds = multiround_result['rounds']
    
    data.update(
        correct=success,
        reward=score,
        judged_response=f"Multi-round game completed in {rounds} rounds. Score: {score}"
    )
```

**关键点**:
- ✅ 不重新执行游戏（避免重复）
- ✅ 直接读取rollout阶段的结果
- ✅ 正确设置correct和reward

---

### 阶段4: Statistics

```python
# 计算指标
accuracy = success_count / total_count
avg_score = sum(scores) / total_count
avg_rounds = sum(rounds_list) / success_count  # 只统计成功的
```

---

## 🚀 使用方法

### 方法1: 标准评估流程（推荐）

```bash
cd /mnt/f/youtu-agent

# 1. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 2. 运行评估（自动支持多轮）
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 3. 查看结果
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed
```

### 方法2: 小规模测试

```bash
# 测试2-3个样本，快速验证
uv run python scripts/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 3 \
  --verbose
```

### 方法3: 完整训练和评估

```bash
# 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 对比结果
uv run python scripts/view_korgym_results.py --game wordle
```

---

## 📊 配置要点

### 关键配置参数

```yaml
# configs/eval/korgym/wordle_eval.yaml
korgym:
  enabled: true
  game_name: "33-wordle"
  game_port: 8777
  level: 5              # 单词长度（4-12，推荐5）
  max_rounds: 10        # ✅ 必须与游戏代码一致
  timeout_per_game: 600
```

**重要**:
- `max_rounds` 必须与游戏代码中的 `attempts` 一致
- `level` 在Wordle中表示单词长度
- 对于其他多轮游戏，参数含义可能不同

---

## 🔍 验证多轮评估是否工作

### 检查日志

```bash
tail -100 logs/utu.log | grep -i "multi-round"

# 应该看到：
# INFO - Detected KORGym multi-round game: 33-wordle
# INFO - Starting multi-round game for seed 1
# INFO - Multi-round game completed: seed=1, rounds=7, score=1, success=True
# INFO - KORGym multi-round judged: seed=1, rounds=7, score=1, success=True
```

### 检查数据库

```bash
uv run python -c "
from utu.utils import SQLModelUtils
from utu.db import EvaluationSample
from sqlmodel import select
import json

with SQLModelUtils.create_session() as session:
    sample = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id == 'wordle_baseline_eval'
        ).limit(1)
    ).first()
    
    if sample:
        print(f'Correct: {sample.correct}')
        print(f'Reward: {sample.reward}')
        if sample.meta and 'multiround_result' in sample.meta:
            mr = sample.meta['multiround_result']
            print(f'Rounds: {mr.get(\"rounds\")}')
            print(f'Final Score: {mr.get(\"final_score\")}')
            print(f'✅ 多轮结果已保存')
        else:
            print('❌ 缺少多轮结果')
"
```

### 检查准确率

```bash
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval

# 应该看到：
# 准确率 (Accuracy): 8-16%  ✅ 大于0%
# (如果是0%，说明有问题)
```

---

## 🐛 故障排查

### 问题1: 准确率仍然是0%

**可能原因**:
1. 游戏服务器未运行
2. 配置缺少korgym部分
3. max_rounds设置错误
4. Agent策略太差

**排查步骤**:
```bash
# 1. 检查服务器
curl http://localhost:8777/docs

# 2. 检查配置
cat configs/eval/korgym/wordle_eval.yaml | grep -A 10 "korgym:"

# 3. 查看日志
tail -50 logs/utu.log | grep -i "wordle\|multi-round"

# 4. 小规模测试
uv run python scripts/test_multiround_eval.py --game_name "33-wordle" --seeds 1 --verbose
```

### 问题2: 日志没有显示 "multi-round"

**原因**: 游戏未被识别为多轮游戏

**检查**:
```python
from utu.practice.korgym_adapter import KORGymGameClassifier
game_type = KORGymGameClassifier.get_game_type("33-wordle")
print(f"Game type: {game_type}")  # 应该是 'multiple'
```

### 问题3: Trajectory为空或只有1轮

**原因**: 
1. Agent在第一轮就失败了（格式错误等）
2. max_rounds设置为1
3. 游戏立即结束（is_end=True）

**检查**:
```bash
# 查看详细的trajectory
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed
```

---

## 📈 预期性能

### Wordle (33-wordle)

| 指标 | 基线 | 训练后 | 说明 |
|------|------|--------|------|
| **Accuracy** | 8-16% | 16-24% | 10次内猜中的比例 |
| **Avg Rounds (成功)** | 7-9 | 6-8 | 成功时的平均轮数 |
| **Avg Rounds (全部)** | 9-10 | 8-10 | 包括失败的样本 |

**注意**: 
- Wordle是很难的游戏，准确率不会很高
- 单词长度4-12字母，增加了难度
- 10次机会比传统Wordle(6次)更宽松

### 其他多轮游戏

不同游戏的评分机制不同：
- **2048**: 累积分数，通常很高
- **Wordle**: 0或1（all-or-nothing）
- **Minesweeper**: 0或1
- **Tower of Hanoi**: 步数越少越好

---

## 🎓 经验学习效果

多轮游戏的经验学习特别有价值：

### L0经验示例（Wordle）
```
[L0-Case] Opening Strategy: Start with "arose" to test common vowels
[L0-Case] Yellow Letter Repositioning: When 'e' is yellow at position 4, try positions 0-3 in next guess
[L0-Case] Green Letter Lock: Once 'o' is green at position 2, always keep it there
```

### L1经验示例
```
[L1-Pattern] Information Maximization: Early guesses should test different letter combinations
[L1-Pattern] Constraint Propagation: Use confirmed letters to narrow down word candidates
[L1-Pattern] Feedback Integration: Systematically apply all feedback before next guess
```

### L2经验示例
```
[L2-Meta] Iterative Refinement: Use each round's feedback to refine hypothesis space
[L2-Meta] Strategic Exploration: Balance exploration (testing new letters) vs exploitation (confirming candidates)
```

---

## 🧪 测试工具

### 1. 小规模测试脚本

```bash
# 测试2个样本
uv run python scripts/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 \
  --verbose

# 测试5个样本
uv run python scripts/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 3 4 5 \
  --verbose

# 保留测试数据（不自动清理）
uv run python scripts/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 \
  --no-cleanup
```

### 2. 结果查看脚本

```bash
# 查看单个实验
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed

# 对比两个实验
uv run python scripts/view_korgym_results.py --compare \
  wordle_baseline_eval \
  wordle_practice_eval

# 查看所有游戏
uv run python scripts/view_korgym_results.py --game all
```

### 3. 详细分析脚本

```bash
# 分析评估结果
uv run python scripts/analyze_word_puzzle_results.py --exp_id wordle_baseline_eval

# 查看trajectory详情
uv run python -c "
from utu.utils import SQLModelUtils
from utu.db import EvaluationSample
from sqlmodel import select
import json

with SQLModelUtils.create_session() as session:
    samples = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id == 'wordle_baseline_eval'
        ).limit(3)
    ).all()
    
    for i, sample in enumerate(samples, 1):
        print(f'\\n样本 {i}:')
        if sample.trajectories:
            traj = json.loads(sample.trajectories)
            print(f'  轮数: {len(traj)}')
            for j, step in enumerate(traj[:3], 1):
                print(f'  Round {j}: action={step.get(\"action\")}, score={step.get(\"score\")}')
"
```

---

## 📝 配置模板

### Wordle评估配置

```yaml
# configs/eval/korgym/wordle_eval.yaml
# @package _global_
defaults:
  - /agents/practice/wordle_agent@agent
  - _self_

exp_id: "wordle_baseline_eval"

data:
  dataset: "KORGym-Wordle-Eval-50"
  type: "single"

concurrency: 32
pass_k: 1

verify_filename: "korgym.py"
verify_func_name: "verify_func"

korgym:
  enabled: true
  game_name: "33-wordle"
  game_host: "localhost"
  game_port: 8777
  level: 5              # 单词长度（4-12）
  max_rounds: 10        # ✅ 关键：必须与游戏代码一致
  timeout_per_game: 600
```

### Wordle训练配置

```yaml
# configs/practice/wordle_practice.yaml
# @package _global_
defaults:
  - /eval/korgym/wordle_eval@evaluation
  - _self_

exp_id: "wordle_practice"

practice:
  epochs: 2
  batch_size: 50
  grpo_n: 3
  rollout_concurrency: 4
  rollout_temperature: 0.7
  task_timeout: 600
  
  agent_objective: |
    input: Wordle game state with previous guesses and color feedback
    output: A strategic word guess that maximizes information gain
  
  learning_objective: |
    Help the agent improve Wordle gameplay by extracting:
    - L0: Specific guess sequences and feedback interpretation
    - L1: General opening strategies and constraint satisfaction
    - L2: Universal deductive reasoning principles
  
  num_experiences_per_query: 1
  
  hierarchical_learning:
    enabled: true
    l1_aggregation_threshold: 5
    l2_aggregation_threshold: 3
    max_l0_per_game: 1
    max_l0_recent: 50
    include_l0_in_prompt: true
    experience_save_path: workspace/hierarchical_experiences/wordle_practice.json
    agent_save_path: configs/agents/practice/wordle_practice_agent.yaml

data:
  practice_dataset_name: "KORGym-Wordle-Train-100"

korgym:
  enabled: true
  game_name: "33-wordle"
  game_host: "localhost"
  game_port: 8777
  level: 5
  max_rounds: 10  # ✅ 关键
```

---

## ✅ 成功标志

评估成功运行后，应该看到：

### 日志输出
```
INFO - Detected KORGym multi-round game: 33-wordle
INFO - Starting multi-round game for seed 1
INFO - Multi-round game completed: seed=1, rounds=7, score=1, success=True
INFO - KORGym multi-round judged: seed=1, rounds=7, score=1, success=True
```

### 评估结果
```
实验结果: wordle_baseline_eval
游戏: 33-wordle
总样本数: 50
成功数: 5-8
准确率 (Accuracy): 10-16%  ✅ 大于0%
平均得分 (Avg Score): 0.10-0.16

得分分布:
  0.00: 42 (84.0%)  # 失败的样本
  1.00:  8 (16.0%)  # 成功的样本
```

### 数据库记录
```python
sample.meta = {
    'seed': 1,
    'game_name': '33-wordle',
    'multiround_result': {
        'final_score': 1,
        'success': True,
        'rounds': 7,
        'responses': [...],  # 所有轮次的响应
        'trajectory': [...]  # 所有轮次的状态
    }
}
```

---

## 🎯 与单轮游戏的对比

| 特性 | 单轮游戏 (Word Puzzle) | 多轮游戏 (Wordle) |
|------|----------------------|------------------|
| **Rollout** | agent.run()一次 | adapter.play_game()多次 |
| **交互次数** | 1次 | 1-10次 |
| **Trajectory** | 单个状态 | 多个状态序列 |
| **Responses** | 1个response | 多个responses |
| **Judge** | 重新验证 | 使用rollout结果 |
| **评分** | 部分分数(0-1) | 全对或全错(0/1) |

---

## 📚 相关文档

- **游戏分析**: `WORDLE_GAME_ANALYSIS.md`
- **快速开始**: `WORDLE_QUICK_START.md`
- **测试指南**: `WORDLE_MULTIROUND_TEST_GUIDE.md`
- **支持分析**: `MULTI_ROUND_GAME_SUPPORT_ANALYSIS.md`
- **命令参考**: `KORGYM_THREE_GAMES_COMMANDS.md`

---

## 🎉 总结

✅ **多轮游戏评估已完全支持**:
- 自动检测游戏类型
- 完整执行多轮交互
- 正确计算最终得分
- 保存完整trajectory
- 支持经验学习

✅ **可以直接使用标准流程**:
- 无需特殊脚本
- 无需修改代码
- 与单轮游戏使用相同的命令

✅ **适用于所有KORGym多轮游戏**:
- Wordle, 2048, Minesweeper等
- 只需正确配置max_rounds
- 系统自动处理其余部分

---

**现在可以放心地评估和训练Wordle等多轮游戏了！** 🚀



