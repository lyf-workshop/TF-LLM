# 📊 Wordle 经验对比：自动生成 vs 手动优化

## 🔄 经验结构对比

| 维度 | 原版（自动生成） | 优化版（手动编写） | 改进 |
|------|-----------------|------------------|------|
| **总数量** | 7条 | 9条 | +2条 |
| **L2 元策略** | 0条 (0%) | 2条 (22%) | ✅ +2条 |
| **L1 模式** | 1条 (14%) | 4条 (44%) | ✅ +3条 |
| **L0 案例** | 6条 (86%) | 3条 (33%) | ✅ 更平衡 |
| **内容重复度** | 高（6条说同一件事） | 低（每条独特） | ✅ |
| **覆盖阶段** | 仅开局 | 全流程 | ✅ |

---

## 📝 详细内容对比

### 原版（自动生成）的7条经验

#### ❌ 问题1：内容高度重复

**[G0] L1-Pattern**:
> Choose an initial guess from a predefined list of high-entropy words that contain a mix of common and unique letters...

**[G1] L0-Case**:
> Choose a common opening word with a mix of vowels and consonants, such as 'crane', to maximize information gain...

**[G2] L0-Case**:
> Choose a common opening word with a mix of vowels and consonants, such as 'crane', to maximize information gain...

**[G3] L0-Case**:
> Choose a common opening word with a mix of vowels and consonants, such as 'crane', to maximize information gain...

**[G5] L0-Case**:
> Choose a consistent set of information-rich opening words with a mix of vowels and consonants, such as 'crane' or 'soare'...

📊 **分析**：G1, G2, G3, G5 几乎完全相同，都在说"用crane/soare开局"。

#### ❌ 问题2：与游戏配置不符

**[G4] L0-Case**:
> Initial Guess 6-Letter: Use a predefined list of high-entropy words with a mix of common and less common letters to maximize information gain in **6-letter Wordle games**.

**[G6] L0-Case**:
> Initial Guess 6-Letter: Use a predefined list of high-entropy words... in **6-letter Wordle games**.

📊 **分析**：提到6字母游戏，但配置是4字母（level: 4），经验不适用。

#### ❌ 问题3：只关注第一步，缺少推理过程

所有7条经验都关于 **"Initial Guess"（第一次猜测）**，完全没有涉及：
- 如何处理 GREEN/YELLOW/GRAY 反馈 ❌
- 如何在第2-10轮进行约束推理 ❌
- 如何避免违反已知约束 ❌
- 如何快速收敛到答案 ❌

---

### 优化版（手动编写）的9条经验

#### ✅ **2条 L2 元策略**（最高层次）

**[L2-META-1] 约束驱动迭代优化**:
```
Treat Wordle as a constraint satisfaction problem. After each guess, immediately 
update three constraint sets:
1. LOCKED positions from GREEN feedback - MUST stay
2. INCLUDED letters from YELLOW feedback - MUST appear but NOT in tested positions
3. EXCLUDED letters from GRAY feedback - MUST NEVER appear again

Each subsequent guess should satisfy ALL accumulated constraints while maximizing 
information gain on remaining unknown positions.
```

**特点**：
- 🎯 将 Wordle 建模为约束满足问题（高层抽象）
- 🎯 定义了3类约束的管理方法
- 🎯 强调"每次猜测满足所有约束"的原则
- 🎯 适用于任何长度的 Wordle 游戏

**[L2-META-2] 渐进式假设消除**:
```
View each round as eliminating a hypothesis space:
- Round 1: broad exploration (test 4 different common letters)
- Rounds 2-3: narrow down (focus on placing YELLOW letters, test new letters)
- Rounds 4+: exploit constraints (only guess words satisfying ALL known constraints)

Never waste a guess on words containing GRAY letters or violating GREEN/YELLOW constraints.
```

**特点**：
- 🎯 定义了清晰的多轮策略（探索 → 缩小 → 利用）
- 🎯 每轮有明确目标
- 🎯 强调不浪费猜测机会
- 🎯 可迁移到不同难度的问题

---

#### ✅ **4条 L1 通用模式**（中层次）

**[L1-PATTERN-1] GREEN反馈利用**:
```
When you get GREEN feedback, that position is SOLVED. Lock it immediately and 
NEVER change it in future guesses. Build your next guess around these anchors.

Example: If position 2 is GREEN='A', all future guesses must have 'A' at position 2.
This dramatically reduces the search space - a single GREEN reduces possibilities by ~96%.
```

**特点**：
- ✅ 针对 GREEN 反馈的具体处理策略
- ✅ 强调"永远锁定"的原则
- ✅ 提供量化理解（减少96%可能性）
- ✅ 给出具体示例

**[L1-PATTERN-2] YELLOW反馈位置轮转**:
```
YELLOW means the letter EXISTS but is MISPLACED. Systematically try this letter 
in ALL other positions (except where it was tested and failed).

Create a mental map: 'E' is YELLOW at position 1 → try 'E' at positions 2, 3, 4 
in subsequent guesses. Don't give up on a YELLOW letter until you've found its 
correct position (it WILL turn GREEN eventually).
```

**特点**：
- ✅ 针对 YELLOW 反馈的系统化处理
- ✅ 强调"系统轮转"而非随机尝试
- ✅ 提供心智模型（mental map）
- ✅ 保证最终会找到正确位置

**[L1-PATTERN-3] GRAY反馈严格消除**:
```
GRAY is absolute - that letter does NOT exist in the target word. Immediately 
remove it from your mental vocabulary for this game.

If 'R', 'S', 'T' are GRAY, the answer CANNOT be 'REST', 'STAR', 'ARTS', etc.
This is the fastest way to shrink the candidate space. One guess can eliminate 
4 letters (4 GRAYS) = eliminates thousands of words.
```

**特点**：
- ✅ 针对 GRAY 反馈的绝对性
- ✅ 强调立即消除，不再考虑
- ✅ 提供具体反例说明
- ✅ 量化效果（消除数千词）

**[L1-PATTERN-4] 后期多约束综合**:
```
By round 3-4, you typically have multiple constraints: some GREEN positions, 
some YELLOW letters needing placement, and many GRAY exclusions.

Your next guess MUST satisfy ALL constraints simultaneously. Method:
1. Start with GREEN positions as template (e.g., '_A_E' if positions 2,4 are GREEN)
2. Place YELLOW letters in untested positions
3. Fill remaining positions with new common letters NOT in GRAY list
4. Verify the resulting word is valid English
```

**特点**：
- ✅ 针对后期复杂情况
- ✅ 提供4步系统化方法
- ✅ 强调"同时满足所有约束"
- ✅ 实用性强

---

#### ✅ **3条 L0 具体案例**（低层次）

**[L0-CASE-1] 4字母开局策略**:
```
For 4-letter Wordle, start with words containing 4 different common letters 
with good vowel-consonant mix. Recommended: 'tale', 'soar', 'mile', 'cone'.
These cover the most frequent 4-letter word patterns.

Avoid double letters in the first guess (e.g., 'ball', 'miss') as they waste 
information potential.
```

**特点**：
- ✅ 专门针对4字母游戏（匹配实际配置）
- ✅ 提供具体推荐词（tale, soar, mile, cone）
- ✅ 解释为什么避免双字母
- ✅ 实用性高

**[L0-CASE-2] 混合反馈示例**:
```
Suppose Round 1 guess 'TALE' gives feedback:
- T=GRAY, A=GREEN (pos 2), L=YELLOW, E=GRAY

Analysis: 
- Position 2 is 'A' (locked)
- Letter 'L' exists but not at position 3
- Letters T, E don't exist

Round 2 strategy: guess '_A L_' pattern with 'L' NOT at position 3, no T/E, 
test new letters. Try 'LAID', 'PALM', 'WALK' depending on 'L' placement hypothesis.
```

**特点**：
- ✅ 提供完整的推理示例
- ✅ 展示如何分析混合反馈
- ✅ 给出具体的后续策略
- ✅ 可学习的案例

**[L0-CASE-3] 多YELLOW恢复**:
```
If Round 1 gives 2-3 YELLOW letters, don't panic - this is valuable information.

Round 2 goal: rearrange these YELLOWs into different positions while testing 1-2 
new letters.

Example: If 'SOAR' gives S=YELLOW, O=YELLOW, A=GRAY, R=YELLOW, then 'S', 'O', 'R' 
are all in the word but misplaced. Round 2 should test permutations: try 'ROSE', 
'ORES', 'ROBS', etc., systematically rotating their positions until they turn GREEN.
```

**特点**：
- ✅ 处理特殊情况（多YELLOW）
- ✅ 提供心理支持（don't panic）
- ✅ 给出系统化解决方案
- ✅ 具体示例

---

## 🎯 核心改进总结

### 1. **层次分布优化**

```
原版：L0(86%) + L1(14%) + L2(0%)  ❌ 不平衡
       ↓
优化版：L0(33%) + L1(44%) + L2(22%)  ✅ 平衡
```

**意义**：
- L2 元策略：提供最强泛化能力，适用于所有题目
- L1 模式：提供通用方法，可迁移到不同场景
- L0 案例：提供具体示例，帮助理解

### 2. **内容覆盖优化**

```
原版：100% 关注 "第一次猜测"  ❌ 片面
       ↓
优化版：
  - 开局策略: 11% (1/9)
  - 反馈处理: 33% (3/9) ← GREEN/YELLOW/GRAY
  - 约束管理: 33% (3/9) ← 多轮推理
  - 整体策略: 22% (2/9) ← L2 元策略
       ✅ 全面
```

### 3. **实用性优化**

**原版问题**：
- ❌ 6条重复说同一件事（信息冗余）
- ❌ 2条提到6字母游戏（配置不符）
- ❌ 0条关于如何处理反馈（核心缺失）

**优化版特点**：
- ✅ 每条经验独特，无重复
- ✅ 所有经验适配4字母配置
- ✅ 重点关注反馈处理和约束推理

### 4. **可操作性优化**

**原版**：
> "Choose a common opening word with a mix of vowels and consonants..."
- 模糊，没有具体指导

**优化版**：
> "For 4-letter Wordle, start with: 'tale', 'soar', 'mile', 'cone'"
- 具体，可直接执行

> "Method: (1) Start with GREEN positions as template (2) Place YELLOW letters (3) Fill with new letters (4) Verify"
- 分步骤，清晰可执行

---

## 📈 预期效果对比

| 指标 | 原版（自动生成） | 优化版（手动编写） | 预期提升 |
|------|-----------------|------------------|---------|
| **准确率** | 基线 + 0-2% | 基线 + 5-15% | +3-13% |
| **开局质量** | 提升 | 提升 | 持平 |
| **推理能力** | 无提升 | 显著提升 | +++ |
| **约束满足** | 无提升 | 提升 | ++ |
| **收敛速度** | 无提升 | 提升 | ++ |
| **错误减少** | 无变化 | 减少 | -- |

---

## 🧪 验证方法

### 定量指标

1. **整体准确率**（核心指标）
   ```bash
   原版: ___%
   优化版: ___%
   提升: +___% 
   ```

2. **平均轮次**（收敛速度）
   ```bash
   原版: ___ rounds
   优化版: ___ rounds
   减少: -___ rounds
   ```

3. **违反约束次数**（推理质量）
   - 统计重复使用GRAY字母的次数
   - 统计改变GREEN位置的次数
   - 统计忽略YELLOW字母的次数

### 定性指标

1. **轨迹分析**
   - 查看具体游戏轨迹
   - 检查是否正确应用了约束
   - 检查推理过程是否合理

2. **错误模式分析**
   - 原版常见错误类型
   - 优化版是否减少了这些错误

---

## 💡 关键洞察

### 为什么手动优化可能有效？

1. **针对性强**
   - 针对 Wordle 游戏的核心难点（约束推理）
   - 针对实际配置（4字母）
   - 针对缺失部分（反馈处理）

2. **质量可控**
   - 每条经验都经过精心设计
   - 避免了自动生成的常见问题（重复、无关）
   - 确保覆盖关键流程

3. **层次完整**
   - L2 提供高层指导
   - L1 提供具体方法
   - L0 提供实例示范
   - 三层协同作用

### 对自动生成的启示

如果手动优化有效，说明：

1. **经验内容比数量更重要**
   - 7条重复经验 < 3条高质量独特经验

2. **需要改进经验生成的 Prompt**
   - 引导关注核心难点（推理过程）
   - 避免生成重复内容
   - 确保层次平衡

3. **需要经验质量评估机制**
   - 自动检测重复经验
   - 评估经验覆盖度
   - 筛选高质量经验

---

## 🚀 测试命令

```bash
# 快速测试（Windows）
test_manual_experiences.bat

# 或手动执行
cd F:\youtu-agent
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_20_eval --force
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval
uv run python scripts/korgym/view_korgym_results.py wordle_practice_20_eval
uv run python scripts/korgym/analyze_wordle_top20.py --exp_id wordle_practice_20_eval --count 20
```

---

**📂 相关文件**：
- 优化后 Agent: `configs/agents/practice/wordle_practice_20_l4_agent.yaml`
- 原版备份: `configs/agents/practice/wordle_practice_20_l4_agent_original.yaml.backup`
- 测试指南: `TEST_MANUAL_EXPERIENCES.md`
- 分析文档: `analyze_wordle_no_improvement.md`

---

**期待你的测试结果！🎯**


