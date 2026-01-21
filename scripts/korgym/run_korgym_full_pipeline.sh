#!/bin/bash
# KORGym Full Pipeline Script
# This script runs the complete pipeline: data preparation → baseline eval → training → practice eval

set -e  # Exit on error

echo "=========================================="
echo "KORGym Hierarchical Learning Pipeline"
echo "=========================================="
echo ""

# Configuration
GAME_NAME="${GAME_NAME:-8-word_puzzle}"
GAME_PORT="${GAME_PORT:-8775}"
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$PROJECT_ROOT"

# Step 1: Check if game server is running
echo "📡 Step 1: Checking game server..."
if ! curl -s http://localhost:${GAME_PORT}/docs > /dev/null 2>&1; then
    echo "❌ Game server is not running on port ${GAME_PORT}"
    echo "Please start the game server first:"
    echo "  cd KORGym/game_lib/${GAME_NAME}"
    echo "  python game_lib.py -p ${GAME_PORT}"
    exit 1
fi
echo "✓ Game server is running"
echo ""

# Step 2: Prepare datasets
echo "📊 Step 2: Preparing datasets..."
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "${GAME_NAME}"
echo ""

# Step 3: Baseline evaluation
echo "📈 Step 3: Running baseline evaluation..."
echo "This will evaluate the agent without any training..."
uv run python scripts/run_eval.py \
    --config_name korgym/korgym_eval
echo ""

# Step 4: Training with hierarchical learning
echo "🎓 Step 4: Running hierarchical learning training..."
echo "This will train the agent and extract L0/L1/L2 experiences..."
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym_practice
echo ""

# Step 5: Practice evaluation
echo "📈 Step 5: Running practice evaluation..."
echo "This will evaluate the agent after training..."
uv run python scripts/run_eval.py \
    --config_name korgym/korgym_practice_eval
echo ""

# Step 6: Compare results
echo "📊 Step 6: Comparing results..."
echo "=========================================="
echo "BASELINE RESULTS:"
echo "=========================================="
if [ -f "workspace/korgym_baseline_eval/score.txt" ]; then
    cat workspace/korgym_baseline_eval/score.txt
else
    echo "Baseline results not found"
fi
echo ""
echo "=========================================="
echo "PRACTICE RESULTS (After Training):"
echo "=========================================="
if [ -f "workspace/korgym_practice_eval/score.txt" ]; then
    cat workspace/korgym_practice_eval/score.txt
else
    echo "Practice results not found"
fi
echo ""

# Step 7: Show experience statistics
echo "=========================================="
echo "EXTRACTED EXPERIENCES:"
echo "=========================================="
if [ -f "workspace/hierarchical_experiences/korgym_practice.json" ]; then
    python -c "
import json
with open('workspace/hierarchical_experiences/korgym_practice.json', 'r') as f:
    data = json.load(f)
    stats = data.get('stats', {})
    print(f\"  - L0 (Case-level) experiences: {stats.get('total_l0', 0)}\")
    print(f\"  - L1 (Pattern-level) experiences: {stats.get('total_l1', 0)}\")
    print(f\"  - L2 (Meta-level) experiences: {stats.get('total_l2', 0)}\")
"
else
    echo "Experience file not found"
fi
echo ""

echo "=========================================="
echo "✅ Pipeline completed successfully!"
echo "=========================================="
echo ""
echo "Generated files:"
echo "  - Experience database: workspace/hierarchical_experiences/korgym_practice.json"
echo "  - Enhanced agent config: configs/agents/practice/korgym_practice_agent.yaml"
echo "  - Baseline results: workspace/korgym_baseline_eval/"
echo "  - Practice results: workspace/korgym_practice_eval/"
echo ""

