#!/bin/bash
# Alphabetical Sorting 完整实验流程 - 使用优化配置
# 确保游戏服务器已在 8775 端口运行

set -e

echo "========================================"
echo "Alphabetical Sorting 完整实验"
echo "基于官方prompt的简洁版配置"
echo "========================================"
echo ""

cd /mnt/f/youtu-agent

# 检查数据集是否存在
echo "检查数据集..."
if ! uv run python -c "
from utu.utils import SQLModelUtils
from utu.db import DatasetSample
from sqlmodel import select

with SQLModelUtils.create_session() as session:
    train_count = len(session.exec(select(DatasetSample).where(DatasetSample.dataset == 'KORGym-AlphabeticalSorting-Train-100')).all())
    eval_count = len(session.exec(select(DatasetSample).where(DatasetSample.dataset == 'KORGym-AlphabeticalSorting-Eval-120')).all())
    
    if train_count != 100:
        raise ValueError(f'训练集应有100局，实际有{train_count}局')
    if eval_count != 120:
        raise ValueError(f'评估集应有120局，实际有{eval_count}局')
    
    print(f'✓ 训练集: {train_count} 局')
    print(f'✓ 评估集: {eval_count} 局')
"; then
    echo "❌ 数据集检查失败！请先运行清理脚本："
    echo "   bash scripts/clean_and_restart_alphabetical_sorting.sh"
    exit 1
fi

echo ""
echo "========================================"
echo "第 1/3 步: 基线评估（简洁prompt）"
echo "========================================"
echo "预计时间: ~20 分钟"
echo ""

uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_simple \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-120" \
    --exp_id alphabetical_sorting_baseline_simple \
    --game_port 8775

echo ""
echo "基线评估完成！查看结果："
cat workspace/korgym_eval/alphabetical_sorting_baseline_simple.json | python -c "
import json, sys
data = json.load(sys.stdin)
print(f\"  平均分: {data['average_score']:.4f} ({data['average_score']*100:.2f}%)\")
print(f\"  成功率: {data['success_rate']:.4f} ({data['success_rate']*100:.2f}%)\")
print(f\"  标准差: {data['std_score']:.4f}\")
print(f\"  最高分: {data['max_score']:.4f}\")
"

echo ""
echo "========================================"
echo "第 2/3 步: 训练（学习分层经验）"
echo "========================================"
echo "配置: 2轮 × 50局 = 100局训练"
echo "预计时间: ~15 分钟"
echo ""

uv run python scripts/run_training_free_GRPO.py \
    --config_name alphabetical_sorting_qwen_simple_100

echo ""
echo "训练完成！经验已保存到："
echo "  workspace/hierarchical_experiences/alphabetical_sorting_simple_100.json"

echo ""
echo "========================================"
echo "第 3/3 步: 增强版评估"
echo "========================================"
echo "预计时间: ~20 分钟"
echo ""

uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_simple_100_agent \
    --dataset_name "KORGym-AlphabeticalSorting-Eval-120" \
    --exp_id alphabetical_sorting_enhanced_simple \
    --game_port 8775

echo ""
echo "========================================"
echo "实验完成！正在对比结果..."
echo "========================================"
echo ""

python scripts/compare_korgym_scores.py \
    workspace/korgym_eval/alphabetical_sorting_baseline_simple.json \
    workspace/korgym_eval/alphabetical_sorting_enhanced_simple.json

echo ""
echo "========================================"
echo "✅ 完整实验已完成！"
echo "========================================"
echo ""
echo "结果文件："
echo "  - 基线: workspace/korgym_eval/alphabetical_sorting_baseline_simple.json"
echo "  - 增强: workspace/korgym_eval/alphabetical_sorting_enhanced_simple.json"
echo "  - 经验: workspace/hierarchical_experiences/alphabetical_sorting_simple_100.json"
echo "  - Agent: configs/agents/practice/alphabetical_sorting_simple_100_agent.yaml"
echo ""
echo "预期结果（简洁prompt版本）："
echo "  - 基线分数: 接近论文的14%"
echo "  - 增强分数: 经验学习后的提升"
echo "  - 对比论文: 验证经验学习的效果"


