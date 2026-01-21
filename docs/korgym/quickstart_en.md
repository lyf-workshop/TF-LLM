# KORGym快速启动指南 ⚡

## 🚀 一键运行（推荐）

### 终端1: 启动游戏服务器
```bash
cd /mnt/f/youtu-agent  # WSL路径
chmod +x scripts/start_korgym_server.sh
./scripts/start_korgym_server.sh 8-word_puzzle 8775
```

### 终端2: 运行完整流程
```bash
cd /mnt/f/youtu-agent
chmod +x scripts/run_korgym_full_pipeline.sh
source .venv/bin/activate
./scripts/run_korgym_full_pipeline.sh
```

---

## 📋 分步运行

### 0. 环境准备
```bash
cd /mnt/f/youtu-agent
uv sync --all-extras
source .venv/bin/activate
```

### 1. 启动游戏服务器（单独终端）
```bash
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
# 保持运行，不要关闭
```

### 2. 准备数据集
```bash
# 使用默认设置（word_puzzle游戏）
uv run python scripts/data/prepare_korgym_data.py

# 或指定其他游戏
uv run python scripts/data/prepare_korgym_data.py --game_name "3-2048"
```

### 3. 基线评估
```bash
uv run python scripts/run_eval.py --config_name korgym/korgym_eval
```

### 4. 训练（分层经验学习）
```bash
uv run python scripts/run_training_free_GRPO.py --config_name korgym_practice
```

### 5. 评估训练后的Agent
```bash
uv run python scripts/run_eval.py --config_name korgym/korgym_practice_eval
```

---

## 🎮 切换游戏

### 1. 修改配置文件
编辑 `configs/practice/korgym_practice.yaml`:
```yaml
korgym:
  game_name: "3-2048"  # 改为你想要的游戏
  game_port: 8776      # 建议使用不同端口
```

### 2. 启动对应游戏服务器
```bash
cd KORGym/game_lib/3-2048
python game_lib.py -p 8776
```

### 3. 创建对应数据集
```bash
uv run python scripts/data/prepare_korgym_data.py --game_name "3-2048"
```

### 4. 运行训练和评估
```bash
# 按照上面的步骤3-5执行
```

---

## 🎯 推荐游戏列表

| 游戏ID | 名称 | 类别 | 端口建议 | 难度 |
|-------|------|------|---------|------|
| 8-word_puzzle | 文字谜题 | Puzzle | 8775 | ⭐⭐⭐ |
| 3-2048 | 2048游戏 | Strategic | 8776 | ⭐⭐⭐ |
| 33-wordle | Wordle | Puzzle | 8777 | ⭐⭐ |
| 4-SudoKu | 数独 | Math-Logic | 8778 | ⭐⭐⭐⭐ |
| 30-Tower_of_Hanoi | 汉诺塔 | Spatial | 8779 | ⭐⭐ |

---

## 📊 查看结果

### 评估结果
```bash
# 基线结果
cat workspace/korgym_baseline_eval/score.txt

# 训练后结果
cat workspace/korgym_practice_eval/score.txt
```

### 提取的经验
```bash
# 查看经验统计
cat workspace/hierarchical_experiences/korgym_practice.json | jq '.stats'

# 查看L0经验（案例级）
cat workspace/hierarchical_experiences/korgym_practice.json | jq '.l0_experiences[0:3]'

# 查看L1经验（模式级）
cat workspace/hierarchical_experiences/korgym_practice.json | jq '.l1_experiences'

# 查看L2经验（元策略级）
cat workspace/hierarchical_experiences/korgym_practice.json | jq '.l2_experiences'
```

### 增强的Agent配置
```bash
cat configs/agents/practice/korgym_practice_agent.yaml
```

---

## 🔧 常见问题

### Q1: 游戏服务器连接失败
```bash
# 检查服务器状态
curl http://localhost:8775/docs

# 如果失败，重启服务器
pkill -f "game_lib.py"
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

### Q2: 训练超时
修改 `configs/practice/korgym_practice.yaml`:
```yaml
practice:
  task_timeout: 1200  # 增加到20分钟
```

### Q3: 内存不足
减少并发数：
```yaml
practice:
  rollout_concurrency: 16  # 从32降到16
evaluation:
  concurrency: 16
```

### Q4: 从头开始训练（清除缓存）
```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym_practice \
  --restart_step 0
```

---

## 📈 预期性能

- **基线准确率**: ~30-50%
- **训练后准确率**: ~40-65%
- **预期提升**: +10-15%

---

## 📁 生成的文件

```
workspace/
├── korgym_baseline_eval/          # 基线评估结果
│   └── score.txt
├── korgym_practice_eval/          # 训练后评估结果
│   └── score.txt
└── hierarchical_experiences/      # 提取的经验
    └── korgym_practice.json

configs/agents/practice/
└── korgym_practice_agent.yaml     # 增强的Agent配置
```

---

## 🎓 理解分层经验

### L0 - 案例级经验
```
从单个游戏回合中提取的具体策略
示例: "在word_puzzle中，优先尝试常见的元音字母组合..."
```

### L1 - 模式级经验
```
从5个L0经验中总结的通用策略
示例: "在谜题类游戏中，系统性地缩小可能性空间比随机尝试更有效..."
```

### L2 - 元策略级经验
```
从3个L1经验中提炼的跨游戏原则
示例: "在所有游戏中，建立明确的状态追踪机制能显著提升决策质量..."
```

---

✅ **现在你可以开始运行KORGym分层经验学习了！**

详细文档请参考: `KORGym_Usage_Guide.md`

