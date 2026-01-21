# KORGym清理并重新运行指南 🔄

## 🗑️ 清理失败的实验

### Word Puzzle

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 方式1: 手动清理
uv run python scripts/clean_experiment_data.py --exp_id \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval \
  word_puzzle_practice

# 方式2: 使用一键脚本
chmod +x cleanup_and_rerun_word_puzzle.sh
./cleanup_and_rerun_word_puzzle.sh
```

### Alphabetical Sorting

```bash
# 方式1: 手动清理
uv run python scripts/clean_experiment_data.py --exp_id \
  alphabetical_sorting_baseline_eval \
  alphabetical_sorting_practice_eval \
  alphabetical_sorting_practice

# 方式2: 使用一键脚本
chmod +x cleanup_and_rerun_alphabetical_sorting.sh
./cleanup_and_rerun_alphabetical_sorting.sh
```

### Wordle

```bash
# 方式1: 手动清理
uv run python scripts/clean_experiment_data.py --exp_id \
  wordle_baseline_eval \
  wordle_practice_eval \
  wordle_practice

# 方式2: 使用一键脚本
chmod +x cleanup_and_rerun_wordle.sh
./cleanup_and_rerun_wordle.sh
```

---

## ⚠️ 重要提醒：必须先启动游戏服务器！

你之前遇到的错误是因为游戏服务器没有运行：
```
Connection refused on port 8775
```

### 启动游戏服务器

**在单独的终端中运行（不要关闭）**：

```bash
# Word Puzzle
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# Alphabetical Sorting
cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8776

# Wordle
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

### 检查服务器是否运行

```bash
# 检查Word Puzzle服务器
curl http://localhost:8775/docs

# 检查Alphabetical Sorting服务器
curl http://localhost:8776/docs

# 检查Wordle服务器
curl http://localhost:8777/docs
```

---

## 🚀 完整重新运行流程

### Word Puzzle（手动步骤）

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 步骤1: 清理旧数据
uv run python scripts/clean_experiment_data.py --exp_id \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval \
  word_puzzle_practice

# 步骤2: 确保游戏服务器在运行
curl http://localhost:8775/docs
# 如果失败，在另一个终端启动服务器

# 步骤3: 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# 步骤4: 基线评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# 步骤5: 训练
uv run python scripts/run_training_free_GRPO.py --config_name word_puzzle_practice

# 步骤6: 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval

# 步骤7: 查看结果
cat workspace/word_puzzle_baseline_eval/score.txt
cat workspace/word_puzzle_practice_eval/score.txt
```

---

## ⚡ 使用一键脚本（推荐）

```bash
cd /mnt/f/youtu-agent

# 先给脚本执行权限
chmod +x cleanup_and_rerun_word_puzzle.sh
chmod +x cleanup_and_rerun_alphabetical_sorting.sh
chmod +x cleanup_and_rerun_wordle.sh

# 确保对应的游戏服务器在运行，然后：

# Word Puzzle
./cleanup_and_rerun_word_puzzle.sh

# Alphabetical Sorting
./cleanup_and_rerun_alphabetical_sorting.sh

# Wordle
./cleanup_and_rerun_wordle.sh
```

---

## 📋 已创建的一键脚本

1. **`cleanup_and_rerun_word_puzzle.sh`**
   - 清理Word Puzzle旧实验
   - 检查服务器
   - 完整运行流程
   - 显示结果对比

2. **`cleanup_and_rerun_alphabetical_sorting.sh`**
   - 清理Alphabetical Sorting旧实验
   - 检查服务器
   - 完整运行流程
   - 显示结果对比

3. **`cleanup_and_rerun_wordle.sh`**
   - 清理Wordle旧实验
   - 检查服务器
   - 完整运行流程
   - 显示结果对比

---

## 🔍 故障排查

### 问题: Connection refused

**原因**: 游戏服务器没有运行

**解决**:
```bash
# 启动对应的游戏服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

### 问题: exp_id already exists

**原因**: 数据库中有旧的实验数据

**解决**:
```bash
# 清理旧实验
uv run python scripts/clean_experiment_data.py --exp_id word_puzzle_baseline_eval
```

---

## ✅ 推荐工作流程

### 使用tmux管理多终端

```bash
# 创建新会话
tmux new -s korgym

# 分割窗口（Ctrl+b 然后按 "）
# 上方: 运行游戏服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# 下方: 运行训练流程（Ctrl+b 然后按 ↓ 切换）
cd /mnt/f/youtu-agent
source .venv/bin/activate
./cleanup_and_rerun_word_puzzle.sh
```

---

## 📊 查看结果

```bash
# 基线 vs 训练后对比
echo "=== Word Puzzle ==="
echo "Baseline:" && cat workspace/word_puzzle_baseline_eval/score.txt
echo "Practice:" && cat workspace/word_puzzle_practice_eval/score.txt

echo ""
echo "=== Alphabetical Sorting ==="
echo "Baseline:" && cat workspace/alphabetical_sorting_baseline_eval/score.txt
echo "Practice:" && cat workspace/alphabetical_sorting_practice_eval/score.txt

echo ""
echo "=== Wordle ==="
echo "Baseline:" && cat workspace/wordle_baseline_eval/score.txt
echo "Practice:" && cat workspace/wordle_practice_eval/score.txt
```

---

**现在可以开始重新运行了！记得先启动游戏服务器！** 🚀

