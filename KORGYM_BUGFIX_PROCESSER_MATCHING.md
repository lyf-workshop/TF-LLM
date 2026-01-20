# ✅ KORGym Processer匹配问题修复

## 🐛 问题描述

运行评估时出现警告：

```bash
Processer for dataset='8-word_puzzle' not found. Using default processer.
```

系统无法找到KORGym的专用处理器，而使用了默认处理器。

## 🔍 问题原因

### Processer匹配逻辑

系统通过数据集的`source`字段来匹配对应的Processer：

```python
# base_benchmark.py
def _get_processer(self, source: str) -> BaseProcesser:
    processer = PROCESSER_FACTORY.get(source, self.config)
    return processer

# 使用时
processer = self._get_processer(sample.source)  # 使用sample.source
```

### 问题所在

1. **KORGymProcesser注册名称**: `"KORGym"`
2. **数据集source字段**: `"training_free_grpo"` ❌

不匹配！导致系统找不到KORGymProcesser。

---

## 🔧 已修复

修改 `scripts/data/prepare_korgym_data.py`，将数据集的`source`字段改为`"KORGym"`：

### 修改前（错误）
```python
sample = DatasetSample(
    dataset="KORGym-Eval-50",
    source="training_free_grpo",  # ❌ 无法匹配到KORGymProcesser
    question=f"Play KORGym game '{game_name}' with seed {seed}",
    ...
)
```

### 修改后（正确）
```python
sample = DatasetSample(
    dataset="KORGym-Eval-50",
    source="KORGym",  # ✅ 匹配到KORGymProcesser
    question=f"Play KORGym game '{game_name}' with seed {seed}",
    ...
)
```

---

## 🚀 如何使用

### 1. 重新创建数据集

由于source字段已更改，需要重新创建数据集：

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 重新准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
```

### 2. 运行评估

现在应该可以正确使用KORGymProcesser：

```bash
# 确保游戏服务器在运行
# 终端1: cd KORGym/game_lib/8-word_puzzle && python game_lib.py -p 8775

# 运行评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

---

## 🎯 预期行为

### 修复前（错误）
```
2026-01-15 xx:xx:xx[utu.eval.processer] - WARNING - Processer for dataset='8-word_puzzle' not found. Using default processer.
```

### 修复后（正确）
```
2026-01-15 xx:xx:xx[utu.eval.processer.korgym_processor] - INFO - ✓ KORGymProcesser initialized with adapter for 8-word_puzzle
Preprocessing: 50/50 [00:01<00:00, 45.12it/s]
Rolling out: 50/50 [00:30<00:00, 1.65it/s]
Judging: 50/50 [00:05<00:00, 9.87it/s]
```

---

## 📋 已修复的所有Bug

1. ✅ **数据库导入错误** (`scripts/data/prepare_korgym_data.py`)
   - 使用 `DBService` 代替 `db_manager`
   - 文档：`KORGYM_BUGFIX_DATABASE.md`

2. ✅ **循环导入错误** (`utu/eval/processer/korgym_processor.py`)
   - 使用延迟导入避免循环依赖
   - 文档：`KORGYM_BUGFIX_CIRCULAR_IMPORT.md`

3. ✅ **Processer匹配错误** (`scripts/data/prepare_korgym_data.py`)
   - 将source字段改为`"KORGym"`
   - 文档：`KORGYM_BUGFIX_PROCESSER_MATCHING.md`（本文件）

---

## 💡 技术要点

### Processer匹配机制

1. **注册机制**：每个Processer类有一个`name`属性
   ```python
   class KORGymProcesser(BaseMatchProcesser):
       name = "KORGym"  # 注册名称
   ```

2. **匹配逻辑**：通过数据集的`source`字段查找
   ```python
   # 数据集sample
   sample = DatasetSample(source="KORGym", ...)
   
   # 系统匹配
   processer = PROCESSER_FACTORY.get(sample.source, config)
   # 会找到 KORGymProcesser
   ```

3. **大小写不敏感**：
   ```python
   # 这些都能匹配到KORGymProcesser
   source = "KORGym"   # ✅
   source = "korgym"   # ✅
   source = "KORGYM"   # ✅
   ```

### 为什么需要正确的source字段？

- ✅ **正确的预处理**：KORGymProcesser会调用游戏服务器生成游戏实例
- ✅ **正确的判断逻辑**：使用游戏服务器验证答案并计算分数
- ✅ **正确的统计方法**：使用KORGym特定的统计逻辑

如果使用默认processer：
- ❌ 无法生成游戏实例
- ❌ 无法正确验证答案
- ❌ 无法计算正确的分数

---

## 🔄 完整流程（修复后）

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 1. 重新准备数据集（必须！source字段已更改）
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# 2. 基线评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval

# 3. 训练
uv run python scripts/run_training_free_GRPO.py --config_name word_puzzle_practice

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

---

*修复时间: 2026-01-15*  
*修复文件: scripts/data/prepare_korgym_data.py*  
*修复内容: source字段 "training_free_grpo" → "KORGym"*

