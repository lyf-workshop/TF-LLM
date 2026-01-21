# KORGym命令速查表 📋

## 🎯 核心命令（在WSL中执行）

### 基础设置
```bash
# 1. 进入项目目录
cd /mnt/f/youtu-agent

# 2. 激活环境
source .venv/bin/activate

# 3. 设置脚本权限（只需执行一次）
chmod +x scripts/*.sh
```

---

## 🎮 完整流程命令

### 终端1: 游戏服务器
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
# 保持运行
```

### 终端2: 训练和评估
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# Step 1: 准备数据集（50题评估 + 100题训练）
uv run python scripts/data/prepare_korgym_data.py

# Step 2: 基线评估（seeds 1-50）
uv run python scripts/run_eval.py --config_name korgym/korgym_eval

# Step 3: 训练（seeds 51-150，提取L0/L1/L2经验）
uv run python scripts/run_training_free_GRPO.py --config_name korgym_practice

# Step 4: 评估训练后的模型（同样seeds 1-50）
uv run python scripts/run_eval.py --config_name korgym/korgym_practice_eval
```

---

## ⚡ 一键运行（推荐）

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate
./scripts/run_korgym_full_pipeline.sh
```

---

## 📊 查看结果

```bash
# 基线结果
cat workspace/korgym_baseline_eval/score.txt

# 训练后结果
cat workspace/korgym_practice_eval/score.txt

# 经验统计
cat workspace/hierarchical_experiences/korgym_practice.json | grep -A 10 '"stats"'

# 查看生成的Agent配置
cat configs/agents/practice/korgym_practice_agent.yaml | head -50
```

---

## 🔄 切换游戏

### 修改配置
```bash
# 编辑训练配置
nano configs/practice/korgym_practice.yaml
# 修改: game_name: "3-2048"
#      game_port: 8776
```

### 准备新游戏
```bash
# 准备数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "3-2048"

# 启动新游戏服务器
cd KORGym/game_lib/3-2048
python game_lib.py -p 8776
```

---

## 🐛 故障排查

### 检查游戏服务器
```bash
curl http://localhost:8775/docs
# 或访问浏览器: http://localhost:8775/docs
```

### 重启游戏服务器
```bash
pkill -f "game_lib.py"
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

### 清除缓存重新训练
```bash
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym_practice \
  --restart_step 0
```

### 查看日志
```bash
# 查看最新的Phoenix traces（如果启用）
# 浏览器访问: http://localhost:6006

# 查看工作目录
ls -lh workspace/
ls -lh workspace/hierarchical_experiences/
```

---

## 📁 重要文件位置

```
配置文件:
├── configs/agents/practice/korgym_agent.yaml          # 基础Agent
├── configs/agents/practice/korgym_practice_agent.yaml # 训练后Agent（自动生成）
├── configs/eval/korgym/korgym_eval.yaml               # 基线评估配置
├── configs/eval/korgym/korgym_practice_eval.yaml      # 训练后评估配置
└── configs/practice/korgym_practice.yaml              # 训练配置

验证函数:
└── utu/practice/verify/korgym.py                      # KORGym验证函数

结果文件:
├── workspace/korgym_baseline_eval/                    # 基线结果
├── workspace/korgym_practice_eval/                    # 训练后结果
└── workspace/hierarchical_experiences/korgym_practice.json  # 经验库
```

---

## 🎓 关键参数说明

### 数据集设置
- **评估集**: seeds 1-50（50题）
- **训练集**: seeds 51-150（100题）
- 保证评估集一致，可公平对比baseline和practice性能

### 分层经验设置
```yaml
l1_aggregation_threshold: 5  # 每5个L0 → 1个L1
l2_aggregation_threshold: 3  # 每3个L1 → 1个L2
max_l0_recent: 50           # Agent prompt中保留最近50个L0
```

### 训练设置
```yaml
epochs: 2              # 2个epoch
batch_size: 50         # 每批50题
grpo_n: 3              # 每题3次rollout
rollout_concurrency: 32  # 32并发
```

---

## ✅ 快速检查清单

```bash
# 检查清单
[ ] WSL环境正常
[ ] 项目路径: /mnt/f/youtu-agent
[ ] 虚拟环境激活
[ ] 游戏服务器运行在 localhost:8775
[ ] 数据集已创建
[ ] 环境变量配置完成（.env）
```

---

## 💡 性能优化建议

### 减少内存使用
```yaml
# 修改 configs/practice/korgym_practice.yaml
rollout_concurrency: 16  # 降低并发数
```

### 加快训练速度
```yaml
batch_size: 100  # 一个epoch完成
epochs: 1
```

### 提取更多经验
```yaml
l1_aggregation_threshold: 3  # 更快生成L1
l2_aggregation_threshold: 2  # 更快生成L2
```

---

📖 **完整文档**: `KORGym_Usage_Guide.md`  
🚀 **快速开始**: `KORGYM_QUICK_START.md`  
🐧 **WSL设置**: `KORGYM_WSL_SETUP.md`

