# KORGym分层经验学习完整使用指南 🎮

本指南提供KORGym游戏集成到youtu-agent框架的完整配置和运行步骤。

## 📋 概述

- **评估数据集**: 50题 (seeds 1-50)
- **训练数据集**: 100题 (seeds 51-150)
- **学习方式**: 分层经验学习 (L0 → L1 → L2)
- **游戏选择**: 8-word_puzzle (可修改为其他KORGym游戏)

## 🗂️ 创建的配置文件

### 1. 验证函数
- `utu/practice/verify/korgym.py` - KORGym游戏结果验证函数

### 2. Agent配置
- `configs/agents/practice/korgym_agent.yaml` - 基础Agent配置
- `configs/agents/practice/korgym_practice_agent.yaml` - 学习后生成的增强Agent配置（自动生成）

### 3. 评估配置
- `configs/eval/korgym/korgym_eval.yaml` - 基线评估配置
- `configs/eval/korgym/korgym_practice_eval.yaml` - 学习后评估配置

### 4. 训练配置
- `configs/practice/korgym_practice.yaml` - 训练配置

## 🚀 完整运行流程 (WSL环境)

### 步骤 0: 环境准备

```bash
# 1. 确保已安装依赖
cd /mnt/f/youtu-agent  # 根据你的WSL路径调整
uv sync --all-extras
source .venv/bin/activate

# 2. 配置环境变量 (.env文件)
# 确保设置了LLM API密钥
cat > .env << 'EOF'
# LLM Configuration
LLM_TYPE=chat.completions
LLM_MODEL=Qwen/Qwen3-14B  # 或其他模型
LLM_BASE_URL=your_base_url
LLM_API_KEY=your_api_key

# Optional: Phoenix Tracing
PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
PHOENIX_PROJECT_NAME=Youtu-Agent-KORGym
EOF

# 3. (可选) 启动Phoenix监控
pip install arize-phoenix
nohup phoenix serve > phoenix.log 2>&1 &
```

### 步骤 1: 启动KORGym游戏服务器

```bash
# 在新的终端窗口中启动游戏服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# 保持此终端运行，不要关闭
# 你应该看到类似信息: "Server running at http://localhost:8775"
```

### 步骤 2: 准备数据集

```bash
# 在另一个终端中，返回项目根目录
cd /mnt/f/youtu-agent

# 创建数据上传脚本
cat > scripts/data/prepare_korgym_data.py << 'EOF'
"""
Prepare KORGym datasets for training and evaluation.
"""
import asyncio
from utu.db import DatasetSample, db_manager

async def create_korgym_datasets():
    """Create training and evaluation datasets for KORGym."""
    
    # Evaluation dataset: seeds 1-50
    eval_samples = []
    for seed in range(1, 51):
        sample = DatasetSample(
            dataset="KORGym-Eval-50",
            source="training_free_grpo",
            question=f"Play KORGym game with seed {seed}",
            answer="success",  # Expected outcome
            metadata={
                "seed": seed,
                "game_name": "8-word_puzzle",
                "dataset_type": "eval"
            }
        )
        eval_samples.append(sample)
    
    # Training dataset: seeds 51-150
    train_samples = []
    for seed in range(51, 151):
        sample = DatasetSample(
            dataset="KORGym-Train-100",
            source="training_free_grpo",
            question=f"Play KORGym game with seed {seed}",
            answer="success",
            metadata={
                "seed": seed,
                "game_name": "8-word_puzzle",
                "dataset_type": "train"
            }
        )
        train_samples.append(sample)
    
    # Upload to database
    print(f"Uploading {len(eval_samples)} evaluation samples...")
    await db_manager.upsert_dataset_samples(eval_samples)
    print(f"✓ Evaluation dataset created: KORGym-Eval-50")
    
    print(f"Uploading {len(train_samples)} training samples...")
    await db_manager.upsert_dataset_samples(train_samples)
    print(f"✓ Training dataset created: KORGym-Train-100")
    
    print("\n📊 Dataset Summary:")
    print(f"  - Evaluation: 50 samples (seeds 1-50)")
    print(f"  - Training: 100 samples (seeds 51-150)")

if __name__ == "__main__":
    asyncio.run(create_korgym_datasets())
EOF

# 运行数据准备脚本
uv run python scripts/data/prepare_korgym_data.py
```

### 步骤 3: 基线评估

```bash
# 评估未经训练的基础Agent
uv run python scripts/run_eval.py \
  --config_name korgym/korgym_eval

# 查看评估结果
# 结果会保存在 workspace/korgym_baseline_eval/ 目录
```

### 步骤 4: 运行分层经验学习训练

```bash
# 运行Training-Free GRPO训练
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym_practice

# 训练过程说明:
# - Epoch 1, Batch 1: 50个游戏 (seeds 51-100)
# - Epoch 1, Batch 2: 50个游戏 (seeds 101-150)
# - 自动提取L0经验，聚合为L1和L2
# - 生成增强的Agent配置

# 训练输出:
# 1. 经验库: workspace/hierarchical_experiences/korgym_practice.json
# 2. 增强Agent: configs/agents/practice/korgym_practice_agent.yaml

# 如果需要完全重新开始训练（清除缓存）:
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym_practice \
  --restart_step 0
```

### 步骤 5: 评估增强后的Agent

```bash
# 使用学习后的Agent进行评估（使用相同的eval数据集）
uv run python scripts/run_eval.py \
  --config_name korgym/korgym_practice_eval

# 查看评估结果
# 结果会保存在 workspace/korgym_practice_eval/ 目录
```

### 步骤 6: 对比结果

```bash
# 对比基线和学习后的性能
cat > scripts/compare_results.py << 'EOF'
"""Compare baseline and practice evaluation results."""
import json
from pathlib import Path

def load_results(exp_id):
    """Load evaluation results."""
    result_file = Path(f"workspace/{exp_id}/score.txt")
    if result_file.exists():
        with open(result_file, 'r') as f:
            content = f.read()
            # Parse success rate from score.txt
            for line in content.split('\n'):
                if 'accuracy' in line.lower() or 'success' in line.lower():
                    return line
    return "Results not found"

print("=" * 60)
print("KORGym Evaluation Results Comparison")
print("=" * 60)
print("\n📊 Baseline (before training):")
print(load_results("korgym_baseline_eval"))
print("\n🎯 After Practice (with hierarchical learning):")
print(load_results("korgym_practice_eval"))
print("\n" + "=" * 60)
EOF

uv run python scripts/compare_results.py
```

## 🎮 切换到其他KORGym游戏

如果想使用其他游戏（如2048），修改以下配置：

### 修改训练配置

编辑 `configs/practice/korgym_practice.yaml`:

```yaml
korgym:
  game_name: "3-2048"  # 改为目标游戏
  game_port: 8776      # 使用不同端口
  level: 4             # 调整难度
```

### 修改评估配置

编辑 `configs/eval/korgym/korgym_eval.yaml` 和 `configs/eval/korgym/korgym_practice_eval.yaml`:

```yaml
korgym:
  game_port: 8776  # 使用相同端口
```

### 更新数据集

修改 `scripts/data/prepare_korgym_data.py` 中的 `game_name` 字段。

### 启动对应的游戏服务器

```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/3-2048
python game_lib.py -p 8776
```

## 📊 支持的KORGym游戏

### 推荐的起始游戏

| 游戏名称 | 游戏ID | 类别 | 难度 | 推荐理由 |
|---------|--------|------|------|---------|
| Word Puzzle | 8-word_puzzle | Puzzle | 中等 | 规则清晰，适合测试 |
| 2048 | 3-2048 | Strategic | 中等 | 经典策略游戏 |
| Wordle | 33-wordle | Puzzle | 简单 | 多轮交互，适合学习 |
| Sudoku | 4-SudoKu | Math-Logic | 中等 | 逻辑推理 |
| Tower of Hanoi | 30-Tower_of_Hanoi | Spatial | 简单 | 经典问题 |

### 游戏分类

- **Math & Logic**: 1-DateCount, 4-SudoKu, 16-jiafa, 32-numeral_bricks
- **Puzzle**: 2-GuessWord, 8-word_puzzle, 33-wordle, 36-CryptoWord
- **Strategic**: 3-2048, 24-snake, 25-Tetris, 27-NpointPlus
- **Spatial**: 30-Tower_of_Hanoi, 31-ball_arrange
- **Control**: 10-minigrid, 11-maze, 12-sokoban

## 🔍 监控和调试

### 查看训练日志

```bash
# Phoenix UI (如果启用)
# 浏览器打开: http://localhost:6006

# 查看经验提取结果
cat workspace/hierarchical_experiences/korgym_practice.json | jq '.stats'

# 查看生成的Agent配置
cat configs/agents/practice/korgym_practice_agent.yaml
```

### 故障排查

#### 问题1: 游戏服务器连接失败

```bash
# 检查服务器是否运行
curl http://localhost:8775/docs

# 重启游戏服务器
cd KORGym/game_lib/8-word_puzzle
pkill -f "game_lib.py"
python game_lib.py -p 8775
```

#### 问题2: 评估或训练超时

修改配置文件中的超时设置:

```yaml
practice:
  task_timeout: 1200  # 增加到20分钟

korgym:
  timeout_per_game: 1200
```

#### 问题3: LLM调用失败

```bash
# 检查环境变量
echo $LLM_API_KEY

# 测试LLM连接
uv run python -c "from utu.utils import SimplifiedAsyncOpenAI; import asyncio; asyncio.run(SimplifiedAsyncOpenAI(type='chat.completions', model='Qwen/Qwen3-14B').generate('test'))"
```

## 📈 预期结果

根据分层经验学习的设计，预期提升：

- **基线准确率**: 30-50% (取决于游戏和模型)
- **训练后准确率**: 40-65% (预期提升10-15%)
- **经验数量**: 
  - ~100 L0经验 (每个游戏1个)
  - ~20 L1经验 (每5个L0聚合1个)
  - ~6-7 L2经验 (每3个L1聚合1个)

## 🎯 高级配置

### 调整分层学习参数

编辑 `configs/practice/korgym_practice.yaml`:

```yaml
hierarchical_learning:
  l1_aggregation_threshold: 5  # 改为3可以更快生成L1
  l2_aggregation_threshold: 3  # 改为2可以更快生成L2
  max_l0_recent: 50           # 增加可包含更多L0经验
```

### 调整GRPO参数

```yaml
practice:
  grpo_n: 3              # 每个问题生成3个rollout
  batch_size: 50         # 每批处理50个样本
  rollout_temperature: 0.7  # 增加温度以获得更多样化的经验
```

## 📚 参考文档

- [Training-Free GRPO原理](utu/practice/README.md)
- [KORGym经验总结机制](KORGym经验总结机制详解.md)
- [KORGym集成指南](KORGym集成指南.md)
- [分层经验学习适配方案](KORGym分层经验学习适配方案.md)

## ✅ 检查清单

- [ ] 环境变量配置完成 (.env文件)
- [ ] KORGym游戏服务器运行中
- [ ] 数据集创建成功 (KORGym-Eval-50, KORGym-Train-100)
- [ ] 基线评估完成
- [ ] 训练完成并生成增强Agent
- [ ] 学习后评估完成
- [ ] 结果对比分析

---

🎮 开始你的KORGym分层经验学习之旅！

如遇到问题，请查看日志文件或参考故障排查部分。

