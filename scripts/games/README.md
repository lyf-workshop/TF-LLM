# Games 游戏实验脚本使用文档

本文档介绍 `scripts/games/` 目录下所有游戏相关脚本的功能和使用方法。这些脚本用于运行和管理四个KORGym游戏的完整实验流程。

---

## 目录

- [概述](#概述)
- [Alphabetical Sorting](#alphabetical-sorting字母排序)
- [Word Puzzle](#word-puzzle单词拼图)
- [Wordle](#wordle猜词游戏)
- [ZebraLogic](#zebralogic逻辑推理)
- [通用实验流程](#通用实验流程)

---

## 概述

### 游戏列表

| 游戏名称 | 游戏ID | 默认端口 | 脚本数量 | 说明 |
|---------|--------|---------|---------|------|
| **Alphabetical Sorting** | `22-alphabetical_sorting` | 8775 | 6 | 字母排序游戏 |
| **Word Puzzle** | `8-word_puzzle` | 8775/8765 | 7 | 单词拼图游戏 |
| **Wordle** | `33-wordle` | 8765 | 7 | 经典猜词游戏 |
| **ZebraLogic** | zebralogic | - | 7 | 逻辑推理游戏 |

### 典型实验流程

所有游戏实验通常遵循相同的五步流程：

```
1. 数据准备    → 创建训练集和评估集
2. 基线评估    → 评估无经验的Agent表现
3. GRPO训练    → Agent学习并生成分层经验(L0/L1/L2)
4. 增强评估    → 评估有经验的Agent表现  
5. 结果对比    → 分析训练前后的性能提升
```

---

## Alphabetical Sorting（字母排序）

### 脚本列表

| 脚本名称 | 类型 | 功能 |
|---------|-----|------|
| `run_alphabetical_sorting_experiment.sh` | Shell | 标准完整实验流程 |
| `run_alphabetical_sorting_full_experiment.sh` | Shell | 优化版完整实验流程 |
| `quick_test_alphabetical_prompts.sh` | Shell | 快速测试不同prompt效果 |
| `clean_and_restart_alphabetical_sorting.sh` | Shell | 清理数据并重新开始 |
| `clean_alphabetical_sorting_cache.py` | Python | 清理经验缓存 |
| `restart_alphabetical_sorting_training.py` | Python | 完整重启训练流程 |

---

### 1. `run_alphabetical_sorting_full_experiment.sh` - 完整实验流程（推荐）

**功能**: 运行完整的Alphabetical Sorting实验，使用优化的简洁prompt配置

**实验配置**:
- 训练数据集: 100局（2轮 × 50局）
- 评估数据集: 120局
- 游戏端口: 8775
- 预计时间: ~55分钟

**使用方法**:

```bash
# 确保在项目根目录
cd /mnt/f/youtu-agent

# 1. 确保游戏服务器正在运行
cd KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8775

# 2. 在另一个终端运行实验
cd /mnt/f/youtu-agent
bash scripts/games/alphabetical_sorting/run_alphabetical_sorting_full_experiment.sh
```

**实验步骤**:
1. 检查数据集（100训练 + 120评估）
2. 基线评估（简洁prompt，~20分钟）
3. 训练阶段（学习分层经验，~15分钟）
4. 增强评估（使用经验，~20分钟）
5. 结果对比分析

**输出文件**:
- 基线结果: `workspace/korgym_eval/alphabetical_sorting_baseline_simple.json`
- 增强结果: `workspace/korgym_eval/alphabetical_sorting_enhanced_simple.json`
- 经验库: `workspace/hierarchical_experiences/alphabetical_sorting_simple_100.json`
- Agent配置: `configs/agents/practice/alphabetical_sorting_simple_100_agent.yaml`

---

### 2. `quick_test_alphabetical_prompts.sh` - 快速Prompt测试

**功能**: 使用5局游戏快速对比不同prompt版本的效果

**使用方法**:

```bash
# 快速测试（~5分钟）
bash scripts/games/alphabetical_sorting/quick_test_alphabetical_prompts.sh
```

**测试内容**:
1. 测试官方风格简洁prompt
2. 测试详细增强prompt
3. 对比两个版本的表现

**用途**: 在运行完整实验前，快速确定最佳prompt配置

---

### 3. `clean_and_restart_alphabetical_sorting.sh` - 清理并重启

**功能**: 完全清理所有Alphabetical Sorting实验数据并重新创建数据集

**使用方法**:

```bash
bash scripts/games/alphabetical_sorting/clean_and_restart_alphabetical_sorting.sh
```

**清理内容**:
- 数据库中的数据集
- 评估结果文件
- 经验文件
- 生成的agent配置
- workspace中的agents

**清理后**: 自动创建新的训练集(100局)和评估集(120局)

---

### 4. `clean_alphabetical_sorting_cache.py` - 清理经验缓存

**功能**: 删除数据库中的经验缓存，允许重新提取经验

**使用方法**:

```bash
uv run python scripts/games/alphabetical_sorting/clean_alphabetical_sorting_cache.py
```

**使用场景**: 当需要重新提取经验但保留数据集时使用

---

### 5. `restart_alphabetical_sorting_training.py` - 重启训练

**功能**: 完整重启训练流程，清理训练相关数据但保留数据集和基线评估

**使用方法**:

```bash
uv run python scripts/games/alphabetical_sorting/restart_alphabetical_sorting_training.py
```

**删除内容**:
- 训练经验缓存
- 训练rollout数据
- 训练后评估数据

**保留内容**:
- 基线评估数据
- 训练和评估数据集

---

## Word Puzzle（单词拼图）

### 脚本列表

| 脚本名称 | 类型 | 功能 |
|---------|-----|------|
| `run_complete_word_puzzle_experiment.sh` | Shell | 论文对齐的完整实验 |
| `run_word_puzzle_experiment.sh` | Shell | 标准实验流程 |
| `run_word_puzzle_72b_full_experiment.sh` | Shell | Qwen2.5-72B专用实验 |
| `clean_word_puzzle_data.sh` | Shell | 清理所有数据 |
| `eval_word_puzzle_paper_aligned.py` | Python | 论文对齐的评估脚本 |
| `analyze_word_puzzle_results.py` | Python | 分析评估结果 |
| `debug_word_puzzle_results.py` | Python | 调试准确率问题 |

---

### 1. `run_complete_word_puzzle_experiment.sh` - 完整实验（论文对齐）

**功能**: 执行完整的Word Puzzle实验，严格按照KORGym论文的评估方式

**实验配置**:
- 游戏: 8-word_puzzle
- 端口: 8775
- 难度等级: 4
- 评估局数: 50局（论文标准）
- 基础Agent: `practice/logic_agent_hierarchical_learning_clean`

**使用方法**:

```bash
# 自动运行完整流程
bash scripts/games/word_puzzle/run_complete_word_puzzle_experiment.sh
```

**实验步骤**:
1. 启动游戏服务器（自动检查或启动）
2. 评估基线Agent（无经验，50局）
3. 训练Agent（生成分层经验）
4. 评估增强Agent（有经验，50局）
5. 对比结果与论文数据

**输出文件**:
- 基线: `workspace/korgym_paper_aligned/baseline_clean_word_puzzle.json`
- 增强: `workspace/korgym_paper_aligned/enhanced_hierarchical_word_puzzle.json`
- 经验库: `workspace/hierarchical_experiences/word_puzzle.json`
- 分数摘要: `workspace/korgym_paper_aligned/score.txt`

**特色功能**:
- 自动与论文Table 7对比
- 显示在论文模型中的排名
- 找出最接近的模型

---

### 2. `eval_word_puzzle_paper_aligned.py` - 论文对齐评估

**功能**: 独立的评估脚本，严格按照论文标准评估Word Puzzle表现

**使用方法**:

```bash
# 评估基线
uv run python scripts/games/word_puzzle/eval_word_puzzle_paper_aligned.py \
  --agent_config practice/logic_agent_hierarchical_learning_clean \
  --exp_id baseline_eval \
  --num_seeds 50

# 评估增强版（训练后）
uv run python scripts/games/word_puzzle/eval_word_puzzle_paper_aligned.py \
  --agent_config word_puzzle_hierarchical_agent \
  --exp_id enhanced_eval \
  --num_seeds 50

# 快速测试（20局）
uv run python scripts/games/word_puzzle/eval_word_puzzle_paper_aligned.py \
  --agent_config my_agent \
  --exp_id test_eval \
  --num_seeds 20 \
  --level 4
```

**参数说明**:
- `--agent_config`: Agent配置名称
- `--exp_id`: 实验ID（用于输出文件名）
- `--num_seeds`: 评估局数（论文使用50，可设为20快速测试）
- `--level`: 游戏难度级别（1-5，论文使用4）
- `--output_dir`: 输出目录（默认：`workspace/korgym_paper_aligned`）

**输出信息**:
- 与论文Table 7的对比
- 分数分布（0.0, 0.0-0.2, 0.2-0.4, etc.）
- 平均分数（可直接用于论文表格）
- 标准差、最高分、最低分
- 时间统计

---

### 3. `run_word_puzzle_72b_full_experiment.sh` - Qwen2.5-72B实验

**功能**: 专门为Qwen2.5-72B-Instruct模型设计的完整实验流程

**使用方法**:

```bash
bash scripts/games/word_puzzle/run_word_puzzle_72b_full_experiment.sh
```

**特点**:
- 针对72B模型优化的配置
- 自动查找训练后生成的agent配置
- 详细的进度显示和结果统计

---

### 4. `analyze_word_puzzle_results.py` - 结果分析

**功能**: 详细分析Word Puzzle评估结果

**使用方法**:

```bash
# 分析基线评估
uv run python scripts/games/word_puzzle/analyze_word_puzzle_results.py \
  --exp_id word_puzzle_baseline_eval

# 分析增强评估
uv run python scripts/games/word_puzzle/analyze_word_puzzle_results.py \
  --exp_id word_puzzle_practice_eval
```

**显示内容**:
- 总样本数和正确数
- 准确率和平均奖励
- 按阶段统计
- 前10个样本详情
- 错误样本分析（≤5个）
- 正确样本分析（≤5个）

---

### 5. `debug_word_puzzle_results.py` - 调试工具

**功能**: 检查评估准确率为0的问题，用于故障排查

**使用方法**:

```bash
uv run python scripts/games/word_puzzle/debug_word_puzzle_results.py
```

**检查内容**:
- 样本数量和基本统计
- 前5个样本的详细信息
- 失败原因分析（无响应、未提取答案、奖励为0）
- 配置检查

---

### 6. `clean_word_puzzle_data.sh` - 数据清理

**功能**: 清理所有Word Puzzle相关数据，重新开始实验

**使用方法**:

```bash
bash scripts/games/word_puzzle/clean_word_puzzle_data.sh
```

**清理内容**:
1. 数据库数据（数据集和评估样本）
2. 评估结果文件
3. 经验文件
4. 生成的agent配置

---

## Wordle（猜词游戏）

### 脚本列表

| 脚本名称 | 类型 | 功能 |
|---------|-----|------|
| `run_wordle_full_experiment.sh` | Shell | 完整实验流程 |
| `clean_wordle_data.sh` | Shell | 清理所有数据 |
| `analyze_wordle_top20.py` | Python | 分析前N题得分 |
| `check_wordle_dataset.py` | Python | 检查数据集 |
| `check_wordle_eval_samples.py` | Python | 检查评估样本 |
| `diagnose_wordle_training.py` | Python | 诊断训练问题 |
| `test_wordle_config.py` | Python | 测试配置 |

---

### 1. `run_wordle_full_experiment.sh` - 完整实验流程

**功能**: Wordle游戏的完整Training-Free GRPO实验流程

**实验配置**:
- 训练数据集: 100题
- 评估数据集: 120题
- 训练轮数: 2 epochs
- 游戏端口: 8765

**使用方法**:

```bash
# 确保Wordle服务器运行在8765端口
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8765

# 在另一个终端运行实验
cd /mnt/f/youtu-agent
bash scripts/games/wordle/run_wordle_full_experiment.sh
```

**实验步骤**:
1. 创建数据集（100训练 + 120评估）
2. 基线评估（120题）
3. GRPO训练（100题 × 2 epochs）
4. 增强评估（120题）
5. 对比结果

**输出文件**:
- 基线: `workspace/korgym_eval/wordle_baseline_120.json`
- 增强: `workspace/korgym_eval/wordle_enhanced_120.json`

**特色**:
- 彩色日志输出
- 每个步骤的确认提示
- 详细的进度信息

---

### 2. `analyze_wordle_top20.py` - Top N 分析

**功能**: 统计Wordle游戏前N题的得分情况，支持详细分析

**使用方法**:

```bash
# 分析前20题（默认）
uv run python scripts/games/wordle/analyze_wordle_top20.py \
  --exp_id wordle_eval

# 分析前30题
uv run python scripts/games/wordle/analyze_wordle_top20.py \
  --exp_id wordle_practice_eval \
  --count 30

# 简短写法
uv run python scripts/games/wordle/analyze_wordle_top20.py -e wordle_eval -n 20
```

**显示内容**:
- 每题详细信息（题号、Seed、得分、结果）
- 统计摘要（总题数、成功数、准确率、平均分）
- 得分分布（1.0分、0.0分的数量和百分比）
- 连续表现（最长连续成功/失败）
- 前后对比（前10题 vs 后10题，仅当N≥20）

**参数说明**:
- `--exp_id, -e`: 实验ID（必需）
- `--count, -n`: 要统计的题目数量（默认20）

---

### 3. `check_wordle_dataset.py` - 数据集检查

**功能**: 检查Wordle数据集的实际情况

**使用方法**:

```bash
uv run python scripts/games/wordle/check_wordle_dataset.py
```

**检查内容**:
- 训练数据集: `KORGym-Wordle-Train-100`（预期100题）
- 评估数据集: `KORGym-Wordle-Eval-120`（预期120题）
- 所有Wordle数据集列表

---

### 4. `check_wordle_eval_samples.py` - 评估样本检查

**功能**: 检查评估样本的详细信息

**使用方法**:

```bash
uv run python scripts/games/wordle/check_wordle_eval_samples.py
```

---

### 5. `diagnose_wordle_training.py` - 训练诊断

**功能**: 诊断Wordle训练过程中的问题

**使用方法**:

```bash
uv run python scripts/games/wordle/diagnose_wordle_training.py
```

---

### 6. `test_wordle_config.py` - 配置测试

**功能**: 测试Wordle配置的正确性

**使用方法**:

```bash
uv run python scripts/games/wordle/test_wordle_config.py
```

---

### 7. `clean_wordle_data.sh` - 数据清理

**功能**: 清理所有Wordle相关数据

**使用方法**:

```bash
bash scripts/games/wordle/clean_wordle_data.sh
```

---

## ZebraLogic（逻辑推理）

### 脚本列表

| 脚本名称 | 类型 | 功能 |
|---------|-----|------|
| `run_zebralogic_experiment.sh` | Shell | 完整实验流程 |
| `analyze_zebra_dataset.py` | Python | 分析数据集 |
| `check_zebralogic_data.py` | Python | 检查数据 |
| `clean_zebralogic_training_data.py` | Python | 清理训练数据 |
| `compare_zebralogic_results.py` | Python | 对比结果 |
| `diagnose_zebralogic_eval.py` | Python | 诊断评估问题 |
| `view_zebralogic_results.py` | Python | 查看结果 |

---

### 1. `run_zebralogic_experiment.sh` - 完整实验流程

**功能**: ZebraLogic的完整Training-Free GRPO实验流程

**实验配置**:
- 训练集: 100题（难度稍高）
- 测试集: 30题（难度中等）
- Epochs: 3
- Batch Size: 100
- GRPO Group Size: 5
- 学习温度: 0.7
- 评估温度: 0.3

**使用方法**:

```bash
bash scripts/games/zebralogic/run_zebralogic_experiment.sh
```

**实验步骤**:
1. 分析并创建数据集
2. 基线评估（训练前）
3. Training-Free GRPO训练（预计30-90分钟）
4. 评估增强后的Agent
5. 结果分析和对比

**输出文件**:
- 经验库: `configs/agents/practice/logic_practice_zebralogic_agent.yaml`

**特色**:
- 交互式确认每个步骤
- 彩色日志输出
- 详细的配置显示
- 完成后提供后续操作建议

---

### 2. `analyze_zebra_dataset.py` - 数据集分析

**功能**: 分析ZebraLogic数据集的统计信息

**使用方法**:

```bash
uv run python scripts/games/zebralogic/analyze_zebra_dataset.py
```

---

### 3. `check_zebralogic_data.py` - 数据检查

**功能**: 检查ZebraLogic数据的完整性

**使用方法**:

```bash
uv run python scripts/games/zebralogic/check_zebralogic_data.py
```

---

### 4. `clean_zebralogic_training_data.py` - 清理训练数据

**功能**: 清理ZebraLogic训练相关数据

**使用方法**:

```bash
uv run python scripts/games/zebralogic/clean_zebralogic_training_data.py
```

---

### 5. `compare_zebralogic_results.py` - 结果对比

**功能**: 对比ZebraLogic训练前后的结果

**使用方法**:

```bash
uv run python scripts/games/zebralogic/compare_zebralogic_results.py
```

---

### 6. `diagnose_zebralogic_eval.py` - 评估诊断

**功能**: 诊断ZebraLogic评估过程中的问题

**使用方法**:

```bash
uv run python scripts/games/zebralogic/diagnose_zebralogic_eval.py
```

---

### 7. `view_zebralogic_results.py` - 查看结果

**功能**: 查看ZebraLogic实验结果的详细信息

**使用方法**:

```bash
uv run python scripts/games/zebralogic/view_zebralogic_results.py
```

---

## 通用实验流程

### 实验前准备

所有游戏实验开始前需要确保：

1. **环境配置**

```bash
# 设置数据库URL
export UTU_DB_URL="postgresql://user:password@localhost/dbname"

# 设置LLM配置
export UTU_LLM_TYPE="openai"
export UTU_LLM_MODEL="gpt-4"
export UTU_LLM_BASE_URL="https://api.openai.com/v1"
export UTU_LLM_API_KEY="your-api-key"
```

2. **游戏服务器运行**

```bash
# Alphabetical Sorting
cd KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8775

# Word Puzzle
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# Wordle
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8765

# ZebraLogic 不需要服务器
```

---

### 常见使用场景

#### 场景1: 运行完整实验

```bash
# 1. 选择游戏（以Alphabetical Sorting为例）
cd /mnt/f/youtu-agent

# 2. 启动游戏服务器
cd KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8775

# 3. 新终端运行实验
cd /mnt/f/youtu-agent
bash scripts/games/alphabetical_sorting/run_alphabetical_sorting_full_experiment.sh

# 4. 等待完成（~55分钟）

# 5. 查看结果
cat workspace/korgym_eval/alphabetical_sorting_baseline_simple.json
cat workspace/korgym_eval/alphabetical_sorting_enhanced_simple.json
```

---

#### 场景2: 快速测试Prompt

```bash
# 使用少量数据快速测试不同配置
bash scripts/games/alphabetical_sorting/quick_test_alphabetical_prompts.sh

# 查看结果，选择最佳prompt
# 然后运行完整实验
```

---

#### 场景3: 重新开始实验

```bash
# 完全清理数据并重新开始
bash scripts/games/alphabetical_sorting/clean_and_restart_alphabetical_sorting.sh

# 或者只清理训练数据（保留基线评估）
uv run python scripts/games/alphabetical_sorting/restart_alphabetical_sorting_training.py
```

---

#### 场景4: 分析实验结果

```bash
# Word Puzzle 结果分析
uv run python scripts/games/word_puzzle/analyze_word_puzzle_results.py \
  --exp_id word_puzzle_baseline_eval

# Wordle Top 20 分析
uv run python scripts/games/wordle/analyze_wordle_top20.py \
  --exp_id wordle_eval --count 20

# 使用通用工具查看
uv run python scripts/utils/view_training_results.py
```

---

#### 场景5: 论文对齐评估

```bash
# Word Puzzle 论文标准评估
uv run python scripts/games/word_puzzle/eval_word_puzzle_paper_aligned.py \
  --agent_config practice/my_agent \
  --exp_id my_eval \
  --num_seeds 50

# 查看与论文Table 7的对比
cat workspace/korgym_paper_aligned/my_eval_word_puzzle.json
```

---

### 故障排查

#### 问题1: 游戏服务器无法连接

```bash
# 检查服务器是否运行
curl http://localhost:8775/health

# 如果未运行，启动服务器
cd KORGym/game_lib/<game_folder>
python game_lib.py -p <port>
```

#### 问题2: 数据集不存在

```bash
# 检查数据集
uv run python scripts/utils/view_datasets.py --list

# 重新创建数据集
bash scripts/games/<game>/clean_and_restart_<game>.sh
```

#### 问题3: 评估准确率为0

```bash
# Word Puzzle 调试
uv run python scripts/games/word_puzzle/debug_word_puzzle_results.py

# 检查Agent配置是否正确加载
# 检查游戏服务器是否正常响应
```

#### 问题4: 训练中断

```bash
# 检查经验缓存
uv run python scripts/utils/check_experiments.py

# 清理缓存重新训练
uv run python scripts/games/<game>/clean_<game>_cache.py
```

---

## 脚本命名规范

### Shell脚本 (`.sh`)

- `run_*_experiment.sh`: 运行完整实验流程
- `run_*_full_experiment.sh`: 运行优化版完整实验
- `clean_*.sh`: 清理数据
- `quick_test_*.sh`: 快速测试

### Python脚本 (`.py`)

- `analyze_*.py`: 分析结果数据
- `check_*.py`: 检查数据完整性
- `diagnose_*.py`: 诊断问题
- `compare_*.py`: 对比结果
- `view_*.py`: 查看数据
- `clean_*.py`: 清理数据（Python版本）
- `eval_*.py`: 评估脚本
- `test_*.py`: 测试脚本

---

## 性能指标说明

### 评估指标

| 指标 | 说明 | 计算方式 |
|-----|------|---------|
| **Accuracy** | 样本准确率 | 正确样本数 / 总样本数 |
| **Average Score** | 平均得分 | 所有样本得分的平均值（0.0-1.0） |
| **Success Rate** | 成功率 | 成功样本数 / 总样本数 |
| **Pass@K** | K次尝试通过率 | 至少一次成功的问题数 / 总问题数 |
| **Standard Deviation** | 得分标准差 | 衡量得分的稳定性 |

### 预期结果（参考）

| 游戏 | 基线准确率 | 增强准确率 | 预期提升 |
|-----|-----------|-----------|---------|
| Alphabetical Sorting | ~14% | ~25% | +11% |
| Word Puzzle | ~45% | ~58% | +13% |
| Wordle | ~30% | ~45% | +15% |
| ZebraLogic | ~20% | ~35% | +15% |

*注：实际结果取决于模型、配置和训练参数*

---

## 最佳实践

### 1. 实验前检查清单

- [ ] 确认数据库连接正常
- [ ] 确认LLM API可用
- [ ] 确认游戏服务器运行（如需要）
- [ ] 确认数据集已创建
- [ ] 确认磁盘空间充足（至少5GB）

### 2. 运行实验建议

- **首次运行**: 使用快速测试脚本验证配置
- **正式实验**: 使用完整实验脚本
- **论文对齐**: 使用论文对齐的评估脚本
- **重复实验**: 先清理数据再运行

### 3. 结果分析建议

- 使用分析脚本查看详细统计
- 对比训练前后的结果
- 检查经验库的L0/L1/L2分布
- 验证与论文结果的一致性

### 4. 调试建议

- 从简单的检查脚本开始
- 逐步排查问题（数据→配置→训练→评估）
- 使用诊断脚本定位具体问题
- 查看日志文件获取详细错误信息

---

## 输出文件结构

```
workspace/
├── korgym_eval/                    # 评估结果
│   ├── <game>_baseline_*.json     # 基线评估结果
│   └── <game>_enhanced_*.json     # 增强评估结果
│
├── korgym_paper_aligned/           # 论文对齐评估
│   ├── baseline_*.json
│   ├── enhanced_*.json
│   └── score.txt                   # 分数摘要
│
├── hierarchical_experiences/       # 分层经验库
│   └── <game>_*.json              # L0/L1/L2经验
│
└── agents/                         # 生成的Agent配置
    └── <game>_*.yaml

configs/agents/practice/            # Agent配置文件
└── <game>_*_agent.yaml            # 训练后的Agent
```

---

## 附录

### 快速参考表

| 操作 | 命令 |
|-----|------|
| 列出所有数据集 | `uv run python scripts/utils/view_datasets.py --list` |
| 查看实验结果 | `uv run python scripts/utils/view_training_results.py` |
| 检查实验状态 | `uv run python scripts/utils/check_experiments.py` |
| 清理所有数据 | `uv run python scripts/utils/clean_experiment_data.py --all` |
| 查看经验库 | `cat workspace/hierarchical_experiences/<game>.json` |

### 常用端口

| 游戏 | 默认端口 |
|-----|---------|
| Alphabetical Sorting | 8775 |
| Word Puzzle | 8775 或 8765 |
| Wordle | 8765 |
| ZebraLogic | 不需要端口 |

---

## 获取帮助

大部分Python脚本支持 `--help` 参数：

```bash
uv run python scripts/games/<game>/<script>.py --help
```

查看Shell脚本内容获取详细说明：

```bash
cat scripts/games/<game>/<script>.sh
```

如遇问题，请：
1. 检查环境变量配置
2. 查看日志文件
3. 使用诊断脚本排查
4. 参考本文档的故障排查部分

---

**文档版本**: v1.0  
**最后更新**: 2026-02-08  
**维护者**: youtu-agent团队
