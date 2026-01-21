# Wordle多轮评估测试指南 🧪

## ✅ 好消息：多轮评估已实现！

经过检查，发现系统已经实现了多轮游戏评估支持：

### 已实现的功能

1. **BaseBenchmark.rollout_one** ✅
   - 自动检测KORGym多轮游戏
   - 调用 `adapter.play_game()` 进行完整多轮交互
   - 保存完整的trajectory和结果

2. **KORGymProcesser.judge_one** ✅
   - 识别多轮游戏结果
   - 直接使用rollout阶段的final_score
   - 不需要重新验证

3. **测试脚本** ✅
   - 创建了 `scripts/test_multiround_eval.py`
   - 支持小规模快速测试
   - 自动清理测试数据

---

## 🧪 测试步骤

### 步骤1: 启动Wordle服务器

在WSL终端1:
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8777

# 验证服务器
# 应该看到: INFO:     Application startup complete.
```

### 步骤2: 小规模测试（2个样本）

在WSL终端2:
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 快速测试2个样本
uv run python scripts/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 \
  --verbose

# 预期输出：
# ✓ 创建了 2 个测试样本
# 阶段1: Preprocessing...
# 阶段2: Rollout (多轮交互)...
#   Starting multi-round game for seed 1
#   Multi-round game completed: seed=1, rounds=X, score=0/1, success=True/False
# 阶段3: Judging...
#   KORGym multi-round judged: seed=1, rounds=X, score=0/1
# 阶段4: Statistics...
# ✅ 测试完成！
```

### 步骤3: 验证结果

检查输出中的关键信息：
```json
{
  "benchmark": "KORGym",
  "metrics": {
    "Pass@1 (%)": 0-50,  // 应该 > 0%
    "Details": {
      "total_problems": 2,
      "solved_problems": 0-2,
      "unsolved_problems": 0-2,
      "total_attempts": 2
    }
  }
}
```

**成功标准**:
- ✅ Rollout阶段显示 "Multi-round game completed"
- ✅ Judge阶段显示 "KORGym multi-round judged"
- ✅ 至少有一些样本的 `success=True`（即使很少）
- ✅ 显示了正确的rounds数量（1-10）

---

## 🚀 完整Wordle评估测试

如果小规模测试成功，进行完整评估：

### 步骤1: 准备数据集

```bash
cd /mnt/f/youtu-agent

# 创建Wordle数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 验证数据集
uv run python scripts/clean_experiment_data.py --list | grep Wordle
# 应该看到:
#   - KORGym-Wordle-Eval-50 (50 samples)
#   - KORGym-Wordle-Train-100 (100 samples)
```

### 步骤2: 清理旧评估结果

```bash
# 清理旧的评估缓存
uv run python scripts/clean_experiment_data.py --exp_id \
  wordle_baseline_eval \
  wordle_practice_eval
```

### 步骤3: 基线评估

```bash
# 确保游戏服务器运行在8777端口

# 运行基线评估（50个样本）
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 查看结果
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed
```

**预期结果**:
```
实验结果: wordle_baseline_eval
游戏: 33-wordle
总样本数: 50
成功数: 4-8
准确率 (Accuracy): 8-16%  ✅ 应该 > 0%
平均得分 (Avg Score): 0.08-0.16
```

### 步骤4: 训练

```bash
# 运行训练（提取经验）
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 查看生成的经验
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.stats'

# 查看Agent配置
cat configs/agents/practice/wordle_practice_agent.yaml | grep -A 3 "L0\|L1\|L2" | head -20
```

### 步骤5: 训练后评估

```bash
# 运行训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 查看对比结果
uv run python scripts/view_korgym_results.py --game wordle
```

**预期结果**:
```
对比分析: 基线 vs 训练后
================================================================================

实验结果: wordle_baseline_eval
准确率: 8-16%

实验结果: wordle_practice_eval  
准确率: 15-25%

提升统计
================================================================================
准确率提升: +7-10% ✅
```

---

## 🔍 调试技巧

### 查看多轮交互详情

```bash
# 查看详细的trajectory
uv run python -c "
from utu.utils import SQLModelUtils
from utu.db import EvaluationSample
from sqlmodel import select
import json

with SQLModelUtils.create_session() as session:
    sample = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id == 'wordle_baseline_eval'
        ).limit(1)
    ).first()
    
    if sample and sample.trajectories:
        traj = json.loads(sample.trajectories)
        print(f'Trajectory有 {len(traj)} 轮')
        for i, step in enumerate(traj[:5], 1):
            print(f'Round {i}: action={step.get(\"action\")}, score={step.get(\"score\")}')
"
```

### 检查日志

```bash
# 查看最新日志
tail -100 logs/utu.log | grep -i "multi-round\|wordle\|rounds"

# 应该看到:
# INFO - Detected KORGym multi-round game: 33-wordle
# INFO - Starting multi-round game for seed 1
# INFO - Multi-round game completed: seed=1, rounds=5, score=0, success=False
# INFO - KORGym multi-round judged: seed=1, rounds=5, score=0, success=False
```

---

## 🐛 常见问题

### 问题1: 测试显示 "KORGym adapter not initialized"

**原因**: 配置文件缺少korgym部分

**解决**: 检查配置文件是否有完整的korgym配置
```yaml
korgym:
  enabled: true
  game_name: "33-wordle"
  game_port: 8777
  level: 5
  max_rounds: 10
```

### 问题2: 仍然只有1轮交互

**原因**: 可能是单轮游戏或max_rounds设置错误

**检查**:
```bash
# 查看日志中的游戏类型
grep "game_type\|Detected KORGym" logs/utu.log | tail -5

# 应该看到: game_type: multiple
```

### 问题3: 准确率仍然是0%

**可能原因**:
1. Agent策略不好（需要改进instructions）
2. 单词长度不匹配（检查level参数）
3. 游戏太难（Wordle本身就很难）

**验证**:
```bash
# 查看详细的失败样本
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed
```

---

## 📊 预期性能

| 指标 | 基线 | 训练后 | 说明 |
|------|------|--------|------|
| **Accuracy** | 8-16% | 15-25% | 10次机会内猜中 |
| **Avg Rounds (成功时)** | 7-9 | 6-8 | 平均用几轮猜中 |
| **Avg Rounds (所有)** | 9-10 | 8-10 | 包括失败的 |

**注意**: Wordle是很难的游戏，即使是10次机会，准确率也不会很高。

---

## ✅ 测试检查清单

- [ ] 游戏服务器运行在8777端口
- [ ] 配置文件中 `max_rounds: 10`
- [ ] 配置文件中 `level: 5`
- [ ] Agent instructions支持动态单词长度
- [ ] 小规模测试通过（2个样本）
- [ ] 日志显示 "multi-round game completed"
- [ ] 完整评估准确率 > 0%

---

## 🎉 成功标志

如果看到以下输出，说明多轮评估成功：

```
INFO - Detected KORGym multi-round game: 33-wordle
INFO - Starting multi-round game for seed 1
INFO - Multi-round game completed: seed=1, rounds=7, score=1, success=True
INFO - KORGym multi-round judged: seed=1, rounds=7, score=1, success=True

实验结果: wordle_baseline_eval
总样本数: 50
成功数: 5
准确率 (Accuracy): 10.00%  ✅ 大于0%！
```

---

**现在可以开始测试了！** 🚀

运行命令:
```bash
cd /mnt/f/youtu-agent
uv run python scripts/test_multiround_eval.py --game_name "33-wordle" --seeds 1 2 --verbose
```



