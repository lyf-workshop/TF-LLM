# KORGym 评估指南 📊

## 🎯 概述

本指南说明如何使用 KORGym 评估脚本进行游戏评估，以及如何查看和分析评估结果。

---

## 🚀 使用方法

### 基线评估（无经验）

```bash
uv run python scripts/run_korgym_eval.py \
    --config_name korgym/word_puzzle_baseline
```

### 增强评估（有经验）

```bash
uv run python scripts/run_korgym_eval.py \
    --config_name korgym/word_puzzle_enhanced
```

---

## 📊 输出示例

运行评估时，终端会显示详细的实时结果：

```
======================================================================
KORGym Evaluation: word_puzzle_baseline_eval
======================================================================
Game: 8-word_puzzle
Number of games: 20
Agent: logic_agent_zebralogic

Starting evaluation (20 games)...

Game 1/20 (seed=0)...
  Result: ✓ Success
  Score: 85.0
  Rounds: 1
  Time: 12.34s

Game 2/20 (seed=1)...
  Result: ✗ Failed
  Score: 42.5
  Rounds: 1
  Time: 10.12s

...

======================================================================
Evaluation Summary
======================================================================
Experiment ID: word_puzzle_baseline_eval
Total games: 20
Successful: 8
Failed: 12
Success rate: 40.0%        ← 基线成功率
Average score: 56.75       ← 基线平均分
======================================================================

✓ Results saved to database with exp_id: word_puzzle_baseline_eval
```

**关键指标：**
- **Success rate**: 成功率（百分比）
- **Average score**: 平均得分
- **Total games**: 总游戏局数
- **Successful/Failed**: 成功/失败局数

---

## 🔍 查看评估结果

### 方法 1: 数据库查询（详细数据）

#### 快速查询统计

```bash
sqlite3 database.db << 'EOF'
SELECT 
    exp_id,
    COUNT(*) as total_games,
    SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as success,
    ROUND(AVG(CASE WHEN correct = 1 THEN 100.0 ELSE 0.0 END), 1) as success_rate,
    ROUND(AVG(time_cost), 2) as avg_time
FROM evaluation_data
WHERE exp_id = 'word_puzzle_baseline_eval'
GROUP BY exp_id;
EOF
```

#### 查看每个游戏的详细结果

```bash
sqlite3 database.db << 'EOF'
SELECT 
    dataset_index as seed,
    correct as success,
    json_extract(meta, '$.score') as score,
    json_extract(meta, '$.rounds') as rounds,
    ROUND(time_cost, 2) as time_sec
FROM evaluation_data
WHERE exp_id = 'word_puzzle_baseline_eval'
ORDER BY dataset_index;
EOF
```

### 方法 2: 使用查看脚本

```bash
# 使用快速查看脚本（推荐）
python scripts/view_korgym_results.py word_puzzle_baseline_eval
```

### 方法 3: 查看 JSON 结果文件

如果评估脚本生成了 JSON 文件：

```bash
# 查看分数汇总
cat workspace/korgym_paper_aligned/score.txt

# 查看详细结果（使用 jq，如果安装了）
jq '.avg_score, .score_distribution' \
    workspace/korgym_paper_aligned/baseline_clean_word_puzzle.json
```

---

## 📁 配置文件

### 基线评估配置

**`configs/eval/korgym/word_puzzle_baseline.yaml`**:

```yaml
exp_id: word_puzzle_baseline_eval
agent: practice/logic_agent_hierarchical_learning_clean  # 无经验
korgym:
  game_name: "8-word_puzzle"
  num_seeds: 20  # 评估 20 个游戏
  level: 4       # 难度级别
```

### 增强评估配置

**`configs/eval/korgym/word_puzzle_enhanced.yaml`**:

```yaml
exp_id: word_puzzle_enhanced_eval
agent: practice/word_puzzle_exp_agent  # 有经验（训练后生成）
korgym:
  game_name: "8-word_puzzle"
  num_seeds: 20  # 相同的 20 个游戏
  level: 4
```

---

## 🔧 常见问题

### 问题 1: 评估脚本找不到

**错误**：`AttributeError: 'NoneType' object has no attribute 'dataset'`

**原因**：KORGym 的评估方式与传统评估不同：
- **传统评估**: 从数据库加载预先准备的题目
- **KORGym 评估**: 实时启动游戏服务器，Agent 玩游戏

**解决**：使用专门的 KORGym 评估脚本 `scripts/run_korgym_eval.py`

### 问题 2: 游戏服务器未启动

**错误**：`Connection refused to localhost:8775`

**解决**：
```bash
# 启动游戏服务器
python scripts/start_korgym_server.py 8-word_puzzle

# 等待 5 秒后再运行评估
sleep 5
uv run python scripts/run_korgym_eval.py --config_name korgym/word_puzzle_baseline
```

### 问题 3: 找不到实验结果

**解决**：
```bash
# 检查数据库中的实验 ID
sqlite3 database.db "SELECT DISTINCT exp_id FROM evaluation_data;"

# 使用正确的 exp_id
```

---

## 📊 对比分析

### 对比基线和增强结果

```bash
uv run python scripts/compare_korgym_results.py \
    --baseline word_puzzle_baseline_eval \
    --enhanced word_puzzle_enhanced_eval
```

**输出示例：**
```
======================================================================
  对比分析结果
======================================================================

指标                 基线 (无经验)          增强 (有经验)          提升      
----------------------------------------------------------------------
成功率                           35.0%              52.5%      +17.5%
平均得分                        45.20             68.75      +52.1%
最高得分                       100.00            100.00
评估局数                           20                 20
----------------------------------------------------------------------

📊 总结:
  • 成功率提升: +17.5 百分点
  • 平均得分提升: +52.1%

  ✅ 分层经验学习显著提升了 Agent 性能！
======================================================================
```

---

## 📚 相关文档

- [Word Puzzle 完整指南](Word_Puzzle完整指南.md)
- [KORGym 集成指南](KORGym集成指南.md)
- [KORGym 快速使用指南](KORGym快速使用指南.md)

---

## ✅ 评估检查清单

在运行评估前，确保：

- [ ] 游戏服务器已启动（`curl http://localhost:8775/health`）
- [ ] Agent 配置文件存在且正确
- [ ] LLM API 配置正确（.env 文件）
- [ ] 虚拟环境已激活
- [ ] 有足够的磁盘空间

运行检查：
```bash
python scripts/check_korgym_env.py
```








