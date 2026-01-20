#!/bin/bash
# 快速测试 Qwen 优化配置
# 目标：从 0.028 提升到 0.040+ (论文水平)

set -e
cd /mnt/f/youtu-agent

echo "======================================================================"
echo "  Testing Qwen2.5-7B Optimizations"
echo "======================================================================"
echo ""
echo "目标: 从 0.028 提升到 0.040+ (论文水平)"
echo ""

# ============================================================================
# Step 1: 启动游戏服务器
# ============================================================================
echo "Step 1/4: Checking game server..."
if curl -s http://localhost:8775/health > /dev/null 2>&1; then
    echo "✓ Server already running"
else
    echo "Starting server..."
    uv run python scripts/start_korgym_server.py \
        --game_name 8-word_puzzle \
        --port 8775 \
        --level 4 > /dev/null 2>&1 &
    sleep 5
    
    if curl -s http://localhost:8775/health > /dev/null 2>&1; then
        echo "✓ Server started"
    else
        echo "✗ Failed to start server"
        exit 1
    fi
fi
echo ""

# ============================================================================
# Step 2: 测试标准优化 (Temperature 0.3)
# ============================================================================
echo "Step 2/4: Testing standard optimization (20 games, ~8 minutes)..."
echo "  Config: word_puzzle_qwen_optimized"
echo "  Temperature: 0.3 (降低自 0.7)"
echo "  Prompt: Enhanced"
echo ""

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config practice/word_puzzle_qwen_optimized \
    --exp_id qwen_optimized_test \
    --num_seeds 20 \
    --level 4

OPTIMIZED_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' workspace/korgym_paper_aligned/qwen_optimized_test_word_puzzle.json | head -1)
echo ""
echo "✓ Standard optimization completed: $OPTIMIZED_SCORE"
echo ""

# ============================================================================
# Step 3: 测试激进优化 (Temperature 0.1)
# ============================================================================
echo "Step 3/4: Testing ultra optimization (20 games, ~8 minutes)..."
echo "  Config: word_puzzle_qwen_ultra_optimized"
echo "  Temperature: 0.1 (极低)"
echo "  Prompt: Ultra-enhanced"
echo ""

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config practice/word_puzzle_qwen_ultra_optimized \
    --exp_id qwen_ultra_optimized_test \
    --num_seeds 20 \
    --level 4

ULTRA_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' workspace/korgym_paper_aligned/qwen_ultra_optimized_test_word_puzzle.json | head -1)
echo ""
echo "✓ Ultra optimization completed: $ULTRA_SCORE"
echo ""

# ============================================================================
# Step 4: 对比结果
# ============================================================================
echo "Step 4/4: Comparing all configurations..."
echo ""

python scripts/compare_paper_scores.py \
    workspace/korgym_paper_aligned/qwen_baseline_word_puzzle.json \
    workspace/korgym_paper_aligned/qwen_optimized_test_word_puzzle.json \
    workspace/korgym_paper_aligned/qwen_ultra_optimized_test_word_puzzle.json

# ============================================================================
# 总结
# ============================================================================
echo ""
echo "======================================================================"
echo "  Optimization Test Results"
echo "======================================================================"
echo ""

BASELINE_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' workspace/korgym_paper_aligned/qwen_baseline_word_puzzle.json | head -1)

echo "📊 Score Comparison:"
echo "  Original (temp=0.7):  $BASELINE_SCORE"
echo "  Optimized (temp=0.3): $OPTIMIZED_SCORE"
echo "  Ultra (temp=0.1):     $ULTRA_SCORE"
echo ""

# 计算提升
if [ -n "$BASELINE_SCORE" ] && [ -n "$OPTIMIZED_SCORE" ]; then
    IMPROVEMENT_OPT=$(python3 -c "print(f'{(float($OPTIMIZED_SCORE) / float($BASELINE_SCORE) - 1) * 100:.1f}%')")
    echo "  Standard improvement: $IMPROVEMENT_OPT"
fi

if [ -n "$BASELINE_SCORE" ] && [ -n "$ULTRA_SCORE" ]; then
    IMPROVEMENT_ULTRA=$(python3 -c "print(f'{(float($ULTRA_SCORE) / float($BASELINE_SCORE) - 1) * 100:.1f}%')")
    echo "  Ultra improvement:    $IMPROVEMENT_ULTRA"
fi

echo ""
echo "📖 Paper Target: 0.040 (4.0%)"
echo ""

# 推荐
if (( $(echo "$OPTIMIZED_SCORE > $ULTRA_SCORE" | bc -l) )); then
    BEST_CONFIG="word_puzzle_qwen_optimized"
    BEST_SCORE=$OPTIMIZED_SCORE
    BEST_NAME="Standard"
elif (( $(echo "$ULTRA_SCORE > $OPTIMIZED_SCORE" | bc -l) )); then
    BEST_CONFIG="word_puzzle_qwen_ultra_optimized"
    BEST_SCORE=$ULTRA_SCORE
    BEST_NAME="Ultra"
else
    BEST_CONFIG="word_puzzle_qwen_optimized"
    BEST_SCORE=$OPTIMIZED_SCORE
    BEST_NAME="Standard"
fi

echo "🏆 Best Configuration: $BEST_NAME ($BEST_CONFIG)"
echo "   Score: $BEST_SCORE"
echo ""

# 判断是否达到目标
if (( $(echo "$BEST_SCORE >= 0.040" | bc -l) )); then
    echo "✅ SUCCESS! Reached paper-level performance!"
    echo ""
    echo "Next steps:"
    echo "  1. Run full 50-game evaluation:"
    echo "     uv run python scripts/eval_word_puzzle_paper_aligned.py \\"
    echo "         --agent_config practice/$BEST_CONFIG \\"
    echo "         --exp_id qwen_baseline_final \\"
    echo "         --num_seeds 50 \\"
    echo "         --level 4"
    echo ""
    echo "  2. Start hierarchical training to reach 12-15%"
else
    echo "⚠️  Still below paper level (0.040)"
    echo ""
    echo "Suggestions:"
    echo "  - Try temperature 0.05"
    echo "  - Add few-shot examples"
    echo "  - Check API configuration"
    echo ""
    echo "Or proceed with training anyway - even 0.028 baseline"
    echo "can improve 3-4x through hierarchical learning!"
fi

echo ""
echo "======================================================================"











