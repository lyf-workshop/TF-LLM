# 🔍 Wordle 评估结果验证分析

## 🤔 用户的关键疑问

> **这两个脚本是否只是查看评估的第一次回答正确与否，而不是 10 次交互后的答案是否正确？**

这是一个**非常关键**的问题！如果确实如此，那么：
- ❌ 准确率统计是错误的（只反映第一轮，不是最终结果）
- ❌ 经验学习没有意义（学习的是第一轮策略，而非完整推理）
- ❌ 所有的改进措施可能都基于错误的评估结果

---

## 📊 分析两个脚本

### 脚本 1：`scripts/games/wordle/analyze_wordle_top20.py`

```python
# Line 73-75
score = sample.reward if sample.reward is not None else 0.0
is_correct = sample.correct
```

**问题**：
- ✅ 脚本本身没问题 - 它读取的是 `sample.reward` 和 `sample.correct`
- ⚠️  但关键在于：这些字段保存的是什么？

### 脚本 2：`scripts/korgym/view_korgym_results.py`

```python
# Line 63-66
correct_count = sum(1 for s in samples if s.correct)
total_score = sum(s.reward for s in samples if s.reward is not None)
```

**问题**：
- ✅ 脚本本身没问题 - 它也是读取 `sample.correct` 和 `sample.reward`
- ⚠️  同样的问题：这些字段的来源是什么？

---

## 🔍 关键：数据来源分析

### 数据流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Preprocess 阶段                                               │
│    - 生成初始 prompt                                             │
│    - 保存到 sample.augmented_question                           │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Rollout 阶段 ⭐ 关键！                                        │
│    - BaseBenchmark.rollout_one()                                │
│    - 检测到多轮游戏 → 调用 _rollout_korgym_multiround()        │
│    - adapter.play_multiple_rounds(agent, seed)                 │
│      ├─ Round 1: agent.run(prompt1)                            │
│      ├─ Round 2: agent.run(prompt2)                            │
│      └─ ...                                                     │
│    - 返回 game_result (包含 final_score, success, rounds)      │
│    - 保存到 sample.meta['multiround_result'] ⭐                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Judge 阶段 ⭐ 关键！                                          │
│    - KORGymProcesser.judge_one()                                │
│    - 检查 meta['multiround_result'] 是否存在                    │
│      ✅ 存在 → 使用 final_score 和 success                      │
│         data.update(                                            │
│             correct = multiround_result['success'],             │
│             reward = multiround_result['final_score']           │
│         )                                                       │
│      ❌ 不存在 → 使用第一轮的 response 进行验证 ⚠️              │
│         (这才是问题所在！)                                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. 数据库保存                                                    │
│    - sample.correct ← 来自 Judge 阶段                           │
│    - sample.reward ← 来自 Judge 阶段                            │
│    - 脚本读取这些字段 → 显示统计结果                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 理论上的正确流程

根据代码分析，**理论上**流程是正确的：

### Rollout 阶段（`utu/eval/benchmarks/base_benchmark.py`，line 161-227）

```python
async def _rollout_korgym_multiround(self, agent, sample: EvaluationSample):
    # 初始化 adapter
    adapter = KORGymAdapter(...)
    seed = meta.get('seed') or meta.get('game_seed', 0)
    
    # ✅ 执行完整多轮游戏
    game_result = await adapter.play_game(agent, seed)
    
    # ✅ 保存完整结果到 meta
    sample.update(
        response=final_response,
        meta={
            **meta,
            'multiround_result': game_result,  # ← 包含 final_score, success, rounds
            'final_score': game_result.get('final_score', 0),
            'success': game_result.get('success', False),
            'rounds': game_result.get('rounds', 0),
            'all_responses': responses
        },
        stage="rollout"
    )
    
    return sample
```

### Judge 阶段（`utu/eval/processer/korgym_processor.py`，line 136-157）

```python
async def judge_one(self, data: EvaluationSample):
    meta = data.meta or {}
    
    # ✅ 检查多轮结果
    if self.adapter.game_type == 'multiple' and 'multiround_result' in meta:
        multiround_result = meta['multiround_result']
        score = float(multiround_result.get('final_score', 0))  # ← 最终得分
        success = multiround_result.get('success', False)       # ← 最终成功状态
        rounds = multiround_result.get('rounds', 0)             # ← 轮数
        
        # ✅ 更新为最终结果
        data.update(
            correct=success,    # ← 这是最终结果，不是第一轮
            reward=score,       # ← 这是最终得分，不是第一轮
            judged_response=f"Multi-round game completed in {rounds} rounds..."
        )
        
        return data
```

---

## ⚠️ 潜在的问题场景

虽然代码逻辑看起来正确，但可能存在以下问题：

### 场景 1：Rollout 阶段没有执行多轮交互 ❌

**可能原因**：
- `_should_use_korgym_multiround()` 返回 `False`
- 游戏类型检测错误
- 配置问题导致走了单轮流程

**结果**：
```python
# 如果没有执行 _rollout_korgym_multiround()，而是执行了普通的 rollout_one()
result = await agent.run(sample.augmented_question, ...)  # ← 只调用一次
sample.update(
    response=result.final_output,  # ← 只有第一轮的响应
    # ❌ meta 中没有 multiround_result！
)
```

### 场景 2：Judge 阶段没有识别到多轮结果 ❌

**可能原因**：
- `meta['multiround_result']` 不存在（因为 Rollout 没执行正确）
- 游戏类型判断错误

**结果**：
```python
# Judge 阶段走了单轮逻辑
if self.adapter.game_type == 'multiple' and 'multiround_result' in meta:
    # ❌ 这个条件不满足
    pass
else:
    # ❌ 走了这里 - 使用第一轮的 response 验证
    action = self.adapter._extract_action(data.response)  # ← 只有第一轮的action
    verified_state = self.adapter.verify_action(game_state)  # ← 只验证第一轮
    score = verified_state.get('score', 0.0)  # ← 第一轮的分数！
    
    data.update(
        correct=(score > 0),  # ← 基于第一轮的分数
        reward=score          # ← 第一轮的分数
    )
```

---

## 🧪 验证方法

我已经创建了一个调试脚本来验证这个问题：

### 运行调试脚本

```bash
# 检查最近的评估结果
uv run python scripts/debug_wordle_multiround.py --exp_id wordle_practice_20_eval --limit 5
```

### 脚本会检查

1. ✅ `meta['multiround_result']` 是否存在
2. ✅ `final_score` 是否等于 `reward`
3. ✅ `success` 是否等于 `correct`
4. ✅ `responses` 数量（应该 > 1）
5. ✅ `trajectory` 长度（应该 > 1）
6. ⚠️  是否只有 1 个 response（表示只执行了第一轮）

### 预期结果

#### 如果多轮交互正常 ✅

```
✅ multiround_result 存在
  - final_score: 1
  - success: True
  - rounds: 7
  - responses 数量: 7  ← 应该 > 1
  - trajectory 长度: 7  ← 应该 > 1
✓ final_score 和 reward 一致
✓ success 和 correct 一致
```

#### 如果只执行了第一轮 ❌

```
❌ meta 中没有 'multiround_result'！
或者
✓ multiround_result 存在
  - responses 数量: 1  ← ⚠️ 只有 1 个
  - trajectory 长度: 1  ← ⚠️ 只有 1 个
```

---

## 🔧 如果发现问题

### 问题 1：没有 `multiround_result`

**原因**：Rollout 阶段没有执行多轮交互

**检查**：
```bash
# 查看评估日志
grep "multi-round" [评估日志文件]
grep "Starting multi-round game" [评估日志文件]
```

**修复**：
- 检查 `_should_use_korgym_multiround()` 逻辑
- 确认游戏分类正确（'33-wordle' 应该是 'multiple' 类型）
- 确认配置中 `korgym.enabled = True`

### 问题 2：只有 1 个 response

**原因**：多轮交互中断或只执行了一轮

**检查**：
```python
# 检查 play_multiple_rounds() 的循环
for round_num in range(1, self.max_rounds + 1):
    ...
    if game_state.get('is_end', False):
        break  # ← 是否提前结束？
```

**可能原因**：
- Agent 第一轮就猜中了（极小概率）
- 游戏状态错误地设置了 `is_end=True`
- 循环逻辑有问题

---

## 📝 验证清单

请按照以下步骤验证：

### Step 1: 运行调试脚本 ⭐

```bash
uv run python scripts/debug_wordle_multiround.py --exp_id wordle_practice_20_eval --limit 5
```

### Step 2: 检查输出

- [ ] `multiround_result` 是否存在？
- [ ] `responses` 数量是否 > 1？
- [ ] `trajectory` 长度是否 > 1？
- [ ] `final_score` 是否等于 `reward`？
- [ ] `success` 是否等于 `correct`？

### Step 3: 如果全部 ✅

**说明**：
- ✅ 多轮交互正常执行
- ✅ 最终结果正确保存
- ✅ `analyze_wordle_top20.py` 和 `view_korgym_results.py` 读取的是正确的最终结果
- ✅ 准确率统计是有效的

### Step 4: 如果发现 ❌

**说明**：
- ❌ 你的怀疑是对的！
- ❌ 可能只执行了第一轮
- ❌ 需要修复 Rollout 或 Judge 阶段的代码

---

## 💡 如果问题确实存在

### 影响

1. **准确率统计完全错误**
   - 当前显示的 10-16% 可能是第一轮猜中的概率
   - 实际的 10 轮交互准确率可能更高（或更低）

2. **经验学习方向错误**
   - 学习的是"第一次猜测策略"
   - 而非"多轮推理和约束满足"

3. **优化措施可能无效**
   - 手动编写的经验关注推理过程
   - 但如果只评估第一轮，这些经验不会被利用

### 紧急修复

如果确认问题，需要：

1. **修复 Rollout 阶段**
   - 确保 `_rollout_korgym_multiround()` 被正确调用
   - 确保 `multiround_result` 被保存

2. **修复 Judge 阶段**
   - 确保识别到 `multiround_result`
   - 确保使用 `final_score` 而非第一轮分数

3. **重新评估**
   - 清除旧数据
   - 重新运行评估
   - 验证结果

---

## 🚀 下一步行动

### 优先级 1：验证数据 ⚠️ **立即执行**

```bash
uv run python scripts/debug_wordle_multiround.py --exp_id wordle_practice_20_eval --limit 5
```

### 优先级 2：根据结果决定

**如果全部正常 ✅**：
- 继续测试对话历史修复的效果
- 评估手动优化经验的提升

**如果发现问题 ❌**：
- 修复 Rollout/Judge 代码
- 重新评估
- 重新统计准确率

---

## 📂 相关文件

- **调试脚本**：`scripts/debug_wordle_multiround.py` ← ✅ 新创建
- **Rollout 逻辑**：`utu/eval/benchmarks/base_benchmark.py` (line 161-227)
- **Judge 逻辑**：`utu/eval/processer/korgym_processor.py` (line 104-183)
- **多轮交互**：`utu/practice/korgym_adapter.py` (line 268-320)

---

**🔍 这是一个非常关键的验证步骤！请先运行调试脚本，我们根据结果来判断是否存在问题！**

