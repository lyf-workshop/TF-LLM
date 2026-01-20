# 多轮交互游戏支持分析 🔍

## ✅ 好消息：训练流程完全支持

### 1. 游戏分类系统 ✅

系统已经正确识别Wordle为多轮游戏：

```python
# utu/practice/korgym_adapter.py
GAME_TYPES = {
    'single': [
        '8-word_puzzle', '9-Jigsaw_puzzle', ...
    ],
    'multiple': [
        '3-2048', '10-minigrid', '33-wordle',  # ✅ Wordle在这里
        '36-CryptoWord', '38-minesweeper', ...
    ]
}
```

### 2. 适配器支持 ✅

`KORGymAdapter` 完整支持多轮游戏：

```python
async def play_multiple_rounds(self, agent, seed: int) -> Dict:
    """Play a multi-turn game."""
    game_state = self.generate_game_instance(seed)
    trajectory = []
    responses = []
    
    for round_num in range(1, self.max_rounds + 1):
        # 1. 获取当前prompt
        prompt = self.get_game_prompt(game_state)
        
        # 2. Agent做出响应
        agent_result = await agent.run(prompt)
        
        # 3. 提取action
        action = self._extract_action(agent_result.final_output)
        game_state['action'] = action
        
        # 4. 验证并更新状态
        game_state = self.verify_action(game_state)
        trajectory.append(dict(game_state))
        
        # 5. 检查游戏是否结束
        if game_state.get('is_end', False):
            break
    
    return {
        'game_name': self.game_name,
        'final_score': game_state.get('score', 0),
        'success': game_state.get('score', 0) > 0,
        'rounds': round_num,
        'trajectory': trajectory,  # ✅ 完整的多轮轨迹
        ...
    }
```

**关键特点**:
- ✅ 循环处理多个回合
- ✅ 每轮获取最新的game prompt
- ✅ 维护完整的trajectory
- ✅ 正确检测游戏结束条件
- ✅ 累积所有响应和状态

### 3. 经验提取器支持 ✅

`KORGymExperienceExtractor` 有专门的多轮游戏模板：

```python
L0_EXTRACTION_PROMPT = """
...
{% if game_type == 'single' %}
Game Prompt:
{{ prompt }}
Agent's Action:
{{ action }}
{% else %}
Multi-Round Game Trajectory:  # ✅ 多轮游戏特殊处理
{% for i, step in enumerate(trajectory) %}
Round {{ i + 1 }}:
  Action: {{ step.get('action', 'N/A') }}
  Score: {{ step.get('score', 0) }}
  State: {{ step.get('board', 'N/A') }}
{% endfor %}

Final Outcome:
- Total Rounds: {{ rounds }}
- Final Score: {{ final_score }}
- Success: {{ success }}
{% endif %}
...
"""
```

**关键特点**:
- ✅ 自动识别game_type
- ✅ 展示完整的多轮轨迹
- ✅ 包含每轮的action、score、state
- ✅ 总结最终结果

---

## ✅ 好消息：评估流程已完全支持！

### 已实现的功能

经过检查发现，系统**已经实现了多轮游戏评估支持**！

#### 1. BaseBenchmark.rollout_one ✅

```python
async def rollout_one(self, sample: EvaluationSample) -> EvaluationSample:
    agent = get_agent(self.config.agent)
    
    # ✅ 自动检测KORGym多轮游戏
    if self._should_use_korgym_multiround(sample):
        return await self._rollout_korgym_multiround(agent, sample)
    
    # 原有逻辑：单轮游戏
    result = await agent.run(sample.augmented_question, ...)
    ...
```

**功能**:
- ✅ 自动检测游戏类型（single vs multiple）
- ✅ 对多轮游戏调用 `adapter.play_game()`
- ✅ 完整执行10轮交互（直到猜中或用完机会）
- ✅ 保存完整trajectory和所有responses

#### 2. KORGymProcesser.judge_one ✅

```python
async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
    meta = data.meta or {}
    
    # ✅ 检查是否是多轮游戏且已有完整结果
    if self.adapter.game_type == 'multiple' and 'multiround_result' in meta:
        # 直接使用rollout阶段的结果
        multiround_result = meta['multiround_result']
        score = float(multiround_result.get('final_score', 0))
        success = multiround_result.get('success', False)
        rounds = multiround_result.get('rounds', 0)
        
        data.update(
            correct=success,
            reward=score,
            judged_response=f"Multi-round game completed in {rounds} rounds. Score: {score}"
        )
        return data
    
    # 原有逻辑：单轮游戏
    ...
```

**功能**:
- ✅ 识别多轮游戏结果
- ✅ 直接使用rollout阶段已经得到的final_score
- ✅ 不需要重新验证（避免重复执行游戏）
- ✅ 正确设置correct和reward

---

## 🎯 实际影响

### 对单轮游戏（如Word Puzzle）：
- ✅ 完全不受影响
- ✅ 继续使用原有逻辑
- ✅ 一次响应，一次验证

### 对多轮游戏（如Wordle）：
- ✅ **完整支持！**
- ✅ Rollout阶段执行完整的10轮交互
- ✅ 每轮获取反馈并继续
- ✅ 保存完整的游戏轨迹
- ✅ 最终得到正确的score（0或1）

### 实际流程（Wordle）

```
✅ 正确流程（已实现）：
Rollout阶段:
  Round 1: Agent猜 "arose" → 反馈：a(黄), r(灰), o(绿), s(灰), e(黄)
  Round 2: Agent根据反馈猜 "quote" → 反馈：...
  Round 3: Agent继续猜...
  ...
  Round 7: Agent猜中 "phone" → score=1, is_end=True

Judge阶段:
  读取rollout结果 → score=1, success=True, rounds=7
  设置 correct=True, reward=1.0
```

---

## 📊 当前Wordle的实际情况

### 训练流程（完全支持）✅

```bash
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
```

**流程**:
1. ✅ 读取100个训练seeds
2. ✅ 对每个seed，调用 `adapter.play_multiple_rounds()`
3. ✅ Agent与游戏进行10轮交互（直到猜中或用完机会）
4. ✅ 收集完整的trajectory（每轮的guess和feedback）
5. ✅ 提取L0经验（分析多轮策略）
6. ✅ 聚合为L1/L2经验
7. ✅ 保存增强的Agent配置

**结果**:
- 生成的经验会包含多轮游戏的策略
- 例如："在第一轮反馈后，应该优先尝试黄色字母的其他位置"
- 训练后的Agent会学习到多轮推理策略

### 评估流程（完全支持）✅

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

**流程**:
1. ✅ 生成游戏prompt
2. ✅ 检测到多轮游戏，调用 `adapter.play_game()`
3. ✅ 执行完整的10轮交互
4. ✅ 每轮Agent根据反馈做出新的猜测
5. ✅ 得到最终score（0或1）

**结果**:
- ✅ 准确率正确反映Agent能力（预期8-16%）
- ✅ 完整记录所有轮次的trajectory
- ✅ 可以分析Agent的多轮推理策略

---

## ✅ 最终结论和建议

### 对于Wordle的接入：

1. **可以正常训练** ✅
   - 训练流程完全支持多轮游戏
   - 经验提取会正确分析多轮策略
   - 训练后的Agent会学习到Wordle策略

2. **可以正常评估** ✅
   - **可以使用** `run_eval.py` 进行评估
   - 系统已实现完整的多轮评估支持
   - 自动检测游戏类型并使用正确的流程

3. **推荐工作流** 🎯
   ```bash
   # 1. 准备数据
   uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
   
   # 2. 基线评估
   uv run python scripts/run_eval.py --config_name korgym/wordle_eval
   
   # 3. 训练
   uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
   
   # 4. 训练后评估
   uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
   
   # 5. 查看对比结果
   uv run python scripts/view_korgym_results.py --game wordle
   ```

### 总结表

| 组件 | 单轮游戏 | 多轮游戏 | Wordle |
|------|---------|---------|--------|
| **游戏分类** | ✅ | ✅ | ✅ 已识别 |
| **训练-Adapter** | ✅ | ✅ | ✅ play_multiple_rounds |
| **训练-经验提取** | ✅ | ✅ | ✅ 多轮模板 |
| **评估-Preprocessor** | ✅ | ✅ | ✅ 生成prompt |
| **评估-Rollout** | ✅ | ✅ | ✅ 完整多轮交互 |
| **评估-Judge** | ✅ | ✅ | ✅ 使用多轮结果 |
| **评估-Metrics** | ✅ | ✅ | ✅ 正确统计 |

---

## 🚀 立即可用的Wordle完整流程

### 快速开始

```bash
# 终端1: 启动服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8777

# 终端2: 完整流程
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 1. 准备数据
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 2. 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 5. 查看结果
uv run python scripts/view_korgym_results.py --game wordle
```

### 预期结果

```
对比分析: 基线 vs 训练后
================================================================================

实验结果: wordle_baseline_eval
总样本数: 50
成功数: 4-8
准确率 (Accuracy): 8-16%  ✅

实验结果: wordle_practice_eval
总样本数: 50
成功数: 8-12
准确率 (Accuracy): 16-24%  ✅

提升统计
================================================================================
准确率提升: +8-10%
平均得分提升: +0.08-0.10
✅ 训练有效！
```

---

**结论**: Wordle的训练和评估都已完全支持！可以直接使用标准流程。🎉

