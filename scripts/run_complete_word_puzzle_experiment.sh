#!/bin/bash
# Word Puzzle 完整实验流程（论文对齐）
#
# 此脚本执行完整的评估流程：
# 1. 启动游戏服务器
# 2. 评估基线 Agent（无经验）
# 3. 训练 Agent（生成分层经验）
# 4. 评估增强 Agent（有经验）
# 5. 对比结果与论文
#
# Usage:
#   bash scripts/run_complete_word_puzzle_experiment.sh

set -e  # 遇到错误立即退出

echo "======================================================================"
echo "  Word Puzzle Complete Experiment (Paper Aligned)"
echo "======================================================================"
echo ""

# 配置参数
GAME_NAME="8-word_puzzle"
GAME_PORT=8775
GAME_LEVEL=4
NUM_SEEDS=50  # 论文使用 50 局，可以改成 20 快速测试
BASE_AGENT="practice/logic_agent_hierarchical_learning_clean"
TRAINING_CONFIG="word_puzzle_hierarchical_experiment"
OUTPUT_DIR="workspace/korgym_paper_aligned"

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# =============================================================================
# 步骤 1: 启动游戏服务器
# =============================================================================
echo "Step 1/5: Starting game server..."
echo "  Game: $GAME_NAME"
echo "  Port: $GAME_PORT"
echo "  Level: $GAME_LEVEL"
echo ""

# 检查服务器是否已运行
if curl -s http://localhost:$GAME_PORT/health > /dev/null 2>&1; then
    echo "✓ Game server already running"
else
    echo "Starting new game server..."
    uv run python scripts/start_korgym_server.py \
        --game_name "$GAME_NAME" \
        --port "$GAME_PORT" \
        --level "$GAME_LEVEL" > /dev/null 2>&1 &
    SERVER_PID=$!
    echo "  Server PID: $SERVER_PID"
    
    # 等待服务器启动
    echo "  Waiting for server to start..."
    for i in {1..30}; do
        if curl -s http://localhost:$GAME_PORT/health > /dev/null 2>&1; then
            echo "✓ Server started successfully"
            break
        fi
        sleep 1
    done
    
    if ! curl -s http://localhost:$GAME_PORT/health > /dev/null 2>&1; then
        echo "✗ Failed to start server"
        exit 1
    fi
fi

echo ""

# =============================================================================
# 步骤 2: 评估基线 Agent
# =============================================================================
echo "Step 2/5: Evaluating baseline agent (no experience)..."
echo "  Agent: $BASE_AGENT"
echo "  Number of games: $NUM_SEEDS"
echo ""

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config "$BASE_AGENT" \
    --exp_id baseline_clean \
    --num_seeds "$NUM_SEEDS" \
    --level "$GAME_LEVEL" \
    --output_dir "$OUTPUT_DIR"

echo ""
echo "✓ Baseline evaluation completed"
echo ""

# =============================================================================
# 步骤 3: 训练 Agent（生成分层经验）
# =============================================================================
echo "Step 3/5: Training agent with hierarchical experience learning..."
echo "  Training config: $TRAINING_CONFIG"
echo ""

uv run python scripts/run_training_free_GRPO.py \
    --config_name "$TRAINING_CONFIG"

echo ""
echo "✓ Training completed"
echo "  Generated agent: workspace/agents/word_puzzle_hierarchical_agent.yaml"
echo "  Experience library: workspace/hierarchical_experiences/word_puzzle.json"
echo ""

# =============================================================================
# 步骤 4: 评估增强 Agent
# =============================================================================
echo "Step 4/5: Evaluating enhanced agent (with experience)..."
echo "  Agent: word_puzzle_hierarchical_agent"
echo "  Number of games: $NUM_SEEDS"
echo ""

uv run python scripts/eval_word_puzzle_paper_aligned.py \
    --agent_config word_puzzle_hierarchical_agent \
    --exp_id enhanced_hierarchical \
    --num_seeds "$NUM_SEEDS" \
    --level "$GAME_LEVEL" \
    --output_dir "$OUTPUT_DIR"

echo ""
echo "✓ Enhanced evaluation completed"
echo ""

# =============================================================================
# 步骤 5: 对比结果
# =============================================================================
echo "Step 5/5: Comparing results with paper..."
echo ""

python scripts/compare_paper_scores.py \
    "$OUTPUT_DIR/baseline_clean_word_puzzle.json" \
    "$OUTPUT_DIR/enhanced_hierarchical_word_puzzle.json"

# =============================================================================
# 清理
# =============================================================================
echo ""
echo "======================================================================"
echo "  Experiment Completed!"
echo "======================================================================"
echo ""

echo "📁 Output Files:"
echo "  Baseline results:  $OUTPUT_DIR/baseline_clean_word_puzzle.json"
echo "  Enhanced results:  $OUTPUT_DIR/enhanced_hierarchical_word_puzzle.json"
echo "  Score summary:     $OUTPUT_DIR/score.txt"
echo ""

echo "📊 Quick Summary:"
BASELINE_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' "$OUTPUT_DIR/baseline_clean_word_puzzle.json" | head -1)
ENHANCED_SCORE=$(grep -oP '"avg_score": \K[0-9.]+' "$OUTPUT_DIR/enhanced_hierarchical_word_puzzle.json" | head -1)
echo "  Baseline score:  $BASELINE_SCORE"
echo "  Enhanced score:  $ENHANCED_SCORE"

if [ -n "$BASELINE_SCORE" ] && [ -n "$ENHANCED_SCORE" ]; then
    IMPROVEMENT=$(python3 -c "print(f'{($ENHANCED_SCORE - $BASELINE_SCORE):.3f}')")
    IMPROVEMENT_PCT=$(python3 -c "print(f'{(($ENHANCED_SCORE - $BASELINE_SCORE) / $BASELINE_SCORE * 100):.1f}%')" 2>/dev/null || echo "N/A")
    echo "  Improvement:     +$IMPROVEMENT ($IMPROVEMENT_PCT)"
fi

echo ""
echo "🎯 Next Steps:"
echo "  1. Review detailed results in JSON files"
echo "  2. Check experience library: workspace/hierarchical_experiences/word_puzzle.json"
echo "  3. Compare with paper Table 7"
echo ""

# 询问是否停止服务器
if [ -n "$SERVER_PID" ]; then
    read -p "Stop game server? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kill $SERVER_PID 2>/dev/null || true
        echo "✓ Server stopped"
    else
        echo "Server still running (PID: $SERVER_PID)"
        echo "To stop: kill $SERVER_PID"
    fi
fi

echo ""
echo "✅ All done!"











