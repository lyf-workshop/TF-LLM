# 命令速查参考

本文档提供所有常用命令的快速查找表，按功能模块分组。

---

## 游戏服务器管理

### 启动 Wordle 服务器

**用途**：启动 Wordle 游戏服务器，用于评估和训练

**命令**：
```bash
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

**参数说明**：
- `-p 8777`：指定端口号（可自定义，需与配置文件一致）

**注意事项**：
- 服务器需在独立终端持续运行
- 确保端口未被占用：`netstat -an | findstr 8777`（Windows）

---

### 启动 Word Puzzle 服务器

**用途**：启动 Word Puzzle 游戏服务器

**命令**：
```bash
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

**参数说明**：
- `-p 8775`：Word Puzzle 默认端口

**注意事项**：
- 与 Wordle 可同时运行（端口不冲突）

---

## 数据集管理

### 准备游戏数据集

**用途**：为指定游戏创建训练集和评估集

**命令**：
```bash
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "33-wordle" \
    --train_count 100 \
    --eval_count 50
```

**参数说明**：
- `--game_name`：游戏ID（如 "8-word_puzzle", "33-wordle"）
- `--train_count`：训练集样本数（默认100）
- `--eval_count`：评估集样本数（默认50）

**注意事项**：
- 数据集会保存到 SQLite 数据库（`test.db`）
- 重复运行会覆盖同名数据集

---

### 查看所有数据集

**用途**：列出数据库中所有可用数据集

**命令**：
```bash
uv run python scripts/data/list_datasets.py
```

**参数说明**：无

**注意事项**：
- 可使用 `grep` 过滤：`... | grep KORGym`

---

### 查看数据集内容

**用途**：查看指定数据集的详细内容

**命令**：
```bash
uv run python scripts/utils/view_dataset.py \
    --dataset_name "KORGym-Wordle-Eval-50" \
    --limit 5
```

**参数说明**：
- `--dataset_name`：数据集名称
- `--limit`：显示样本数量（默认10）

---

## 评估命令

### 运行基线评估

**用途**：评估未经训练的 Agent 性能

**命令**：
```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

**参数说明**：
- `--config_name`：配置文件名（相对于 `configs/eval/`）

**注意事项**：
- 确保游戏服务器已启动
- 结果保存在数据库中，可通过 `exp_id` 查询

---

### 运行训练后评估

**用途**：评估经过 Training-Free GRPO 训练后的 Agent

**命令**：
```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
```

**参数说明**：同上

---

## 训练命令

### 运行 Training-Free GRPO 训练

**用途**：对 Agent 进行经验学习训练

**命令**：
```bash
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym/wordle_practice
```

**参数说明**：
- `--config_name`：训练配置文件名（相对于 `configs/practice/`）

**注意事项**：
- 训练时间取决于数据集大小和模型速度
- 生成的经验会保存到 `workspace/hierarchical_experiences/`

---

### 使用自定义参数训练

**用途**：覆盖配置文件中的默认参数

**命令**：
```bash
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym/wordle_practice \
    --epochs 3 \
    --batch_size 50 \
    --restart_step 0
```

**参数说明**：
- `--epochs`：训练轮数
- `--batch_size`：批次大小
- `--restart_step`：重启步骤（0=完全重新开始，null=使用缓存）

---

## 结果查看

### 查看 KORGym 实验结果

**用途**：对比多个实验的评估结果

**命令**：
```bash
uv run python scripts/games/view_korgym_results.py \
    wordle_baseline_eval \
    wordle_practice_eval
```

**参数说明**：
- 参数1, 2, ...：要对比的实验 ID

**注意事项**：
- 显示准确率、分数等关键指标

---

### 分析 Wordle 前N题

**用途**：详细分析 Wordle 评估中前N题的表现

**命令**：
```bash
uv run python scripts/games/wordle/analyze_wordle_results.py \
    --exp_id wordle_practice_eval \
    --top_n 20
```

**参数说明**：
- `--exp_id`：实验ID
- `--top_n`：分析前N题（默认20）

---

## 清理和维护

### 清理实验缓存

**用途**：删除特定实验的数据库记录

**命令**：
```bash
uv run python scripts/utils/clean_experiment_data.py \
    --exp_id wordle_baseline_eval
```

**参数说明**：
- `--exp_id`：要清理的实验ID

**注意事项**：
- 操作不可逆，请谨慎使用

---

### 清理并重新运行实验

**用途**：一键清理缓存并重新运行完整流程

**命令**：
```bash
bash cleanup_and_rerun_wordle.sh
```

**参数说明**：无（脚本内置配置）

**注意事项**：
- 适用于 WSL/Linux 环境
- Windows 用户需手动执行等效命令

---

## 环境管理

### 检查 KORGym 环境

**用途**：验证所有依赖是否正确安装

**命令**：
```bash
python scripts/korgym/check_korgym_env.py
```

**参数说明**：无

---

### 测试游戏服务器连接

**用途**：测试游戏服务器是否可访问

**命令**：
```bash
python scripts/korgym/test_korgym_server.py
```

**参数说明**：无

---

## 快速参考表

| 操作 | 命令 |
|------|------|
| 启动 Wordle 服务器 | `cd KORGym/game_lib/33-wordle && python game_lib.py -p 8777` |
| 准备数据集 | `uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"` |
| 基线评估 | `uv run python scripts/run_eval.py --config_name korgym/wordle_eval` |
| 训练 | `uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice` |
| 训练后评估 | `uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval` |
| 查看结果 | `uv run python scripts/games/view_korgym_results.py wordle_baseline_eval wordle_practice_eval` |
