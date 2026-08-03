#!/bin/bash
# ============================================================================
# Qwen2.5-7B-Instruct Word Puzzle 完整实验
# 与 KORGym 论文完全对齐（Level 4, 50 seeds）
# ============================================================================

set -e
cd /mnt/f/youtu-agent

echo "======================================================================"
echo "  Qwen2.5-7B-Instruct Word Puzzle Experiment (Paper Aligned)"
echo "======================================================================"
echo ""
echo "配置对齐："
echo "  - 游戏: Word Problem (8-word_puzzle)"
echo "  - 难度: Level 4"
echo "  - 局数: 50 seeds"
echo "  - 模型: Qwen2.5-7B-Instruct"
echo ""
echo "预计时间: 约 2.5-3 小时"
echo ""

# ============================================================================
# Step 1: 启动游戏服务器
# ============================================================================
echo "Step 1/5: Starting game server (Level 4)..."
if curl -s http://localhost:8775/health > /dev/null 2>&1; then
    echo "✓ Game server already running"
else
    uv run python scripts/start_korgym_server.py \
        --game_name 8-word_puzzle \
        --port 8775 \
        --level 4 > /dev/null 2>&1 &
    echo "  Waiting for server..."
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
# Step 2: 基线评估（无经验）
# ============================================================================
echo "Step 2/5: Baseline evaluation (50 games, ~20 minutes)..."
echo "  Model: Qwen2.5-7B-Instruct"
echo "  Config: practice/word_puzzle_qwen_clean"
echo ""

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config practice/word_puzzle_qwen_clean \
    --exp_id qwen_baseline \
    --num_seeds 50 \
    --level 4 \
    --output_dir workspace/korgym_paper_aligned

echo ""
echo "✓ Baseline evaluation completed"
echo "  Result: workspace/korgym_paper_aligned/qwen_baseline_word_puzzle.json"
echo ""

# ============================================================================
# Step 3: 分层经验学习训练
# ============================================================================
echo "Step 3/5: Hierarchical training (50 games, ~90 minutes)..."
echo "  Training: 10 batches × 5 games = 50 games"
echo "  L0 → L1 → L2 hierarchical aggregation"
echo ""

uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_qwen_hierarchical

echo ""
echo "✓ Training completed"
echo "  Agent: workspace/agents/word_puzzle_qwen_enhanced.yaml"
echo "  Experiences: workspace/hierarchical_experiences/word_puzzle_qwen.json"
echo ""

# ============================================================================
# Step 4: 增强评估（有经验）
# ============================================================================
echo "Step 4/5: Enhanced evaluation (50 games, ~20 minutes)..."
echo "  Model: Qwen2.5-7B-Instruct + Hierarchical Experiences"
echo "  Config: word_puzzle_qwen_enhanced"
echo ""

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config word_puzzle_qwen_enhanced \
    --exp_id qwen_enhanced \
    --num_seeds 50 \
    --level 4 \
    --output_dir workspace/korgym_paper_aligned

echo ""
echo "✓ Enhanced evaluation completed"
echo "  Result: workspace/korgym_paper_aligned/qwen_enhanced_word_puzzle.json"
echo ""

# ============================================================================
# Step 5: 对比结果与论文
# ============================================================================
echo "Step 5/5: Comparing results with KORGym paper..."
echo ""

python scripts/compare_paper_scores.py \
    workspace/korgym_paper_aligned/qwen_baseline_word_puzzle.json \
    workspace/korgym_paper_aligned/qwen_enhanced_word_puzzle.json

# ============================================================================
# 总结
# ============================================================================
echo ""
echo "======================================================================"
echo "  Experiment Completed!"
echo "======================================================================"
echo ""

BASELINE_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' workspace/korgym_paper_aligned/qwen_baseline_word_puzzle.json | head -1)
ENHANCED_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' workspace/korgym_paper_aligned/qwen_enhanced_word_puzzle.json | head -1)

echo "📊 Results Summary:"
echo "  Baseline score:  $BASELINE_SCORE"
echo "  Enhanced score:  $ENHANCED_SCORE"

if [ -n "$BASELINE_SCORE" ] && [ -n "$ENHANCED_SCORE" ]; then
    IMPROVEMENT=$(python3 -c "print(f'{float($ENHANCED_SCORE) - float($BASELINE_SCORE):.3f}')")
    IMPROVEMENT_PCT=$(python3 -c "print(f'{(float($ENHANCED_SCORE) - float($BASELINE_SCORE)) / float($BASELINE_SCORE) * 100:.1f}%')")
    echo "  Improvement:     +$IMPROVEMENT ($IMPROVEMENT_PCT)"
fi

echo ""
echo "📁 Output Files:"
echo "  - workspace/korgym_paper_aligned/qwen_baseline_word_puzzle.json"
echo "  - workspace/korgym_paper_aligned/qwen_enhanced_word_puzzle.json"
echo "  - workspace/korgym_paper_aligned/score.txt"
echo "  - workspace/agents/word_puzzle_qwen_enhanced.yaml"
echo "  - workspace/hierarchical_experiences/word_puzzle_qwen.json"
echo ""

echo "📖 Paper Comparison:"
echo "  - Qwen-Max (论文): 0.480 (48%)"
echo "  - Doubao-1.5-pro (论文): 0.120 (12%)"
echo "  - DeepSeek-R1-Distill-Qwen-7B (论文): 0.020 (2%)"
echo "  - Qwen2.5-7B-Instruct Enhanced (yours): $ENHANCED_SCORE"
echo ""

echo "✅ All done!"











