#!/bin/bash

# Evaluate KORGym agent using dataset-based approach
# Usage: bash scripts/eval_with_dataset.sh

set -e

# Configuration
DATASET_NAME="KORGym-WordPuzzle-Eval-50"
NUM_SAMPLES=50
AGENT_BASELINE="practice/word_puzzle_qwen_temp1"
AGENT_ENHANCED="practice/word_puzzle_qwen_temp1_hierarchical_agent"
OUTPUT_DIR="workspace/korgym_eval"

echo "=========================================="
echo "KORGym Dataset-Based Evaluation"
echo "=========================================="
echo ""

# Step 1: Create evaluation dataset
echo "📊 Step 1: Creating evaluation dataset..."
uv run python scripts/init_korgym_eval_dataset.py \
    --dataset_name "$DATASET_NAME" \
    --num_samples $NUM_SAMPLES

echo ""
echo "✓ Dataset created"
echo ""

# Step 2: Evaluate baseline agent
echo "🎯 Step 2: Evaluating baseline agent..."
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config "$AGENT_BASELINE" \
    --dataset_name "$DATASET_NAME" \
    --exp_id "qwen_temp1_baseline_dataset_50" \
    --output_dir "$OUTPUT_DIR"

echo ""
echo "✓ Baseline evaluation completed"
echo ""

# Step 3: Evaluate enhanced agent (with experiences)
echo "🚀 Step 3: Evaluating enhanced agent..."
uv run python scripts/eval_korgym_with_dataset.py \
    --agent_config "$AGENT_ENHANCED" \
    --dataset_name "$DATASET_NAME" \
    --exp_id "qwen_temp1_enhanced_dataset_50" \
    --output_dir "$OUTPUT_DIR"

echo ""
echo "✓ Enhanced evaluation completed"
echo ""

# Step 4: Compare results
echo "📈 Step 4: Comparing results..."
python scripts/compare_paper_scores.py \
    "$OUTPUT_DIR/qwen_temp1_baseline_dataset_50.json" \
    "$OUTPUT_DIR/qwen_temp1_enhanced_dataset_50.json"

echo ""
echo "=========================================="
echo "✅ Evaluation complete!"
echo "=========================================="
echo ""
echo "Results saved to: $OUTPUT_DIR"











