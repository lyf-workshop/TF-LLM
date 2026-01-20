# Wordle 快速开始指南 🎯

## 🎮 游戏概况

- **类型**: 猜词游戏（多轮）
- **目标**: 10次机会内猜出4-12字母的单词
- **端口**: 8777
- **评分**: 猜中=1分，失败=0分（All-or-nothing）

## ⚡ 5分钟快速测试

### 终端1: 启动服务器
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

### 终端2: 运行完整流程
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 1️⃣ 准备数据（首次运行）
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 2️⃣ 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 3️⃣ 训练（提取经验）
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 4️⃣ 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 5️⃣ 查看结果对比
uv run python scripts/view_korgym_results.py --game wordle
```

## ✅ 已修复的配置问题

| 问题 | 原值 | 新值 | 影响 |
|------|------|------|------|
| 尝试次数 | `max_rounds: 6` | `max_rounds: 10` | ✅ 匹配游戏代码 |
| 单词长度 | `level: 3` | `level: 5` | ✅ 有效范围（4-12） |
| Agent策略 | 固定5字母 | 支持4-12字母 | ✅ 动态适应 |

## 📊 预期性能

| 阶段 | 准确率 | 说明 |
|------|--------|------|
| 基线 | 8-15% | 没有经验学习 |
| 训练后 | 15-25% | 提升50-100% |

## 🐛 快速排查

```bash
# 检查服务器
curl http://localhost:8777/docs

# 检查数据集
uv run python scripts/clean_experiment_data.py --list

# 清理评估缓存（重新评估前）
uv run python scripts/clean_experiment_data.py --exp_id wordle_baseline_eval wordle_practice_eval

# 查看详细结果
uv run python scripts/view_korgym_results.py --exp_id wordle_baseline_eval --detailed
```

## 📚 相关文档

- **详细分析**: `WORDLE_GAME_ANALYSIS.md`
- **完整命令**: `KORGYM_THREE_GAMES_COMMANDS.md`
- **评分指南**: `KORGYM_SCORING_GUIDE.md`

---

**准备好了就开始吧！** 🚀



