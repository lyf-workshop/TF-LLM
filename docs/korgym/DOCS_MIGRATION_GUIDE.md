# KORGym 文档整理和迁移指南

本文档说明了 KORGym 相关文档的整理情况，以及根目录散落文档与 `docs/korgym/` 中正式文档的对应关系。

## 📁 文档结构

### 正式文档（`docs/korgym/`）

这些是经过整理的、面向用户的正式文档：

| 文档 | 用途 | 状态 |
|------|------|------|
| **[index.md](index.md)** | KORGym 总览和入口 | ✅ 完整 |
| **[quick_reference.md](quick_reference.md)** | 快速命令和配置参考 | ✅ 完整 |
| **[wordle_guide.md](wordle_guide.md)** | Wordle 完整实验指南 | ✅ 完整 |
| **[word_puzzle_guide.md](word_puzzle_guide.md)** | Word Puzzle 完整实验指南 | ✅ 完整 |
| **[alphabetical_sorting_guide.md](alphabetical_sorting_guide.md)** | Alphabetical Sorting 完整实验指南 | ✅ 完整 |
| **[troubleshooting.md](troubleshooting.md)** | 系统化问题排查指南 | ✅ 完整 |

### 根目录临时文档（待归档或删除）

这些是在开发和调试过程中创建的临时文档，内容已经整合到正式文档中：

#### 🟢 核心参考文档（保留，但已整合）

| 根目录文档 | 内容 | 整合位置 | 建议 |
|-----------|------|---------|------|
| **KORGYM_THREE_GAMES_COMMANDS.md** | 三个游戏的完整命令参考 | [quick_reference.md](quick_reference.md) | ✅ 保留（作为详细参考） |
| **PRACTICE_RETRY_MECHANISM_GUIDE.md** | Practice 模块重试机制详解 | `utu/practice/README.md` | ✅ 保留（技术文档） |
| **PRACTICE_RETRY_QUICK_REFERENCE.md** | 重试机制快速参考 | 同上 | ⚠️ 可合并到 GUIDE |

#### 🟡 问题修复文档（可归档）

这些文档记录了特定问题的修复过程，已整合到 [troubleshooting.md](troubleshooting.md)：

| 根目录文档 | 问题 | 整合位置 | 建议 |
|-----------|------|---------|------|
| **ALPHABETICAL_SORTING_CACHE_ISSUE.md** | API 限流和缓存问题 | [troubleshooting.md](troubleshooting.md#error-429-api-rate-limiting) | 📦 归档到 `docs/archive/` |
| **HIERARCHICAL_LEARNING_FIX.md** | 层次学习配置错误 | [troubleshooting.md](troubleshooting.md#hierarchical-learning-not-enabled) | 📦 归档 |
| **WORD_PUZZLE_ZERO_ACCURACY_FIX.md** | 准确率为 0% 问题 | [troubleshooting.md](troubleshooting.md#level-mismatch) | 📦 归档 |
| **PREPARE_KORGYM_DATA_FIX.md** | 数据准备脚本修复 | [troubleshooting.md](troubleshooting.md#no-game_seed-found-in-meta) | 📦 归档 |
| **WORDLE_TRAJECTORIES_FIX.md** | Trajectories 为 None | [troubleshooting.md](troubleshooting.md#typeerror-object-of-type-nonetype-has-no-len) | 📦 归档 |
| **THREE_GAMES_CONFIG_FIX_SUMMARY.md** | 配置修复总结 | 各游戏指南 | 📦 归档 |
| **KORGYM_SERVER_500_ERROR_FIX.md** | 服务器 500 错误 | [troubleshooting.md](troubleshooting.md#500-server-error-game-server-crash) | 📦 归档 |
| **WORD_PUZZLE_CACHE_CLEANUP.md** | 缓存清理 | [troubleshooting.md](troubleshooting.md#cached-evaluation-results) | 📦 归档 |

#### 🟡 临时操作指南（已整合，可删除）

| 根目录文档 | 内容 | 替代文档 | 建议 |
|-----------|------|---------|------|
| **WORDLE_QUICK_START.md** | Wordle 快速开始 | [wordle_guide.md](wordle_guide.md) | ❌ 删除 |
| **Word_Puzzle完整指南.md** | Word Puzzle 指南 | [word_puzzle_guide.md](word_puzzle_guide.md) | ❌ 删除 |
| **Alphabetical_Sorting快速命令.md** | Sorting 快速命令 | [alphabetical_sorting_guide.md](alphabetical_sorting_guide.md) | ❌ 删除 |
| **KORGYM_QUICK_START.md** | KORGym 快速开始 | [index.md](index.md) | ❌ 删除 |
| **KORGYM_CLEANUP_AND_RERUN.md** | 清理和重新运行 | [quick_reference.md](quick_reference.md#🧹-清理命令) | ❌ 删除 |
| **KORGYM_VIEW_RESULTS_GUIDE.md** | 结果查看指南 | [quick_reference.md](quick_reference.md#查看结果) | ❌ 删除 |
| **KORGYM_SCORING_GUIDE.md** | 评分机制说明 | 各游戏指南中的"评分机制"章节 | ❌ 删除 |

#### 🟡 重复/过时的分析和说明文档（可删除）

| 根目录文档 | 内容 | 状态 | 建议 |
|-----------|------|------|------|
| **WORDLE_GAME_ANALYSIS.md** | Wordle 游戏分析 | 内容已整合 | ❌ 删除 |
| **WORDLE_MULTIROUND_TEST_GUIDE.md** | 多轮测试指南 | 已整合到 wordle_guide | ❌ 删除 |
| **MULTI_ROUND_GAME_SUPPORT_ANALYSIS.md** | 多轮支持分析 | 已实现 | ❌ 删除 |
| **MULTI_ROUND_GAME_EVAL_GUIDE.md** | 多轮评估指南 | 已整合 | ❌ 删除 |
| **MULTI_ROUND_EVAL_TODO.md** | TODO 列表 | 已完成 | ❌ 删除 |
| **MULTI_ROUND_EVAL_IMPLEMENTATION.md** | 实现说明 | 已完成 | ❌ 删除 |
| **MULTI_ROUND_EVAL_IMPLEMENTATION_SUMMARY.md** | 实现总结 | 已完成 | ❌ 删除 |
| **ALPHABETICAL_SORTING_STRATEGY_UPDATE.md** | 策略更新 | 已应用 | ❌ 删除 |
| **WORD_PUZZLE_DIAGNOSIS.md** | 诊断记录 | 临时文档 | ❌ 删除 |

#### 🟡 环境和集成文档（部分保留）

| 根目录文档 | 内容 | 状态 | 建议 |
|-----------|------|------|------|
| **KORGym_WSL环境配置完整指南.md** | WSL 环境配置 | 环境相关 | ⚠️ 移到 `docs/korgym/` 或合并到 quickstart |
| **KORGYM_WSL_SETUP.md** | WSL 设置 | 同上 | ⚠️ 可合并 |
| **KORGYM_INTEGRATION_README.md** | 集成说明 | 开发文档 | 📦 归档到 `docs/advanced/` |
| **KORGYM_SETUP_COMPLETE.md** | 设置完成记录 | 临时 | ❌ 删除 |
| **KORGym适配修改说明.md** | 适配说明 | 开发文档 | 📦 归档到 `docs/advanced/` |

#### 🟡 各种版本的使用指南（重复，可删除）

| 根目录文档 | 状态 | 建议 |
|-----------|------|------|
| **KORGym_Usage_Guide.md** | 重复 | ❌ 删除 |
| **KORGym快速使用指南.md** | 重复 | ❌ 删除 |
| **KORGym集成指南.md** | 重复 | ❌ 删除 |
| **KORGYM_THREE_GAMES_GUIDE.md** | 重复 | ❌ 删除 |
| **KORGYM_THREE_GAMES_SUMMARY.md** | 重复 | ❌ 删除 |
| **KORGYM_COMMANDS_SUMMARY.md** | 重复 | ❌ 删除 |

#### 🟡 Bug 修复记录（可归档）

| 根目录文档 | 建议 |
|-----------|------|
| **KORGYM_BUGFIX_PROCESSER_MATCHING.md** | 📦 归档到 `docs/archive/bugfixes/` |
| **KORGYM_BUGFIX_DATABASE.md** | 📦 归档 |
| **KORGYM_BUGFIX_CIRCULAR_IMPORT.md** | 📦 归档 |
| **KORGYM_ALL_BUGFIXES_SUMMARY.md** | 📦 归档 |
| **KORGYM_VERIFY_FUNCTION_UPGRADE.md** | 📦 归档 |

#### 🟡 经验总结相关（可归档或删除）

| 根目录文档 | 建议 |
|-----------|------|
| **KORGym经验总结流程图.md** | 📦 归档或整合到 practice.md |
| **KORGym经验总结机制详解.md** | 📦 归档或整合到 practice.md |
| **经验生成机制详解.md** | 📦 归档或整合到 practice.md |
| **经验库使用机制说明.md** | 📦 归档或整合到 practice.md |
| **KORGym分层经验学习适配方案.md** | 📦 归档 |
| **分层经验学习-完整运行指南.md** | 📦 归档 |

#### 🟡 其他临时文档

| 根目录文档 | 建议 |
|-----------|------|
| **Training-Free_GRPO完整流程详解.md** | 📦 归档或整合到 `docs/practice.md` |
| **KORGym评估指南.md** | ❌ 删除（已有 eval.md） |
| **GRPO无关文件清单.md** | ❌ 删除 |

## 📝 迁移建议

### 立即操作（高优先级）

1. **创建归档目录**:
   ```bash
   mkdir -p docs/archive/korgym/{bugfixes,fixes,guides}
   ```

2. **移动核心文档**:
   ```bash
   # 保留但移到更合适的位置
   mv KORGym_WSL环境配置完整指南.md docs/korgym/wsl_setup.md
   mv KORGYM_WSL_SETUP.md docs/archive/korgym/  # 或合并到上面
   ```

3. **删除明显重复的文档**:
   ```bash
   # 这些内容已完全整合到新文档中
   rm WORDLE_QUICK_START.md
   rm Word_Puzzle完整指南.md
   rm Alphabetical_Sorting快速命令.md
   rm KORGYM_QUICK_START.md
   rm KORGYM_CLEANUP_AND_RERUN.md
   rm KORGYM_VIEW_RESULTS_GUIDE.md
   rm KORGYM_SCORING_GUIDE.md
   # ... 等等
   ```

4. **归档问题修复文档**:
   ```bash
   mv ALPHABETICAL_SORTING_CACHE_ISSUE.md docs/archive/korgym/fixes/
   mv HIERARCHICAL_LEARNING_FIX.md docs/archive/korgym/fixes/
   mv WORD_PUZZLE_ZERO_ACCURACY_FIX.md docs/archive/korgym/fixes/
   # ... 等等
   ```

### 后续操作（中优先级）

1. **整合经验总结文档** 到 `docs/practice.md`:
   - 从 `KORGym经验总结机制详解.md` 等文档中提取有用内容
   - 更新 `docs/practice.md` 的层次学习章节
   - 删除或归档原文档

2. **整合 Training-Free GRPO 文档**:
   - 检查 `Training-Free_GRPO完整流程详解.md`
   - 将有价值的内容整合到 `docs/practice.md`

3. **更新配置模板文档**:
   - 确保 `configs/eval/korgym/README_TEMPLATES.md` 与新文档一致

### 低优先级

1. **创建开发者文档专区** `docs/advanced/korgym/`:
   - 移动 `KORGYM_INTEGRATION_README.md`
   - 移动 `KORGym适配修改说明.md`

2. **Bug 修复历史归档**:
   - 创建 `docs/archive/korgym/bugfixes/README.md` 作为索引
   - 归档所有 `KORGYM_BUGFIX_*.md` 文档

## 🗂️ 最终文档结构

```
docs/
├── korgym/                          # KORGym 正式文档
│   ├── index.md                     # ✅ 总览
│   ├── quick_reference.md           # ✅ 快速参考
│   ├── wordle_guide.md              # ✅ Wordle 指南
│   ├── word_puzzle_guide.md         # ✅ Word Puzzle 指南
│   ├── alphabetical_sorting_guide.md# ✅ Sorting 指南
│   ├── troubleshooting.md           # ✅ 问题排查
│   ├── wsl_setup.md                 # 🔄 WSL 环境配置
│   └── DOCS_MIGRATION_GUIDE.md      # 📝 本文档
├── advanced/
│   └── korgym/                      # KORGym 进阶/开发文档
│       ├── integration.md           # 集成说明
│       └── architecture.md          # 架构说明
└── archive/
    └── korgym/                      # 历史归档
        ├── fixes/                   # 问题修复记录
        ├── bugfixes/                # Bug 修复记录
        └── guides/                  # 过时的指南

根目录/
├── KORGYM_THREE_GAMES_COMMANDS.md   # ✅ 保留（详细命令参考）
├── PRACTICE_RETRY_MECHANISM_GUIDE.md# ✅ 保留（技术文档）
└── [其他已归档或删除]
```

## ✅ 文档质量检查清单

新文档应满足：

- [ ] **完整性**: 包含游戏规则、流程、配置、问题排查
- [ ] **可操作性**: 提供具体的命令和配置示例
- [ ] **导航性**: 有清晰的章节结构和内部链接
- [ ] **准确性**: 命令和配置经过验证
- [ ] **可维护性**: 使用相对链接，避免硬编码路径
- [ ] **一致性**: 术语、格式、风格统一

当前 `docs/korgym/` 中的所有文档都满足上述要求 ✅

## 📊 整理进度

| 任务 | 状态 | 完成度 |
|------|------|--------|
| 创建完整的游戏指南 | ✅ 完成 | 100% |
| 创建问题排查指南 | ✅ 完成 | 100% |
| 创建快速参考 | ✅ 完成 | 100% |
| 更新 mkdocs.yml 导航 | ✅ 完成 | 100% |
| 分析散落文档 | ✅ 完成 | 100% |
| 创建迁移指南（本文档） | ✅ 完成 | 100% |
| **执行文档迁移/清理** | ⏳ 待执行 | 0% |

## 🎯 下一步行动

**建议用户执行以下操作**:

```bash
# 1. 备份当前根目录文档
mkdir -p backup/korgym_docs_$(date +%Y%m%d)
cp *KORGYM*.md *KORGym*.md *wordle*.md *WORD*.md backup/korgym_docs_$(date +%Y%m%d)/

# 2. 创建归档目录
mkdir -p docs/archive/korgym/{bugfixes,fixes,guides}

# 3. 执行移动和删除（根据本文档的建议）
# 建议逐步执行，而不是一次性全部删除
```

## 📞 反馈

如果发现：
- 新文档缺少某些有用信息
- 某个旧文档不应该被删除
- 文档分类或迁移建议有误

请及时反馈，我们会相应调整！











