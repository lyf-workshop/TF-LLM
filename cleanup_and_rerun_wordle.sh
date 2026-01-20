#!/bin/bash
# Wordle 清理并重新运行脚本

set -e

cd /mnt/f/youtu-agent
source .venv/bin/activate

echo "=========================================="
echo "Wordle - 清理并重新运行"
echo "=========================================="
echo ""

# 步骤1: 清理旧实验数据
echo "🗑️  步骤1: 清理旧实验数据..."
uv run python scripts/clean_experiment_data.py --exp_id \
  wordle_baseline_eval \
  wordle_practice_eval \
  wordle_practice

echo ""
echo "✓ 旧实验数据已清理"
echo ""

# 步骤2: 检查游戏服务器
echo "🔍 步骤2: 检查游戏服务器..."
if curl -s http://localhost:8777/docs > /dev/null 2>&1; then
    echo "✓ 游戏服务器正在运行 (端口 8777)"
else
    echo "❌ 游戏服务器未运行！"
    echo ""
    echo "请在另一个终端启动游戏服务器："
    echo "  cd /mnt/f/youtu-agent/KORGym/game_lib/33-wordle"
    echo "  python game_lib.py -p 8777"
    echo ""
    exit 1
fi
echo ""

# 步骤3: 准备数据集
echo "📊 步骤3: 准备数据集..."
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
echo ""

# 步骤4: 基线评估
echo "📈 步骤4: 运行基线评估..."
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
echo ""

# 步骤5: 训练
echo "🎓 步骤5: 运行训练..."
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
echo ""

# 步骤6: 训练后评估
echo "📈 步骤6: 运行训练后评估..."
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
echo ""

# 步骤7: 显示结果
echo "=========================================="
echo "📊 结果对比"
echo "=========================================="
echo ""
echo "--- 基线结果 ---"
cat workspace/wordle_baseline_eval/score.txt 2>/dev/null || echo "未找到结果文件"
echo ""
echo "--- 训练后结果 ---"
cat workspace/wordle_practice_eval/score.txt 2>/dev/null || echo "未找到结果文件"
echo ""
echo "--- 经验统计 ---"
if [ -f "workspace/hierarchical_experiences/wordle_practice.json" ]; then
    python3 -c "
import json
with open('workspace/hierarchical_experiences/wordle_practice.json', 'r') as f:
    data = json.load(f)
    stats = data.get('stats', {})
    print(f\"  L0经验: {stats.get('total_l0', 0)} 个\")
    print(f\"  L1经验: {stats.get('total_l1', 0)} 个\")
    print(f\"  L2经验: {stats.get('total_l2', 0)} 个\")
"
else
    echo "未找到经验文件"
fi
echo ""
echo "=========================================="
echo "✅ Wordle 流程完成！"
echo "=========================================="

