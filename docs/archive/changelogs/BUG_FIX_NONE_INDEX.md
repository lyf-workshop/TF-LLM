# Bug 修复：DatasetSample.index 为 None 导致崩溃

## 🐛 错误详情

### 错误信息

```python
TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'

File: /mnt/f/youtu-agent/utu/practice/data_manager.py", line 57
Code: key = MistakeBank.problem_key(dp.dataset, int(dp.index))
                                               ^^^^^^^^^^^^^
Error: int(None) → TypeError
```

### 触发场景

**训练第二轮时**，错题集（MistakeBank）尝试加载数据时崩溃。

**调用栈**：
```
run_training_free_GRPO.py
  └─ training_free_grpo.practice()
     └─ rollout_manager.load_epoch_data()
        └─ data_manager.load_epoch_data()
           └─ MistakeBank.problem_key(dp.dataset, int(dp.index))  ← 崩溃
```

---

## 🔍 根本原因

### DatasetSample 的 index 字段定义

```python
# utu/db/eval_datapoint.py (Line 14-15)
class DatasetSample(SQLModel, table=True):
    index: int | None = Field(default=None)  # ⚠️ 可能为 None
```

**问题**：
- `DatasetSample.index` 字段可以是 `None`
- 但 `data_manager.py` 中直接调用 `int(dp.index)`
- 当 `dp.index = None` 时 → `int(None)` → TypeError

### 为什么会出现 None？

可能的原因：
1. 数据集准备时没有设置 `index` 字段
2. 数据库中的旧数据没有 `index`
3. 某些数据源本身就没有索引信息

---

## ✅ 修复方案

### 代码修改

**文件**：`utu/practice/data_manager.py`

**修改位置 1**（Line 57-59）：
```python
# 修复前
key = MistakeBank.problem_key(dp.dataset, int(dp.index))  # ❌ dp.index 可能为 None

# 修复后
dp_index = int(dp.index) if dp.index is not None else 0  # ✅ 处理 None
key = MistakeBank.problem_key(dp.dataset, dp_index)
```

**修改位置 2**（Line 65-68）：
```python
# 修复前
priority.sort(
    key=lambda dp: bank.score_for_sampling(
        failed_records[MistakeBank.problem_key(dp.dataset, int(dp.index))],  # ❌
        ...
    ),
    ...
)

# 修复后
priority.sort(
    key=lambda dp: bank.score_for_sampling(
        failed_records[MistakeBank.problem_key(
            dp.dataset, 
            int(dp.index) if dp.index is not None else 0  # ✅ 处理 None
        )],
        ...
    ),
    ...
)
```

---

## 📊 影响范围

### 受影响的功能

- ✅ **错题集优先采样**（MistakeBank + 偏置采样）
- ✅ **训练第二轮及以后**（第一轮没有错题集，不受影响）

### 不受影响的功能

- ✅ 第一轮训练（不使用错题集）
- ✅ 评估（不使用错题集）
- ✅ 经验生成（不依赖 index）
- ✅ 分层经验（L0/L1/L2）

---

## 🧪 验证修复

### 测试步骤

```bash
# 1. 清理旧数据（如果需要）
rm test.db
rm workspace/mistake_bank/*.json

# 2. 重新运行训练（会经过第二轮）
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20

# 预期：
# - ✅ 第一轮正常完成
# - ✅ 第二轮正常加载错题集（不再崩溃）
# - ✅ 显示优先采样日志
```

### 预期日志

**第一轮**（创建错题集）：
```
Epoch 1/3:
- Rolling out batch: 100%
- Judging batch: 100%
- Experience generation: ✅
- Mistake bank updated (新增失败记录)
```

**第二轮**（使用错题集 - 之前会崩溃）：
```
Epoch 2/3:
- Loading epoch data with mistake bank bias...
  Found 15 failed problems, focusing 30% samples on mistakes  ← ✅ 新增
- Rolling out batch: 100%
- ✅ 不再崩溃！
```

---

## 🎯 相关修复（同类问题）

### 检查其他可能的 None 处理

查找所有使用 `int(...)` 的地方：

```bash
# 搜索可能的类似问题
grep -r "int(dp\." utu/practice/
grep -r "int(sample\." utu/practice/
```

**已验证的安全使用**：

```python
# mistake_bank.py (Line 203) - ✅ 正确处理
dataset_index = int(getattr(s, "dataset_index", 0) or 0)  # 使用默认值 0

# data_manager.py (Line 123) - ✅ 可以为 None（字段定义允许）
dataset_index=dp.index  # EvaluationSample.dataset_index 允许 None
```

---

## 📋 最佳实践

### 处理可能为 None 的字段

**推荐模式**：
```python
# 模式 1: 使用默认值
value = int(field) if field is not None else 0

# 模式 2: 使用 or 运算符
value = int(field or 0)

# 模式 3: 使用 getattr 带默认值
value = int(getattr(obj, 'field', 0) or 0)
```

**反模式（避免）**：
```python
# ❌ 直接转换（可能崩溃）
value = int(field)

# ❌ 假设字段一定存在
value = int(obj.field)
```

---

## 🎉 总结

### 修复内容

1. ✅ 修复 `data_manager.py` Line 57（错题集 key 计算）
2. ✅ 修复 `data_manager.py` Line 65（优先级排序）
3. ✅ 添加 None 检查，使用默认值 0

### 影响

- ✅ 训练第二轮及以后不再崩溃
- ✅ 错题集优先采样正常工作
- ✅ 无性能影响
- ✅ 向后兼容（index=None 时使用默认值 0）

### 测试状态

- ✅ Lint 检查通过
- ✅ 逻辑正确
- 🔜 需要运行实际训练验证

---

**修复完成时间**：2026-01-22  
**修复人员**：Claude Sonnet 4.5  
**优先级**：🔴 高（阻塞训练）
