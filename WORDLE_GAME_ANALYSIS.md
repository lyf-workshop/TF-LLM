# Wordle游戏分析与接入指南 🎯

## 🎮 游戏机制分析

### 基本规则
- **游戏类型**: 多轮猜词游戏
- **目标**: 在有限次数内猜出隐藏的单词
- **尝试次数**: 10次（代码第113行）
- **单词长度**: 4-12个字母（随机生成）
- **游戏端口**: 8777
- **单词库**: `words.txt`（16922个单词）

### 反馈机制

每次猜测后，会收到详细反馈：
```
The letter X located at idx=i is in the word and in the correct spot,    (绿色 ✅ 正确位置)
The letter X located at idx=i is in the word but in the wrong spot,       (黄色 ⚠️ 错误位置)
The letter X located at idx=i is not in the word in any spot,              (灰色 ❌ 不在单词中)
```

### 评分规则

```python
if guess == secret_word:
    score = 1  # 猜中
    is_end = True
elif epoch >= 10:
    score = 0  # 用完10次机会
    is_end = True
else:
    score = 0  # 游戏继续
```

**特点**:
- ❌ All-or-nothing（全对或全错）
- ✅ 多轮交互
- ✅ 支持4-12字母单词（不限于传统5字母Wordle）
- ✅ 10次尝试机会（比传统Wordle的6次更宽松）

---

## ⚠️ 发现的配置问题

### 问题1: 尝试次数不匹配 🔴 高优先级

**游戏代码**（`game_lib.py:113`）:
```python
"attempts": 10  # 允许10次尝试
```

**原配置**:
```yaml
max_rounds: 6  # 只允许6次尝试 ❌
```

**影响**: 
- Agent只用了6次机会就停止
- 浪费了4次宝贵的尝试机会
- 降低成功率约40%

**已修复**: ✅ 更新为 `max_rounds: 10`

---

### 问题2: Agent策略假设错误 🟡 中优先级

**Agent配置** (`wordle_agent.yaml`):
```yaml
instructions: |-
  Your goal is to guess the hidden 5-letter word...
  - Provide your guess as a single 5-letter word
  - Use uppercase letters
```

**实际游戏**（`game_lib.py:108`）:
```python
level = random.randint(4, 12)  # 单词长度是4-12字母
secret_word = generate_secret_word(seed, level, bank_getter)
```

**影响**: 
- Agent只猜5字母单词
- 对于4字母或6-12字母的单词会失败
- 策略与实际游戏不匹配

**建议修复**: 更新Agent的instructions（见下方）

---

### 问题3: Level参数混淆 🟢 低优先级

**游戏代码** (`game_lib.py:54-62`):
```python
def generate_secret_word(seed: int, level: int, bank_getter=None) -> str:
    """
    根据给定 seed 与 level（单词长度）生成随机 secret word。
    """
    possible_words = word_bank.get(level, [])  # level就是单词长度
```

**原配置**:
```yaml
level: 3  # ❓ 不在4-12范围内
```

**说明**: 
- `level`参数在Wordle中是单词长度
- 应该设置为4-12之间的值
- 推荐使用5（传统Wordle长度）

**已修复**: ✅ 更新为 `level: 5`

---

## ✅ 配置修复总结

| 文件 | 参数 | 原值 | 新值 | 原因 |
|------|------|------|------|------|
| `wordle_eval.yaml` | `max_rounds` | 6 | 10 | 匹配游戏代码 |
| `wordle_practice_eval.yaml` | `max_rounds` | 6 | 10 | 匹配游戏代码 |
| `wordle_practice.yaml` | `max_rounds` | 6 | 10 | 匹配游戏代码 |
| `wordle_eval.yaml` | `level` | 3 | 5 | 有效单词长度范围 |
| `wordle_practice_eval.yaml` | `level` | 3 | 5 | 有效单词长度范围 |
| `wordle_practice.yaml` | `level` | 3 | 5 | 有效单词长度范围 |

---

## 🔧 需要手动修复：Agent策略

更新 `configs/agents/practice/wordle_agent.yaml`:

```yaml
agent:
  name: wordle_agent
  instructions: |-
    You are an expert Wordle player for KORGym games. Your goal is to guess the hidden word within 10 attempts using feedback from previous guesses.
    
    Game Rules:
    - Word length: 4-12 letters (varies by game, check "Word length" in the prompt)
    - Attempts: 10 tries
    - Feedback after each guess:
      * "in the correct spot" = Green (letter is right position)
      * "in the wrong spot" = Yellow (letter exists but wrong position)  
      * "not in the word" = Gray (letter doesn't exist)
    
    Strategy:
    1. **Check word length first** - The prompt shows "Word length: X"
    2. Start with common words matching that length containing frequent letters (e, a, r, i, o, t, n, s)
    3. Analyze feedback carefully:
       - Lock in green letters (correct position)
       - Try yellow letters in different positions
       - Eliminate gray letters completely
    4. Use process of elimination to narrow possibilities
    5. Consider common word patterns and letter frequencies
    6. Don't waste guesses on words with known wrong letters
    
    Multi-round Strategy:
    - Track ALL previous guesses and feedback in History
    - Build a mental model of what letters must/can't be where
    - Focus on high-information guesses early on
    - Save "sure bets" for later rounds when you have more info
    
    Output Format:
    - Provide your guess as a single word matching the required length
    - Format: Answer: WORD
    - Use lowercase letters (e.g., "Answer: happy", "Answer: word")
    - Only guess valid English words from the word bank
```

---

## 🚀 完整接入流程

### 步骤1: 启动游戏服务器

在WSL终端1:
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8777

# 验证服务器
# 应该看到: INFO:     Application startup complete.
```

### 步骤2: 准备数据集

在WSL终端2:
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 创建评估和训练数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 验证数据集
uv run python scripts/clean_experiment_data.py --list
# 应该看到:
#   - KORGym-Wordle-Eval-50 (50 samples)
#   - KORGym-Wordle-Train-100 (100 samples)
```

### 步骤3: 基线评估

```bash
# 清理旧评估结果（如果存在）
uv run python scripts/clean_experiment_data.py --exp_id wordle_baseline_eval

# 运行基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 查看结果
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed
```

### 步骤4: 训练（提取经验）

```bash
# 清理旧经验缓存（如果重新训练）
uv run python scripts/clean_alphabetical_sorting_cache.py --exp_id wordle_practice --force

# 运行训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 查看生成的经验
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.stats'

# 查看生成的Agent配置
cat configs/agents/practice/wordle_practice_agent.yaml | head -50
```

### 步骤5: 训练后评估

```bash
# 清理旧评估结果
uv run python scripts/clean_experiment_data.py --exp_id wordle_practice_eval

# 运行训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 查看对比结果
uv run python scripts/view_korgym_results.py --game wordle
```

---

## 📊 预期结果

### 基线性能（估计）
- **Accuracy**: 8-15%（10次机会猜中的比例）
- **Average attempts**: 7-9次（成功时的平均尝试次数）

### 训练后性能（估计）
- **Accuracy**: 15-25%（相对提升50-100%）
- **Improvement**: +7-10个百分点

### Wordle难点
1. 单词长度变化大（4-12字母）
2. 单词库很大（16922个单词）
3. 需要很强的推理能力
4. 10次机会仍然有限

---

## 🐛 故障排查

### 问题1: 游戏服务器启动失败

**症状**: `FileNotFoundError: words.txt`

**解决**:
```bash
# 确保在正确目录启动
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
ls -la words.txt  # 验证文件存在
python game_lib.py -p 8777
```

### 问题2: Agent答案长度不匹配

**症状**: 日志中看到 "guess length != secret length"

**原因**: Agent只猜5字母单词，但游戏要求4-12字母

**解决**: 更新Agent的instructions（见上方）

### 问题3: 准确率仍然很低

**可能原因**:
1. Agent没有正确解析反馈信息
2. Agent没有利用历史猜测
3. Agent猜测的不是有效英语单词

**调试**:
```bash
# 查看详细的失败样本
uv run python scripts/analyze_word_puzzle_results.py --exp_id wordle_baseline_eval

# 检查Agent响应
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed
```

---

## 📝 快速命令参考

```bash
# 一键运行完整流程（需要手动启动服务器）
cd /mnt/f/youtu-agent

# 准备数据
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 查看结果对比
uv run python scripts/view_korgym_results.py --game wordle
```

---

## ✅ 检查清单

接入前确认:
- [ ] 游戏服务器运行在8777端口
- [ ] `max_rounds: 10`（已修复✅）
- [ ] `level: 5`（已修复✅）
- [ ] Agent instructions更新（需手动修复）
- [ ] 数据集已创建（50 eval + 100 train）
- [ ] 清理了旧的评估缓存

完成后验证:
- [ ] 基线评估准确率 > 0%
- [ ] 训练生成了L0/L1/L2经验
- [ ] 训练后准确率有提升
- [ ] 没有API rate limit错误

---

**准备好了就可以开始测试Wordle了！** 🚀



