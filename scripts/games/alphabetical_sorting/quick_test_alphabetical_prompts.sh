#!/bin/bash
# 快速测试不同prompt版本的效果
# 使用5局游戏快速对比

set -e

echo "========================================"
echo "快速测试 Alphabetical Sorting Prompts"
echo "========================================"
echo ""

cd /mnt/f/youtu-agent

# 创建5局测试集
echo "创建 5 局测试数据集..."
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-AlphabeticalSorting-Test-5" \
    --num_samples 5

echo ""
echo "========================================"
echo "测试 1/2: 官方风格简洁prompt"
echo "========================================"

uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_simple \
    --dataset_name "KORGym-AlphabeticalSorting-Test-5" \
    --exp_id test_simple_prompt \
    --game_port 8775

echo ""
echo "简洁prompt结果："
cat workspace/korgym_eval/test_simple_prompt.json | python -c "
import json, sys
data = json.load(sys.stdin)
print(f\"  平均分: {data['average_score']:.4f} ({data['average_score']*100:.2f}%)\")
print(f\"  成功率: {data['success_rate']:.4f} ({data['success_rate']*100:.2f}%)\")
"

echo ""
echo "========================================"
echo "测试 2/2: 详细增强prompt"
echo "========================================"

uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/alphabetical_sorting_qwen_enhanced \
    --dataset_name "KORGym-AlphabeticalSorting-Test-5" \
    --exp_id test_enhanced_prompt \
    --game_port 8775

echo ""
echo "详细prompt结果："
cat workspace/korgym_eval/test_enhanced_prompt.json | python -c "
import json, sys
data = json.load(sys.stdin)
print(f\"  平均分: {data['average_score']:.4f} ({data['average_score']*100:.2f}%)\")
print(f\"  成功率: {data['success_rate']:.4f} ({data['success_rate']*100:.2f}%)\")
"

echo ""
echo "========================================"
echo "对比结果"
echo "========================================"

python scripts/compare_korgym_scores.py \
    workspace/korgym_eval/test_simple_prompt.json \
    workspace/korgym_eval/test_enhanced_prompt.json

echo ""
echo "提示："
echo "  - 如果简洁版接近论文14%，使用简洁版"
echo "  - 如果详细版明显更好，使用详细版"
echo "  - 建议：基于结果选择，然后运行完整实验"







