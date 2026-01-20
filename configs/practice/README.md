# Practice Configurations

训练无需梯度的强化学习（Training-Free GRPO）配置文件。

## 📂 目录结构

配置文件按任务类型分类存储：

```
practice/
├── korgym/          # KORGym 游戏任务（19个配置）
│   ├── alphabetical_sorting_*.yaml  # 字母排序游戏
│   ├── word_puzzle_*.yaml          # 单词拼图游戏
│   ├── wordle_*.yaml               # Wordle 猜词游戏
│   └── korgym_*.yaml               # KORGym 通用配置
├── logic/           # 逻辑推理任务（15个配置）
│   ├── logic_reasoning_zebralogic_*.yaml  # ZebraLogic 推理
│   ├── easy_reasoning_*.yaml              # 简单推理任务
│   ├── medium_reasoning_*.yaml            # 中等推理任务
│   └── qwen_reasoning_*.yaml              # Qwen 模型优化版
├── math/            # 数学推理任务（2个配置）
│   └── math_reasoning*.yaml
└── web/             # Web 搜索任务（1个配置）
    └── web_search.yaml
```

## 🚀 使用方法

### 1. 基本用法

使用配置文件时需要指定子目录路径：

```bash
# 运行 KORGym 游戏训练
uv run python scripts/run_training_free_grpo.py \
    --config_name korgym/alphabetical_sorting_practice

# 运行逻辑推理训练
uv run python scripts/run_training_free_grpo.py \
    --config_name logic/logic_reasoning_zebralogic

# 运行数学推理训练
uv run python scripts/run_training_free_grpo.py \
    --config_name math/math_reasoning

# 运行 Web 搜索训练
uv run python scripts/run_training_free_grpo.py \
    --config_name web/web_search
```

### 2. 配置文件说明

每个配置文件包含以下主要部分：

```yaml
# @package _global_
defaults:
  - /eval/xxx/xxx_eval@evaluation  # 引用评估配置
  - _self_

exp_id: "experiment_name"

# 训练参数
practice:
  epochs: 3                      # 训练轮数
  batch_size: 100                # 批次大小
  grpo_n: 5                      # GRPO 采样数
  rollout_concurrency: 4         # 并发数
  rollout_temperature: 0.8       # 采样温度
  
  # 分层学习设置（可选）
  hierarchical_learning:
    enabled: true
    l1_aggregation_threshold: 5  # L0→L1 聚合阈值
    l2_aggregation_threshold: 3  # L1→L2 聚合阈值
    experience_save_path: workspace/hierarchical_experiences/xxx.json
    agent_save_path: configs/agents/practice/xxx_agent.yaml

# 数据集配置
data:
  practice_dataset_name: "YourDatasetName"

# 任务特定设置（如 KORGym）
korgym:
  enabled: true
  game_name: "22-alphabetical_sorting"
  # ... 其他游戏特定参数
```

## 📊 配置文件分类详情

### KORGym 游戏（19个文件）

**Alphabetical Sorting**（6个）：
- `alphabetical_sorting_practice.yaml` - 基础版本
- `alphabetical_sorting_qwen_100.yaml` - Qwen 模型优化
- `alphabetical_sorting_qwen_enhanced_100.yaml` - 增强版
- `alphabetical_sorting_qwen_optimized.yaml` - 最优化版
- `alphabetical_sorting_qwen_simple_100.yaml` - 简化版
- `alphabetical_sorting_qwen_temp1_simple.yaml` - 温度实验版

**Word Puzzle**（6个）：
- `word_puzzle_practice.yaml` - 基础版本
- `word_puzzle_hierarchical_experiment.yaml` - 分层学习实验
- `word_puzzle_qwen_hierarchical.yaml` - Qwen 分层学习
- `word_puzzle_qwen_optimized_hierarchical.yaml` - 优化分层版
- `word_puzzle_qwen_temp1_hierarchical.yaml` - 温度实验分层版
- `word_puzzle_qwen_temp1_simple.yaml` - 温度实验简化版
- `word_puzzle_qwen72b_grpo.yaml` - Qwen-72B GRPO 版

**Wordle**（4个）：
- `wordle_practice.yaml` - 基础版本
- `wordle_qwen_grpo.yaml` - Qwen GRPO
- `wordle_qwen32b_grpo.yaml` - Qwen-32B GRPO
- `wordle_qwen72b_grpo.yaml` - Qwen-72B GRPO

**通用**（2个）：
- `korgym_practice.yaml` - 通用游戏配置
- `korgym_hierarchical_test.yaml` - 分层学习测试

### 逻辑推理（15个文件）

**ZebraLogic 系列**（7个）：
- `logic_reasoning_zebralogic.yaml` - 基础版
- `logic_reasoning_zebralogic_100.yaml` - 100题版本
- `logic_reasoning_zebralogic_structured.yaml` - 结构化版
- `logic_reasoning_zebralogic_optimized.yaml` - 优化版
- `logic_reasoning_zebralogic_optimized_normalverify.yaml` - 标准验证优化版
- `logic_reasoning_zebralogic_with_error_analysis.yaml` - 带错误分析
- `logic_reasoning_zebralogic_with_error_extractor.yaml` - 带错误提取

**难度分级**（5个）：
- `easy_reasoning_enhance_num1.yaml` - 简单增强版
- `medium_reasoning_enhance_num1.yaml` - 中等增强版1
- `medium_reasoning_enhance_num2.yaml` - 中等增强版2
- `medium_reasoning_hierarchical_num1.yaml` - 中等分层版
- `medium_reasoning_normal_num1.yaml` - 中等标准版

**Qwen 优化**（3个）：
- `qwen_reasoning_easy.yaml` - Qwen 简单推理
- `qwen_reasoning_medium.yaml` - Qwen 中等推理
- `qwen_reasoning_medium_old.yaml` - Qwen 中等推理（旧版）

### 数学推理（2个文件）

- `math_reasoning.yaml` - 基础数学推理
- `math_reasoning_paper_exp.yaml` - 论文实验版本

### Web 搜索（1个文件）

- `web_search.yaml` - Web 搜索任务

## ⚠️ 重要说明

### 1. 配置加载机制

配置加载器会自动处理子目录路径：

```python
# utu/config/loader.py
if not name.startswith("practice/"):
    name = "practice/" + name
```

因此你只需要指定 `korgym/xxx` 而不是完整路径 `practice/korgym/xxx`。

### 2. 引用路径说明

配置文件内部的引用路径**不需要修改**：

- ✅ **evaluation 引用**：在 `defaults:` 中引用 eval 配置，路径保持不变
  ```yaml
  defaults:
    - /eval/korgym/alphabetical_sorting_eval@evaluation
  ```

- ✅ **agent_save_path**：指向 `configs/agents/practice/` 的路径保持不变
  ```yaml
  hierarchical_learning:
    agent_save_path: configs/agents/practice/xxx_agent.yaml
  ```

### 3. 命令行使用示例

```bash
# KORGym 游戏
uv run python scripts/run_training_free_grpo.py --config_name korgym/wordle_practice
uv run python scripts/run_training_free_grpo.py --config_name korgym/word_puzzle_qwen_hierarchical

# 逻辑推理
uv run python scripts/run_training_free_grpo.py --config_name logic/logic_reasoning_zebralogic_optimized
uv run python scripts/run_training_free_grpo.py --config_name logic/qwen_reasoning_medium

# 数学推理
uv run python scripts/run_training_free_grpo.py --config_name math/math_reasoning

# Web 搜索
uv run python scripts/run_training_free_grpo.py --config_name web/web_search
```

## 📝 添加新配置

创建新的 practice 配置时：

1. 根据任务类型选择对应的子目录
2. 复制相似的配置文件作为模板
3. 修改配置参数
4. 使用 `子目录/文件名` 的方式引用

## 🔗 相关文档

- [Practice 系统文档](../../docs/practice.md)
- [评估配置](../eval/)
- [智能体配置](../agents/practice/)
- [分层学习指南](../../分层经验学习-完整运行指南.md)















