# 根目录文件整理方案

**分析日期**: 2026-03-16  
**当前状态**: 56个文件（过于混乱）

---

## 📊 当前问题分析

### 文件类型统计
- **Markdown文档**: 13个（部分应移到docs/）
- **Shell脚本**: 15个（应整理到scripts/）
- **Batch脚本**: 13个（应整理到scripts/）
- **Python脚本**: 4个（应整理到scripts/）
- **配置文件**: 10个（.env, pyproject.toml等，合理）
- **临时/测试文件**: 3个（应删除）
- **数据库文件**: 2个（合理但需优化）

**问题**: 根目录过于拥挤，脚本、测试文件、文档混杂

---

## 🎯 整理方案

### 方案A：基础整理（推荐）

#### 1. Markdown文档处理

**保留在根目录**（4个核心文档）:
- ✅ `README.md` - 项目主README
- ✅ `INSTALLATION_GUIDE.md` - 安装指南
- ✅ `CHANGELOG.md` - 变更日志
- ✅ `CONTRIBUTING.md` - 贡献指南

**移动到 docs/reference/**（4个参考文档）:
- → `EXAMPLES_FOLDER_GUIDE.md`
- → `VIEW_DATASETS_GUIDE.md`
- → `README_KORGYM_FORK.md`
- → `FORMAT_CONVERSION_EXPLANATION.md`

**移动到 docs/concepts/**（3个概念文档）:
- → `HIERARCHICAL_EXPERIENCE_FLOW_SUMMARY.md`
- → `EXPERIENCE_DEDUP_SUMMARY.md`
- → `RETRIEVAL_BASED_EXPERIENCE_PROPOSAL.md`

**移动到 docs/guides/**（1个测试指南）:
- → `TEST_MANUAL_EXPERIENCES.md`

**移动到 docs/reference/**（1个格式对比）:
- → `YAML_FORMAT_COMPARISON.md`

---

#### 2. Shell脚本整理

**创建 scripts/shell/** 目录，移动以下脚本：

**KORGym相关**（移动到 `scripts/shell/korgym/`）:
- `activate_korgym.sh`
- `setup_korgym_wsl.sh`
- `test_korgym_env.sh`

**清理和重运行**（移动到 `scripts/shell/cleanup/`）:
- `cleanup_and_rerun_alphabetical_sorting.sh`
- `cleanup_and_rerun_wordle.sh`
- `cleanup_and_rerun_word_puzzle.sh`

**测试脚本**（移动到 `scripts/shell/test/`）:
- `test_qwen_optimization.sh`
- `test_view_datasets.sh`

**修复脚本**（移动到 `scripts/shell/fix/`）:
- `fix_ipython_jedi.sh`

**快速命令**（移动到 `scripts/shell/quick/`）:
- `Qwen2.5-7B快速命令.sh`
- `Qwen优化版完整流程.sh`

**安装脚本**（移动到 `scripts/shell/install/`）:
- `install_all_dependencies.sh`

---

#### 3. Batch脚本整理

**创建 scripts/batch/** 目录，移动以下脚本：

**测试脚本**（移动到 `scripts/batch/test/`）:
- `test_conversation_history_fix.bat`
- `test_korgym_experience_fix.bat`
- `test_manual_experiences.bat`
- `test_view_datasets.bat`
- `test_wordle_compact_history.bat`
- `test_zhizengzeng_api.bat`

**工具脚本**（移动到 `scripts/batch/tools/`）:
- `analyze_l0_duplicates.bat`
- `cleanup_root.bat`
- `organize_scripts.bat`
- `verify_experience_filtering.bat`

**安装脚本**（移动到 `scripts/batch/install/`）:
- `install_all_dependencies.bat`

---

#### 4. Python脚本整理

**移动到 scripts/utils/**:
- `fix_ipython_jedi.py`
- `test_practice_config_loading.py`
- `test_zhizengzeng_api.py`

---

#### 5. 临时文件处理

**删除或移动到临时目录**:
- `failed_trajectory.json` → 删除或移到 `workspace/temp/`
- `temp_trajectory.txt` → 删除或移到 `workspace/temp/`
- `recent_wordle_results.txt` → 移到 `workspace/results/`

---

#### 6. 配置文件（保留）

**保留在根目录**（这些是标准位置）:
- `.env`, `.env.backup`, `.env.example`, `.env.full`
- `env.template`, `env_siliconflow.template`
- `.gitignore`, `.pre-commit-config.yaml`
- `pyproject.toml`, `uv.lock`
- `LICENSE`, `Makefile`, `mkdocs.yml`

---

#### 7. 数据库文件处理

**当前**:
- `test.db` (3.6GB) - 保留
- `test.db.backup.20251123_162836` (32KB) - 可删除（太旧）

**建议**:
- 保留 `test.db`
- 删除旧备份
- 未来备份移到 `backup/` 目录

---

## 📁 整理后的根目录结构

```
f:\youtu-agent\
│
├── 📄 核心文档（4个）
│   ├── README.md
│   ├── INSTALLATION_GUIDE.md
│   ├── CHANGELOG.md
│   └── CONTRIBUTING.md
│
├── ⚙️ 配置文件（13个）
│   ├── .env, .env.*, env.*
│   ├── .gitignore, .pre-commit-config.yaml
│   ├── pyproject.toml, uv.lock
│   ├── LICENSE, Makefile, mkdocs.yml
│   └── test.db
│
├── 📁 代码目录
│   ├── utu/              - 核心代码
│   ├── scripts/          - 脚本
│   │   ├── shell/        - Shell脚本（新建）
│   │   │   ├── korgym/
│   │   │   ├── cleanup/
│   │   │   ├── test/
│   │   │   ├── fix/
│   │   │   ├── quick/
│   │   │   └── install/
│   │   ├── batch/        - Batch脚本（新建）
│   │   │   ├── test/
│   │   │   ├── tools/
│   │   │   └── install/
│   │   └── utils/        - Python工具脚本
│   ├── tests/            - 测试代码
│   └── configs/          - 配置
│
├── 📁 数据和工作目录
│   ├── workspace/
│   ├── logs/
│   └── data/
│
├── 📁 文档
│   └── docs/
│       ├── guides/       - 使用指南
│       ├── reference/    - 参考文档（+4个）
│       ├── concepts/     - 概念说明（+3个）
│       └── ...
│
└── 📁 其他
    ├── .venv/, venv/     - 虚拟环境
    ├── KORGym/           - KORGym子项目
    └── .github/, .idea/  - Git和IDE配置
```

**整理后根目录文件数**: 17个（从56个减少 **70%**）

---

## 🚀 执行步骤

### 步骤1: 创建目录结构
```bash
# Shell脚本目录
mkdir -p scripts/shell/korgym
mkdir -p scripts/shell/cleanup
mkdir -p scripts/shell/test
mkdir -p scripts/shell/fix
mkdir -p scripts/shell/quick
mkdir -p scripts/shell/install

# Batch脚本目录
mkdir -p scripts/batch/test
mkdir -p scripts/batch/tools
mkdir -p scripts/batch/install

# 临时文件目录
mkdir -p workspace/temp
mkdir -p workspace/results
```

### 步骤2: 移动文档
```bash
# 移动到 docs/reference/
mv EXAMPLES_FOLDER_GUIDE.md docs/reference/
mv VIEW_DATASETS_GUIDE.md docs/reference/
mv README_KORGYM_FORK.md docs/reference/
mv FORMAT_CONVERSION_EXPLANATION.md docs/reference/
mv YAML_FORMAT_COMPARISON.md docs/reference/

# 移动到 docs/concepts/
mv HIERARCHICAL_EXPERIENCE_FLOW_SUMMARY.md docs/concepts/
mv EXPERIENCE_DEDUP_SUMMARY.md docs/concepts/
mv RETRIEVAL_BASED_EXPERIENCE_PROPOSAL.md docs/concepts/

# 移动到 docs/guides/
mv TEST_MANUAL_EXPERIENCES.md docs/guides/
```

### 步骤3: 移动Shell脚本
```bash
# KORGym相关
mv activate_korgym.sh scripts/shell/korgym/
mv setup_korgym_wsl.sh scripts/shell/korgym/
mv test_korgym_env.sh scripts/shell/korgym/

# 清理脚本
mv cleanup_and_rerun_*.sh scripts/shell/cleanup/

# 测试脚本
mv test_qwen_optimization.sh scripts/shell/test/
mv test_view_datasets.sh scripts/shell/test/

# 修复脚本
mv fix_ipython_jedi.sh scripts/shell/fix/

# 快速命令
mv Qwen*.sh scripts/shell/quick/

# 安装脚本
mv install_all_dependencies.sh scripts/shell/install/
```

### 步骤4: 移动Batch脚本
```bash
# 测试脚本
mv test_*.bat scripts/batch/test/

# 工具脚本
mv analyze_l0_duplicates.bat scripts/batch/tools/
mv cleanup_root.bat scripts/batch/tools/
mv organize_scripts.bat scripts/batch/tools/
mv verify_experience_filtering.bat scripts/batch/tools/

# 安装脚本
mv install_all_dependencies.bat scripts/batch/install/
```

### 步骤5: 移动Python脚本
```bash
mv fix_ipython_jedi.py scripts/utils/
mv test_practice_config_loading.py scripts/utils/
mv test_zhizengzeng_api.py scripts/utils/
```

### 步骤6: 清理临时文件
```bash
# 移动到workspace
mv failed_trajectory.json workspace/temp/
mv temp_trajectory.txt workspace/temp/
mv recent_wordle_results.txt workspace/results/

# 删除旧备份
rm test.db.backup.20251123_162836
```

---

## 📊 整理效果预测

### 文件数量对比

| 位置 | 整理前 | 整理后 | 改善 |
|------|--------|--------|------|
| **根目录总文件** | 56 | 17 | **-70%** |
| 核心文档 | 4 | 4 | 保持 |
| 配置文件 | 13 | 13 | 保持 |
| 脚本文件 | 32 | 0 | **-100%** |
| MD参考文档 | 9 | 0 | **-100%** |
| 临时文件 | 3 | 0 | **-100%** |

### 组织性改善

| 指标 | 整理前 | 整理后 |
|------|--------|--------|
| **根目录清晰度** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **脚本可发现性** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **文档结构** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **新手友好度** | ⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## ⚠️ 注意事项

### 1. 更新引用
移动脚本后，需要更新以下位置的引用：
- 文档中的脚本路径
- CI/CD配置
- Makefile中的路径
- README中的快速开始命令

### 2. 测试
整理后需要测试：
- 所有脚本是否能正常运行
- 相对路径是否正确
- 文档链接是否有效

### 3. 备份
在执行大规模移动前，建议：
```bash
# 创建git提交点
git add -A
git commit -m "Backup before root directory reorganization"
```

---

## 🎯 建议执行顺序

1. **立即执行**（影响小）:
   - ✅ 移动文档到docs/
   - ✅ 清理临时文件
   - ✅ 删除旧数据库备份

2. **谨慎执行**（需要测试）:
   - ⚠️ 移动脚本到scripts/
   - ⚠️ 更新文档中的路径引用
   - ⚠️ 测试脚本功能

3. **可选**（进一步优化）:
   - 💡 创建脚本索引README
   - 💡 添加脚本使用文档
   - 💡 统一脚本命名规范

---

## 📋 创建索引文件

整理后建议创建以下索引：

1. `scripts/shell/README.md` - Shell脚本索引
2. `scripts/batch/README.md` - Batch脚本索引
3. `docs/reference/README.md` - 参考文档索引
4. `docs/concepts/README.md` - 概念文档索引

---

## 🎉 预期结果

整理后的根目录将：
- ✅ **清晰明了**: 只有核心文档和配置
- ✅ **易于导航**: 脚本按功能分类存放
- ✅ **专业规范**: 符合开源项目最佳实践
- ✅ **新手友好**: 清晰的结构便于快速上手

---

*方案制定时间: 2026-03-16*  
*建议执行方式: 分阶段、逐步整理、充分测试*
