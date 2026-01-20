#!/bin/bash
# 完全清理 Alphabetical Sorting 实验数据并重新开始
# 使用优化的agent配置

set -e

echo "========================================"
echo "清理 Alphabetical Sorting 实验数据"
echo "========================================"
echo ""

cd /mnt/f/youtu-agent

echo "步骤 1/4: 清理数据库中的数据集..."
echo "----------------------------------------"

# 清理数据库中的 Alphabetical Sorting 相关数据
uv run python scripts/cleanup_korgym_temp_data.py \
    --dataset_prefix "KORGym-AlphabeticalSorting" || echo "  数据库清理完成（或没有数据需要清理）"

echo ""
echo "步骤 2/4: 清理评估结果..."
echo "----------------------------------------"

# 删除评估结果文件
rm -f workspace/korgym_eval/alphabetical_sorting_*.json
echo "  ✓ 评估结果已清理"

echo ""
echo "步骤 3/4: 清理经验和agent文件..."
echo "----------------------------------------"

# 删除经验文件
rm -f workspace/hierarchical_experiences/alphabetical_sorting*.json
echo "  ✓ 经验文件已清理"

# 删除生成的agent配置
rm -f configs/agents/practice/alphabetical_sorting_qwen_*_agent.yaml
rm -f configs/agents/practice/alphabetical_sorting_enhanced_*_agent.yaml
echo "  ✓ Agent文件已清理"

# 删除workspace中的agents
rm -rf workspace/agents/alphabetical_sorting*
echo "  ✓ Workspace agents已清理"

echo ""
echo "步骤 4/4: 创建新的数据集..."
echo "----------------------------------------"

# 创建训练数据集（100局）
echo "创建 100 局训练数据集..."
uv run python scripts/init_korgym_dataset.py \
    --dataset "KORGym-AlphabeticalSorting-Train-100" \
    --num_samples 100

# 创建评估数据集（120局）
echo "创建 120 局评估数据集..."
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-120" \
    --num_samples 120

echo ""
echo "========================================"
echo "✅ 清理完成！数据集已准备好"
echo "========================================"
echo ""
echo "数据集信息："
echo "  - 训练集: KORGym-AlphabeticalSorting-Train-100 (100局)"
echo "  - 评估集: KORGym-AlphabeticalSorting-Eval-120 (120局)"
echo ""
echo "下一步："
echo "1. 确保游戏服务器在运行："
echo "   cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting"
echo "   python game_lib.py --port 8775"
echo ""
echo "2. 运行完整实验："
echo "   bash scripts/run_alphabetical_sorting_full_experiment.sh"








