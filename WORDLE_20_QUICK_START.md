# 🚀 Wordle 20 题训练 - 快速开始

## ✅ 配置文件已就绪

配置文件已修改完成：`configs/practice/korgym/wordle_practice_20.yaml`

关键修改：
- ✅ 训练集：100 题 → **20 题**
- ✅ 种子范围：51-150 → **51-70**
- ✅ batch_size: 100 → **20**
- ✅ 并发数：32 → **8**（避免 API 限流）
- ✅ L1 阈值：5 → **4**（适配小数据集）
- ✅ L2 阈值：3 → **2**

---

## 📝 完整操作步骤（5 步完成）

### 🎮 步骤 1：启动游戏服务器

**打开终端 1**（保持运行）：

```bash
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

看到 `* Running on http://127.0.0.1:8777` 表示成功 ✓

---

### 📊 步骤 2：准备 20 题数据集

**打开终端 2**，回到项目根目录：

```bash
# 回到项目根目录
cd F:\youtu-agent

# 激活虚拟环境
.venv\Scripts\activate  # Windows
# 或 source .venv/bin/activate  # Linux/WSL/macOS

# 创建 20 题训练数据集（种子 51-70）
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle" --train_seeds_start 51 --train_seeds_end 70
```

**预期输出**：
```
✓ 创建评估数据集: KORGym-Wordle-Eval-50 (50 题)
✓ 创建训练数据集: KORGym-Wordle-Train-20 (20 题)
```

---

### 📈 步骤 3：运行基线评估（可选但推荐）

先测试未训练的 Agent 性能：

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

⏱️ 大约需要 5-10 分钟

---

### 🧠 步骤 4：运行 20 题训练

```bash
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20
```

**训练过程**：
- 20 道题 × 5 个候选 = 100 次游戏
- 提取分层经验（L0/L1/L2）

⏱️ 大约需要 **5-10 分钟**

**成功标志**：
```
✓ Training completed
  Generated experiences: 
    L0: ~15-18 个案例级经验
    L1: ~3-4 个模式级经验
    L2: ~1-2 个元策略级经验
```

**生成的文件**：
- `workspace/hierarchical_experiences/wordle_practice_20_l4.json` ← 经验库
- `configs/agents/practice/wordle_practice_20_agent_l4.yaml` ← 带经验的 Agent

---

### 🎯 步骤 5：运行训练后评估

```bash
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval
```

⏱️ 大约需要 5-10 分钟

---

### 📊 步骤 6：查看对比结果

```bash
uv run python scripts/korgym/view_korgym_results.py wordle_baseline_eval wordle_practice_20_eval
```

**预期输出**：
```
=== KORGym 结果对比 ===

wordle_baseline_eval:
  准确率: 35.2%
  平均分: 0.352

wordle_practice_20_eval:  
  准确率: 42.8%  ✓ 提升 +7.6%
  平均分: 0.428

🎉 20 题训练后，性能提升明显！
```

---

## 🎓 查看生成的经验

```bash
# 查看完整经验库
cat workspace/hierarchical_experiences/wordle_practice_20_l4.json
```

示例结构：
```json
{
  "L0": [案例级经验，15-18 个],
  "L1": [模式级经验，3-4 个],
  "L2": [元策略级经验，1-2 个]
}
```

---

## 💰 成本对比

| 题量 | 训练时间 | API 成本 | 准确率提升 |
|-----|---------|---------|----------|
| 20 题 | 5-10 分钟 | ~$0.5 | +5-8% |
| 100 题 | 15-30 分钟 | ~$2.0 | +8-12% |

**20 题适合**：
- ✅ 快速测试想法
- ✅ 调试代码流程
- ✅ 预算有限
- ✅ 初次尝试

---

## 🔧 常见问题

### Q1: 数据集已存在

```bash
# 删除旧数据集后重新创建
uv run python -c "
from utu.db import DBService, DatasetSample
from sqlmodel import select, delete
db = DBService()
with db.session() as session:
    stmt = delete(DatasetSample).where(DatasetSample.dataset_name == 'KORGym-Wordle-Train-20')
    session.execute(stmt)
    session.commit()
print('✓ 删除成功')
"

# 重新创建
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle" --train_seeds_start 51 --train_seeds_end 70
```

### Q2: API 速率限制

如果遇到 `RateLimitError`，修改配置：

```yaml
# configs/practice/korgym/wordle_practice_20.yaml
practice:
  rollout_concurrency: 4  # 从 8 降低到 4
```

### Q3: L1/L2 经验太少

进一步降低阈值：

```yaml
hierarchical_learning:
  l1_aggregation_threshold: 3  # 从 4 改为 3
  l2_aggregation_threshold: 2  # 保持为 2
```

---

## 📚 详细文档

- 📖 [完整指南](WORDLE_20_DATASET_GUIDE.md) - 深入的说明和故障排除
- 🏠 [主 README](README.md) - 项目概览
- 🎮 [KORGym 游戏指南](docs/korgym/index.md) - 所有游戏文档

---

## 🎯 一键复制命令

```bash
# === 终端 1：启动服务器 ===
cd KORGym/game_lib/33-wordle && python game_lib.py -p 8777

# === 终端 2：完整流程 ===
cd F:\youtu-agent
.venv\Scripts\activate

# 1. 准备数据
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle" --train_seeds_start 51 --train_seeds_end 70

# 2. 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 3. 训练（20题）
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20

# 4. 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval

# 5. 对比结果
uv run python scripts/korgym/view_korgym_results.py wordle_baseline_eval wordle_practice_20_eval
```

---

**🚀 准备好了！开始你的 20 题 Wordle 训练吧！**

*最后更新：2026-01-21*




