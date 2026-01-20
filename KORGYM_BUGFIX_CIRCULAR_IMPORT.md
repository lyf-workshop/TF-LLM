# ✅ KORGym循环导入问题修复

## 🐛 问题描述

运行评估脚本时遇到循环导入错误：

```bash
ImportError: cannot import name 'BaseBenchmark' from partially initialized module 
'utu.eval.benchmarks.base_benchmark' (most likely due to a circular import)
```

## 🔍 循环导入链

```
utu.eval.benchmarks.base_benchmark
  ↓ imports
utu.eval.processer
  ↓ imports
utu.eval.processer.korgym_processor (KORGymProcesser)
  ↓ imports
utu.practice.korgym_adapter (KORGymAdapter)
  ↓ imports
utu.practice.__init__
  ↓ imports
utu.practice.rollout_manager (RolloutManager)
  ↓ tries to import
utu.eval.benchmarks.base_benchmark (BaseBenchmark)
  ↑ CIRCULAR!
```

## 🔧 已修复

修改 `utu/eval/processer/korgym_processor.py`，使用**延迟导入（Lazy Import）**：

### 修改前（问题代码）
```python
# 模块级别导入 - 会立即执行，导致循环
from ...practice.korgym_adapter import KORGymAdapter

class KORGymProcesser(BaseMatchProcesser):
    def __init__(self, config: EvalConfig):
        if config.korgym and config.korgym.enabled:
            self.adapter = KORGymAdapter(...)
```

### 修改后（正确代码）
```python
# 类型检查时导入（不会实际执行）
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...practice.korgym_adapter import KORGymAdapter

class KORGymProcesser(BaseMatchProcesser):
    def __init__(self, config: EvalConfig):
        if config.korgym and config.korgym.enabled:
            # 仅在需要时导入 - 延迟导入
            from ...practice.korgym_adapter import KORGymAdapter
            
            self.adapter = KORGymAdapter(...)
```

## ✅ 修复说明

1. **TYPE_CHECKING导入**：仅用于类型提示，不会实际导入模块
2. **延迟导入**：在`__init__`方法中导入，只在真正需要时才执行
3. **打破循环**：避免了模块初始化时的循环依赖

---

## 🚀 现在可以正常运行

### 完整测试流程（Word Puzzle）

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 确保游戏服务器在运行
# 终端1: cd KORGym/game_lib/8-word_puzzle && python game_lib.py -p 8775

# 1. 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# 2. 基线评估（现在应该可以运行了）
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name word_puzzle_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

---

## 📋 已修复的Bug清单

1. ✅ **数据库导入错误** (`scripts/data/prepare_korgym_data.py`)
   - 修复：使用 `DBService` 代替 `db_manager`
   - 文档：`KORGYM_BUGFIX_DATABASE.md`

2. ✅ **循环导入错误** (`utu/eval/processer/korgym_processor.py`)
   - 修复：使用延迟导入避免循环依赖
   - 文档：`KORGYM_BUGFIX_CIRCULAR_IMPORT.md`（本文件）

---

## 🎯 预期行为

运行评估时应该看到：

```
2026-01-15 xx:xx:xx[utu.tracing.setup] - WARNING - PHOENIX_ENDPOINT not set! Skipping tracing.
2026-01-15 xx:xx:xx[utu.eval.processer.korgym_processor] - INFO - KORGymProcesser init: hasattr(config, 'korgym')=True
2026-01-15 xx:xx:xx[utu.eval.processer.korgym_processor] - INFO - ✓ KORGymProcesser initialized with adapter for 8-word_puzzle
2026-01-15 xx:xx:xx[utu.eval.benchmarks.base_benchmark] - INFO - Starting evaluation...
...
```

---

## 💡 技术要点

### 什么是延迟导入？

延迟导入（Lazy Import）是指在需要使用模块时才导入，而不是在文件开头导入。

**优点**：
- ✅ 避免循环依赖
- ✅ 减少启动时间
- ✅ 减少内存占用（如果某些分支不执行）

**适用场景**：
- 存在循环依赖风险
- 可选功能（如KORGym适配器）
- 大型或慢速模块

### TYPE_CHECKING 的作用

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...practice.korgym_adapter import KORGymAdapter
```

- `TYPE_CHECKING` 在运行时为 `False`
- 仅在类型检查时（mypy/pylance）为 `True`
- 允许类型提示但不实际导入模块

---

*修复时间: 2026-01-15*  
*修复文件: utu/eval/processer/korgym_processor.py*  
*修复方法: 延迟导入（Lazy Import）*

