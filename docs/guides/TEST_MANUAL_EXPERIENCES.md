# 🧪 测试手动优化经验的效果

## 📋 实验设置

### 对比对象

| Agent | 经验来源 | 经验数量 | 经验质量 |
|-------|---------|---------|---------|
| **原版** | 自动学习生成 | 7条 (6xL0 + 1xL1) | ❌ 重复、只关注开局 |
| **优化版** | 手动精心编写 | 9条 (3xL0 + 4xL1 + 2xL2) | ✅ 多样、关注推理过程 |

---

## 🎯 优化版经验的核心改进

### ✅ **新增：2条 L2 元策略**（最高层次，最强泛化能力）

1. **[L2-META-1] 约束驱动迭代优化**
   - 将 Wordle 视为约束满足问题
   - 维护 3 个约束集：LOCKED（GREEN）、INCLUDED（YELLOW）、EXCLUDED（GRAY）
   - 每次猜测必须满足所有累积约束

2. **[L2-META-2] 渐进式假设消除**
   - Round 1: 广度探索（测试4个不同字母）
   - Rounds 2-3: 缩小范围（放置YELLOW字母，测试新字母）
   - Rounds 4+: 利用约束（仅猜满足所有约束的词）

### ✅ **新增：4条 L1 通用模式**（中层次，可迁移）

1. **[L1-PATTERN-1] GREEN反馈利用**
   - GREEN位置已解决，永远锁定
   - 以GREEN位置为锚点构建后续猜测
   - 单个GREEN减少96%可能性

2. **[L1-PATTERN-2] YELLOW反馈位置轮转**
   - YELLOW = 字母存在但位置错误
   - 系统地在所有其他位置尝试
   - 创建心智地图跟踪测试过的位置

3. **[L1-PATTERN-3] GRAY反馈严格消除**
   - GRAY是绝对的 - 字母不存在
   - 立即从候选空间删除
   - 4个GRAY可消除数千个单词

4. **[L1-PATTERN-4] 后期多约束综合**
   - Round 3-4通常有多个约束
   - 下一次猜测必须同时满足所有约束
   - 方法：GREEN模板 → 放置YELLOW → 填充新字母（非GRAY）→ 验证有效

### ✅ **优化：3条 L0 具体案例**（低层次，提供示例）

1. **[L0-CASE-1] 4字母开局策略**
   - 推荐：tale, soar, mile, cone
   - 避免双字母（浪费信息潜力）

2. **[L0-CASE-2] 混合反馈示例**
   - 具体演示如何处理 GREEN + YELLOW + GRAY 的组合
   - TALE → T=GRAY, A=GREEN(pos2), L=YELLOW, E=GRAY
   - Round 2: _AL_ 模式，L不在pos3，无T/E

3. **[L0-CASE-3] 多YELLOW恢复**
   - 处理2-3个YELLOW的策略
   - 系统性轮转位置直到变GREEN

---

## 🚀 测试步骤

### 步骤 1: 清理旧评估结果

```bash
cd F:\youtu-agent

# 删除之前的评估结果（如果有）
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_20_eval wordle_practice_eval_20_1
```

### 步骤 2: 使用优化版 Agent 进行评估

```bash
# 评估优化版（手动编写经验）
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval
```

**配置文件**：`configs/eval/korgym/wordle_practice_20_eval.yaml`
**使用的 Agent**：`configs/agents/practice/wordle_practice_20_l4_agent.yaml` (已优化)

### 步骤 3: 对比基线结果

如果你有基线评估（无经验的版本），可以对比：

```bash
# 查看所有 Wordle 评估结果
uv run python scripts/utils/clean_experiment_data.py --list
```

找到基线实验ID（例如 `wordle_eval`），然后对比：

```bash
# 方法1: 使用对比脚本
uv run python scripts/korgym/compare_korgym_results.py \
  --baseline wordle_eval \
  --enhanced wordle_practice_20_eval

# 方法2: 查看详细结果
uv run python scripts/korgym/view_korgym_results.py wordle_eval
uv run python scripts/korgym/view_korgym_results.py wordle_practice_20_eval
```

### 步骤 4: 分析前20题表现

由于训练集是20题，可以重点关注评估集前20题的表现：

```bash
# 分析基线的前20题
uv run python scripts/korgym/analyze_wordle_top20.py --exp_id wordle_eval --count 20

# 分析优化版的前20题
uv run python scripts/korgym/analyze_wordle_top20.py --exp_id wordle_practice_20_eval --count 20
```

---

## 📊 预期结果

### 如果优化有效，你会看到：

✅ **准确率提升 5-15%**
- 原版（自动生成）：可能无提升或仅+1-2%
- 优化版（手动编写）：预期 +5-15%

✅ **后期轮次表现改善**
- 更少的无效猜测（违反约束的猜测）
- 更快的收敛速度（3-5轮内解决）
- 更少的超时/失败

✅ **错误类型减少**
- 减少重复使用GRAY字母的错误
- 减少违反GREEN锁定位置的错误
- 减少忽略YELLOW字母的错误

---

## 🔍 如果仍然没有提升

### 可能原因：

1. **基线Prompt已经很强**
   - 你的基础 instructions 已经覆盖了核心策略
   - 经验只是重复了 Prompt 中的内容

2. **LLM能力限制**
   - Qwen2.5-72B 在复杂约束推理上可能有限
   - 可尝试更强模型（如 Qwen2.5-110B 或 DeepSeek）

3. **评估集与训练集差异大**
   - 评估集 seeds 1-50，训练集 seeds 51-70
   - 不同 seed → 完全不同的目标词
   - 经验可能难以泛化

4. **数据量仍然太小**
   - 20题训练集覆盖的模式有限
   - 需要增加到 50-100 题

### 下一步尝试：

```bash
# 选项A: 增加训练数据到50题
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --train_seeds_start 51 \
  --train_seeds_end 100 \
  --level 4

# 修改 configs/practice/korgym/wordle_practice_50.yaml
# 重新训练并评估

# 选项B: 尝试更强的模型
# 修改 model: 改为 Qwen/Qwen2.5-110B-Instruct 或 deepseek-chat

# 选项C: 降低temperature增加确定性
# temperature: 0.3 → 0.1
```

---

## 📝 记录对比结果

### 基线（无经验）：

```
实验ID: wordle_eval
准确率: ____%
平均得分: ____
成功/总数: ___/50
```

### 原版（自动生成经验）：

```
实验ID: wordle_practice_20_eval (before manual optimization)
准确率: ____%
平均得分: ____
成功/总数: ___/50
提升: +___% (vs 基线)
```

### 优化版（手动编写经验）：

```
实验ID: wordle_practice_20_eval (after manual optimization)
准确率: ____%
平均得分: ____
成功/总数: ___/50
提升: +___% (vs 基线)
提升: +___% (vs 原版)
```

---

## 🎯 快速一键测试

```bash
# 完整测试流程（Windows PowerShell）
cd F:\youtu-agent

# 1. 清理旧结果
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_20_eval

# 2. 运行评估（使用优化版Agent）
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval

# 3. 查看结果
uv run python scripts/korgym/view_korgym_results.py wordle_practice_20_eval

# 4. 分析前20题
uv run python scripts/korgym/analyze_wordle_top20.py --exp_id wordle_practice_20_eval --count 20

# 5. 对比基线（如果有）
uv run python scripts/korgym/compare_korgym_results.py --baseline wordle_eval --enhanced wordle_practice_20_eval
```

---

## 📂 相关文件

- **优化后的 Agent**: `configs/agents/practice/wordle_practice_20_l4_agent.yaml`
- **原始备份**: `configs/agents/practice/wordle_practice_20_l4_agent_original.yaml.backup`
- **评估配置**: `configs/eval/korgym/wordle_practice_20_eval.yaml`
- **分析文档**: `analyze_wordle_no_improvement.md`

---

## 💡 关键洞察

这个实验的意义：

1. **验证经验质量的重要性**
   - 不是"有经验"就够了
   - 需要"高质量、多样化、关注关键过程"的经验

2. **对比自动生成 vs 手动优化**
   - 自动生成：可能重复、浅层、关注简单部分
   - 手动优化：针对性强、深度推理、覆盖核心难点

3. **为改进自动生成提供参考**
   - 如果手动经验有效 → 说明经验内容很重要
   - 可以改进 LLM 经验生成的 prompt，引导其生成类似质量的经验

---

**🚀 开始测试吧！期待看到结果！**


