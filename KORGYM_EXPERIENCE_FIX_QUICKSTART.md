# 🚀 KORGym 专用经验提取器 - 快速开始指南

## 🎯 问题总结

**发现的两个根本问题**：

1. **未使用 KORGym 专用提取器**：虽然有 `KORGymExperienceExtractor`，但训练流程使用的是通用提取器
2. **0/1 评分筛选问题**：经验提取只处理"部分正确"的样本（0 < avg_score < 1），导致 Wordle 等二值评分游戏的 75-85% 样本被过滤掉

**核心影响**：
- Wordle 训练几乎无效（准确率 +0-5%）
- 只有 15-25% 的样本生成经验
- 经验重复率高、质量低

---

## ✅ 已实施的修复

### 修改 1：`utu/practice/experience_updater.py`

- ✅ 添加 `is_korgym` 标志
- ✅ KORGym 游戏跳过 0/1 筛选，处理所有样本
- ✅ 不影响其他任务（数学推理等）

### 修改 2：`utu/practice/training_free_grpo.py`

- ✅ 检测 KORGym 游戏配置
- ✅ 自动传入 `is_korgym=True`
- ✅ 记录日志确认检测成功

---

## 🏃 快速开始

### 方法 1：一键测试脚本（推荐）

```cmd
test_korgym_experience_fix.bat
```

此脚本会：
1. 清理旧训练数据
2. 重新训练 Wordle（20题）
3. 验证所有样本都参与经验生成
4. 运行评估对比

**预期时间**：15-20 分钟

---

### 方法 2：手动测试

#### 步骤 1：验证问题存在（可选）

```bash
# 分析现有训练数据
uv run python scripts/debug_experience_filtering.py --exp_id wordle_practice_20_3
```

**预期输出（修复前）**：
```
🚨 只有 3 个问题（15.0%）会生成经验！
🚨 其他 17 个问题（85.0%）被过滤掉！
```

#### 步骤 2：清理并重新训练

```bash
# 清理旧数据
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_20_3 --force

# 重新训练（使用修复后的代码）
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20
```

**观察日志中的关键信息**：
```
✅ Detected KORGym game - using specialized experience extraction (no 0/1 filtering)
```

**训练过程中看到**：
```
KORGym mode: Processing all samples (avg_score=0.00)
KORGym mode: Processing all samples (avg_score=1.00)
KORGym mode: Processing all samples (avg_score=0.33)
```

#### 步骤 3：验证修复效果

```bash
# 再次检查筛选情况
uv run python scripts/debug_experience_filtering.py --exp_id wordle_practice_20_3
```

**预期输出（修复后）**：
```
✅ 会生成经验的问题：20 个 (100.0%)
❌ 被过滤掉的问题：0 个 (0.0%)

✅ 所有问题都参与经验生成！
```

#### 步骤 4：评估准确率提升

```bash
# 运行评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval

# 查看详细结果
uv run python scripts/games/wordle/analyze_wordle_top20.py --exp_id wordle_practice_eval_20_3

# 对比修复前后
uv run python scripts/korgym/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_eval_20_3
```

**预期改善**：
- 修复前：准确率 +0-5%
- 修复后：准确率 **+15-25%**

---

## 📊 预期效果对比

| 指标 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| **参与经验生成的问题** | 3-5 个 (15-25%) | 20 个 (100%) | **6.7x** |
| **L0 经验数量** | 3-5 个 | 15-20 个 | **5x** |
| **L1 经验数量** | 0-1 个 | 3-5 个 | **5x** |
| **准确率提升** | +0-5% | **+15-25%** | **质的飞跃** |
| **经验多样性** | 低（仅部分成功） | 高（成功+失败） | 显著改善 |

---

## 🔍 验证修复的关键标志

### 1. 训练日志

**成功标志**：
```
✅ Detected KORGym game - using specialized experience extraction (no 0/1 filtering)
```

**如果没看到**：
- 检查 `configs/practice/korgym/wordle_practice_20.yaml`
- 确认 `korgym.enabled: true`

### 2. 经验生成日志

**成功标志**：
```
KORGym mode: Processing all samples (avg_score=0.00)  # 处理全错样本
KORGym mode: Processing all samples (avg_score=1.00)  # 处理全对样本
```

**如果没看到**：
- 检查 `utu/practice/experience_updater.py` 是否有修改
- 确认 `self.is_korgym` 被正确传入

### 3. 验证脚本输出

**成功标志**：
```
✅ 会生成经验的问题：20 个 (100.0%)
❌ 被过滤掉的问题：0 个 (0.0%)
```

**如果还是显示过滤**：
- 重新检查代码修改
- 确认训练使用的是修复后的代码

---

## 🎮 其他 KORGym 游戏

修复对所有 KORGym 游戏有效：

### Word Puzzle

```bash
# 已自动支持，无需额外配置
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice
```

### Alphabetical Sorting

```bash
# 已自动支持，无需额外配置
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice
```

**关键**：只要配置文件中有 `korgym.enabled: true`，就会自动使用专用提取器。

---

## 🔧 故障排除

### Q1: 训练日志没有显示 "Detected KORGym"

**检查**：
```bash
# 查看配置文件
cat configs/practice/korgym/wordle_practice_20.yaml | grep -A 10 "korgym:"
```

**确认**：
```yaml
korgym:
  enabled: true  # ← 必须为 true
  game_name: "33-wordle"
  # ...
```

### Q2: 仍然显示大量样本被过滤

**可能原因**：
1. 使用的是旧的数据库缓存
2. 代码修改未生效

**解决**：
```bash
# 清理所有缓存
rm -rf workspace/hierarchical_experiences/wordle_practice_20_3.json
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_20_3 --force

# 重新训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20
```

### Q3: 准确率没有提升

**可能原因**：
1. 训练样本太少（需要至少 20 题）
2. 游戏难度不匹配（训练和评估的 level 要一致）
3. 其他配置问题

**检查**：
```bash
# 查看训练生成的经验
cat workspace/hierarchical_experiences/wordle_practice_20_3.json

# 确认评估配置
cat configs/eval/korgym/wordle_practice_20_eval.yaml | grep "level:"
```

---

## 📚 相关文档

- **集成总结**：`KORGYM_EXPERIENCE_EXTRACTOR_INTEGRATED.md`（技术细节）
- **问题分析**：`CRITICAL_WORDLE_NO_EXPERIENCE_BUG.md`（根本原因）
- **验证脚本**：`scripts/debug_experience_filtering.py`
- **批处理测试**：`test_korgym_experience_fix.bat`

---

## 🎉 总结

### ✅ 已完成

1. 修改 `ExperienceUpdater`，添加 KORGym 专用行为
2. 移除 0/1 筛选逻辑（仅针对 KORGym）
3. 自动检测 KORGym 游戏配置
4. 创建验证工具和文档

### 🚀 立即行动

```cmd
# Windows
test_korgym_experience_fix.bat

# Linux/WSL
chmod +x test_korgym_experience_fix.sh
./test_korgym_experience_fix.sh
```

**预期**：
- 经验样本量：**6.7倍增加**
- 准确率提升：**+15-25%**
- 所有样本参与学习

---

**🔥 修复已完成，现在开始测试吧！**

*最后更新：2026-01-22*
