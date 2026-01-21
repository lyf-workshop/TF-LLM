# KORGym三个游戏训练指南 🎮

本指南提供Word Puzzle、Alphabetical Sorting和Wordle三个游戏的完整训练流程。

---

## 📦 已创建的配置文件

### ✅ 总览（每个游戏4个文件 × 3个游戏 = 12个文件）

```
configs/
├── agents/practice/
│   ├── word_puzzle_agent.yaml                          # Word Puzzle Agent
│   ├── alphabetical_sorting_agent.yaml                 # Alphabetical Sorting Agent
│   └── wordle_agent.yaml                               # Wordle Agent
├── eval/korgym/
│   ├── word_puzzle_eval.yaml                          # Word Puzzle基线评估
│   ├── word_puzzle_practice_eval.yaml                 # Word Puzzle训练后评估
│   ├── alphabetical_sorting_eval.yaml                 # Alphabetical Sorting基线评估
│   ├── alphabetical_sorting_practice_eval.yaml        # Alphabetical Sorting训练后评估
│   ├── wordle_eval.yaml                               # Wordle基线评估
│   └── wordle_practice_eval.yaml                      # Wordle训练后评估
└── practice/
    ├── word_puzzle_practice.yaml                      # Word Puzzle训练配置
    ├── alphabetical_sorting_practice.yaml             # Alphabetical Sorting训练配置
    └── wordle_practice.yaml                           # Wordle训练配置
```

---

## 🎮 游戏信息

| 游戏名称 | 游戏ID | 类型 | 端口 | 难度 | 回合数 |
|---------|--------|------|------|------|--------|
| Word Puzzle | 8-word_puzzle | 单轮 | 8775 | 3 | 1 |
| Alphabetical Sorting | 22-alphabetical_sorting | 单轮 | 8776 | 3 | 1 |
| Wordle | 33-wordle | 多轮 | 8777 | 3 | 6 |

---

## 🚀 完整运行流程（WSL环境）

### 🎯 游戏1: Word Puzzle (8-word_puzzle)

#### 步骤1: 启动游戏服务器（终端1）
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
# 保持运行
```

#### 步骤2: 准备数据集（终端2）
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 创建Word Puzzle数据集
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "8-word_puzzle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 150
```

#### 步骤3: 基线评估
```bash
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

#### 步骤4: 训练（分层经验学习）
```bash
uv run python scripts/run_training_free_GRPO.py --config_name word_puzzle_practice
```

#### 步骤5: 训练后评估
```bash
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

#### 步骤6: 查看结果
```bash
# 基线结果
cat workspace/word_puzzle_baseline_eval/score.txt

# 训练后结果
cat workspace/word_puzzle_practice_eval/score.txt

# 提取的经验
cat workspace/hierarchical_experiences/word_puzzle_practice.json
```

---

### 🎯 游戏2: Alphabetical Sorting (22-alphabetical_sorting)

#### 步骤1: 启动游戏服务器（新终端或停止之前的服务器）
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8776
# 保持运行
```

#### 步骤2: 准备数据集
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 创建Alphabetical Sorting数据集
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "22-alphabetical_sorting" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 150
```

#### 步骤3: 基线评估
```bash
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval
```

#### 步骤4: 训练
```bash
uv run python scripts/run_training_free_GRPO.py --config_name alphabetical_sorting_practice
```

#### 步骤5: 训练后评估
```bash
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
```

#### 步骤6: 查看结果
```bash
cat workspace/alphabetical_sorting_baseline_eval/score.txt
cat workspace/alphabetical_sorting_practice_eval/score.txt
cat workspace/hierarchical_experiences/alphabetical_sorting_practice.json
```

---

### 🎯 游戏3: Wordle (33-wordle)

#### 步骤1: 启动游戏服务器
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8777
# 保持运行
```

#### 步骤2: 准备数据集
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 创建Wordle数据集
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 150
```

#### 步骤3: 基线评估
```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

#### 步骤4: 训练
```bash
uv run python scripts/run_training_free_GRPO.py --config_name wordle_practice
```

#### 步骤5: 训练后评估
```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
```

#### 步骤6: 查看结果
```bash
cat workspace/wordle_baseline_eval/score.txt
cat workspace/wordle_practice_eval/score.txt
cat workspace/hierarchical_experiences/wordle_practice.json
```

---

## ⚡ 一键运行所有游戏

创建批处理脚本：

```bash
cat > run_all_games.sh << 'EOF'
#!/bin/bash
# 依次运行三个游戏的完整流程

cd /mnt/f/youtu-agent
source .venv/bin/activate

GAMES=("word_puzzle:8-word_puzzle:8775" "alphabetical_sorting:22-alphabetical_sorting:8776" "wordle:33-wordle:8777")

for game_info in "${GAMES[@]}"; do
    IFS=':' read -r name id port <<< "$game_info"
    
    echo "=========================================="
    echo "Processing Game: $name"
    echo "=========================================="
    
    # 准备数据集
    echo "📊 Preparing dataset..."
    uv run python scripts/data/prepare_korgym_data.py --game_name "$id"
    
    # 基线评估
    echo "📈 Running baseline evaluation..."
    uv run python scripts/run_eval.py --config_name "korgym/${name}_eval"
    
    # 训练
    echo "🎓 Running training..."
    uv run python scripts/run_training_free_GRPO.py --config_name "${name}_practice"
    
    # 训练后评估
    echo "📈 Running practice evaluation..."
    uv run python scripts/run_eval.py --config_name "korgym/${name}_practice_eval"
    
    echo "✅ Completed: $name"
    echo ""
done

echo "🎉 All games completed!"
EOF

chmod +x run_all_games.sh
```

**注意**：每个游戏的服务器需要手动启动在对应端口！

---

## 📊 数据集配置

每个游戏使用相同的数据集划分策略：

```
评估数据集: seeds 1-50  (50题)
  ↓ 用于基线评估和训练后评估（保证一致性）
  
训练数据集: seeds 51-150 (100题)
  ↓ 仅用于训练（不与评估集重叠）
```

---

## 🎯 关键配置差异

### Word Puzzle
- **类型**: 单轮游戏（一次性提交答案）
- **输出**: 多个单词列表
- **温度**: 0.3（需要准确性）
- **超时**: 600秒

### Alphabetical Sorting  
- **类型**: 单轮游戏
- **输出**: 排序后的列表
- **温度**: 0.1（需要确定性）
- **超时**: 300秒（较简单）

### Wordle
- **类型**: 多轮游戏（最多6次猜测）
- **输出**: 单个5字母单词
- **温度**: 0.5（需要探索性）
- **超时**: 600秒
- **回合数**: 最多6回合

---

## 📁 结果文件位置

### Word Puzzle
```
workspace/
├── word_puzzle_baseline_eval/
│   └── score.txt
├── word_puzzle_practice_eval/
│   └── score.txt
└── hierarchical_experiences/
    └── word_puzzle_practice.json

configs/agents/practice/
└── word_puzzle_practice_agent.yaml (训练后生成)
```

### Alphabetical Sorting
```
workspace/
├── alphabetical_sorting_baseline_eval/
│   └── score.txt
├── alphabetical_sorting_practice_eval/
│   └── score.txt
└── hierarchical_experiences/
    └── alphabetical_sorting_practice.json

configs/agents/practice/
└── alphabetical_sorting_practice_agent.yaml (训练后生成)
```

### Wordle
```
workspace/
├── wordle_baseline_eval/
│   └── score.txt
├── wordle_practice_eval/
│   └── score.txt
└── hierarchical_experiences/
    └── wordle_practice.json

configs/agents/practice/
└── wordle_practice_agent.yaml (训练后生成)
```

---

## 🔧 故障排查

### 问题1: 游戏服务器端口冲突
```bash
# 检查端口占用
netstat -tuln | grep 8775
netstat -tuln | grep 8776
netstat -tuln | grep 8777

# 杀死占用进程
pkill -f "game_lib.py"
```

### 问题2: 数据集已存在
```bash
# 如果需要重新创建数据集，可以先删除
# 使用数据库管理工具或直接重新上传
```

### 问题3: 训练超时
```bash
# 增加超时时间（编辑对应的practice.yaml）
task_timeout: 1200  # 改为20分钟
```

---

## 📊 预期性能提升

| 游戏 | 基线准确率 | 训练后准确率 | 预期提升 |
|------|-----------|-------------|---------|
| Word Puzzle | 30-50% | 40-65% | +10-15% |
| Alphabetical Sorting | 70-85% | 80-95% | +5-10% |
| Wordle | 40-60% | 50-70% | +10% |

*注：实际效果取决于模型能力和游戏复杂度*

---

## 🎓 分层经验示例

### Word Puzzle
```
L0: "在填字游戏中，优先解决有多个交叉的单词，可以相互验证..."
L1: "对于谜题类游戏，利用约束传播和相互验证策略可以提高准确率..."
L2: "在约束满足问题中，优先处理约束最多的变量可以最快缩小搜索空间..."
```

### Alphabetical Sorting
```
L0: "排序时要逐字母比较，当首字母相同时比较下一个字母..."
L1: "对于序列排序问题，使用稳定的比较策略比反复试错更有效..."
L2: "在确定性任务中，建立系统化的处理流程比启发式更可靠..."
```

### Wordle
```
L0: "首次猜测使用包含常见元音的词（如AROSE），可以快速排除可能性..."
L1: "在信息收集类游戏中，早期最大化信息增益比早期猜测答案更优..."
L2: "在约束逐步增加的问题中，动态调整策略比固定策略更有效..."
```

---

## ✅ 快速命令速查

```bash
# ===== Word Puzzle (端口8775) =====
# 数据准备
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# 基线评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# 训练
uv run python scripts/run_training_free_GRPO.py --config_name word_puzzle_practice

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval

# ===== Alphabetical Sorting (端口8776) =====
# 数据准备
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"

# 基线评估
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval

# 训练
uv run python scripts/run_training_free_GRPO.py --config_name alphabetical_sorting_practice

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval

# ===== Wordle (端口8777) =====
# 数据准备
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 训练
uv run python scripts/run_training_free_GRPO.py --config_name wordle_practice

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
```

---

## 🎉 总结

✅ **已创建12个配置文件**（3游戏 × 4文件/游戏）
✅ **每个游戏独立的端口**（避免冲突）
✅ **统一的数据集划分**（seeds 1-50评估，51-150训练）
✅ **针对性的Agent指令**（根据游戏特点优化）

**开始运行，祝训练顺利！** 🚀

---

*创建时间: 2026-01-15*  
*游戏数量: 3个*  
*配置文件: 12个*

