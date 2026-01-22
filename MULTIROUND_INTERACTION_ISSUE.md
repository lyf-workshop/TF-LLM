# 🐛 多轮交互的对话历史问题分析

## 📋 问题概述

当前 Wordle 多轮交互实现存在**对话历史缺失**的问题：

- ✅ **游戏状态历史**：正确保存（通过 `game_state['history']`）
- ✅ **Prompt 包含历史**：正确生成（通过 `print_board()` 函数）
- ❌ **Agent 对话历史**：未保存（每轮都是独立会话）

---

## 🔍 根本原因

### 问题代码位置

**文件**：`utu/practice/korgym_adapter.py`  
**方法**：`play_multiple_rounds()`（line 268-320）

```python
async def play_multiple_rounds(self, agent, seed: int) -> Dict:
    game_state = self.generate_game_instance(seed)
    trajectory = []
    responses = []
    
    for round_num in range(1, self.max_rounds + 1):
        # Get current state prompt (包含游戏历史)
        prompt = self.get_game_prompt(game_state)
        
        # ❌ 问题：每次都是独立调用，没有对话历史
        agent_result = await agent.run(prompt)  # ← 缺少 save=True
        
        # Extract action
        action = self._extract_action(agent_result.final_output)
        game_state['action'] = action
        responses.append(agent_result.final_output)
        
        # Verify and update game state
        game_state = self.verify_action(game_state)
        trajectory.append(dict(game_state))
        
        if game_state.get('is_end', False):
            break
    
    return {...}
```

---

## 🎯 核心问题

### Agent.run() 的对话历史机制

**文件**：`utu/agents/simple_agent.py`  
**方法**：`run()`（line 238-277）

```python
async def run(
    self, 
    input: str | list[TResponseInputItem], 
    trace_id: str = None, 
    save: bool = False,  # ← 关键参数！
    log_to_db: bool = True
) -> TaskRecorder:
    """
    Args:
        save: whether to update massage history (use `input_items`)
    """
    ...
    # Line 261-262: 使用历史消息
    if isinstance(input, str):
        input = self.input_items + [{"content": input, "role": "user"}]
    
    # Line 271-272: 保存历史消息
    if save:
        self.input_items = run_result.to_input_list()  # ← 保存对话历史
        self.current_agent = run_result.last_agent
    
    return recorder
```

### 当前行为

```
Round 1:
  self.input_items = []  # ← 空历史
  input = [] + [{"content": prompt1, "role": "user"}]
  agent.run(prompt1)  # ← save=False（默认）
  # ❌ 历史没有保存！

Round 2:
  self.input_items = []  # ← 仍然是空！
  input = [] + [{"content": prompt2, "role": "user"}]
  agent.run(prompt2)  # ← save=False（默认）
  # ❌ Agent 不记得 Round 1 的对话！

Round 3:
  ...  # ← 每轮都是独立会话
```

---

## ⚠️ 实际影响

### 对 Wordle 的影响

#### 当前实现（无对话历史）

```
Round 1:
  Agent Input:
    - Wordle Game
    - Attempt: 1 of 10
    - Word length: 4
    - History: (empty)
  
  Agent Thinking: "我需要猜一个4字母单词，用常见字母开始"
  Agent Output: "Answer: tale"

Round 2:
  Agent Input:
    - Wordle Game
    - Attempt: 2 of 10
    - Word length: 4
    - History:
      1. Guess: tale
         Feedback: t=gray, a=yellow, l=gray, e=yellow
  
  Agent Thinking:
    ❌ "让我分析一下反馈：t=gray, a=yellow..."
    ❌ 需要重新理解反馈含义
    ❌ 不记得自己在 Round 1 的推理过程
  
  Agent Output: "Answer: soar"

Round 3:
  ...  ← 每轮都需要"重新"分析所有历史
```

#### 理想实现（有对话历史）

```
Round 1:
  Agent Input:
    - Wordle Game
    - Attempt: 1 of 10
    - Word length: 4
    - History: (empty)
  
  Agent Thinking: "我需要猜一个4字母单词，用常见字母开始"
  Agent Output: "Answer: tale"
  ✅ 对话历史保存

Round 2:
  Agent Input:
    - [Previous Conversation History]  ← ✅ 包含 Round 1 的完整对话
    - Wordle Game
    - Attempt: 2 of 10
    - Word length: 4
    - History:
      1. Guess: tale
         Feedback: t=gray, a=yellow, l=gray, e=yellow
  
  Agent Thinking:
    ✅ "好的，我上一轮猜了 'tale'"
    ✅ "根据反馈，'a' 和 'e' 在单词里但位置不对"
    ✅ "我的分析是：'a' 可能在位置 2,3,4，'e' 可能在位置 1,2,3"
    ✅ "所以我现在猜一个包含 'a' 和 'e' 但位置不同的词"
  
  Agent Output: "Answer: each"
  ✅ 对话历史继续累积

Round 3:
  Agent Input:
    - [Complete Conversation History]  ← ✅ Round 1 + Round 2
    - Wordle Game
    - ...
  
  Agent Thinking:
    ✅ 能看到完整的推理链
    ✅ 不需要重新分析
    ✅ 可以基于之前的推理继续优化
```

---

## 📊 对性能的影响

| 指标 | 无对话历史（当前） | 有对话历史（理想） | 差异 |
|------|------------------|------------------|------|
| **推理连贯性** | ❌ 低 - 每轮独立分析 | ✅ 高 - 连续推理链 | 显著改善 |
| **token 使用** | ⚠️ 高 - 重复分析历史反馈 | ✅ 中 - 利用上下文 | 减少 20-30% |
| **准确率** | ⚠️ 低 - 缺少推理连贯性 | ✅ 高 - 更好的约束追踪 | +5-15% |
| **收敛速度** | ❌ 慢 - 可能违反已知约束 | ✅ 快 - 严格遵循约束 | 减少 1-2 轮 |

### 具体示例

**场景**：Agent 在 Round 1 已经推理出 "位置 2 必须是 'a'"

**无对话历史**（当前）：
```
Round 1: Agent 推理 "位置 2 是 'a'"，猜 "tale"
Round 2: Agent 重新分析反馈，可能忘记 "位置 2 是 'a'" 的结论
         可能猜出 "soar"（位置 2 不是 'a' ❌ 违反约束）
```

**有对话历史**（理想）：
```
Round 1: Agent 推理 "位置 2 是 'a'"，猜 "tale"，历史保存
Round 2: Agent 看到之前的推理 "位置 2 是 'a'"
         严格遵循约束，猜 "each"（位置 2 是 'a' ✅）
```

---

## 🛠️ 解决方案

### 方案 1：在多轮交互中启用 `save=True`

**修改文件**：`utu/practice/korgym_adapter.py`

```python
async def play_multiple_rounds(self, agent, seed: int) -> Dict:
    game_state = self.generate_game_instance(seed)
    trajectory = []
    responses = []
    total_time = 0
    
    for round_num in range(1, self.max_rounds + 1):
        # Get current state prompt
        prompt = self.get_game_prompt(game_state)
        
        # ✅ 启用对话历史保存
        start_time = time.time()
        agent_result = await agent.run(prompt, save=True)  # ← 添加 save=True
        response_time = time.time() - start_time
        total_time += response_time
        
        # Extract action
        action = self._extract_action(agent_result.final_output)
        game_state['action'] = action
        responses.append(agent_result.final_output)
        
        # Verify action and update state
        game_state = self.verify_action(game_state)
        trajectory.append(dict(game_state))
        
        # Check if game ended
        if game_state.get('is_end', False):
            break
    
    return {
        'game_name': self.game_name,
        'game_category': self.game_category,
        'seed': seed,
        'responses': responses,
        'final_score': game_state.get('score', 0),
        'success': game_state.get('score', 0) > 0,
        'is_end': game_state.get('is_end', True),
        'rounds': round_num,
        'response_time': total_time,
        'trajectory': trajectory,
        'round_id': f"{self.game_name}_seed{seed}_{int(time.time())}"
    }
```

### 方案 2：显式传递对话历史（更灵活）

```python
async def play_multiple_rounds(self, agent, seed: int) -> Dict:
    game_state = self.generate_game_instance(seed)
    trajectory = []
    responses = []
    total_time = 0
    conversation_history = []  # ← 显式管理历史
    
    for round_num in range(1, self.max_rounds + 1):
        # Get current state prompt
        prompt = self.get_game_prompt(game_state)
        
        # ✅ 传递完整对话历史
        start_time = time.time()
        if conversation_history:
            # 后续轮次：使用历史
            input_with_history = conversation_history + [{"content": prompt, "role": "user"}]
            agent_result = await agent.run(input_with_history, save=True)
        else:
            # 第一轮：无历史
            agent_result = await agent.run(prompt, save=True)
        
        response_time = time.time() - start_time
        total_time += response_time
        
        # 更新对话历史
        conversation_history = agent_result.to_input_list()
        
        # Extract action
        action = self._extract_action(agent_result.final_output)
        game_state['action'] = action
        responses.append(agent_result.final_output)
        
        # Verify action and update state
        game_state = self.verify_action(game_state)
        trajectory.append(dict(game_state))
        
        # Check if game ended
        if game_state.get('is_end', False):
            break
    
    return {...}
```

---

## 🎯 推荐方案

### **推荐方案 1** - 更简单、影响最小

**优点**：
- ✅ 只需改一行代码（添加 `save=True`）
- ✅ 利用 Agent 内置的历史管理机制
- ✅ 对现有代码影响最小

**缺点**：
- ⚠️ 依赖 Agent 的 `self.input_items` 状态
- ⚠️ 如果同一个 Agent 实例处理多个游戏，历史可能混淆

**适用场景**：
- 每个游戏都使用独立的 Agent 实例
- 评估和训练流程

---

## 🧪 测试建议

### 测试 1：验证对话历史是否保存

```python
# 测试脚本
agent = get_agent(config)
adapter = KORGymAdapter(game_name="33-wordle", ...)

# 第一轮
result1 = await agent.run("Round 1 prompt", save=True)
print(f"Round 1 - input_items length: {len(agent.input_items)}")

# 第二轮
result2 = await agent.run("Round 2 prompt", save=True)
print(f"Round 2 - input_items length: {len(agent.input_items)}")

# 预期输出：
# Round 1 - input_items length: 2  (user + assistant)
# Round 2 - input_items length: 4  (2 from round1 + 2 from round2)
```

### 测试 2：对比 save=True 前后的准确率

```bash
# 修改前：评估基线
uv run python scripts/run_eval.py --config_name korgym/wordle_baseline

# 修改后：评估改进版
# (修改 korgym_adapter.py，添加 save=True)
uv run python scripts/run_eval.py --config_name korgym/wordle_baseline_with_history

# 对比准确率
uv run python scripts/korgym/compare_korgym_results.py \
  --baseline wordle_baseline \
  --enhanced wordle_baseline_with_history
```

---

## 📈 预期改进

| 指标 | 改进前 | 改进后 | 预期提升 |
|------|--------|--------|---------|
| **准确率** | ~10-16% | ~15-25% | +5-10% |
| **平均轮数** | ~8-9 轮 | ~6-7 轮 | 减少 1-2 轮 |
| **约束违反次数** | 高 | 低 | 显著减少 |
| **推理连贯性** | 差 | 好 | 质的提升 |

---

## 🔧 实施步骤

### Step 1: 修改代码

```bash
# 编辑文件
code utu/practice/korgym_adapter.py

# 在 play_multiple_rounds() 方法中
# Line 291: agent_result = await agent.run(prompt)
# 改为:   agent_result = await agent.run(prompt, save=True)
```

### Step 2: 测试验证

```bash
# 小规模测试（2个样本）
uv run python scripts/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 \
  --verbose

# 查看日志，确认对话历史累积
```

### Step 3: 完整评估

```bash
# 清理旧结果
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_baseline_v2

# 运行评估
uv run python scripts/run_eval.py --config_name korgym/wordle_baseline

# 查看结果
uv run python scripts/korgym/view_korgym_results.py wordle_baseline_v2
```

### Step 4: 对比分析

```bash
# 对比改进前后
uv run python scripts/korgym/compare_korgym_results.py \
  --baseline wordle_baseline \
  --enhanced wordle_baseline_v2

# 分析具体案例
uv run python scripts/korgym/analyze_wordle_cases.py --exp_id wordle_baseline_v2
```

---

## 💡 关键洞察

1. **对话历史 ≠ 游戏历史**
   - 游戏历史：在 prompt 中（通过 `print_board()`）
   - 对话历史：Agent 的推理过程和上下文

2. **对话历史的重要性**
   - 对于复杂推理任务（如 Wordle），对话历史能保持推理连贯性
   - Agent 能记住自己的分析和结论
   - 减少重复分析，提高效率

3. **为什么之前没发现**
   - 游戏历史在 prompt 中，看起来"有历史"
   - 但 Agent 每轮都在"重新分析"相同的历史
   - 缺少推理链的连续性

---

## 📂 相关文件

- **核心问题**：`utu/practice/korgym_adapter.py` (line 268-320)
- **Agent 实现**：`utu/agents/simple_agent.py` (line 238-277)
- **多轮评估**：`utu/eval/benchmarks/base_benchmark.py` (line 161-227)
- **经验提取**：`utu/practice/experience_updater.py`

---

## 🎯 总结

这是一个**隐蔽但影响重大**的问题：

- ✅ **表面上**：游戏历史正确传递（prompt 中有反馈）
- ❌ **实际上**：Agent 对话历史缺失（每轮独立推理）
- 🔥 **影响**：推理不连贯，准确率降低，轮数增加

**修复方法**：仅需添加 `save=True` 参数！

---

**这可能是 Wordle 准确率低的关键原因之一！** 🎯

