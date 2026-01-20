#!/bin/bash
# 重启 KORGym Word Puzzle 训练（Temperature 1.0）

set -e

cd "$(dirname "$0")/.."

echo "🧹 Cleaning old data..."
uv run python scripts/cleanup_korgym_temp_data.py

echo ""
echo "📊 Reinitializing datasets..."
uv run python scripts/init_korgym_dataset.py \
    --dataset KORGym-WordPuzzle-Qwen-Temp1-Train \
    --num_samples 50

uv run python scripts/init_korgym_dataset.py \
    --dataset KORGym-WordPuzzle-Qwen-Temp1-Eval \
    --num_samples 50

echo ""
echo "🚀 Starting training..."
uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_qwen_temp1_simple

echo ""
echo "✅ Training completed!"











