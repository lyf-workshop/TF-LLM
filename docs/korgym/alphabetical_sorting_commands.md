# Alphabetical Sorting - 快速命令指南

## 游戏介绍

**Alphabetical Sorting**（字母排序）是一个单轮益智游戏：
- **规则**：3x3方格中包含一个9字母单词的打乱字母
- **目标**：识别出这个隐藏的单词
- **约束**：字母按照DFS路径（上下左右相邻）依次放置
- **输出格式**：`Answer: word`（单个单词，小写）

## 一、启动 KORGym 服务器

在**新终端**中运行（保持运行状态）：

```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting
python game_lib.py --port 8775
```

或者使用默认端口：

```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting
python game_lib.py
```

## 二、预览游戏示例

```bash
cd /mnt/f/youtu-agent

# 预览 seed=100 的游戏
uv run python scripts/preview_korgym_game.py \
    --game_name "22-alphabetical_sorting" \
    --seed 100 \
    --game_port 8775
```

## 三、初始化数据集

### 3.1 训练数据集（50局，seeds 0-49）

```bash
uv run python scripts/init_korgym_dataset.py \
    --dataset "KORGym-AlphabeticalSorting-Qwen-Temp1-Train" \
    --num_samples 50
```

### 3.2 评估数据集（30局，seeds 10000-10029）

```bash
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-AlphabeticalSorting-Qwen-Temp1-Eval" \
    --num_samples 30
```

## 四、运行完整实验流程

### 4.1 评估基线（无经验）

```bash
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_temp1 \
    --dataset_name "KORGym-AlphabeticalSorting-Qwen-Temp1-Eval" \
    --exp_id alphabetical_sorting_baseline_30 \
    --game_port 8775
```

### 4.2 训练（学习分层经验）

```bash
uv run python scripts/run_training_free_GRPO.py \
    --config-name alphabetical_sorting_qwen_temp1_simple
```

**训练过程**：
- 3轮 × 50局 = 150局总训练量
- 每轮后提取 L0（案例）、L1（模式）、L2（元）级经验
- 自动保存经验到 `workspace/alphabetical_sorting_qwen_temp1/experiences/`

### 4.3 评估增强版（使用学习的经验）

```bash
# 增强版配置会自动加载学习到的经验
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_temp1_hierarchical_agent \
    --dataset_name "KORGym-AlphabeticalSorting-Qwen-Temp1-Eval" \
    --exp_id alphabetical_sorting_enhanced_30 \
    --game_port 8775
```

### 4.4 对比结果

```bash
python scripts/compare_paper_scores.py \
    workspace/korgym_eval/alphabetical_sorting_baseline_30.json \
    workspace/korgym_eval/alphabetical_sorting_enhanced_30.json
```

## 五、大规模评估（500局）

### 5.1 创建500局评估数据集

```bash
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-500" \
    --num_samples 500
```

### 5.2 评估基线（500局）

```bash
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_temp1 \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-500" \
    --exp_id alphabetical_sorting_baseline_500 \
    --game_port 8775
```

### 5.3 评估增强版（500局）

```bash
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_temp1_hierarchical_agent \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-500" \
    --exp_id alphabetical_sorting_enhanced_500 \
    --game_port 8775
```

### 5.4 对比结果

```bash
python scripts/compare_paper_scores.py \
    workspace/korgym_eval/alphabetical_sorting_baseline_500.json \
    workspace/korgym_eval/alphabetical_sorting_enhanced_500.json
```

## 六、查看数据集内容

```bash
# 查看训练数据集
uv run python scripts/view_dataset.py \
    --dataset_name "KORGym-AlphabeticalSorting-Qwen-Temp1-Train" \
    --limit 10

# 查看评估数据集
uv run python scripts/view_dataset.py \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-500" \
    --limit 20
```

## 七、清理数据（重新开始）

```bash
uv run python scripts/cleanup_korgym_temp_data.py \
    --dataset_prefix "KORGym-AlphabeticalSorting"
```

## 重要提示

1. **游戏服务器**：必须先启动并保持运行
2. **游戏名称**：配置中使用 `"22-alphabetical_sorting"` 或 `"Alphabetical Sorting"`
3. **端口**：默认 8775，确保与服务器一致
4. **答案格式**：单个小写单词，不要用引号或列表
5. **种子范围**：训练用 0-49，评估用 10000+，避免重叠

## 配置文件位置

- 基线 Agent：`configs/agents/practice/alphabetical_sorting_qwen_temp1.yaml`
- 训练配置：`configs/practice/alphabetical_sorting_qwen_temp1_simple.yaml`
- 增强版 Agent：训练后自动生成在 `workspace/alphabetical_sorting_qwen_temp1/`

## 预期结果

根据 KORGym 论文，Alphabetical Sorting 游戏：
- 属于 **puzzle** 类别
- 单轮游戏（single-turn）
- 难度等级：Level 4
- 预期基线分数：待测试
- 预期提升：使用分层经验后应有显著提升

## 故障排除

1. **连接拒绝**：检查 KORGym 服务器是否运行
2. **端口错误**：确保所有命令使用相同端口
3. **答案格式错误**：答案必须是单个单词，不要包含特殊字符
4. **模块未找到**：使用 `uv run` 而不是直接 `python`

