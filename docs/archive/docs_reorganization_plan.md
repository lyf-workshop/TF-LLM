# 文档重组计划

## 📁 目标目录结构

```
docs/
├── korgym/              # KORGym 游戏文档
├── practice/            # 训练与实践
│   └── guides/          # 详细指南
├── setup/               # 环境配置
├── troubleshooting/     # 故障排除
└── advanced/            # 高级功能
    ├── papers/          # 论文
    └── error_analysis/  # 错误分析
```

## 📋 文档移动清单

### 1. KORGym 游戏相关 → `docs/korgym/`

**命令和指南**：
- KORGYM_THREE_GAMES_COMMANDS.md → commands.md
- KORGYM_THREE_GAMES_GUIDE.md → games_guide.md
- KORGYM_THREE_GAMES_SUMMARY.md → games_summary.md
- KORGYM_QUICK_START.md → quickstart.md
- KORGYM_SCORING_GUIDE.md → scoring_guide.md
- KORGYM_VIEW_RESULTS_GUIDE.md → viewing_results.md
- KORGYM_COMMANDS_SUMMARY.md → commands_summary.md
- KORGYM_INTEGRATION_README.md → integration.md
- KORGYM_SETUP_COMPLETE.md → setup_complete.md

**游戏特定**：
- Alphabetical_Sorting快速命令.md → alphabetical_sorting_commands.md
- Word_Puzzle完整指南.md → word_puzzle_complete_guide.md
- WORDLE_QUICK_START.md → wordle_quickstart.md
- WORDLE_GAME_ANALYSIS.md → wordle_analysis.md
- WORDLE_MULTIROUND_TEST_GUIDE.md → wordle_multiround_testing.md

**适配和机制**：
- KORGym分层经验学习适配方案.md → hierarchical_adaptation.md
- KORGym经验总结机制详解.md → experience_mechanism.md
- KORGym经验总结流程图.md → experience_flowchart.md
- KORGym适配修改说明.md → adaptation_changes.md
- KORGYM_VERIFY_FUNCTION_UPGRADE.md → verify_function_upgrade.md

**中文指南**：
- KORGym快速使用指南.md → quickstart_zh.md
- KORGym评估指南.md → evaluation_guide_zh.md
- KORGym集成指南.md → integration_guide_zh.md
- KORGym_Usage_Guide.md → usage_guide.md

**多轮游戏**：
- MULTI_ROUND_GAME_EVAL_GUIDE.md → multiround_evaluation.md
- MULTI_ROUND_GAME_SUPPORT_ANALYSIS.md → multiround_support.md
- MULTI_ROUND_EVAL_IMPLEMENTATION_SUMMARY.md → multiround_implementation_summary.md
- MULTI_ROUND_EVAL_IMPLEMENTATION.md → multiround_implementation.md
- MULTI_ROUND_EVAL_TODO.md → multiround_todo.md

### 2. 分层经验学习 → `docs/practice/guides/`

- 分层经验学习-完整运行指南.md → hierarchical_learning_guide.md
- HIERARCHICAL_LEARNING_FIX.md → hierarchical_learning_fix.md
- 经验库使用机制说明.md → experience_library.md
- 经验生成机制详解.md → experience_generation.md
- Training-Free_GRPO完整流程详解.md → training_free_grpo_guide.md
- PRACTICE_RETRY_MECHANISM_GUIDE.md → retry_mechanism.md
- PRACTICE_RETRY_QUICK_REFERENCE.md → retry_quick_reference.md

### 3. 环境配置 → `docs/setup/`

- KORGYM_WSL_SETUP.md → korgym_wsl_setup.md
- KORGym_WSL环境配置完整指南.md → wsl_setup_complete.md
- GITHUB_UPLOAD_GUIDE.md → github_upload.md

### 4. 故障排除 → `docs/troubleshooting/`

**KORGym Bug 修复**：
- KORGYM_ALL_BUGFIXES_SUMMARY.md → all_bugfixes_summary.md
- KORGYM_BUGFIX_CIRCULAR_IMPORT.md → circular_import_fix.md
- KORGYM_BUGFIX_DATABASE.md → database_fix.md
- KORGYM_BUGFIX_PROCESSER_MATCHING.md → processer_matching_fix.md
- KORGYM_SERVER_500_ERROR_FIX.md → server_500_fix.md
- KORGYM_CLEANUP_AND_RERUN.md → cleanup_and_rerun.md

**游戏特定问题**：
- WORD_PUZZLE_CACHE_CLEANUP.md → word_puzzle_cache.md
- WORD_PUZZLE_DIAGNOSIS.md → word_puzzle_diagnosis.md
- WORD_PUZZLE_ZERO_ACCURACY_FIX.md → word_puzzle_zero_accuracy.md
- WORDLE_TRAJECTORIES_FIX.md → wordle_trajectories_fix.md
- ALPHABETICAL_SORTING_CACHE_ISSUE.md → alphabetical_sorting_cache.md
- ALPHABETICAL_SORTING_STRATEGY_UPDATE.md → alphabetical_sorting_strategy.md

**数据和准备**：
- PREPARE_KORGYM_DATA_FIX.md → prepare_data_fix.md

### 5. 论文 → `docs/advanced/papers/`

- Training-Free Group Relative Policy Optimization.pdf → (已存在)

### 6. 保留在根目录

**项目管理**：
- README.md
- README_JA.md
- README_KORGYM_FORK.md
- LICENSE
- CHANGELOG.md
- CONTRIBUTING.md
- Makefile
- pyproject.toml
- uv.lock
- mkdocs.yml

**脚本和工具**：
- activate_korgym.sh
- setup_korgym_wsl.sh
- test_korgym_env.sh
- test_practice_config_loading.py
- test_qwen_optimization.sh
- cleanup_and_rerun_*.sh
- Qwen*.sh
- fix_ipython_jedi.*
- env*.template

**数据库**：
- test.db*

### 7. 归档/删除

**临时文档整理记录**：
- DOCS_CLEANUP_SUMMARY.md → 移到 docs/archive/
- DOCS_REORGANIZATION_SUMMARY.md → 移到 docs/archive/
- GRPO无关文件清单.md → 移到 docs/archive/
- THREE_GAMES_CONFIG_FIX_SUMMARY.md → 移到 docs/archive/

**其他**：
- AGENTS.md → 移到 docs/archive/（已有 docs/agents.md）

## ✅ 执行步骤

1. 移动 KORGym 文档到 docs/korgym/
2. 移动训练指南到 docs/practice/guides/
3. 移动环境配置到 docs/setup/
4. 移动故障排除到 docs/troubleshooting/
5. 创建归档目录并移动临时文档
6. 更新所有文档内部链接
7. 创建新的索引文件

