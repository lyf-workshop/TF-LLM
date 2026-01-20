# Wordle训练时trajectories为None的修复 🔧

## 🔍 问题诊断

### 错误信息
```python
TypeError: object of type 'NoneType' has no len()
File "/mnt/f/youtu-agent/utu/practice/experience_updater.py", line 84
    if len(rollout.trajectories) > 0:
```

### 根本原因

在Wordle等多轮游戏的rollout过程中，某些样本的 `trajectories` 字段为 `None`，导致经验提取时出错。

**可能原因**:
1. Rollout过程中出现异常，trajectories未正确保存
2. 多轮游戏的trajectory格式与单轮不同
3. 某些失败的rollout没有trajectory数据

---

## ✅ 修复内容

### 修复1: 添加空值检查（第84行）

```python
# ❌ 原代码
for rollout in rollouts:
    if len(rollout.trajectories) > 0:  # trajectories可能为None
        problems_to_rollouts[rollout.raw_question].append(rollout)

# ✅ 修复后
for rollout in rollouts:
    if rollout.trajectories and len(rollout.trajectories) > 0:  # 先检查是否为None
        problems_to_rollouts[rollout.raw_question].append(rollout)
```

### 修复2: 添加trajectory解析的安全检查（第119行）

```python
# ❌ 原代码
trajectory=json.loads(item.trajectories)[0]["trajectory"],  # 可能失败

# ✅ 修复后
trajectory_data = "No trajectory available"
if item.trajectories:
    try:
        traj_list = json.loads(item.trajectories)
        if traj_list and len(traj_list) > 0:
            trajectory_data = traj_list[0].get("trajectory", "No trajectory in first entry")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning(f"Failed to parse trajectories: {e}")
        trajectory_data = "Trajectory parsing failed"

trajectory=trajectory_data,
```

---

## 🚀 修复后重新运行

```bash
cd /mnt/f/youtu-agent

# 清理旧的训练数据（如果需要）
uv run python scripts/clean_experiment_data.py --exp_id wordle_practice

# 清理经验缓存
uv run python -c "
from utu.utils.experience_cache import ExperienceCache
ExperienceCache.delete_experiment_cache('wordle_practice')
print('✓ 经验缓存已清理')
"

# 重新运行训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
```

---

## 🔍 为什么会出现None？

### 可能的原因

1. **Rollout失败**
   - Agent响应超时
   - 游戏服务器错误
   - 格式解析失败

2. **多轮游戏特殊性**
   - 多轮游戏的trajectory是列表的JSON字符串
   - 如果游戏在第一轮就失败，可能没有保存trajectory

3. **数据库序列化问题**
   - trajectory太大导致保存失败
   - JSON序列化错误

### 验证方法

```bash
# 查看rollout结果
uv run python -c "
from utu.utils import SQLModelUtils
from utu.db import EvaluationSample
from sqlmodel import select

with SQLModelUtils.create_session() as session:
    samples = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id == 'wordle_practice'
        ).limit(5)
    ).all()
    
    for i, sample in enumerate(samples, 1):
        traj_status = 'None' if sample.trajectories is None else f'{len(sample.trajectories)} chars'
        print(f'Sample {i}: trajectories={traj_status}, stage={sample.stage}, reward={sample.reward}')
"
```

---

## 📊 预期结果

修复后，训练应该能正常完成：

```
Preprocessing batch: 100%|████████████| 100/100 [00:30<00:00,  3.33it/s]
Rolling out: 100%|████████████████████| 300/300 [15:00<00:00,  3.00s/it]
Judging: 100%|███████████████████████| 300/300 [00:10<00:00, 30.00it/s]

Trajectory Summarization: 100%|██████| 50/50 [02:00<00:00,  2.40s/it]
Semantic Group Advantage: 100%|███████| 20/20 [01:00<00:00,  3.00s/it]
Group update: 100%|████████████████████| 20/20 [00:40<00:00,  2.00s/it]

✓ Step 2 completed. New experiences added: 15
✓ Processing hierarchical experiences...
✓ Added 15 L0 experiences (total: 15)
✓ Generating L1 from 5 L0 experiences...
✓ Generated L1_0
✓ Hierarchical processing complete. L0=15, L1=3, L2=0
```

---

## 🐛 如果问题仍然存在

### 检查rollout阶段

```bash
# 查看日志中的rollout错误
tail -200 logs/utu.log | grep -i "error\|failed\|exception" | grep -i "rollout"

# 常见问题：
# - "Failed to execute multi-round game"
# - "Game generation failed"
# - "Timeout"
```

### 检查游戏服务器

```bash
# 测试游戏服务器
curl -X POST http://localhost:8777/generate \
  -H "Content-Type: application/json" \
  -d '{"seed": 1}'

# 应该返回游戏状态JSON
```

### 降低并发数

如果仍有问题，可能是并发太高导致部分rollout失败：

```yaml
# configs/practice/korgym/wordle_practice.yaml
practice:
  rollout_concurrency: 2  # 降低到2（更保守）
```

---

## ✅ 验证修复

修复后，检查：

1. **训练能正常完成** ✅
2. **经验文件生成** ✅
   ```bash
   cat workspace/hierarchical_experiences/wordle_practice.json | jq '.stats'
   ```
3. **Agent配置生成** ✅
   ```bash
   cat configs/agents/practice/wordle_practice_agent.yaml | head -50
   ```

---

**修复完成！现在可以重新运行Wordle训练了。** 🚀

---

**创建时间**: 2026-01-18  
**问题**: trajectories为None导致经验提取失败  
**修复**: 添加空值检查和异常处理  
**影响**: 所有使用experience_updater的训练流程















