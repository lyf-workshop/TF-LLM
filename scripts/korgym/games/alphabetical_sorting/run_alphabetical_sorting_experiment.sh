#!/bin/bash
# Alphabetical Sorting 完整实验流程
# 使用前请确保 KORGym 服务器已在 8775 端口运行

set -e  # 遇到错误立即退出

echo "========================================"
echo "Alphabetical Sorting 完整实验流程"
echo "========================================"
echo ""

# 切换到项目目录
cd /mnt/f/youtu-agent

echo "步骤 1/5: 准备数据集..."
echo "----------------------------------------"

# 创建训练数据集
echo "创建 100 局训练数据集..."
uv run python scripts/init_korgym_dataset.py \
    --dataset "KORGym-AlphabeticalSorting-Train-100" \
    --num_samples 100

# 创建评估数据集
echo "创建 120 局评估数据集..."
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-120" \
    --num_samples 120

echo ""
echo "步骤 2/5: 基线评估（无经验）..."
echo "----------------------------------------"
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_temp1 \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-120" \
    --exp_id alphabetical_sorting_baseline_120 \
    --game_port 8775

echo ""
echo "步骤 3/5: 训练（学习分层经验）..."
echo "----------------------------------------"
echo "预计时间：15-20 分钟"
uv run python scripts/run_training_free_GRPO.py \
    --config_name alphabetical_sorting_qwen_100

echo ""
echo "步骤 4/5: 增强版评估（使用学到的经验）..."
echo "----------------------------------------"
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_100_agent \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-120" \
    --exp_id alphabetical_sorting_enhanced_120 \
    --game_port 8775

echo ""
echo "步骤 5/5: 对比结果..."
echo "----------------------------------------"
python scripts/compare_korgym_scores.py \
    workspace/korgym_eval/alphabetical_sorting_baseline_120.json \
    workspace/korgym_eval/alphabetical_sorting_enhanced_120.json

echo ""
echo "========================================"
echo "✅ 实验完成！"
echo "========================================"
echo ""
echo "结果文件："
echo "  - 基线: workspace/korgym_eval/alphabetical_sorting_baseline_120.json"
echo "  - 增强: workspace/korgym_eval/alphabetical_sorting_enhanced_120.json"
echo "  - 经验: workspace/hierarchical_experiences/alphabetical_sorting_100.json"
echo "  - Agent: configs/agents/practice/alphabetical_sorting_qwen_100_agent.yaml"








