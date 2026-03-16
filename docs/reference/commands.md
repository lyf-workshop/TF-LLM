# 命令速查参考

本文档提供所有常用命令的快速查找表，按功能模块分组。

**快速跳转**：
- [游戏服务器管理](#游戏服务器管理)
- [数据集管理](#数据集管理)
- [评估命令](#评估命令)
- [训练命令](#训练命令)
- [结果查看](#结果查看)
- [清理和维护](#清理和维护)
- [调试命令](#调试命令)
- [完整实验流程](#完整实验流程)

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
- 确保端口未被占用

**检查服务器状态**：
```bash
# Windows
netstat -an | findstr 8777

# Linux/WSL
netstat -tuln | grep 8777
lsof -i :8777
```

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

### 启动 Alphabetical Sorting 服务器

**用途**：启动 Alphabetical Sorting 游戏服务器

**命令**：
```bash
cd KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8776
```

**参数说明**：
- `-p 8776`：Alphabetical Sorting 默认端口

---

### 测试服务器连接

**用途**：验证游戏服务器是否正常响应

**命令**：
```bash
# 测试 Wordle 服务器
curl http://localhost:8777/generate -X POST \
    -H "Content-Type: application/json" \
    -d '{"seed": 1}'

# 测试 Word Puzzle 服务器
curl http://localhost:8775/generate -X POST \
    -H "Content-Type: application/json" \
    -d '{"seed": 1}'

# 测试 Alphabetical Sorting 服务器
curl http://localhost:8776/generate -X POST \
    -H "Content-Type: application/json" \
    -d '{"seed": 1}'
```

**预期输出**：应返回游戏实例的JSON数据

---

### 重启游戏服务器

**用途**：解决服务器500错误或卡顿问题

**命令**：
```bash
# 停止服务器：在服务器终端按 Ctrl+C

# 查找并杀死进程（如果Ctrl+C无效）
# Linux/WSL
pkill -f "game_lib.py"

# Windows
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *game_lib*"

# 重新启动
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

---

## 数据集管理

### 准备游戏数据集（标准方式）

**用途**：为指定游戏创建训练集和评估集

**命令**：
```bash
# Wordle（50题评估 + 100题训练）
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# Word Puzzle
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# Alphabetical Sorting
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
```

**参数说明**：
- `--game_name`：游戏ID（必需）
- `--train_count`：训练集样本数（默认100）
- `--eval_count`：评估集样本数（默认50）
- `--eval_seeds_start`：评估集起始种子（默认1）
- `--eval_seeds_end`：评估集结束种子（默认50）
- `--train_seeds_start`：训练集起始种子（默认51）
- `--train_seeds_end`：训练集结束种子（默认150）

**注意事项**：
- 数据集会保存到 SQLite 数据库（`test.db`）
- 重复运行会覆盖同名数据集
- 评估集和训练集的种子不应重叠

---

### 准备自定义数据集

**用途**：创建不同规模的数据集（如20题训练）

**命令**：
```bash
# 创建20题训练集
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 70  # 70-51+1 = 20题
```

---

### 查看所有数据集

**用途**：列出数据库中所有可用数据集

**命令**：
```bash
# 列出所有数据集
uv run python scripts/data/list_datasets.py

# 只看 KORGym 数据集
uv run python scripts/data/list_datasets.py | grep KORGym
```

**参数说明**：无

---

### 查看数据集内容

**用途**：查看指定数据集的详细内容

**命令**：
```bash
# 查看前5个样本
uv run python scripts/utils/view_dataset.py \
  --dataset_name "KORGym-Wordle-Eval-50" \
  --limit 5

# 查看特定索引的样本
uv run python scripts/utils/view_dataset.py \
  --dataset_name "KORGym-Wordle-Eval-50" \
  --index 0
```

**参数说明**：
- `--dataset_name`：数据集名称（必需）
- `--limit`：显示样本数量（默认10）
- `--index`：查看特定索引的样本

---

## 评估命令

### 运行基线评估

**用途**：评估未经训练的 Agent 性能

**命令**：
```bash
# Wordle 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# Word Puzzle 基线评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# Alphabetical Sorting 基线评估
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval
```

**参数说明**：
- `--config_name`：配置文件名（相对于 `configs/eval/`）

**注意事项**：
- 确保游戏服务器已启动
- 结果保存在数据库中，可通过 `exp_id` 查询
- 评估时间：单轮游戏约10-15分钟，多轮游戏（Wordle）约30-40分钟

---

### 运行训练后评估

**用途**：评估经过 Training-Free GRPO 训练后的 Agent

**命令**：
```bash
# Wordle 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# Word Puzzle 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval

# Alphabetical Sorting 训练后评估
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
```

**参数说明**：同上

**注意事项**：
- 必须先完成训练，生成 `*_practice_agent.yaml` 文件
- 使用相同的评估数据集，确保对比公平

---

## 训练命令

### 运行 Training-Free GRPO 训练

**用途**：对 Agent 进行经验学习训练

**命令**：
```bash
# Wordle 训练
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/wordle_practice

# Word Puzzle 训练
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/word_puzzle_practice

# Alphabetical Sorting 训练
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/alphabetical_sorting_practice
```

**参数说明**：
- `--config_name`：训练配置文件名（相对于 `configs/practice/`）
- `--epochs`：覆盖配置文件中的训练轮数
- `--batch_size`：覆盖配置文件中的批次大小
- `--restart_step`：重启步骤（0=完全重新开始，null=使用缓存）

**训练时间**：
- Word Puzzle：约2-3小时（100题）
- Alphabetical Sorting：约1-2小时（100题）
- Wordle：约2-3小时（100题）

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
- `--restart_step`：
  - `0`：完全重新开始，不使用缓存
  - `null`：使用缓存，从断点继续
  - `N`：从第N步重新开始

---

### 完全重新训练（清除缓存）

**用途**：强制重新开始训练，不使用任何缓存

**命令**：
```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/wordle_practice \
  --restart_step 0
```

---

## 结果查看

### 使用 KORGym 专用结果查看器（推荐）

**用途**：查看和对比KORGym游戏的评估结果

**命令**：
```bash
# 查看所有游戏的结果
uv run python scripts/games/view_korgym_results.py

# 对比特定实验
uv run python scripts/games/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_eval

# 查看单个实验详情
uv run python scripts/games/view_korgym_results.py \
  --exp_id wordle_baseline_eval \
  --detailed
```

**参数说明**：
- 位置参数：要对比的实验ID
- `--exp_id`：查看单个实验
- `--detailed`：显示详细信息

---

### 分析 Wordle 前N题表现

**用途**：详细分析 Wordle 评估中前N题的得分情况

**命令**：
```bash
# 分析前20题（默认）
uv run python scripts/games/wordle/analyze_wordle_results.py \
  --exp_id wordle_practice_eval

# 分析前10题
uv run python scripts/games/wordle/analyze_wordle_results.py \
  --exp_id wordle_practice_eval \
  --top_n 10

# 对比两个实验的前20题
uv run python scripts/games/wordle/analyze_wordle_results.py \
  --exp_id wordle_baseline_eval \
  --compare wordle_practice_eval
```

**参数说明**：
- `--exp_id`：实验ID（必需）
- `--top_n`：分析前N题（默认20）
- `--compare`：对比另一个实验

---

### 查看生成的经验

**用途**：查看训练后生成的分层经验

**命令**：
```bash
# 查看完整经验文件
cat workspace/hierarchical_experiences/wordle_practice.json | python -m json.tool

# 或使用 jq（如果已安装）
cat workspace/hierarchical_experiences/wordle_practice.json | jq .

# 只看统计信息
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.stats'

# 查看经验数量
cat workspace/hierarchical_experiences/wordle_practice.json | jq '{L0: (.L0|length), L1: (.L1|length), L2: (.L2|length)}'
```

---

### 查看 Agent 配置中的经验

**用途**：检查训练后生成的Agent配置

**命令**：
```bash
# 查看完整配置
cat configs/agents/practice/wordle_practice_agent.yaml

# 只看经验部分
cat configs/agents/practice/wordle_practice_agent.yaml | grep -A 5 "L0\|L1\|L2"
```

---

## 清理和维护

### 清理实验缓存

**用途**：删除特定实验的数据库记录

**命令**：
```bash
# 清理单个实验
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id wordle_baseline_eval

# 清理多个实验
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id wordle_baseline_eval wordle_practice_eval

# 清理所有Wordle实验
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id_pattern "wordle%"

# 列出所有实验
uv run python scripts/utils/clean_experiment_data.py --list
```

**参数说明**：
- `--exp_id`：要清理的实验ID
- `--exp_id_pattern`：使用通配符模式清理
- `--list`：列出所有实验
- `--force`：强制删除，不询问确认

**注意事项**：
- 操作不可逆，请谨慎使用
- 清理前建议先备份数据库

---

### 清理数据集

**用途**：删除并重新创建数据集

**命令**：
```bash
# 清理所有 KORGym 数据集
uv run python scripts/utils/clean_and_recreate_datasets.py

# 删除特定数据集（需手动操作数据库）
uv run python -c "
from utu.db import DBService, DatasetSample
from sqlmodel import select
db = DBService()
with db.session() as session:
    stmt = select(DatasetSample).where(
        DatasetSample.dataset == 'KORGym-Wordle-Train-100'
    )
    for sample in session.exec(stmt):
        session.delete(sample)
    session.commit()
print('✓ 删除成功')
"
```

---

### 清理生成的文件

**用途**：删除训练生成的经验和Agent配置

**命令**：
```bash
# 删除经验文件
rm workspace/hierarchical_experiences/wordle_practice*.json
rm workspace/hierarchical_experiences/word_puzzle_practice*.json
rm workspace/hierarchical_experiences/alphabetical_sorting_practice*.json

# 删除生成的Agent配置
rm configs/agents/practice/wordle_practice*_agent.yaml
rm configs/agents/practice/word_puzzle_practice*_agent.yaml
rm configs/agents/practice/alphabetical_sorting_practice*_agent.yaml

# 删除评估结果
rm -rf workspace/wordle_*_eval/
rm -rf workspace/word_puzzle_*_eval/
rm -rf workspace/alphabetical_sorting_*_eval/
```

---

### 完全重置实验环境

**用途**：清除所有实验数据，重新开始

**命令**：
```bash
# 1. 停止所有游戏服务器（各终端按 Ctrl+C）

# 2. 清理数据库
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id_pattern "wordle%" \
  --exp_id_pattern "word_puzzle%" \
  --exp_id_pattern "alphabetical_sorting%" \
  --force

# 3. 清理数据集
uv run python scripts/utils/clean_and_recreate_datasets.py --force

# 4. 删除生成的文件
rm -f configs/agents/practice/*_practice*_agent.yaml
rm -f workspace/hierarchical_experiences/*_practice*.json
rm -rf workspace/*_eval/

# 5. 重新准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
```

---

## 调试命令

### 检查环境

**用途**：验证Python环境和依赖

**命令**：
```bash
# 检查Python版本
python --version  # 需要3.12+

# 检查虚拟环境
which python  # 应该指向 .venv/bin/python

# 检查关键包
python -c "import utu; print(utu.__version__)"
python -c "import flask; print(flask.__version__)"
```

---

### 检查配置文件

**用途**：验证YAML配置文件语法

**命令**：
```bash
# 检查语法
python -c "import yaml; yaml.safe_load(open('configs/eval/korgym/wordle_eval.yaml'))"

# 查看关键参数
grep -E "level:|max_rounds:|concurrency:" configs/eval/korgym/wordle_eval.yaml
```

---

### 查看日志

**用途**：检查系统日志和错误信息

**命令**：
```bash
# 查看最新日志
ls -lt logs/*.log | head -1 | xargs tail -100

# 搜索错误
grep -i "error\|exception\|failed" logs/*.log | tail -20

# 查看特定实验的日志
grep "wordle_practice" logs/*.log

# 查看API限流错误
grep "429\|rate limit" logs/*.log
```

---

### 查看数据库状态

**用途**：检查数据库中的数据

**命令**：
```bash
# 查看数据集统计
sqlite3 test.db "SELECT dataset, COUNT(*) FROM dataset_samples GROUP BY dataset"

# 查看评估结果统计
sqlite3 test.db "SELECT exp_id, COUNT(*), AVG(correct) FROM evaluation_data GROUP BY exp_id"

# 查看特定实验的样本
sqlite3 test.db "SELECT * FROM evaluation_data WHERE exp_id='wordle_baseline_eval' LIMIT 3"
```

---

### 测试KORGym环境

**用途**：验证KORGym环境是否正确配置

**命令**：
```bash
# 运行环境检查脚本
python scripts/korgym/check_korgym_env.py

# 测试游戏服务器
python scripts/korgym/test_korgym_server.py
```

---

## 完整实验流程

### Wordle 完整流程

```bash
# ===== 终端1: 游戏服务器 =====
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777

# ===== 终端2: 实验流程 =====
cd /path/to/youtu-agent
source .venv/bin/activate  # Linux/WSL/macOS
# 或 .venv\Scripts\activate  # Windows

# 1. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 2. 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 5. 查看结果对比
uv run python scripts/games/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_eval
```

---

### Word Puzzle 完整流程

```bash
# ===== 终端1: 游戏服务器 =====
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# ===== 终端2: 实验流程 =====
cd /path/to/youtu-agent
source .venv/bin/activate

uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
uv run python scripts/games/view_korgym_results.py \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval
```

---

### Alphabetical Sorting 完整流程

```bash
# ===== 终端1: 游戏服务器 =====
cd KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8776

# ===== 终端2: 实验流程 =====
cd /path/to/youtu-agent
source .venv/bin/activate

uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
uv run python scripts/games/view_korgym_results.py \
  alphabetical_sorting_baseline_eval \
  alphabetical_sorting_practice_eval
```

---

## 快速参考表

### 游戏端口和数据集

| 游戏 | 游戏ID | 端口 | 评估集 | 训练集 | 类型 |
|------|--------|------|--------|--------|------|
| **Wordle** | 33-wordle | 8777 | KORGym-Wordle-Eval-50 | KORGym-Wordle-Train-100 | 多轮 |
| **Word Puzzle** | 8-word_puzzle | 8775 | KORGym-WordPuzzle-Eval-50 | KORGym-WordPuzzle-Train-100 | 单轮 |
| **Alphabetical Sorting** | 22-alphabetical_sorting | 8776 | KORGym-AlphabeticalSorting-Eval-50 | KORGym-AlphabeticalSorting-Train-100 | 单轮 |

### 配置文件路径

| 用途 | 路径模板 |
|------|---------|
| Agent配置 | `configs/agents/practice/{game}_agent.yaml` |
| 基线评估配置 | `configs/eval/korgym/{game}_eval.yaml` |
| 训练配置 | `configs/practice/korgym/{game}_practice.yaml` |
| 训练后评估配置 | `configs/eval/korgym/{game}_practice_eval.yaml` |
| 训练后Agent配置 | `configs/agents/practice/{game}_practice_agent.yaml` (自动生成) |

### 关键参数

| 参数 | Wordle | Word Puzzle | Alphabetical Sorting |
|------|--------|-------------|---------------------|
| **level** | 5 (单词长度) | 3 (难度) | 3 (难度) |
| **max_rounds** | 10 | 1 | 1 |
| **concurrency** | 2 (低并发) | 32 (高并发) | 4 (中并发，避免429) |
| **temperature** | 0.7 | 0.3 | 0.0 |
| **训练时间** | 2-3小时 | 2-3小时 | 1-2小时 |

---

## 获取帮助

如需更多帮助：

1. **查看详细文档**：
   - [Wordle指南](../guides/korgym/wordle.md)
   - [Word Puzzle指南](../guides/korgym/word_puzzle.md)
   - [Alphabetical Sorting指南](../guides/korgym/alphabetical_sorting.md)
   - [故障排除](../troubleshooting/index.md)

2. **查看配置模板**：
   - `configs/eval/korgym/TEMPLATE_korgym_game_eval.yaml`
   - `configs/practice/TEMPLATE_korgym_game_practice.yaml`

3. **提交Issue**：
   - 包含完整错误信息
   - 配置文件内容
   - 重现步骤
   - 环境信息

---

*最后更新：2026-03-16*  
*文档版本：v2.0（整合版）*
