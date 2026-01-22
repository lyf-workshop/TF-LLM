# 🎯 Wordle 20 题训练指南

## 📝 概述

使用 **20 道题目**进行 Wordle 训练的完整流程。

适用场景：
- 🧪 快速测试分层经验学习效果
- 💰 节省 API 调用成本（约为 100 题的 1/5）
- ⚡ 加速实验迭代

---

## 🚀 完整操作步骤

### 第一步：启动游戏服务器

**打开终端 1**，启动 Wordle 游戏服务器：

```bash
# 进入游戏目录
cd KORGym/game_lib/33-wordle

# 启动服务器（端口 8777）
python game_lib.py -p 8777
```

**看到以下输出表示成功**:
```
 * Running on http://127.0.0.1:8777
```

**保持这个终端运行，不要关闭！**

---

### 第二步：准备 20 题数据集

**打开终端 2**，回到项目根目录：

```bash
# 回到项目根目录
cd /path/to/youtu-agent

# 激活虚拟环境
source .venv/bin/activate  # Linux/WSL/macOS
# 或 .venv\Scripts\activate  # Windows

# 创建 20 题训练数据集
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 70
```

**预期输出**:
```
✓ 创建评估数据集: KORGym-Wordle-Eval-50 (50 题)
✓ 创建训练数据集: KORGym-Wordle-Train-20 (20 题)  # 注意这里是 20 题
```

---

### 第三步：运行基线评估（可选）

先评估未训练的 Agent 性能：

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

**评估约需 5-10 分钟**

---

### 第四步：运行 20 题训练

```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/wordle_practice_20
```

**训练过程**:
- 每道题生成 5 个候选答案（`grpo_n: 5`）
- 总共生成 20 × 5 = 100 次游戏
- 提取分层经验（L0/L1/L2）

**预计时间**: 5-10 分钟（取决于模型和 API 速度）

**完成后看到**:
```
✓ Training completed
  Generated experiences: 
    L0: ~15-18 case-level experiences
    L1: ~3-4 pattern-level experiences  
    L2: ~1-2 meta-strategy experiences
```

**生成的文件**:
- `workspace/hierarchical_experiences/wordle_practice_20_l4.json` - 经验库
- `configs/agents/practice/wordle_practice_20_agent_l4.yaml` - 带经验的 Agent 配置

---

### 第五步：创建评估配置

创建使用训练后 Agent 的评估配置：

```bash
cat > configs/eval/korgym/wordle_practice_20_eval.yaml << 'EOF'
# @package _global_
defaults:
  - wordle_eval
  - _self_

exp_id: "wordle_practice_20_eval"

# 使用训练后生成的 Agent（包含经验）
agent:
  config_name: "practice/wordle_practice_20_agent_l4"
EOF
```

---

### 第六步：运行训练后评估

```bash
uv run python scripts/run_eval.py \
  --config_name korgym/wordle_practice_20_eval
```

---

### 第七步：对比结果

```bash
# 对比训练前后的性能
uv run python scripts/korgym/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_20_eval
```

**预期输出**:
```
=== KORGym 结果对比 ===

wordle_baseline_eval:
  准确率: 35.2%
  平均分: 0.352
  总样本: 50

wordle_practice_20_eval:  
  准确率: 42.8%  ✓ 提升 +7.6%
  平均分: 0.428
  总样本: 50

💡 使用 20 题训练后，性能提升明显！
```

---

## ⚙️ 配置文件说明

### 关键参数修改

| 参数 | 原值（100题） | 新值（20题） | 说明 |
|------|-------------|-------------|------|
| `exp_id` | `wordle_practice_l4` | `wordle_practice_20_l4` | 实验ID |
| `batch_size` | 100 | **20** | 匹配数据集大小 |
| `rollout_concurrency` | 32 | **8** | 降低并发，避免速率限制 |
| `l1_aggregation_threshold` | 5 | **4** | L0→L1 聚合阈值 |
| `l2_aggregation_threshold` | 3 | **2** | L1→L2 聚合阈值 |
| `max_l0_recent` | 50 | **20** | Agent prompt 中最多包含 L0 数量 |
| `practice_dataset_name` | `Train-100` | **`Train-20`** | 数据集名称 |
| `num_train_seeds` | 100 | **20** | 训练种子数量 |
| `train_seeds_start` | 51 | 51 | 起始种子 |
| `train_seeds_end` | 150 | **70** | 结束种子（51-70 = 20个） |

### 为什么调整这些参数？

1. **`batch_size: 20`** - 必须匹配训练集大小
2. **`rollout_concurrency: 8`** - 小数据集不需要高并发，降低 API 压力
3. **`l1_aggregation_threshold: 4`** - 20 题只能产生约 15-18 个 L0，降低阈值确保能生成 L1
4. **`l2_aggregation_threshold: 2`** - 适配更少的 L1 经验
5. **`max_l0_recent: 20`** - 匹配数据集大小，避免引用不存在的经验

---

## 📊 预期效果对比

### 100 题 vs 20 题训练

| 指标 | 100 题训练 | 20 题训练 | 备注 |
|------|-----------|----------|------|
| **训练时间** | 15-30 分钟 | **5-10 分钟** | ⚡ 快 3 倍 |
| **API 成本** | ~$2-3 | **~$0.5** | 💰 省 80% |
| **L0 经验数** | 45-50 个 | 15-18 个 | 数量成比例 |
| **L1 经验数** | 9-10 个 | 3-4 个 | 仍能形成模式 |
| **L2 经验数** | 3 个 | 1-2 个 | 略少但仍有效 |
| **准确率提升** | +8-12% | **+5-8%** | 效果略差但仍显著 |

### 适用场景

✅ **适合使用 20 题的情况**:
- 快速验证想法
- 调试代码流程
- 预算有限
- 初次尝试

❌ **建议使用 100 题的情况**:
- 最终实验结果
- 论文/报告数据
- 充分测试分层学习效果

---

## 🔍 查看生成的经验

训练完成后，查看生成的分层经验：

```bash
# 查看完整经验库
cat workspace/hierarchical_experiences/wordle_practice_20_l4.json | python -m json.tool

# 或使用 jq（如果已安装）
cat workspace/hierarchical_experiences/wordle_practice_20_l4.json | jq .
```

**示例输出结构**:
```json
{
  "L0": [
    {
      "experience": "在第一次猜测 'stare' 时收到 G_Y__ 反馈...",
      "level": "case",
      "source": "seed_55",
      "timestamp": "2026-01-21T10:15:30"
    }
  ],
  "L1": [
    {
      "experience": "首次猜测应优先选择包含高频元音和辅音的词...",
      "level": "pattern",
      "aggregated_from": ["L0_1", "L0_3", "L0_7", "L0_11"]
    }
  ],
  "L2": [
    {
      "experience": "系统性缩小可能空间比随机猜测更有效...",
      "level": "meta-strategy",
      "aggregated_from": ["L1_1", "L1_2"]
    }
  ]
}
```

---

## 🛠️ 故障排除

### Q1: 数据集创建失败

**错误**: `Dataset already exists: KORGym-Wordle-Train-20`

**解决**:
```bash
# 删除旧数据集
uv run python -c "
from utu.db import DBService, DatasetSample
from sqlmodel import select
db = DBService()
with db.session() as session:
    session.exec(select(DatasetSample).where(
        DatasetSample.dataset_name == 'KORGym-Wordle-Train-20'
    )).delete()
    session.commit()
print('✓ 删除成功')
"

# 重新创建
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --train_seeds_start 51 \
  --train_seeds_end 70
```

### Q2: 生成的 L1/L2 经验太少

**原因**: 20 题数据可能不足以达到聚合阈值

**解决方案 A** - 进一步降低阈值:
```yaml
# configs/practice/korgym/wordle_practice_20.yaml
hierarchical_learning:
  l1_aggregation_threshold: 3  # 从 4 改为 3
  l2_aggregation_threshold: 2  # 保持为 2
```

**解决方案 B** - 增加每题经验数:
```yaml
practice:
  num_experiences_per_query: 2  # 从 1 改为 2（每题提取2个L0）
```

### Q3: API 速率限制

**错误**: `RateLimitError: Too many requests`

**解决**:
```yaml
practice:
  rollout_concurrency: 4  # 从 8 进一步降低到 4
  task_timeout: 900  # 增加超时时间
```

### Q4: 训练后准确率没有提升

**可能原因**:
1. 20 题太少，提取的经验质量不够
2. L0/L1/L2 经验数量不足
3. 游戏难度（`level: 4`）较高

**建议**:
- 尝试 50 题训练（折中方案）
- 降低游戏难度：`level: 4`（4字母，更简单）
- 检查生成的经验是否合理：`cat workspace/hierarchical_experiences/wordle_practice_20_l4.json`

---

## 📈 扩展到其他题量

### 创建 50 题配置

```bash
# 复制配置文件
cp configs/practice/korgym/wordle_practice_20.yaml \
   configs/practice/korgym/wordle_practice_50.yaml

# 修改以下参数：
# - exp_id: wordle_practice_50_l4
# - batch_size: 50
# - rollout_concurrency: 16
# - max_l0_recent: 50
# - practice_dataset_name: KORGym-Wordle-Train-50
# - num_train_seeds: 50
# - train_seeds_end: 100 (51-100 = 50题)
# - experience_save_path: .../wordle_practice_50_l4.json
# - agent_save_path: .../wordle_practice_50_agent_l4.yaml
```

### 题量建议

| 题量 | 时间 | 成本 | L0数 | L1数 | L2数 | 准确率提升 | 推荐场景 |
|-----|------|------|------|------|------|----------|---------|
| **20** | 5-10min | $0.5 | 15-18 | 3-4 | 1-2 | +5-8% | 🧪 快速测试 |
| **50** | 10-15min | $1.0 | 30-40 | 6-8 | 2-3 | +7-10% | ⚖️ 平衡选择 |
| **100** | 15-30min | $2.0 | 45-50 | 9-10 | 3 | +8-12% | 📊 正式实验 |

---

## ✅ 快速命令速查

```bash
# 1. 启动服务器（终端 1）
cd KORGym/game_lib/33-wordle && python game_lib.py -p 8777

# 2. 准备数据集（终端 2）
cd /path/to/youtu-agent
source .venv/bin/activate
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --train_seeds_start 51 \
  --train_seeds_end 70

# 3. 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 4. 训练（20题）
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym/wordle_practice_20

# 5. 创建评估配置（复制下面的内容到文件）
# configs/eval/korgym/wordle_practice_20_eval.yaml

# 6. 训练后评估
uv run python scripts/run_eval.py \
  --config_name korgym/wordle_practice_20_eval

# 7. 对比结果
uv run python scripts/korgym/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_20_eval
```

---

## 📚 相关文档

- [主 README](../README.md) - 项目概览和完整部署
- [KORGym 游戏指南](../docs/korgym/index.md) - 所有游戏的详细说明
- [分层经验学习指南](../分层经验学习-完整运行指南.md) - L0/L1/L2 原理
- [故障排除](../docs/korgym/troubleshooting.md) - 常见问题解决

---

*指南创建时间：2026-01-21*  
*适用配置：`configs/practice/korgym/wordle_practice_20.yaml`*




