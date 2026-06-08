# 📦 Scripts 文件夹重组完成指南

## 🎯 重组目标

将 90+ 个脚本文件按照游戏和功能分类，提高项目的可维护性和易用性。

---

## 📁 新的目录结构

```
scripts/
├── korgym/                    # KORGym 框架脚本（18个）
│   ├── view_korgym_results.py
│   ├── check_korgym_env.py
│   ├── start_korgym_server.py
│   └── ...
│
├── games/                     # 游戏特定脚本
│   ├── zebralogic/           # ZebraLogic（7个）
│   │   ├── view_zebralogic_results.py
│   │   ├── analyze_zebra_dataset.py
│   │   └── ...
│   ├── wordle/               # Wordle（7个）
│   │   ├── analyze_wordle_top20.py
│   │   ├── run_wordle_full_experiment.sh
│   │   └── ...
│   ├── word_puzzle/          # Word Puzzle（7个）
│   │   ├── analyze_word_puzzle_results.py
│   │   ├── run_word_puzzle_experiment.sh
│   │   └── ...
│   └── alphabetical_sorting/ # Alphabetical Sorting（6个）
│       ├── clean_alphabetical_sorting_cache.py
│       └── ...
│
├── error_analysis/           # 错误分析工具（16个）
│   ├── logic_conflict_detector.py
│   ├── logic_error_analyzer.py
│   └── ...
│
├── experiments/              # 论文实验脚本（17个）
│   ├── run_paper_experiment.py
│   ├── compare_paper_scores.py
│   └── ...
│
├── utils/                    # 通用工具（17个）
│   ├── view_eval_results.py
│   ├── clean_experiment_data.py
│   └── ...
│
├── data/                     # 数据处理（保持不变）
├── copy_trainingfree_grpo.sh # Training-Free GRPO（不移动）
├── copy_trainingfree_grpo.ps1
└── clean_obsolete_docs.sh
```

---

## 🚀 执行重组

### 方法 1：运行批处理脚本（推荐）

```cmd
organize_scripts.bat
```

### 方法 2：手动创建目录并移动文件

参考 `REORGANIZE_SCRIPTS.md` 中的详细清单。

---

## 📊 分类统计

| 目录 | 文件数 | 主要内容 |
|------|--------|----------|
| **korgym/** | 18 | KORGym 框架级脚本、服务器管理、数据集初始化 |
| **games/zebralogic/** | 7 | ZebraLogic 数据集分析、实验运行、结果查看 |
| **games/wordle/** | 7 | Wordle 实验、诊断、数据清理 |
| **games/word_puzzle/** | 7 | Word Puzzle 实验、结果分析、论文对齐评估 |
| **games/alphabetical_sorting/** | 6 | Alphabetical Sorting 实验、缓存清理 |
| **error_analysis/** | 16 | 逻辑错误检测、冲突分析、验证工具 |
| **experiments/** | 17 | 论文实验、统计分析、难度分布 |
| **utils/** | 17 | 通用评估、训练统计、模型配置检查 |
| **总计** | **95** | **已分类的脚本** |

---

## 🎯 组织原则

### 1. 按游戏分类
每个游戏的相关脚本集中在 `games/游戏名/` 目录：
- **ZebraLogic** - 数据集准备和分析
- **Wordle** - 多轮游戏实验
- **Word Puzzle** - 单轮填字游戏
- **Alphabetical Sorting** - 排序游戏

### 2. 按功能分类
- **korgym/** - KORGym 框架级功能
- **error_analysis/** - 错误检测和分析工具
- **experiments/** - 论文实验和数据分析
- **utils/** - 跨游戏的通用工具

### 3. 保持独立性
- **Training-Free GRPO 脚本** 保持在根目录
- **data/** 子目录保持不变
- 避免影响现有的导入路径

---

## 📖 使用指南

### 快速查找脚本

#### 想运行 ZebraLogic 实验？
```bash
cd scripts/games/zebralogic/
./run_zebralogic_experiment.sh
```

#### 想查看 Wordle 结果？
```bash
python scripts/games/wordle/analyze_wordle_top20.py --exp_id wordle_eval
```

#### 想检查 KORGym 环境？
```bash
python scripts/korgym/check_korgym_env.py
```

#### 想进行错误分析？
```bash
python scripts/error_analysis/logic_conflict_detector.py
```

### 常用脚本索引

| 任务 | 脚本位置 |
|------|----------|
| 查看 KORGym 结果 | `korgym/view_korgym_results.py` |
| 启动游戏服务器 | `korgym/start_korgym_server.py` |
| ZebraLogic 数据集分析 | `games/zebralogic/analyze_zebra_dataset.py` |
| Wordle 前20题分析 | `games/wordle/analyze_wordle_top20.py` |
| Word Puzzle 结果分析 | `games/word_puzzle/analyze_word_puzzle_results.py` |
| 错误分析 | `error_analysis/logic_error_analyzer.py` |
| 论文实验 | `experiments/run_paper_experiment.py` |
| 查看评估结果 | `utils/view_eval_results.py` |
| 清理实验数据 | `utils/clean_experiment_data.py` |

---

## 🔧 路径更新建议

重组后，某些脚本可能需要更新导入路径：

### 更新前
```python
from view_korgym_results import analyze_results
```

### 更新后
```python
from scripts.korgym.view_korgym_results import analyze_results
```

### 或者使用相对导入
```python
import sys
sys.path.append('..')
from korgym.view_korgym_results import analyze_results
```

---

## ✅ 重组后的优势

### 1. 清晰的层次结构 🎯
- 按游戏分类 - 快速定位游戏相关脚本
- 按功能分类 - 工具类脚本集中管理

### 2. 易于查找 🔍
- 需要 ZebraLogic 脚本？直接去 `games/zebralogic/`
- 需要错误分析？直接去 `error_analysis/`

### 3. 便于维护 🔧
- 相关脚本集中，便于统一更新
- 新脚本有明确的归属位置

### 4. 专业规范 ⭐
- 符合大型项目的组织标准
- 提升项目整体质量

---

## 📝 后续任务

### 1. 创建各目录的 README
为每个子目录创建 README.md，说明：
- 目录用途
- 主要脚本功能
- 使用示例

### 2. 更新主文档
在主 `README.md` 中更新脚本使用说明：
```markdown
## 📜 Scripts

- **[KORGym 脚本](scripts/korgym/)** - 框架级脚本
- **[游戏脚本](scripts/games/)** - 各游戏特定脚本
- **[错误分析](scripts/error_analysis/)** - 分析工具
- **[实验脚本](scripts/experiments/)** - 论文实验
- **[通用工具](scripts/utils/)** - 实用工具
```

### 3. 检查脚本依赖
确保移动后的脚本导入路径正确：
```bash
# 测试 KORGym 脚本
python scripts/korgym/check_korgym_env.py

# 测试游戏脚本
python scripts/games/wordle/analyze_wordle_top20.py --help
```

### 4. 提交到 Git
```bash
git add scripts/
git commit -m "refactor: 重组 scripts 文件夹结构

- 按游戏分类（zebralogic, wordle, word_puzzle, alphabetical_sorting）
- 按功能分类（korgym, error_analysis, experiments, utils）
- 提升脚本组织的清晰度和可维护性"
```

---

## 🎊 完成标志

当以下条件满足时，重组完成：

- ✅ 所有脚本已移动到对应目录
- ✅ 各子目录已创建
- ✅ 脚本运行测试通过
- ✅ 文档已更新
- ✅ Git 提交完成

---

*重组方案创建时间：2026-01-21*  
*脚本总数：95 个*  
*新增子目录：8 个*






