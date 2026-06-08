---
name: Project File Reorganization
overview: 将项目中积累的实验迭代文件归档，统一目录结构，分离"源文件"与"实验产物"，降低主线开发的视觉噪音。不删除任何文件，全部归入 archive/ 子目录。
todos:
  - id: phase1-agents
    content: 归档 configs/agents/practice/ 中约46个实验迭代 agent YAML 到 archive/ 子目录
    status: pending
  - id: phase2-eval-logic
    content: 归档 configs/eval/logic/ 中约25个探索性变体到 archive/ 子目录
    status: pending
  - id: phase2-eval-korgym
    content: 归档 configs/eval/korgym/ 中约14个旧变体到 archive/ 子目录
    status: pending
  - id: phase3-practice-korgym
    content: 归档 configs/practice/korgym/ 中约23个 Qwen/难度梯度变体到 archive/ 子目录，删除根目录的重复模板
    status: pending
  - id: phase3-practice-logic
    content: 归档 configs/practice/logic/ 中约10个旧版实验配置到 archive/ 子目录
    status: pending
  - id: phase4-verify
    content: 归档 utu/practice/verify/ 中2个旧 logic 验证变体到 archive/ 子目录
    status: pending
  - id: phase5-1-root
    content: "scripts/ 根目录瘦身：3个文件移入 games/wordle/，6个移入 utils/，16个归档到 archive/"
    status: pending
  - id: phase5-2-subdirs
    content: "scripts/error_analysis/（整个）和 scripts/experiments/（整个）归档到 archive/ 子目录"
    status: pending
  - id: phase5-3-analysis
    content: "scripts/analysis/tool_usage.py 移入 scripts/utils/，删除空目录"
    status: pending
isProject: false
---

# TF-LLM 项目文件整理方案

## 整理原则

- **不删除**：所有文件移入同级 `archive/` 子目录，git history 不受影响
- **归档标准**：有更新版本替代 / 仅用于某次探索实验 / auto-generated 产物
- **保留标准**：当前主线实验引用 / 模板文件 / 基础 baseline

---

## Phase 1：Agent 配置（最大噪音来源）

**目标**：`configs/agents/practice/` 从 61 个文件缩减到 ~15 个

**保留**（每个任务域保留：base agent + 当前最新 practice agent + 模板）：
- SkillsBench：`skillsbench_agent.yaml`、`skillsbench_practice_agent.yaml`
- KORGym：`korgym_agent.yaml`、`wordle_agent.yaml`、`wordle_practice_agent.yaml`、`word_puzzle_agent.yaml`、`word_puzzle_practice_agent.yaml`、`alphabetical_sorting_agent.yaml`、`alphabetical_sorting_practice_agent.yaml`
- Math：`math_agent.yaml`、`math_practice_agent.yaml`
- Logic：`logic_agent_zebralogic.yaml`
- Web：`web_agent.yaml`、`web_practice_agent.yaml`
- 模板：`TEMPLATE_korgym_game_agent.yaml`

**归档到 `configs/agents/practice/archive/`**（约 46 个）：
- 所有 `medium_reasoning_hierarchical_num1_1` 到 `_6` 的迭代版本
- 所有 `qwen_reasoning_*` 系列（7个）
- logic 各变体（`basepro`、`normalverify`、`hierarchical_learning`、`clean`、`structured` 等）
- word_puzzle 难度梯度变体（`easy`、`medium`、`easy_medium`、`easy_medium_hard`）
- wordle 变体（`practice_2`、`l4`、`l4_2`、`_less`）
- 其他：`word_puzzle_agent_off`、`word_encryption_agent`、`*.backup`

---

## Phase 2：Eval 配置

### `configs/eval/logic/`（33 → ~8 个）

**保留**：
- `easy_base_hierarchical.yaml`（被 practice configs 引用）
- `easy_practice_hierarchical_num1.yaml`
- `logic_zebralogic_baseline.yaml`
- `logic_zebralogic_practice.yaml`
- `qwen_easy_baseline.yaml`、`qwen_easy_practice.yaml`
- `qwen_medium_base.yaml`、`qwen_medium_practice.yaml`

**归档到 `configs/eval/logic/archive/`**（约 25 个）：
- basepro/strupro/hierarchical_clean 变体
- enhance_num1/2、hierarchical_num5、normal_num1
- `logic_practice_30`、`logic_practice_30_nor`
- `logic_zebralogic_practice_30_*`（normalverify/official/v2verify 三个）
- `logic_zebralogic_baseline_basepro`、`practice_normalverify`、`practice_sum`
- `logic_practice_zebralogic_test`、`logic_zebralogic_test`
- qwen basepro 变体（3个）

### `configs/eval/korgym/`（22 → ~8 个）

**保留**：
- 每款游戏的 `*_eval` + `*_practice_eval` 各一个（3对共6个）
- 两个模板文件

**归档到 `configs/eval/korgym/archive/`**（约 14 个）：
- `*_llm.yaml` 系列（LLM打分变体）
- `word_puzzle_baseline`、`word_puzzle_enhanced`
- word_puzzle 难度组合 eval（easyexpractice、easypractice、expmediumpractice）
- `wordle_practice_20_eval`
- `korgym_eval`、`korgym_practice_eval`（被具体游戏配置替代）
- `word_encryption_eval`

---

## Phase 3：Practice 配置

### `configs/practice/korgym/`（28 → ~5 个）

**保留**：
- `wordle_practice.yaml`、`word_puzzle_practice.yaml`、`alphabetical_sorting_practice.yaml`
- `TEMPLATE_korgym_game_practice.yaml`（保留此处，删除根目录的重复副本）
- `korgym_practice.yaml`

**归档到 `configs/practice/korgym/archive/`**（约 23 个）：
- 全部 `*_qwen*` 系列（qwen32b/72b/temp1/optimized 等）
- word_puzzle 难度梯度（easy/medium/easy_medium/easy_medium_hard）
- wordle 变体（practice_20、easy、medium）
- `word_puzzle_hierarchical_experiment`、`korgym_hierarchical_test`
- alphabetical_sorting_qwen_* 系列（5个）

### `configs/practice/logic/`（14 → ~4 个）

**保留**：
- `medium_reasoning_hierarchical_num1.yaml`（当前主实验）
- `qwen_reasoning_easy.yaml`、`qwen_reasoning_medium.yaml`
- `easy_reasoning_enhance_num1.yaml`

**归档到 `configs/practice/logic/archive/`**（约 10 个）：
- `logic_reasoning_zebralogic` 系列（base/100/optimized/structured/error_analysis 等，共 7 个）
- `medium_reasoning_enhance_num1/2`、`medium_reasoning_normal_num1`
- `qwen_reasoning_medium_old.yaml`

---

## Phase 4：验证模块（代码层）

**目标**：`utu/practice/verify/` 4 个 logic 变体 → 明确主次

**当前状态**：`logic.py` → `logic_with_error_analysis.py` → `_v2.py` → `logic_error_extractor.py`（进化链）

**建议**：
- 保留 `logic.py`（核心基准）和 `logic_error_extractor.py`（最新、被 medium_reasoning_hierarchical 引用）
- 归档 `logic_with_error_analysis.py` 和 `logic_with_error_analysis_v2.py` 到 `utu/practice/verify/archive/`
- 其余文件（math、korgym、skillsbench、webwalker）保持不变

---

## Phase 5：Scripts 整理（优先执行）

当前总计 ~150 个文件，根目录 28 个文件（3个核心脚本混在杂项里）。

### 5.1 根目录瘦身（28 → 3 个文件）

**保留在根目录**（唯一的主入口脚本）：
- `run_eval.py`
- `run_training_free_GRPO.py`
- `regen_practice_agent_yaml.py`

**移入 `scripts/utils/`**（结果查看 & 经验管理工具）：
- `view_skillsbench_results.py`
- `view_livecodebench_results.py`
- `merge_experiences.py`
- `remove_l0_experiences.py`
- `analyze_l0_duplicates.py`
- `bench_retrieval.py`（经验检索对比 benchmark）

**移入 `scripts/games/wordle/`**（wordle 专属工具）：
- `debug_wordle_multiround.py`
- `test_wordle_compact_history.py`
- `calculate_wordle_accuracy.py`

**归档到 `scripts/archive/`**（其余 16 个一次性/过时文件）：
- 一次性测试脚本：`test_conversation_history.py`、`test_experience_filter.py`、`test_llm_api_connection.py`、`test_llm_experience_filter.py`、`debug_experience_filtering.py`
- 平台工具脚本：`copy_trainingfree_grpo.ps1`、`copy_trainingfree_grpo.sh`、`fix_phoenix_error.bat`、`fix_phoenix_error.sh`、`clean_obsolete_docs.sh`
- 一次性生成工具：`gen_simple_agent.py`、`gen_tool.py`、`verify_imports.py`、`chat_ui.py`、`cli_chat.py`
- 已完成的记录文档：`REORGANIZE_SCRIPTS.md`、`SCRIPTS_ORGANIZATION_COMPLETE.md`

### 5.2 整体子目录归档

**`scripts/error_analysis/`（16个文件）→ 整体归档**

该目录是 ZebraLogic 错误分析探索阶段的产物，结论已沉淀到 `utu/practice/verify/logic_error_extractor.py`，日常不再需要。整体移入 `scripts/archive/error_analysis/`。

**`scripts/experiments/`（17个文件）→ 整体归档**

历次实验的分析脚本（`analyze_*`、`compare_*`、`run_paper_experiment_wsl*`），是过去实验的记录，不是日常工具。整体移入 `scripts/archive/experiments/`。

**`scripts/analysis/`（1个文件：`tool_usage.py`）→ 合并**

只有 1 个文件，空目录意义不大，移入 `scripts/utils/`，然后删除空目录。

### 5.3 保持不动的目录

以下子目录结构已合理，仅做内容微调（korgym 内的 test 脚本可选归档）：

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `scripts/data/` | 13 | 数据集准备脚本，结构清晰，不动 |
| `scripts/db/` | 2 | 数据库工具，不动 |
| `scripts/games/` | 30 | 四个游戏子目录，结构合理，不动 |
| `scripts/korgym/` | 17 | KORGym 专属工具，整体保留（`test_korgym_*.py` 可选归档） |
| `scripts/tracing/` | 2 | Phoenix tracing 工具，不动 |
| `scripts/utils/` | 23+6 | 通用工具，接收从根目录迁入的文件 |

### 5.4 整理后的目录结构

```
scripts/
├── run_eval.py                    ← 核心入口
├── run_training_free_GRPO.py      ← 核心入口
├── regen_practice_agent_yaml.py   ← 核心工具
│
├── data/          (13 files)      ← 数据集准备
├── db/            (2 files)       ← 数据库工具
├── games/                         ← 游戏专属脚本
│   ├── alphabetical_sorting/ (6)
│   ├── word_puzzle/          (7)
│   ├── wordle/               (7+3) ← 新增3个从根目录迁入
│   └── zebralogic/           (7)
├── korgym/        (17 files)      ← KORGym 工具
├── tracing/       (2 files)       ← 链路追踪工具
├── utils/         (23+7 files)    ← 通用工具（接收6个从根目录迁入 + tool_usage.py）
│
└── archive/                       ← 归档区（不删除）
    ├── [根目录16个一次性脚本]
    ├── error_analysis/ (16 files)
    └── experiments/   (17 files)
```

---

## 整理后结构预览

```
configs/
├── agents/practice/
│   ├── skillsbench_agent.yaml          ← base
│   ├── skillsbench_practice_agent.yaml ← active
│   ├── wordle_agent.yaml / wordle_practice_agent.yaml
│   ├── ... (约15个活跃文件)
│   └── archive/                        ← 约46个旧版本
├── eval/
│   ├── korgym/   (8个 + archive/)
│   ├── logic/    (8个 + archive/)
│   ├── math/     (12个，结构已合理，不动)
│   └── skillsbench/ (3个，不动)
└── practice/
    ├── korgym/   (5个 + archive/)
    ├── logic/    (4个 + archive/)
    └── skillsbench/ (1个，不动)

utu/practice/verify/
├── logic.py / logic_error_extractor.py / math.py / korgym.py / skillsbench.py / webwalker.py
└── archive/  ← logic_with_error_analysis.py / _v2.py

scripts/
├── run_eval.py
├── run_training_free_GRPO.py
├── regen_practice_agent_yaml.py
├── utils/    (已有，追加4个文件)
└── archive/  ← 约20个旧脚本
```

---

## 不在此次范围内

- `utu/eval/processer/` 的拼写 typo（`processer` vs `processor`）：涉及代码引用，需要单独重构
- `workspace/` 目录下的 JSON 产物：建议加入 `.gitignore`，本次不移动
- `configs/eval/math/` 12 个文件：结构已经清晰（AIME24/25 × 有无工具 × 论文复现），不需整理
