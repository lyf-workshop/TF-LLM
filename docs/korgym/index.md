# KORGym 游戏实验指南

KORGym（Knowledge-Oriented Reasoning Gym）是一个专为知识推理任务设计的游戏环境集合，用于训练和评估智能体的推理能力。本框架使用 Training-Free GRPO（Group Relative Policy Optimization）方法，无需模型参数更新即可提升智能体性能。

## 📚 文档导航

### 🎮 游戏实验指南

每个游戏都有完整的实验文档，包括规则说明、数据准备、训练流程和问题排查：

- **[Wordle 实验指南](wordle_guide.md)** - 多轮交互猜单词游戏
  - 游戏规则和评分机制
  - 完整实验流程（数据集→训练→评估）
  - 多轮交互策略优化
  - 常见问题和优化建议

- **[Word Puzzle 实验指南](word_puzzle_guide.md)** - 单轮填字游戏
  - 约束满足问题求解
  - 层次经验学习应用
  - 缓存问题处理
  - Level 配置注意事项

- **[Alphabetical Sorting 实验指南](alphabetical_sorting_guide.md)** - 字母排序游戏
  - 字典序排序规则
  - API 限流问题处理（重点）
  - 层次经验学习示例
  - 并发和模型配置优化

### 🔧 工具和参考

- **[常见问题排查指南](troubleshooting.md)** - 系统化的问题诊断和解决方案
  - API 和网络错误（429限流、500服务器错误）
  - 配置错误（层次学习、Level不匹配）
  - 数据和数据库问题（缓存、字段错误）
  - 训练和经验学习错误
  - 完整的诊断流程和检查清单

- **[完整命令参考](../../KORGYM_THREE_GAMES_COMMANDS.md)** - 所有游戏的命令速查表
  - 环境配置和服务器启动
  - 数据集管理命令
  - 训练和评估命令
  - 结果查看和分析工具
  - 清理和重置命令

## 🎮 支持的游戏

当前框架支持以下 KORGym 游戏（点击游戏名称查看详细指南）：

| 游戏 | 类型 | 推理能力 | 端口 | 难度 | 文档 |
|------|------|----------|------|------|------|
| **[Wordle](wordle_guide.md)** | 多轮交互 | 约束推理、信息收集 | 8765 | ⭐⭐⭐ | ✅ 完整 |
| **[Word Puzzle](word_puzzle_guide.md)** | 单轮求解 | 约束满足、逻辑推理 | 8775 | ⭐⭐⭐⭐ | ✅ 完整 |
| **[Alphabetical Sorting](alphabetical_sorting_guide.md)** | 单轮排序 | 比较推理、序列排序 | 8780 | ⭐⭐ | ✅ 完整 |
| **[ZebraLogic](zebralogic_dataset.md)** | 逻辑谜题 | 复杂约束推理 | - | ⭐⭐⭐⭐⭐ | 📝 数据准备 |

### 游戏特点对比

| 特性 | Wordle | Word Puzzle | Alphabetical Sorting |
|------|--------|-------------|---------------------|
| **交互轮数** | 多轮（最多10次） | 单轮 | 单轮 |
| **反馈类型** | 结构化（绿/黄/灰） | 分数 | 分数 |
| **主要挑战** | 信息利用、策略优化 | 约束满足、搜索 | 比较规则、边界情况 |
| **常见问题** | Trajectories处理 | Level不匹配、缓存 | API限流（最突出） |
| **基线准确率** | 30-50% | 20-40% | 60-80% |
| **提升空间** | +10-20% | +10-15% | +10-15% |
| **层次学习适用性** | ✅ 高 | ✅ 高 | ✅ 非常高 |

## 🚀 快速开始

### 5 分钟快速实验

选择一个游戏开始（以 Wordle 为例）：

```bash
# 1. 启动游戏服务器（独立终端）
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8765

# 2. 准备数据集（另一个终端）
cd /mnt/f/youtu-agent
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "33-wordle" \
    --train_count 100 \
    --eval_count 50

# 3. 基线评估
uv run python scripts/run_eval.py \
    --config_name korgym/wordle_eval

# 4. 训练（学习经验）
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym/wordle_practice

# 5. 增强评估
uv run python scripts/run_eval.py \
    --config_name korgym/wordle_practice_eval

# 6. 查看结果对比
uv run python scripts/view_korgym_results.py
```

### 完整实验流程

详细步骤请查看各游戏的实验指南：
- [Wordle 完整流程](wordle_guide.md#🚀-快速开始)
- [Word Puzzle 完整流程](word_puzzle_guide.md#🚀-快速开始)
- [Alphabetical Sorting 完整流程](alphabetical_sorting_guide.md#🚀-快速开始)

## 🎯 核心概念

### Training-Free GRPO

Training-Free GRPO 是一种无需模型参数更新的智能体优化方法：

1. **Rollout Generation**: 对每个问题生成多个候选解（通常 5 个）
2. **Group Advantage**: 基于相对表现计算优势分数
3. **Experience Extraction**: 从高分 rollouts 中提取经验
4. **Experience Integration**: 将经验融入 agent prompt

**优势**:
- ✅ 无需模型微调，成本低
- ✅ 快速迭代，实验周期短
- ✅ 可解释性强（经验以文本形式存在）
- ✅ 灵活适配不同任务

### 层次经验学习

三层抽象的经验提取机制：

- **L0 (案例级别)**: 具体问题的解决方案和错误案例
  - 例："在猜测 'apple' 时，'e' 被标记为黄色，说明它在单词中但位置不对"

- **L1 (模式级别)**: 通用策略和规则
  - 例："优先在开头使用包含高频字母（e,a,r,i,o,t）的单词"

- **L2 (元认知级别)**: 抽象原理和思维模式
  - 例："通过排除法系统性地缩小可能性空间"

**配置示例**:
```yaml
practice:
  hierarchical_learning:
    enabled: true
    levels:
      - name: "L0"
        description: "具体案例和错误分析"
      - name: "L1"
        description: "通用模式和策略"
      - name: "L2"
        description: "元认知原理"
```

## 📊 实验管理

### 数据集管理

```bash
# 创建数据集
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "33-wordle" \
    --train_count 100 \
    --eval_count 50

# 列出所有数据集
uv run python scripts/list_datasets.py | grep KORGym

# 查看数据集详情
uv run python scripts/view_dataset.py \
    --dataset_name "KORGym-Wordle-Eval-50" \
    --limit 5

# 清理并重新创建
uv run python scripts/clean_and_recreate_datasets.py
```

### 实验结果管理

```bash
# 查看所有实验结果
uv run python scripts/view_experiment_results.py

# 查看特定实验
uv run python scripts/view_experiment_results.py \
    --exp_id wordle_baseline_eval wordle_practice_eval

# 使用专用的 KORGym 结果查看器
uv run python scripts/view_korgym_results.py

# 分析前N题表现（以 Wordle 为例）
uv run python scripts/analyze_wordle_top20.py \
    --exp_id wordle_practice_eval \
    --top_n 20

# 清理特定实验结果
uv run python scripts/clean_experiment_data.py \
    --exp_id wordle_baseline_eval
```

### 配置文件结构

```
configs/
├── agents/practice/           # Agent 配置
│   ├── wordle_agent.yaml     # 基础 agent
│   ├── wordle_practice_agent.yaml  # 训练后的 agent（自动生成）
│   ├── word_puzzle_agent.yaml
│   └── alphabetical_sorting_agent.yaml
├── practice/korgym/          # 训练配置
│   ├── wordle_practice.yaml
│   ├── word_puzzle_practice.yaml
│   └── alphabetical_sorting_practice.yaml
└── eval/korgym/              # 评估配置
    ├── wordle_eval.yaml      # 基线评估
    ├── wordle_practice_eval.yaml  # 训练后评估
    ├── word_puzzle_eval.yaml
    └── alphabetical_sorting_eval.yaml
```

## 🔍 常见问题快速索引

遇到问题？先查看 [常见问题排查指南](troubleshooting.md)，或直接跳转到：

- [API 限流（429错误）](troubleshooting.md#error-429-api-rate-limiting)
- [服务器500错误](troubleshooting.md#500-server-error-game-server-crash)
- [层次学习未启用](troubleshooting.md#hierarchical-learning-not-enabled)
- [Level 不匹配](troubleshooting.md#level-mismatch)
- [评估结果缓存](troubleshooting.md#cached-evaluation-results)
- [Trajectories 错误](troubleshooting.md#typeerror-object-of-type-nonetype-has-no-len)

**最常见的三个问题**:
1. **Alphabetical Sorting API 限流** → 降低 `rollout_concurrency` 到 4，使用 7B 模型
2. **Word Puzzle 准确率 0%** → 检查训练和评估的 `level` 是否一致，清理缓存
3. **经验数量少** → 确保 `hierarchical_learning` 在 `practice:` 块内

## 📖 相关文档

### 框架文档
- [Agent Practice 主文档](../practice.md) - Training-Free GRPO 框架详细说明
- [评估框架](../eval.md) - 评估系统使用指南
- [配置系统](../config.md) - 配置文件结构说明
- [Agent 范式](../agents.md) - SimpleAgent 和 OrchestraAgent

### 进阶主题
- [Practice 重试机制](../../PRACTICE_RETRY_MECHANISM_GUIDE.md) - 重试策略和指数退避
- [错误分析系统](../advanced/error_analysis/index.md) - 经验质量分析

### 配置模板
- [配置文件模板说明](../../configs/eval/korgym/README_TEMPLATES.md)
- [通用游戏评估模板](../../configs/eval/korgym/TEMPLATE_korgym_game_eval.yaml)
- [训练配置模板](../../configs/practice/TEMPLATE_korgym_game_practice.yaml)

## 🔗 外部资源

- [KORGym 项目主页](https://razor233.github.io/KORGYM_HomePage/)
- [KORGym GitHub](https://github.com/TencentCloudADP/youtu-agent)
- [Training-Free GRPO 论文 (arXiv)](https://arxiv.org/abs/2510.08191)
- [Wordle 游戏规则](https://www.nytimes.com/games/wordle/index.html)

## 🤝 贡献和反馈

遇到问题或有改进建议？

1. 查看 [常见问题排查指南](troubleshooting.md)
2. 搜索已有的 GitHub Issues
3. 创建新的 Issue，包含：
   - 详细的错误信息
   - 配置文件内容
   - 重现步骤
   - 环境信息

---

**快速链接**:
[Wordle](wordle_guide.md) | [Word Puzzle](word_puzzle_guide.md) | [Alphabetical Sorting](alphabetical_sorting_guide.md) | [排查指南](troubleshooting.md) | [命令参考](../../KORGYM_THREE_GAMES_COMMANDS.md)

