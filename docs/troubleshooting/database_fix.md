# ✅ KORGym数据准备脚本修复说明

## 🐛 问题描述

运行数据准备脚本时遇到导入错误：

```bash
ImportError: cannot import name 'db_manager' from 'utu.db'
```

## 🔧 已修复

已更新 `scripts/data/prepare_korgym_data.py`，修复内容：

### 修改1: 导入语句
```python
# 旧版本（错误）
from utu.db import DatasetSample, db_manager

# 新版本（正确）
from utu.db import DatasetSample, DBService
from utu.utils import get_logger, SQLModelUtils
```

### 修改2: 函数签名
```python
# 旧版本（异步）
async def create_korgym_datasets(...):

# 新版本（同步）
def create_korgym_datasets(...):
```

### 修改3: 数据库操作
```python
# 旧版本
await db_manager.upsert_dataset_samples(eval_samples)

# 新版本
DBService.add(eval_samples)
```

### 修改4: 数据库检查
```python
# 新增数据库可用性检查
if not SQLModelUtils.check_db_available():
    logger.error("Database is not available. Please check your UTU_DB_URL environment variable.")
    return
```

---

## ✅ 现在可以正常运行

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 测试脚本
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
```

---

## 📊 完整的三个游戏命令

### Word Puzzle
```bash
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
```

### Alphabetical Sorting
```bash
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
```

### Wordle
```bash
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
```

---

## 🎯 预期输出

成功运行后应该看到：

```
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO - Creating KORGym datasets for game: 8-word_puzzle
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO -   - Evaluation: 50 samples (seeds 1-50)
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO -   - Training: 100 samples (seeds 51-150)
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO - Uploading 50 evaluation samples...
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO - ✓ Evaluation dataset created: KORGym-Eval-50
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO - Uploading 100 training samples...
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO - ✓ Training dataset created: KORGym-Train-100
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO - 
📊 Dataset Summary:
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO -   - Evaluation: 50 samples (seeds 1-50)
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO -   - Training: 100 samples (seeds 51-150)
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO -   - Game: 8-word_puzzle
2026-01-15 16:xx:xx[utu.data.prepare_korgym_data] - INFO - 
✅ Datasets created successfully!
```

---

## 🔄 继续完整流程

数据准备成功后，继续执行：

```bash
# 基线评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# 训练
uv run python scripts/run_training_free_GRPO.py --config_name word_puzzle_practice

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

---

*修复时间: 2026-01-15*  
*修复文件: scripts/data/prepare_korgym_data.py*

