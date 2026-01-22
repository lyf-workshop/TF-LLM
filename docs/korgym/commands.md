# KORGym三个游戏执行命令速查 ⚡

## 📋 游戏信息

| 游戏 | 游戏ID | 端口 | 类型 | 回合数 |
|------|--------|------|------|--------|
| **Word Puzzle** | 8-word_puzzle | 8775 | 单轮 | 1 |
| **Alphabetical Sorting** | 22-alphabetical_sorting | 8776 | 单轮 | 1 |
| **Wordle** | 33-wordle | 8777 | 多轮 | 6 |

---

## 🎮 游戏1: Word Puzzle

### 终端1: 启动游戏服务器
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

### 终端2: 完整流程
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 1. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# 2. 基线评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval

# 5. 查看结果
cat workspace/word_puzzle_baseline_eval/score.txt
cat workspace/word_puzzle_practice_eval/score.txt
```

---

## 🎮 游戏2: Alphabetical Sorting

### 终端1: 启动游戏服务器
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8776
```

### 终端2: 完整流程
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 1. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"

# 2. 基线评估
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval

# 5. 查看结果
cat workspace/alphabetical_sorting_baseline_eval/score.txt
cat workspace/alphabetical_sorting_practice_eval/score.txt
```

---

## 🎮 游戏3: Wordle（多轮交互游戏）⭐

**特点**: 
- 🔄 多轮交互游戏（最多10次尝试）
- 📏 单词长度：4-12字母（随机）
- 🎯 评分：猜中=1分，失败=0分
- ✅ 系统已完全支持多轮评估

### 终端1: 启动游戏服务器
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

### 终端2: 完整流程
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 0. 小规模测试（推荐先执行）
uv run python scripts/test_multiround_eval.py --game_name "33-wordle" --seeds 1 2 --verbose

# 1. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 2. 基线评估（✅ 支持完整的10轮交互）
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 5. 查看结果（推荐使用专用脚本）
uv run python scripts/view_korgym_results.py --game wordle

# 6. 统计前20题得分情况（新增）
uv run python scripts/analyze_wordle_top20.py --exp_id wordle_eval
uv run python scripts/analyze_wordle_top20.py --exp_id wordle_practice_eval
# 或统计前N题（例如前10题）
uv run python scripts/analyze_wordle_top20.py --exp_id wordle_eval --count 10
```

---

## 🚀 一键复制命令（按游戏）

### Word Puzzle - 所有命令
```bash
# ===== Word Puzzle =====
# [终端1] 启动服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle && python game_lib.py -p 8775

# [终端2] 运行流程
cd /mnt/f/youtu-agent && source .venv/bin/activate
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
echo "===== Results =====" && cat workspace/word_puzzle_baseline_eval/score.txt && echo "---" && cat workspace/word_puzzle_practice_eval/score.txt
```

### Alphabetical Sorting - 所有命令
```bash
# ===== Alphabetical Sorting =====
# [终端1] 启动服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting && python game_lib.py -p 8776

# [终端2] 运行流程
cd /mnt/f/youtu-agent && source .venv/bin/activate
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
echo "===== Results =====" && cat workspace/alphabetical_sorting_baseline_eval/score.txt && echo "---" && cat workspace/alphabetical_sorting_practice_eval/score.txt
```

### Wordle - 所有命令
```bash
# ===== Wordle =====
# [终端1] 启动服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle && python game_lib.py -p 8777

# [终端2] 运行流程
cd /mnt/f/youtu-agent && source .venv/bin/activate
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
echo "===== Results =====" && cat workspace/wordle_baseline_eval/score.txt && echo "---" && cat workspace/wordle_practice_eval/score.txt
```

---

## 📊 批量运行脚本

创建自动化脚本：

```bash
cat > /mnt/f/youtu-agent/run_all_three_games.sh << 'EOF'
#!/bin/bash
set -e

cd /mnt/f/youtu-agent
source .venv/bin/activate

echo "🎮 Starting KORGym Three Games Training Pipeline"
echo "================================================"
echo ""

# Game 1: Word Puzzle
echo "📝 [1/3] Word Puzzle (8-word_puzzle)"
echo "⚠️  Please ensure game server is running on port 8775"
read -p "Press Enter when ready..."

uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
echo "✅ Word Puzzle completed"
echo ""

# Game 2: Alphabetical Sorting
echo "🔤 [2/3] Alphabetical Sorting (22-alphabetical_sorting)"
echo "⚠️  Please switch game server to port 8776"
read -p "Press Enter when ready..."

uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
echo "✅ Alphabetical Sorting completed"
echo ""

# Game 3: Wordle
echo "🎯 [3/3] Wordle (33-wordle)"
echo "⚠️  Please switch game server to port 8777"
read -p "Press Enter when ready..."

uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
echo "✅ Wordle completed"
echo ""

# Summary
echo "================================================"
echo "🎉 All Games Completed!"
echo "================================================"
echo ""
echo "📊 Results Summary:"
echo ""
echo "--- Word Puzzle ---"
cat workspace/word_puzzle_baseline_eval/score.txt 2>/dev/null || echo "No results"
cat workspace/word_puzzle_practice_eval/score.txt 2>/dev/null || echo "No results"
echo ""
echo "--- Alphabetical Sorting ---"
cat workspace/alphabetical_sorting_baseline_eval/score.txt 2>/dev/null || echo "No results"
cat workspace/alphabetical_sorting_practice_eval/score.txt 2>/dev/null || echo "No results"
echo ""
echo "--- Wordle ---"
cat workspace/wordle_baseline_eval/score.txt 2>/dev/null || echo "No results"
cat workspace/wordle_practice_eval/score.txt 2>/dev/null || echo "No results"
echo ""
echo "✅ All results saved in workspace/"
EOF

chmod +x /mnt/f/youtu-agent/run_all_three_games.sh
```

**运行批量脚本**：
```bash
cd /mnt/f/youtu-agent
./run_all_three_games.sh
```

---

## 🔍 结果查看

### 📊 推荐方式：使用专用脚本（符合论文评分标准）

```bash
cd /mnt/f/youtu-agent

# 查看所有游戏的对比结果
uv run python scripts/view_korgym_results.py --game all

# 查看单个游戏的对比
uv run python scripts/view_korgym_results.py --game word_puzzle
uv run python scripts/view_korgym_results.py --game alphabetical_sorting
uv run python scripts/view_korgym_results.py --game wordle

# 查看单个实验的详细结果
uv run python scripts/view_korgym_results.py --exp_id word_puzzle_baseline_eval --detailed
uv run python scripts/view_korgym_results.py --exp_id word_puzzle_practice_eval --detailed

# 对比两个实验
uv run python scripts/view_korgym_results.py --compare word_puzzle_baseline_eval word_puzzle_practice_eval
```

### 📈 评分机制说明

**Word Puzzle (Crossword)**:
- 评分 = 答对的单词数 / 总单词数
- 例如：5个单词答对3个 = 0.6分
- Success = score > 0
- 论文指标：Average Score（平均得分）

**Alphabetical Sorting (Word Path Puzzle)**:
- 评分 = 0或1（找到正确路径=1，否则=0）
- Success = score > 0
- 论文指标：Accuracy（准确率）

**Wordle** (多轮交互):
- 评分 = 0或1（10次内猜中=1，否则=0）
- Success = score == 1
- 论文指标：Accuracy（准确率）
- 特点：✅ 完整支持多轮交互评估

### 📊 Wordle前20题详细统计（新增功能）

```bash
# 统计基线评估的前20题得分
uv run python scripts/analyze_wordle_top20.py --exp_id wordle_eval

# 统计训练后评估的前20题得分
uv run python scripts/analyze_wordle_top20.py --exp_id wordle_practice_eval

# 统计前N题（例如前10题）
uv run python scripts/analyze_wordle_top20.py --exp_id wordle_eval --count 10
```

**输出示例**：
```
================================================================================
Wordle 前 20 题得分统计
================================================================================
实验ID: wordle_eval
游戏: 33-wordle
================================================================================

题号    Seed     得分      结果      状态
--------------------------------------------------------------------------------
1       1        1.0000    正确      ✅ 成功
2       2        0.0000    错误      ❌ 失败
3       3        1.0000    正确      ✅ 成功
...

================================================================================
统计摘要
================================================================================
总题数: 20
成功数: 12
失败数: 8
准确率 (Accuracy): 60.00%
平均得分 (Avg Score): 0.6000
总得分: 12.00

得分分布:
  1.0分 (成功):  12 题 ( 60.0%)
  0.0分 (失败):   8 题 ( 40.0%)

连续表现:
  最长连续成功: 3 题
  最长连续失败: 2 题

前后对比 (前10题 vs 后10题):
  前10题准确率: 50.00% (5/10)
  后10题准确率: 70.00% (7/10)
  ✅ 后10题表现更好，提升了 20.00%
================================================================================
```

### 🗂️ 传统方式：查看文件

```bash
cd /mnt/f/youtu-agent

# Word Puzzle
echo "=== Word Puzzle ==="
echo "Baseline:" && cat workspace/word_puzzle_baseline_eval/score.txt
echo "Practice:" && cat workspace/word_puzzle_practice_eval/score.txt
echo ""

# Alphabetical Sorting
echo "=== Alphabetical Sorting ==="
echo "Baseline:" && cat workspace/alphabetical_sorting_baseline_eval/score.txt
echo "Practice:" && cat workspace/alphabetical_sorting_practice_eval/score.txt
echo ""

# Wordle
echo "=== Wordle ==="
echo "Baseline:" && cat workspace/wordle_baseline_eval/score.txt
echo "Practice:" && cat workspace/wordle_practice_eval/score.txt
```

### 📚 查看提取的经验

```bash
# Word Puzzle经验
cat workspace/hierarchical_experiences/word_puzzle_practice.json | jq '.stats'

# Alphabetical Sorting经验
cat workspace/hierarchical_experiences/alphabetical_sorting_practice.json | jq '.stats'

# Wordle经验
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.stats'
```

---

## ⚙️ 重要提醒

1. **游戏服务器必须先启动**
   - 每个游戏使用不同端口
   - 在运行评估/训练前确保服务器正在运行

2. **数据集命名**
   - Word Puzzle: `KORGym-WordPuzzle-Eval-50` / `KORGym-WordPuzzle-Train-100`
   - Alphabetical Sorting: `KORGym-AlphabeticalSorting-Eval-50` / `KORGym-AlphabeticalSorting-Train-100`
   - Wordle: `KORGym-Wordle-Eval-50` / `KORGym-Wordle-Train-100`

3. **训练时间估算**
   - Word Puzzle: ~2-3小时
   - Alphabetical Sorting: ~1-2小时（较简单）
   - Wordle: ~2-3小时（多轮游戏）

4. **生成的Agent配置**
   - `configs/agents/practice/word_puzzle_practice_agent.yaml`
   - `configs/agents/practice/alphabetical_sorting_practice_agent.yaml`
   - `configs/agents/practice/wordle_practice_agent.yaml`

5. **清理缓存**
   ```bash
   # 清理评估结果缓存（重新评估前必须执行）
   uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval
   
   # 清理经验缓存（重新训练前执行）
   uv run python scripts/clean_alphabetical_sorting_cache.py --exp_id alphabetical_sorting_practice --force
   
   # 查看所有实验
   uv run python scripts/clean_experiment_data.py --list
   ```

---

## ✅ 快速检查清单

在运行前确认：

### 环境准备
- [ ] WSL环境可访问 `/mnt/f/youtu-agent`
- [ ] 虚拟环境已激活 `source .venv/bin/activate`
- [ ] 环境变量已配置 `.env` 文件

### 游戏服务器
- [ ] Word Puzzle服务器运行在 8775
- [ ] Alphabetical Sorting服务器运行在 8776  
- [ ] Wordle服务器运行在 8777

### 配置文件
- [ ] 已创建12个配置文件（3游戏 × 4文件）
- [ ] 验证函数 `utu/practice/verify/korgym.py` 已更新
- [ ] 训练和评估的`level`参数一致

### 数据集
- [ ] 评估数据集已创建（50个样本，seed 1-50）
- [ ] 训练数据集已创建（100个样本）
- [ ] 数据集名称与配置文件匹配

### 缓存清理
- [ ] 重新评估前清理了评估缓存
- [ ] 重新训练前清理了经验缓存

---

## 🐛 常见问题排查

### 问题1: 评估准确率显示0%

**症状**: `view_korgym_results.py`或`view_training_results.py`显示0%准确率

**可能原因**:
1. ✅ **评估结果被缓存** - 数据库中存在旧的评估结果
2. ✅ **配置level不匹配** - 训练和评估使用不同难度
3. ✅ **数据集不存在** - 评估数据集未创建或名称不匹配
4. ✅ **游戏服务器未运行** - 服务器崩溃或端口错误

**解决方案**:
```bash
# Step 1: 检查并分析当前结果
uv run python scripts/analyze_word_puzzle_results.py --exp_id word_puzzle_baseline_eval

# Step 2: 清理评估缓存
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval

# Step 3: 检查配置一致性
grep "level:" configs/practice/word_puzzle_practice.yaml
grep "level:" configs/eval/korgym/word_puzzle_eval.yaml

# Step 4: 重新运行评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# Step 5: 查看新结果
uv run python scripts/view_korgym_results.py --exp_id word_puzzle_baseline_eval --detailed
```

### 问题2: 训练时出现429 Rate Limit错误

**症状**: 大量"Rate limit hit, retrying after X.0s: Error code: 429"

**原因**: API请求速率超过限制（TPM limit）

**解决方案**:
```bash
# 方案1: 降低并发数
# 修改 configs/practice/{game}_practice.yaml
# 将 rollout_concurrency: 16 改为 rollout_concurrency: 4

# 方案2: 使用更小的模型
# 将 model: "Qwen/Qwen2.5-72B-Instruct" 改为 "Qwen/Qwen2.5-7B-Instruct"
```

### 问题3: 训练未生成分层经验

**症状**: 训练完成但agent配置中没有L0/L1/L2经验

**原因**: 
1. `hierarchical_learning`配置位置错误
2. 经验被缓存，系统跳过提取

**解决方案**:
```bash
# 检查配置结构（应该在 practice: 部分下，不是顶层）
cat configs/practice/word_puzzle_practice.yaml | grep -A 10 "hierarchical_learning"

# 清理经验缓存
uv run python scripts/clean_alphabetical_sorting_cache.py --exp_id word_puzzle_practice --force

# 重新训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice
```

### 问题4: 游戏服务器500错误

**症状**: "500 Server Error: Internal Server Error for url: http://localhost:XXXX/generate"

**原因**: 游戏服务器崩溃或某些seed生成失败

**解决方案**:
```bash
# 重启游戏服务器（在游戏服务器终端）
# Ctrl+C 停止现有服务器，然后重新启动
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

### 问题5: 数据集meta字段缺失

**症状**: "No game_seed found in meta, cannot judge"

**原因**: 旧版本`prepare_korgym_data.py`使用了错误的字段名

**解决方案**:
```bash
# 重新创建所有数据集
uv run python scripts/clean_and_recreate_datasets.py --force

# 或单独重新创建某个游戏的数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
```

---

## 📊 调试命令集合

```bash
# 查看数据库中的实验列表
uv run python scripts/clean_experiment_data.py --list

# 分析评估结果（详细模式）
uv run python scripts/analyze_word_puzzle_results.py --exp_id word_puzzle_baseline_eval

# 查看KORGym结果（推荐）
uv run python scripts/view_korgym_results.py --game all

# 验证并清理缓存
uv run python scripts/verify_clean.py

# 查看经验提取统计
cat workspace/hierarchical_experiences/word_puzzle_practice.json | jq '.stats'

# 检查Agent配置中的经验
cat configs/agents/practice/word_puzzle_practice_agent.yaml | grep -A 5 "L0\|L1\|L2"

# 测试游戏服务器
curl http://localhost:8775/docs
curl -X POST http://localhost:8775/generate -H "Content-Type: application/json" -d '{"seed": 1}'
```

---

## 🎯 预期输出

每个游戏完成后会生成：

1. **评估结果**
   - `workspace/{game}_baseline_eval/score.txt` - 基线准确率
   - `workspace/{game}_practice_eval/score.txt` - 训练后准确率

2. **经验库**
   - `workspace/hierarchical_experiences/{game}_practice.json` - L0/L1/L2经验

3. **增强Agent**
   - `configs/agents/practice/{game}_practice_agent.yaml` - 包含经验的Agent配置

---

## 🚀 开始运行

选择你想要的方式：

**方式1: 逐个游戏运行**（推荐，便于调试）
- 复制上面对应游戏的命令，一个个执行

**方式2: 使用批量脚本**（全自动）
```bash
cd /mnt/f/youtu-agent
./run_all_three_games.sh
```

**方式3: 自定义顺序**
- 根据需要调整游戏顺序和参数

---

**祝训练顺利！** 🎮✨






