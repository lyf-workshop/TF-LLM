# Wordle 评估中 LLM 回答问题分析

## 📊 评估结果总览

**实验**：`wordle_practice_eval_20_23`
- **总题数**：50 题
- **成功数**：11 题
- **失败数**：39 题
- **准确率**：22%

**配置**：
- Model: `qwen3-32b`
- Level: 5（固定5字母）
- 经验：L2 (1个) + L1 (3个) 精简版
- Prompt格式：✅ 简洁历史格式（已生效）

---

## 🔍 发现的主要问题

### 问题 1：猜测不存在的单词 ❌

从实际案例中发现，LLM 会猜一些**不是真实英语单词**的词：

#### 案例 A（失败）

```
Word length: 6
Final Answer: teelle

分析：
- "teelle" 不是一个真实的英语单词！
- 推理过程看起来很合理（满足所有颜色约束）
- 但最终猜测是无效单词
```

#### 案例 B（失败）

```
Word length: 8
Final Answer: forestor

分析：
- "forestor" 不是真实单词（正确的是 "forester"）
- LLM 可能混淆了相似的单词
```

**根本问题**：
- ✅ LLM 能正确解析颜色反馈
- ✅ LLM 能正确应用约束
- ❌ **但 LLM 生成的候选词不一定是真实单词**

---

### 问题 2：推理过程冗长但无效

#### 案例 C（失败，7字母）

```
正确答案：（未知，可能是类似 "portent" 的变体）
LLM 猜测：portent

推理过程（第9轮）：
1. 解析反馈："Y:p@0 Y:o@1 Y:r@2 G:e@3 G:t@4 G:o@5 N:n@6"
2. 提取约束：
   - Green: e@3, t@4, o@5
   - Yellow: p@0, o@1, r@2
   - Gray: n@6
3. 生成候选：portent
4. 验证：✅ 满足所有约束
5. 提交：portent

结果：失败（可能长度不对或单词拼写错误）
```

**问题**：
- ✅ 逻辑推理清晰
- ✅ 约束满足正确
- ❌ 最终单词可能不匹配或无效

---

### 问题 3：长单词（6-8字母）成功率极低

#### 统计分析（从 recent_wordle_results.txt）

| 单词长度 | 案例 | 成功率 | 典型问题 |
|---------|------|-------|---------|
| **4 字母** | type, road | ✅ 高 | 推理正确 |
| **5 字母** | （标准）| ✅ 中等 | 大部分正确 |
| **6 字母** | teelle | ❌ 低 | 猜无效单词 |
| **7 字母** | portent | ❌ 极低 | 推理复杂 |
| **8 字母** | forestor | ❌ 极低 | 猜无效单词 |

**发现**：
- ✅ 4-5 字母单词：LLM 表现良好
- ❌ 6+ 字母单词：频繁猜无效单词

---

### 问题 4：重复猜测相同单词

#### 案例 D（从历史记录）

```
Attempt 6: softcore
Attempt 7: softcore (same as attempt 6)
Feedback is identical. No new information.
```

**问题**：
- LLM 在某些情况下会重复猜测
- 浪费尝试次数
- 可能是因为没有意识到已经猜过

---

## ✅ LLM 表现良好的地方

### 1. 简洁历史格式解析正确 ✅

LLM 能够正确解析简洁历史格式：

```
Input: "Y:p@0 Y:o@1 Y:r@2 G:e@3 G:t@4 G:o@5 N:n@6"

LLM 理解：
- Green: e@3, t@4, o@5
- Yellow: p@0, o@1, r@2
- Gray: n@6
```

**说明**：简洁历史格式修复已生效！

### 2. 约束推理清晰 ✅

LLM 能够系统性地：
- 提取颜色反馈
- 构建位置约束
- 排除不可能的字母
- 生成候选词

### 3. 短单词成功率高 ✅

从案例看，4-5 字母单词的推理通常是正确的：

```
案例：type (4字母)
- 推理过程清晰
- 最终答案正确
- 成功！
```

---

## 🎯 根本原因分析

### 原因 1：qwen3-32b 词汇量限制

**对比**：
- `qwen2.5-72b`：72B 参数，词汇掌握更全面
- `qwen3-32b`：32B 参数，**词汇量相对较小**

**结果**：
- ✅ 对常见 5 字母单词（crane, table, stare）掌握良好
- ❌ 对罕见 6+ 字母单词容易"编造"不存在的词

### 原因 2：level=5（随机长度）仍然包含长词

虽然你改成了 `level: 5`，但这是**给游戏服务器的参数**。

从 `game_lib.py` 看：

```python
def generate(seed: int, bank_getter=None) -> dict:
    random.seed(seed)
    level = random.randint(4, 12)  # ⚠️ 忽略传入的 level，随机生成！
    secret_word = generate_secret_word(seed, level, bank_getter)
```

**问题**：即使配置 `level: 5`，游戏服务器仍会生成 **4-12 字母的随机长度单词**！

### 原因 3：缺少"单词有效性检查"

LLM 的 instructions 中没有强调：

```
❌ 当前：只要求满足约束
✅ 应该：满足约束 + 必须是真实英语单词
```

---

## ✅ 解决方案

### 方案 1：修复 Wordle 服务器（使用固定长度）

<function_calls>
<invoke name="Read">
<parameter name="path">KORGym/game_lib/33-wordle/game_lib.py