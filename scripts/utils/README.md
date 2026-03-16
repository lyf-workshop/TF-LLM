# Utils 工具脚本使用文档

本文档介绍 `scripts/utils/` 目录下所有工具脚本的功能和使用方法。

---

## 目录

- [数据管理](#数据管理)
- [实验分析](#实验分析)
- [评估结果查看](#评估结果查看)
- [经验学习分析](#经验学习分析)
- [开发调试](#开发调试)
- [工具检查](#工具检查)

---

## 数据管理

### 1. `view_datasets.py` - 数据集查看工具

**功能**: 查看、对比和导出数据库中的数据集信息

**主要功能**:
- 列出所有数据集及统计信息
- 查看特定数据集的详细信息和样本
- 对比多个数据集
- 根据游戏名称搜索数据集
- 导出数据集信息到 JSON

**使用方法**:

```bash
# 列出所有数据集
python scripts/utils/view_datasets.py --list

# 查看特定数据集（显示3个样本）
python scripts/utils/view_datasets.py --dataset "KORGym-WordPuzzle-Eval-50" --samples 3

# 过滤显示（只显示KORGym相关）
python scripts/utils/view_datasets.py --list --filter KORGym

# 对比多个数据集
python scripts/utils/view_datasets.py --compare "KORGym-Wordle-Train-100" "KORGym-Wordle-Eval-50"

# 根据游戏名称搜索
python scripts/utils/view_datasets.py --game "33-wordle"

# 导出数据集到JSON
python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Eval-50" --export dataset.json
```

---

### 2. `view_dataset.py` - 简单数据集查看工具

**功能**: 快速查看单个数据集的内容

**使用方法**:

```bash
# 查看数据集（默认显示10个样本）
python scripts/utils/view_dataset.py --dataset_name "KORGym-WordPuzzle-Eval-50"

# 自定义显示样本数量
python scripts/utils/view_dataset.py --dataset_name "KORGym-WordPuzzle-Eval-50" --limit 20
```

---

### 3. `clean_experiment_data.py` - 实验数据清理工具

**功能**: 删除数据库中的评估结果和数据集

**使用方法**:

```bash
# 列出所有实验和数据集
python scripts/utils/clean_experiment_data.py --list

# 删除特定实验
python scripts/utils/clean_experiment_data.py --exp_id word_puzzle_baseline_eval

# 删除多个实验
python scripts/utils/clean_experiment_data.py --exp_id exp1 exp2 exp3

# 删除特定数据集
python scripts/utils/clean_experiment_data.py --dataset "KORGym-WordPuzzle-Eval-50"

# 删除所有数据（危险操作，需要确认）
python scripts/utils/clean_experiment_data.py --all

# 删除论文实验相关数据
python scripts/utils/clean_experiment_data.py --paper_exp

# 跳过确认提示（慎用）
python scripts/utils/clean_experiment_data.py --exp_id test_exp --force
```

---

### 4. `clean_and_recreate_datasets.py` - 重建KORGym数据集

**功能**: 清理旧的KORGym数据集并重新创建（修复meta字段问题）

**使用方法**:

```bash
# 自动清理并重新创建所有KORGym数据集
uv run python scripts/utils/clean_and_recreate_datasets.py
```

**操作流程**:
1. 删除所有KORGym相关数据集（需要用户确认）
2. 重新创建三个游戏的训练和评估数据集：
   - Word Puzzle (8-word_puzzle)
   - Alphabetical Sorting (22-alphabetical_sorting)
   - Wordle (33-wordle)

---

## 实验分析

### 5. `check_experiments.py` - 实验检查工具

**功能**: 检查数据库中存储的所有实验的详细信息

**主要功能**:
- 列出所有评估实验及统计信息
- 列出所有经验缓存实验
- 显示实验的样本数、准确率、时间成本等

**使用方法**:

```bash
# 检查所有实验
python scripts/utils/check_experiments.py
```

**输出信息**:
- 实验ID
- 样本统计（总数、问题数、每题样本数）
- 正确性（正确数、准确率、平均reward）
- 时间统计（平均耗时、时间范围）
- 数据集和阶段分布

---

### 6. `view_eval_results.py` - 评估结果查看工具

**功能**: 查看和对比评估实验的结果

**使用方法**:

```bash
# 列出所有实验
python scripts/utils/view_eval_results.py --list

# 查看特定实验
python scripts/utils/view_eval_results.py --exp_id word_puzzle_baseline_eval

# 查看详细信息（显示前10个样本）
python scripts/utils/view_eval_results.py --exp_id word_puzzle_baseline_eval --detailed

# 对比两个实验（基线 vs 训练后）
python scripts/utils/view_eval_results.py --compare baseline_exp practice_exp
```

**显示指标**:
- 总样本数和已判断样本数
- 正确样本数和准确率
- Pass@K（问题级别的通过率）
- 平均Reward
- 唯一问题数

---

### 7. `view_training_results.py` - Training-Free GRPO训练结果对比

**功能**: 查看Training-Free GRPO训练前后的结果对比

**使用方法**:

```bash
# 查看论文实验结果对比（默认）
python scripts/utils/view_training_results.py

# 显示详细的Pass@K统计
python scripts/utils/view_training_results.py --detailed

# 查看特定实验
python scripts/utils/view_training_results.py --exp_ids baseline_exp practice_exp

# 导出结果为JSON
python scripts/utils/view_training_results.py --export results.json
```

**对比指标**:
- 训练前后的准确率变化
- 正确样本数变化
- Pass@K指标对比（K=1,5,10,32）
- 总体提升百分比

---

### 8. `get_training_statistics.py` - 训练统计获取工具

**功能**: 获取训练前后的详细统计信息

**使用方法**:

```bash
# 使用默认实验ID
python scripts/utils/get_training_statistics.py

# 指定实验ID
python scripts/utils/get_training_statistics.py \
  --baseline_exp_id logic_zebralogic_test_eval \
  --practice_exp_id logic_practice_zebralogic_test_eval
```

**输出信息**:
- 样本级别统计（总数、正确数、准确率）
- 问题级别统计（问题数、解决数、Pass@32）
- 对比分析（准确率变化、问题解决率变化）
- 变化趋势（提升/下降/保持）

---

### 9. `analyze_training_statistics.py` - 训练统计分析工具

**功能**: 深度分析训练前后的详细统计和变化

**使用方法**:

```bash
# 使用默认实验ID
python scripts/utils/analyze_training_statistics.py

# 指定实验ID
python scripts/utils/analyze_training_statistics.py \
  --baseline_exp_id baseline_exp \
  --practice_exp_id practice_exp
```

**详细分析**:
- Baseline和Practice的完整统计
- 样本级别和问题级别的对比
- Pass@32指标
- 问题改进详情（改进、退化、保持正确、保持错误）
- 净改进统计

---

### 10. `quick_view_results.py` - 快速查看评估结果

**功能**: 快速查看多个实验的评估结果统计

**使用方法**:

```bash
# 查看默认实验
python scripts/utils/quick_view_results.py

# 查看特定实验
python scripts/utils/quick_view_results.py exp1 exp2 exp3
```

**显示信息**:
- 总样本数和问题数
- 每题采样数
- 正确数和准确率
- Pass@1和Pass@5

---

## 评估结果查看

### 11. `verify_clean.py` - 验证并清理评估缓存

**功能**: 验证并强制清理Word Puzzle评估缓存

**使用方法**:

```bash
# 交互式清理
python scripts/utils/verify_clean.py
```

**操作流程**:
1. 查找评估记录
2. 显示样本详情
3. 询问是否删除
4. 执行删除并验证

---

## 经验学习分析

### 12. `analyze_hierarchical_experiences.py` - 分层经验分析工具

**功能**: 分析分层经验学习的结果（L0/L1/L2）

**使用方法**:

```bash
# 分析默认经验文件
python scripts/utils/analyze_hierarchical_experiences.py
```

**注意**: 需要修改脚本中的文件路径 (`exp_file`) 以指向实际的经验JSON文件

**显示信息**:
- L0（案例级）经验数量
- L1（模式级）经验数量
- L2（元策略级）经验数量
- L2元策略内容和来源L1
- L1模式内容和来源L0

---

### 13. `test_hierarchical_experience.py` - 分层经验测试工具

**功能**: 测试分层经验生成功能（L0/L1/L2）

**使用方法**:

```bash
# 运行测试
python scripts/utils/test_hierarchical_experience.py
```

**测试内容**:
- 模拟多个训练步骤
- 生成L0、L1、L2经验
- 测试经验聚合阈值
- 验证去重机制
- 保存经验到JSON

---

## 开发调试

### 14. `check_model_config.py` - 模型配置检查工具

**功能**: 检查模型配置和测试模型调用

**使用方法**:

```bash
# 检查环境变量和配置
python scripts/utils/check_model_config.py

# 测试模型调用
python scripts/utils/check_model_config.py --test-call
```

**检查内容**:
- 环境变量（UTU_LLM_TYPE、UTU_LLM_MODEL等）
- Agent配置（模型提供商、模型设置、Instructions）
- 模型调用测试（发送测试请求验证连接）

---

### 15. `check_siliconflow_models.py` - 硅基流动模型检查工具

**功能**: 检查硅基流动可用的模型列表

**使用方法**:

```bash
# 列出可用模型
python scripts/utils/check_siliconflow_models.py
```

**输出信息**:
- DeepSeek系列模型列表
- 推荐的模型配置
- .env文件配置示例

---

### 16. `simple_debug.py` - 简化调试脚本

**功能**: 检查Word Puzzle评估失败原因

**使用方法**:

```bash
# 运行调试检查
python scripts/utils/simple_debug.py
```

**检查内容**:
1. 数据集是否存在
2. 评估样本是否存在
3. 样本的详细信息（问题、回答、正确性、元数据）

---

### 17. `test_multiround_eval.py` - 多轮游戏评估测试

**功能**: 测试多轮游戏（如Wordle）的评估流程

**使用方法**:

```bash
# 测试2个Wordle样本
uv run python scripts/utils/test_multiround_eval.py --game_name "33-wordle" --seeds 1 2

# 测试5个样本并显示详细信息
uv run python scripts/utils/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 3 4 5 \
  --verbose

# 使用特定配置
uv run python scripts/utils/test_multiround_eval.py \
  --game_name "33-wordle" \
  --config_name korgym/wordle_eval \
  --seeds 1 2

# 保留测试数据（不清理）
uv run python scripts/utils/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 \
  --no-cleanup
```

**测试流程**:
1. 创建测试样本
2. 运行评估（Preprocess → Rollout → Judge → Statistics）
3. 显示结果（准确率、多轮信息、轨迹等）
4. 清理测试数据

---

## 工具检查

### 18. `dump_tool_schemas.py` - 工具Schema导出

**功能**: 导出所有工具的Schema信息到Excel

**使用方法**:

```bash
# 导出工具信息
python scripts/utils/dump_tool_schemas.py
```

**输出**: `tools.xlsx` 文件，包含：
- 工具名称
- 工具描述
- 参数Schema

---

### 19. `start_tools_mcp.py` - MCP工具服务器

**功能**: 启动MCP服务器以检查工具（配合@modelcontextprotocol/inspector使用）

**使用方法**:

```bash
# 启动所有工具
python scripts/utils/start_tools_mcp.py

# 启动特定工具
python scripts/utils/start_tools_mcp.py --toolkits toolkit1 toolkit2
```

**服务配置**:
- Host: 0.0.0.0
- Port: 3005
- Transport: streamable-http

---

### 20. `replay_server.py` - 事件回放服务器

**功能**: 回放保存的事件流（用于UI调试）

**使用方法**:

```bash
# 启动回放服务器
python scripts/utils/replay_server.py \
  --events events.pkl \
  --query "Your query here"
```

**参数说明**:
- `--events`: 事件pickle文件路径
- `--query`: 示例查询文本

**访问**: 打开浏览器访问 `http://localhost:8848/`

---

### 21. `merge_stream_events.py` - 事件流合并工具

**功能**: 合并流式事件（用于优化事件流）

**使用方法**:

```bash
# 合并事件
python scripts/utils/merge_stream_events.py \
  --events events.pkl \
  --output merged_events.pkl
```

**功能说明**:
- 合并连续的文本和推理事件
- 保留工具调用事件
- 优化事件流大小

---

## 环境要求

所有脚本需要以下环境变量:

```bash
# 数据库连接
export UTU_DB_URL="postgresql://user:password@localhost/dbname"

# LLM配置（用于需要调用模型的脚本）
export UTU_LLM_TYPE="openai"
export UTU_LLM_MODEL="gpt-4"
export UTU_LLM_BASE_URL="https://api.openai.com/v1"
export UTU_LLM_API_KEY="your-api-key"
```

---

## 常见使用场景

### 场景1: 查看训练效果

```bash
# 1. 查看实验列表
python scripts/utils/check_experiments.py

# 2. 对比训练前后结果
python scripts/utils/view_training_results.py

# 3. 查看详细统计
python scripts/utils/analyze_training_statistics.py \
  --baseline_exp_id baseline_exp \
  --practice_exp_id practice_exp
```

### 场景2: 数据集管理

```bash
# 1. 列出所有数据集
python scripts/utils/view_datasets.py --list

# 2. 查看特定数据集
python scripts/utils/view_datasets.py \
  --dataset "KORGym-WordPuzzle-Eval-50" \
  --samples 5

# 3. 清理旧数据集并重建
uv run python scripts/utils/clean_and_recreate_datasets.py
```

### 场景3: 调试评估问题

```bash
# 1. 检查数据集和评估样本
python scripts/utils/simple_debug.py

# 2. 测试多轮评估
uv run python scripts/utils/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 \
  --verbose

# 3. 清理缓存并重新评估
python scripts/utils/verify_clean.py
```

### 场景4: 分析分层经验

```bash
# 1. 测试分层经验生成
python scripts/utils/test_hierarchical_experience.py

# 2. 分析生成的经验
python scripts/utils/analyze_hierarchical_experiences.py
```

---

## 注意事项

1. **数据库连接**: 大部分脚本需要正确配置 `UTU_DB_URL` 环境变量
2. **删除操作**: 涉及删除操作的脚本（如 `clean_experiment_data.py`）会要求确认，请谨慎操作
3. **路径配置**: 某些脚本（如 `analyze_hierarchical_experiences.py`）需要修改内部路径指向实际文件
4. **模型调用**: 需要调用LLM的脚本（如测试工具）需要配置API密钥
5. **权限要求**: 某些脚本可能需要数据库写权限

---

## 脚本分类总结

| 类别 | 脚本数量 | 主要用途 |
|------|---------|---------|
| 数据管理 | 4 | 查看、清理、重建数据集 |
| 实验分析 | 6 | 分析训练和评估结果 |
| 经验学习 | 2 | 测试和分析分层经验 |
| 开发调试 | 5 | 配置检查、问题调试 |
| 工具检查 | 3 | 工具Schema、MCP服务器 |
| **总计** | **21** | **完整的工具生态系统** |

---

## 获取帮助

大部分脚本支持 `--help` 参数查看详细用法:

```bash
python scripts/utils/<script_name>.py --help
```

如遇到问题，请检查:
1. 环境变量是否正确配置
2. 数据库连接是否正常
3. 依赖包是否已安装
4. 文件路径是否正确
