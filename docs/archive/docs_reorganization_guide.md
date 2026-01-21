# 文档重组指南

## 📋 重组目标

将根目录下散落的 60+ 个文档文件整理到 `docs` 文件夹的合适位置，提高项目文档的可维护性。

---

## 📁 新的文档结构

```
docs/
├── korgym/                    # KORGym 游戏文档（27个文件）
│   ├── index.md               # 总览（已存在）
│   ├── commands.md            # 三游戏命令速查
│   ├── games_guide.md         # 游戏指南
│   ├── games_summary.md       # 游戏总结
│   ├── quickstart_en.md       # 快速开始（英文）
│   ├── quickstart_zh.md       # 快速开始（中文）
│   ├── word_puzzle_*.md       # Word Puzzle 相关
│   ├── wordle_*.md            # Wordle 相关
│   ├── alphabetical_sorting_*.md  # Alphabetical Sorting 相关
│   ├── multiround_*.md        # 多轮游戏相关
│   └── ...
│
├── practice/                  # 训练与实践
│   ├── practice.md            # 主文档（已存在）
│   └── guides/                # 详细指南（7个文件）
│       ├── index.md
│       ├── hierarchical_learning_guide.md    # 分层学习指南
│       ├── training_free_grpo_guide.md       # GRPO 流程详解
│       ├── experience_library.md             # 经验库机制
│       ├── experience_generation.md          # 经验生成详解
│       ├── retry_mechanism.md                # 重试机制
│       └── ...
│
├── setup/                     # 环境配置（3个文件）
│   ├── index.md
│   ├── korgym_wsl_setup.md    # KORGym WSL 设置
│   ├── wsl_setup_complete.md  # WSL 完整配置指南
│   └── github_upload.md       # GitHub 上传指南
│
├── troubleshooting/           # 故障排除（13个文件）
│   ├── index.md
│   ├── all_bugfixes_summary.md        # 所有 Bug 修复总结
│   ├── *_fix.md                       # 各种修复文档
│   ├── word_puzzle_*.md               # Word Puzzle 问题
│   ├── wordle_*.md                    # Wordle 问题
│   └── ...
│
├── advanced/                  # 高级功能（已存在）
│   ├── error_analysis/        # 错误分析工具
│   └── papers/                # 论文
│       └── training_free_grpo.pdf
│
├── archive/                   # 归档（5个文件）
│   ├── docs_cleanup_summary.md
│   ├── docs_reorganization_summary.md
│   ├── grpo_unrelated_files.md
│   ├── three_games_config_fix.md
│   └── agents_old.md
│
├── agents.md                  # Agent 范式（保留）
├── config.md                  # 配置系统（保留）
├── eval.md                    # 评估框架（保留）
├── environment_variables.md   # 环境变量（保留）
└── assets/                    # 资源文件
```

---

## 🚀 执行步骤

### 方式1：使用批处理脚本（Windows推荐）

1. 在项目根目录打开命令提示符或PowerShell
2. 运行批处理脚本：
   ```cmd
   reorganize_docs.bat
   ```
3. 等待完成提示

### 方式2：使用Python脚本（跨平台）

```bash
# 查看移动计划（不实际移动）
uv run python reorganize_docs.py --dry-run

# 执行实际移动
uv run python reorganize_docs.py
```

### 方式3：使用辅助脚本

```bash
uv run python execute_reorganization.py
```

---

## 📊 移动清单统计

| 目标目录 | 文件数 | 说明 |
|---------|--------|------|
| `docs/korgym/` | 27 | KORGym 游戏相关文档 |
| `docs/practice/guides/` | 7 | 训练与实践指南 |
| `docs/setup/` | 3 | 环境配置文档 |
| `docs/troubleshooting/` | 13 | 故障排除文档 |
| `docs/archive/` | 5 | 归档的临时文档 |
| **总计** | **55** | **需要移动的文件** |

---

## 📝 移动的文件清单

### KORGym 游戏文档（27个）

**命令和指南**：
- `KORGYM_THREE_GAMES_COMMANDS.md` → `commands.md`
- `KORGYM_THREE_GAMES_GUIDE.md` → `games_guide.md`
- `KORGYM_THREE_GAMES_SUMMARY.md` → `games_summary.md`
- `KORGYM_QUICK_START.md` → `quickstart_en.md`
- `KORGYM_SCORING_GUIDE.md` → `scoring_guide.md`
- `KORGYM_VIEW_RESULTS_GUIDE.md` → `viewing_results.md`
- `KORGYM_COMMANDS_SUMMARY.md` → `commands_summary.md`
- `KORGYM_INTEGRATION_README.md` → `integration.md`
- `KORGYM_SETUP_COMPLETE.md` → `setup_complete.md`

**游戏特定**：
- `Alphabetical_Sorting快速命令.md` → `alphabetical_sorting_commands.md`
- `Word_Puzzle完整指南.md` → `word_puzzle_complete_guide.md`
- `WORDLE_QUICK_START.md` → `wordle_quickstart.md`
- `WORDLE_GAME_ANALYSIS.md` → `wordle_analysis.md`
- `WORDLE_MULTIROUND_TEST_GUIDE.md` → `wordle_multiround_testing.md`

**适配和机制**：
- `KORGym分层经验学习适配方案.md` → `hierarchical_adaptation.md`
- `KORGym经验总结机制详解.md` → `experience_mechanism.md`
- `KORGym经验总结流程图.md` → `experience_flowchart.md`
- `KORGym适配修改说明.md` → `adaptation_changes.md`
- `KORGYM_VERIFY_FUNCTION_UPGRADE.md` → `verify_function_upgrade.md`

**中文指南**：
- `KORGym快速使用指南.md` → `quickstart_zh.md`
- `KORGym评估指南.md` → `evaluation_guide_zh.md`
- `KORGym集成指南.md` → `integration_guide_zh.md`
- `KORGym_Usage_Guide.md` → `usage_guide.md`

**多轮游戏**：
- `MULTI_ROUND_GAME_EVAL_GUIDE.md` → `multiround_evaluation.md`
- `MULTI_ROUND_GAME_SUPPORT_ANALYSIS.md` → `multiround_support.md`
- `MULTI_ROUND_EVAL_IMPLEMENTATION_SUMMARY.md` → `multiround_implementation_summary.md`
- `MULTI_ROUND_EVAL_IMPLEMENTATION.md` → `multiround_implementation.md`
- `MULTI_ROUND_EVAL_TODO.md` → `multiround_todo.md`

### 训练实践指南（7个）

- `分层经验学习-完整运行指南.md` → `hierarchical_learning_guide.md`
- `HIERARCHICAL_LEARNING_FIX.md` → `hierarchical_learning_fix.md`
- `经验库使用机制说明.md` → `experience_library.md`
- `经验生成机制详解.md` → `experience_generation.md`
- `Training-Free_GRPO完整流程详解.md` → `training_free_grpo_guide.md`
- `PRACTICE_RETRY_MECHANISM_GUIDE.md` → `retry_mechanism.md`
- `PRACTICE_RETRY_QUICK_REFERENCE.md` → `retry_quick_reference.md`

### 环境配置（3个）

- `KORGYM_WSL_SETUP.md` → `korgym_wsl_setup.md`
- `KORGym_WSL环境配置完整指南.md` → `wsl_setup_complete.md`
- `GITHUB_UPLOAD_GUIDE.md` → `github_upload.md`

### 故障排除（13个）

- `KORGYM_ALL_BUGFIXES_SUMMARY.md` → `all_bugfixes_summary.md`
- `KORGYM_BUGFIX_CIRCULAR_IMPORT.md` → `circular_import_fix.md`
- `KORGYM_BUGFIX_DATABASE.md` → `database_fix.md`
- `KORGYM_BUGFIX_PROCESSER_MATCHING.md` → `processer_matching_fix.md`
- `KORGYM_SERVER_500_ERROR_FIX.md` → `server_500_fix.md`
- `KORGYM_CLEANUP_AND_RERUN.md` → `cleanup_and_rerun.md`
- `WORD_PUZZLE_CACHE_CLEANUP.md` → `word_puzzle_cache.md`
- `WORD_PUZZLE_DIAGNOSIS.md` → `word_puzzle_diagnosis.md`
- `WORD_PUZZLE_ZERO_ACCURACY_FIX.md` → `word_puzzle_zero_accuracy.md`
- `WORDLE_TRAJECTORIES_FIX.md` → `wordle_trajectories_fix.md`
- `ALPHABETICAL_SORTING_CACHE_ISSUE.md` → `alphabetical_sorting_cache.md`
- `ALPHABETICAL_SORTING_STRATEGY_UPDATE.md` → `alphabetical_sorting_strategy.md`
- `PREPARE_KORGYM_DATA_FIX.md` → `prepare_data_fix.md`

### 归档（5个）

- `DOCS_CLEANUP_SUMMARY.md` → `docs_cleanup_summary.md`
- `DOCS_REORGANIZATION_SUMMARY.md` → `docs_reorganization_summary.md`
- `GRPO无关文件清单.md` → `grpo_unrelated_files.md`
- `THREE_GAMES_CONFIG_FIX_SUMMARY.md` → `three_games_config_fix.md`
- `AGENTS.md` → `agents_old.md`（已有新版本）

---

## ✅ 保留在根目录的文件

以下文件保留在根目录：

- **项目文件**: `README.md`, `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`
- **配置文件**: `pyproject.toml`, `uv.lock`, `Makefile`, `mkdocs.yml`
- **脚本**: `*.sh`, `*.bat`, `*.py`（工具脚本）
- **环境文件**: `env*.template`, `fix_ipython_jedi.*`
- **数据**: `test.db*`, `data/`, `analysis/`

---

## 🔗 后续工作

重组完成后，建议：

1. **更新 mkdocs.yml** - 添加新目录到导航
2. **检查内部链接** - 确保文档间链接正确
3. **更新主 README** - 指向新的文档位置
4. **删除重组脚本** - 清理 `reorganize_docs.*` 临时文件

---

## 📖 使用新文档结构

### 快速访问

- **KORGym 游戏**: `docs/korgym/`
- **训练指南**: `docs/practice/guides/`
- **环境设置**: `docs/setup/`
- **问题排查**: `docs/troubleshooting/`

### MkDocs 导航

如果使用 MkDocs 构建文档站点，导航结构将自动反映新的组织方式。

---

*重组计划创建时间：2026-01-21*  
*计划移动文件数：55 个*

