# Scripts 文件夹重组方案

## 📁 新的目录结构

```
scripts/
├── korgym/                    # KORGym 通用脚本
├── games/                     # 各游戏特定脚本
│   ├── zebralogic/           # ZebraLogic 相关
│   ├── wordle/               # Wordle 相关
│   ├── word_puzzle/          # Word Puzzle 相关
│   └── alphabetical_sorting/ # Alphabetical Sorting 相关
├── error_analysis/           # 错误分析工具
├── experiments/              # 论文实验脚本
├── utils/                    # 通用工具
└── data/                     # 数据处理（保持不变）
```

---

## 📋 文件分类清单

### 1. KORGym 通用脚本 → `scripts/korgym/`

KORGym 框架级别的脚本：
- `view_korgym_results.py` - 查看 KORGym 结果
- `check_korgym_env.py` - 检查 KORGym 环境
- `test_korgym_server.py` - 测试游戏服务器
- `run_korgym_full_pipeline.sh` - 完整流程
- `start_korgym_server.sh` - 启动服务器
- `compare_korgym_scores.py` - 对比分数
- `eval_with_dataset.sh` - 数据集评估
- `preview_korgym_game.py` - 预览游戏
- `cleanup_korgym_temp_data.py` - 清理临时数据
- `eval_korgym_with_dataset.py` - 数据集评估
- `init_korgym_dataset.py` - 初始化数据集
- `init_korgym_eval_dataset.py` - 初始化评估数据集
- `restart_korgym_training.sh` - 重启训练
- `run_korgym_eval.py` - 运行评估
- `compare_korgym_results.py` - 对比结果
- `debug_game_server.py` - 调试服务器
- `start_korgym_server.py` - 启动服务器（Python版）
- `test_korgym_adapter.py` - 测试适配器

### 2. ZebraLogic → `scripts/games/zebralogic/`

- `view_zebralogic_results.py` - 查看结果
- `run_zebralogic_experiment.sh` - 运行实验
- `diagnose_zebralogic_eval.py` - 诊断评估
- `compare_zebralogic_results.py` - 对比结果
- `clean_zebralogic_training_data.py` - 清理训练数据
- `check_zebralogic_data.py` - 检查数据
- `analyze_zebra_dataset.py` - 分析数据集

### 3. Wordle → `scripts/games/wordle/`

- `analyze_wordle_top20.py` - 分析前20题
- `test_wordle_config.py` - 测试配置
- `run_wordle_full_experiment.sh` - 完整实验
- `diagnose_wordle_training.py` - 诊断训练
- `clean_wordle_data.sh` - 清理数据
- `check_wordle_eval_samples.py` - 检查评估样本
- `check_wordle_dataset.py` - 检查数据集

### 4. Word Puzzle → `scripts/games/word_puzzle/`

- `analyze_word_puzzle_results.py` - 分析结果
- `debug_word_puzzle_results.py` - 调试结果
- `run_complete_word_puzzle_experiment.sh` - 完整实验
- `run_word_puzzle_experiment.sh` - 运行实验
- `run_word_puzzle_72b_full_experiment.sh` - 72B模型实验
- `eval_word_puzzle_paper_aligned.py` - 论文对齐评估
- `clean_word_puzzle_data.sh` - 清理数据

### 5. Alphabetical Sorting → `scripts/games/alphabetical_sorting/`

- `clean_alphabetical_sorting_cache.py` - 清理缓存
- `restart_alphabetical_sorting_training.py` - 重启训练
- `run_alphabetical_sorting_full_experiment.sh` - 完整实验
- `run_alphabetical_sorting_experiment.sh` - 运行实验
- `quick_test_alphabetical_prompts.sh` - 快速测试提示词
- `clean_and_restart_alphabetical_sorting.sh` - 清理并重启

### 6. 错误分析工具 → `scripts/error_analysis/`

- `inspect_error_analysis_output.py` - 检查错误分析输出
- `logic_conflict_detector.py` - 逻辑冲突检测器
- `logic_conflict_detector_example.py` - 检测器示例
- `test_error_analysis_v2.py` - 测试错误分析V2
- `test_logic_verify.py` - 测试逻辑验证
- `view_actual_error_analysis.py` - 查看实际错误分析
- `view_problem_details.py` - 查看问题详情
- `test_error_extractor.py` - 测试错误提取器
- `test_agent_answers_verification.py` - 测试答案验证
- `logic_error_analyzer.py` - 逻辑错误分析器
- `simple_test_logic_error_analyzer.py` - 简单测试
- `test_logic_error_analyzer.py` - 测试分析器
- `detailed_debug_verifier.py` - 详细调试验证器
- `debug_logic_verifier.py` - 调试逻辑验证器
- `test_improved_verifier.py` - 测试改进的验证器
- `test_logic_verifier.py` - 测试逻辑验证器

### 7. 论文实验脚本 → `scripts/experiments/`

- `compare_paper_scores.py` - 对比论文分数
- `run_paper_experiment_wsl_v2.sh` - WSL实验V2
- `run_paper_experiment_wsl.sh` - WSL实验
- `run_paper_experiment.py` - 运行论文实验
- `get_per_problem_stats.py` - 获取每题统计
- `generate_per_problem_report.py` - 生成每题报告
- `extract_specific_problems.py` - 提取特定问题
- `compare_training_changes.py` - 对比训练变化
- `compare_specific_problems.py` - 对比特定问题
- `analyze_report_statistics.py` - 分析报告统计
- `analyze_problem_commonality.py` - 分析问题共性
- `analyze_per_problem_correctness.py` - 分析每题正确性
- `analyze_incomplete_reasoning_detection.py` - 分析不完整推理检测
- `analyze_difficulty_distribution.py` - 分析难度分布
- `analyze_clues_difficulty.py` - 分析线索难度
- `analyze_baseline_failures.py` - 分析基线失败
- `analyze_answer_format.py` - 分析答案格式

### 8. 通用工具 → `scripts/utils/`

- `view_eval_results.py` - 查看评估结果
- `view_dataset.py` - 查看数据集
- `clean_and_recreate_datasets.py` - 清理并重建数据集
- `get_training_statistics.py` - 获取训练统计
- `analyze_training_statistics.py` - 分析训练统计
- `view_training_results.py` - 查看训练结果
- `check_experiments.py` - 检查实验
- `clean_experiment_data.py` - 清理实验数据
- `quick_view_results.py` - 快速查看结果
- `view_evaluation_details.py` - 查看评估详情
- `check_model_config.py` - 检查模型配置
- `check_siliconflow_models.py` - 检查SiliconFlow模型
- `simple_debug.py` - 简单调试
- `verify_clean.py` - 验证清理
- `test_multiround_eval.py` - 测试多轮评估
- `analyze_hierarchical_experiences.py` - 分析分层经验
- `test_hierarchical_experience.py` - 测试分层经验

### 9. 保持不变

**根目录保留**（Training-Free GRPO）：
- `copy_trainingfree_grpo.sh`
- `copy_trainingfree_grpo.ps1`
- `clean_obsolete_docs.sh`

**子目录保持不变**：
- `data/` - 数据处理脚本
- `__pycache__/` - Python缓存

---

## 📊 统计

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `korgym/` | 18 | KORGym 框架级脚本 |
| `games/zebralogic/` | 7 | ZebraLogic 游戏脚本 |
| `games/wordle/` | 7 | Wordle 游戏脚本 |
| `games/word_puzzle/` | 7 | Word Puzzle 游戏脚本 |
| `games/alphabetical_sorting/` | 6 | Alphabetical Sorting 游戏脚本 |
| `error_analysis/` | 16 | 错误分析工具 |
| `experiments/` | 17 | 论文实验脚本 |
| `utils/` | 16 | 通用工具脚本 |
| **总计** | **94** | **需要分类的脚本** |

---

## 🎯 组织原则

1. **按游戏分类** - 每个游戏的相关脚本放在 `games/游戏名/` 下
2. **按功能分类** - 错误分析、实验、工具等按功能分类
3. **保持引用** - 确保脚本间的相对路径引用正确
4. **不移动 GRPO** - Training-Free GRPO 脚本保持在根目录

---

## ✅ 优势

- **清晰的层次结构** - 按游戏和功能组织
- **易于查找** - 需要什么脚本一目了然
- **便于维护** - 相关脚本集中管理
- **专业规范** - 符合大型项目的脚本组织标准

