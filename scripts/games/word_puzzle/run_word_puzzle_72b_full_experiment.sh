#!/bin/bash
# Word Puzzle - Qwen2.5-72B-Instruct 完整实验流程
# 包括：数据集创建、基线评估、GRPO训练、学习后评估

set -e  # 遇到错误立即退出

# 配置
GAME_NAME="8-word_puzzle"
GAME_PORT=8765
TRAIN_SIZE=100
EVAL_SIZE=120
MODEL="Qwen2.5-72B-Instruct"

echo "================================================================================"
echo "Word Puzzle - ${MODEL} 完整实验"
echo "================================================================================"
echo "游戏: ${GAME_NAME}"
echo "端口: ${GAME_PORT}"
echo "训练集: ${TRAIN_SIZE} 题"
echo "测试集: ${EVAL_SIZE} 题"
echo "================================================================================"
echo ""

# 检查是否在正确目录
if [ ! -f "scripts/run_training_free_GRPO.py" ]; then
    echo "错误: 请在项目根目录下运行此脚本"
    exit 1
fi

# 步骤1: 创建数据集
echo "[INFO] ================================================"
echo "[INFO] 步骤1：创建数据集"
echo "[INFO] ================================================"

echo "[INFO] 创建训练数据集（${TRAIN_SIZE}题）..."
uv run python scripts/init_korgym_dataset.py \
    --dataset "KORGym-WordPuzzle-Train-100" \
    --num_samples ${TRAIN_SIZE}

echo "[INFO] 创建评估数据集（${EVAL_SIZE}题）..."
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "KORGym-WordPuzzle-Eval-120" \
    --num_samples ${EVAL_SIZE}

echo ""
echo "[SUCCESS] ✓ 数据集创建完成"
echo ""

# 步骤2: 基线评估
echo "[INFO] ================================================"
echo "[INFO] 步骤2：基线评估（未学习经验）"
echo "[INFO] ================================================"

echo "[INFO] 确保游戏服务器在运行..."
echo "[INFO] 如果没有，请在另一个终端运行："
echo "[INFO]   cd KORGym/game_lib/8-word_puzzle"
echo "[INFO]   python game_lib.py --port ${GAME_PORT}"
echo ""
echo "[INFO] 按Enter继续，或Ctrl+C取消..."
read

echo "[INFO] 运行基线评估..."
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config practice/word_puzzle_qwen72b_agent \
    --dataset_name "KORGym-WordPuzzle-Eval-120" \
    --exp_id word_puzzle_qwen72b_baseline \
    --game_port ${GAME_PORT}

echo ""
echo "[SUCCESS] ✓ 基线评估完成"
echo "[INFO] 查看结果: workspace/korgym_eval/word_puzzle_qwen72b_baseline.json"
echo ""

# 显示基线结果
if [ -f "workspace/korgym_eval/word_puzzle_qwen72b_baseline.json" ]; then
    echo "[INFO] 基线评估结果："
    python -c "
import json
data = json.load(open('workspace/korgym_eval/word_puzzle_qwen72b_baseline.json'))
print(f\"  平均分: {data.get('average_score', data.get('avg_score', 0)):.4f}\")
print(f\"  成功率: {data.get('success_rate', 0):.4f}\")
print(f\"  标准差: {data.get('std_score', 0):.4f}\")
"
    echo ""
fi

# 步骤3: GRPO训练
echo "[INFO] ================================================"
echo "[INFO] 步骤3：GRPO训练（${TRAIN_SIZE}题，2 epochs）"
echo "[INFO] ================================================"

echo "[INFO] 开始训练..."
uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_qwen72b_grpo

echo ""
echo "[SUCCESS] ✓ GRPO训练完成"
echo ""

# 查找生成的agent配置文件
ENHANCED_AGENT=$(find configs/agents/practice -name "word_puzzle_qwen72b_*_agent.yaml" -type f | sort -r | head -1)

if [ -z "$ENHANCED_AGENT" ]; then
    echo "[ERROR] 未找到训练后的agent配置文件！"
    exit 1
fi

ENHANCED_AGENT_NAME=$(basename "$ENHANCED_AGENT" .yaml)
echo "[INFO] 找到增强agent: ${ENHANCED_AGENT_NAME}"
echo ""

# 步骤4: 学习后评估
echo "[INFO] ================================================"
echo "[INFO] 步骤4：学习后评估（使用经验）"
echo "[INFO] ================================================"

echo "[INFO] 运行增强评估..."
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config "practice/${ENHANCED_AGENT_NAME}" \
    --dataset_name "KORGym-WordPuzzle-Eval-120" \
    --exp_id word_puzzle_qwen72b_enhanced \
    --game_port ${GAME_PORT}

echo ""
echo "[SUCCESS] ✓ 学习后评估完成"
echo "[INFO] 查看结果: workspace/korgym_eval/word_puzzle_qwen72b_enhanced.json"
echo ""

# 显示增强结果
if [ -f "workspace/korgym_eval/word_puzzle_qwen72b_enhanced.json" ]; then
    echo "[INFO] 学习后评估结果："
    python -c "
import json
data = json.load(open('workspace/korgym_eval/word_puzzle_qwen72b_enhanced.json'))
print(f\"  平均分: {data.get('average_score', data.get('avg_score', 0)):.4f}\")
print(f\"  成功率: {data.get('success_rate', 0):.4f}\")
print(f\"  标准差: {data.get('std_score', 0):.4f}\")
"
    echo ""
fi

# 步骤5: 结果对比
echo "[INFO] ================================================"
echo "[INFO] 步骤5：结果对比"
echo "[INFO] ================================================"

python scripts/compare_korgym_scores.py \
    workspace/korgym_eval/word_puzzle_qwen72b_baseline.json \
    workspace/korgym_eval/word_puzzle_qwen72b_enhanced.json

echo ""
echo "================================================================================"
echo "✅ Word Puzzle - ${MODEL} 实验全部完成！"
echo "================================================================================"
echo ""
echo "结果文件："
echo "  - 基线: workspace/korgym_eval/word_puzzle_qwen72b_baseline.json"
echo "  - 增强: workspace/korgym_eval/word_puzzle_qwen72b_enhanced.json"
echo "  - Agent: ${ENHANCED_AGENT}"
echo ""
echo "================================================================================"


