#!/bin/bash
# ============================================================================
# Qwen2.5-7B-Instruct 完整实验流程（标准优化版）
# 
# 使用配置：
#   - 基线: word_puzzle_qwen_optimized (Temperature 0.3 + Enhanced Prompt)
#   - 训练: word_puzzle_qwen_optimized_hierarchical
#   - 目标: 基线 0.040+ → 训练后 0.120-0.150
# ============================================================================

set -e
cd /mnt/f/youtu-agent

echo "======================================================================"
echo "  Qwen2.5-7B-Instruct Complete Experiment (Optimized Version)"
echo "======================================================================"
echo ""
echo "配置:"
echo "  - 模型: Qwen2.5-7B-Instruct"
echo "  - Temperature: 0.3 (优化版)"
echo "  - Prompt: Enhanced"
echo "  - 游戏: Word Problem (Level 4)"
echo "  - 局数: 50 seeds"
echo ""
echo "预期:"
echo "  - 基线: 0.040-0.045 (4.0-4.5%)"
echo "  - 增强: 0.120-0.150 (12-15%)"
echo "  - 提升: 3-4 倍"
echo ""
echo "预计总时间: 2.5-3 小时"
echo ""

read -p "按 Enter 开始实验，或 Ctrl+C 取消... "
echo ""

# ============================================================================
# Step 1: 启动游戏服务器
# ============================================================================
echo "======================================================================"
echo "Step 1/5: Starting game server (Level 4)"
echo "======================================================================"
echo ""

if curl -s http://localhost:8775/health > /dev/null 2>&1; then
    echo "✓ Game server already running"
else
    echo "Starting new game server..."
    uv run python scripts/start_korgym_server.py \
        --game_name 8-word_puzzle \
        --port 8775 \
        --level 4 > /dev/null 2>&1 &
    SERVER_PID=$!
    echo "  Server PID: $SERVER_PID"
    
    echo "  Waiting for server to start..."
    for i in {1..30}; do
        if curl -s http://localhost:8775/health > /dev/null 2>&1; then
            echo "✓ Server started successfully"
            break
        fi
        sleep 1
    done
    
    if ! curl -s http://localhost:8775/health > /dev/null 2>&1; then
        echo "✗ Failed to start server"
        exit 1
    fi
fi

echo ""
echo "Server health check:"
curl http://localhost:8775/health
echo ""
echo ""

# ============================================================================
# Step 2: 基线评估（优化配置，无经验）
# ============================================================================
echo "======================================================================"
echo "Step 2/5: Baseline Evaluation (Optimized, No Experience)"
echo "======================================================================"
echo ""
echo "配置: word_puzzle_qwen_optimized"
echo "  - Temperature: 0.3"
echo "  - Prompt: Enhanced"
echo "  - 游戏局数: 50"
echo ""
echo "预期得分: 0.040-0.045 (4.0-4.5%)"
echo "预计时间: 15-25 分钟"
echo ""

START_TIME=$(date +%s)

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config practice/word_puzzle_qwen_optimized \
    --exp_id qwen_optimized_baseline \
    --num_seeds 50 \
    --level 4 \
    --output_dir workspace/korgym_paper_aligned

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "✓ Baseline evaluation completed in $((DURATION / 60)) minutes"
echo ""

# 获取基线分数
BASELINE_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' workspace/korgym_paper_aligned/qwen_optimized_baseline_word_puzzle.json | head -1)
echo "📊 Baseline Score: $BASELINE_SCORE"
echo ""

# 检查是否达到预期
if (( $(echo "$BASELINE_SCORE >= 0.038" | bc -l) )); then
    echo "✅ Great! Baseline score is good ($BASELINE_SCORE >= 0.038)"
    echo "   Ready to proceed with training!"
else
    echo "⚠️  Warning: Baseline score ($BASELINE_SCORE) is lower than expected (0.040)"
    echo "   But we can still proceed - training should still improve 3-4x!"
    echo ""
    read -p "Continue with training? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Experiment cancelled."
        exit 1
    fi
fi

echo ""

# ============================================================================
# Step 3: 分层经验学习训练
# ============================================================================
echo "======================================================================"
echo "Step 3/5: Hierarchical Experience Learning Training"
echo "======================================================================"
echo ""
echo "配置: word_puzzle_qwen_optimized_hierarchical"
echo "  - 基线配置: word_puzzle_qwen_optimized (temp=0.3)"
echo "  - 训练: 10 批 × 5 局 = 50 局"
echo "  - 分层: L0 (50) → L1 (10) → L2 (3)"
echo ""
echo "预计时间: 60-90 分钟"
echo ""

START_TIME=$(date +%s)

uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_qwen_optimized_hierarchical

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "✓ Training completed in $((DURATION / 60)) minutes"
echo ""

# 检查生成的文件
if [ -f "workspace/agents/word_puzzle_qwen_optimized_enhanced.yaml" ]; then
    echo "✓ Enhanced agent created:"
    echo "  workspace/agents/word_puzzle_qwen_optimized_enhanced.yaml"
else
    echo "✗ Enhanced agent not found!"
    exit 1
fi

if [ -f "workspace/hierarchical_experiences/word_puzzle_qwen_optimized.json" ]; then
    echo "✓ Experience library created:"
    echo "  workspace/hierarchical_experiences/word_puzzle_qwen_optimized.json"
    
    # 统计经验数量
    L0_COUNT=$(grep -o '"level": "L0-Case"' workspace/hierarchical_experiences/word_puzzle_qwen_optimized.json | wc -l)
    L1_COUNT=$(grep -o '"level": "L1-Pattern"' workspace/hierarchical_experiences/word_puzzle_qwen_optimized.json | wc -l)
    L2_COUNT=$(grep -o '"level": "L2-Meta"' workspace/hierarchical_experiences/word_puzzle_qwen_optimized.json | wc -l)
    
    echo ""
    echo "  Experience statistics:"
    echo "    L0 (Case):    $L0_COUNT"
    echo "    L1 (Pattern): $L1_COUNT"
    echo "    L2 (Meta):    $L2_COUNT"
else
    echo "✗ Experience library not found!"
    exit 1
fi

echo ""
echo ""

# ============================================================================
# Step 4: 增强评估（有经验）
# ============================================================================
echo "======================================================================"
echo "Step 4/5: Enhanced Evaluation (With Experience)"
echo "======================================================================"
echo ""
echo "配置: word_puzzle_qwen_optimized_enhanced"
echo "  - 基线: Optimized (temp=0.3)"
echo "  - 经验: L0 ($L0_COUNT) + L1 ($L1_COUNT) + L2 ($L2_COUNT)"
echo "  - 游戏局数: 50"
echo ""
echo "预期得分: 0.120-0.150 (12-15%)"
echo "预计时间: 15-25 分钟"
echo ""

START_TIME=$(date +%s)

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config word_puzzle_qwen_optimized_enhanced \
    --exp_id qwen_optimized_enhanced \
    --num_seeds 50 \
    --level 4 \
    --output_dir workspace/korgym_paper_aligned

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "✓ Enhanced evaluation completed in $((DURATION / 60)) minutes"
echo ""

# 获取增强分数
ENHANCED_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' workspace/korgym_paper_aligned/qwen_optimized_enhanced_word_puzzle.json | head -1)
echo "📊 Enhanced Score: $ENHANCED_SCORE"
echo ""
echo ""

# ============================================================================
# Step 5: 对比结果与论文
# ============================================================================
echo "======================================================================"
echo "Step 5/5: Comparing Results with Paper"
echo "======================================================================"
echo ""

python scripts/compare_paper_scores.py \
    workspace/korgym_paper_aligned/qwen_optimized_baseline_word_puzzle.json \
    workspace/korgym_paper_aligned/qwen_optimized_enhanced_word_puzzle.json

# ============================================================================
# 最终总结
# ============================================================================
echo ""
echo "======================================================================"
echo "  EXPERIMENT COMPLETED!"
echo "======================================================================"
echo ""

# 计算提升
if [ -n "$BASELINE_SCORE" ] && [ -n "$ENHANCED_SCORE" ]; then
    IMPROVEMENT=$(python3 -c "print(f'{float($ENHANCED_SCORE) - float($BASELINE_SCORE):.3f}')")
    IMPROVEMENT_PCT=$(python3 -c "print(f'{(float($ENHANCED_SCORE) - float($BASELINE_SCORE)) / float($BASELINE_SCORE) * 100:.1f}%')")
    IMPROVEMENT_MULT=$(python3 -c "print(f'{float($ENHANCED_SCORE) / float($BASELINE_SCORE):.2f}x')")
fi

echo "📊 Final Results:"
echo "  Baseline (Optimized):  $BASELINE_SCORE ($(python3 -c "print(f'{float($BASELINE_SCORE) * 100:.1f}%')"))"
echo "  Enhanced (Trained):    $ENHANCED_SCORE ($(python3 -c "print(f'{float($ENHANCED_SCORE) * 100:.1f}%')"))"
echo ""
echo "  Improvement:           +$IMPROVEMENT ($IMPROVEMENT_PCT)"
echo "  Multiplier:            $IMPROVEMENT_MULT"
echo ""

echo "📖 Paper Comparison:"
echo "  论文 Qwen2.5-7B-Instruct:  0.040 (4.0%)"
echo "  你的 Baseline:             $BASELINE_SCORE"
echo "  你的 Enhanced:             $ENHANCED_SCORE"
echo ""

# 判断训练效果
if (( $(echo "$ENHANCED_SCORE >= 0.100" | bc -l) )); then
    echo "✅ EXCELLENT! Enhanced score >= 0.100 (10%)"
    echo "   Hierarchical learning is working very well!"
elif (( $(echo "$ENHANCED_SCORE >= 0.070" | bc -l) )); then
    echo "✅ GOOD! Enhanced score >= 0.070 (7%)"
    echo "   Significant improvement achieved!"
elif (( $(echo "$ENHANCED_SCORE > $BASELINE_SCORE" | bc -l) )); then
    echo "✓ Enhanced score improved"
    echo "  Consider: more training rounds or prompt tuning"
else
    echo "⚠️  No improvement detected"
    echo "  Check: experience quality, prompt engineering"
fi

echo ""
echo "📁 Output Files:"
echo "  - workspace/korgym_paper_aligned/qwen_optimized_baseline_word_puzzle.json"
echo "  - workspace/korgym_paper_aligned/qwen_optimized_enhanced_word_puzzle.json"
echo "  - workspace/korgym_paper_aligned/score.txt"
echo "  - workspace/agents/word_puzzle_qwen_optimized_enhanced.yaml"
echo "  - workspace/hierarchical_experiences/word_puzzle_qwen_optimized.json"
echo ""

echo "======================================================================"
echo "🎉 All experiments completed successfully!"
echo "======================================================================"
echo ""











