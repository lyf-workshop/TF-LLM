#!/bin/bash
# Word Puzzle 完整对比实验
# 基线评估 → 训练获得经验 → 增强评估 → 对比分析

set -e  # 遇到错误立即退出

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "  Word Puzzle 分层经验学习对比实验"
echo "========================================================================"
echo ""

# 检查是否在正确的目录
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 步骤 0: 启动游戏服务器
echo -e "${BLUE}步骤 0: 启动 Word Puzzle 游戏服务器...${NC}"
echo "在另一个终端运行: python scripts/start_korgym_server.py 8-word_puzzle"
echo ""
read -p "服务器已启动？按 Enter 继续，或 Ctrl+C 取消: "

# 步骤 1: 基线评估（无经验）
echo ""
echo -e "${BLUE}步骤 1: 基线评估（无经验 Agent）${NC}"
echo "========================================================================"
echo "评估原始 Agent 在 Word Puzzle 上的表现..."
echo ""

uv run python scripts/run_korgym_eval.py \
    --config_name korgym/word_puzzle_baseline

echo ""
echo -e "${GREEN}✓ 基线评估完成${NC}"
echo ""
read -p "按 Enter 继续训练阶段..."

# 步骤 2: 训练获得经验
echo ""
echo -e "${BLUE}步骤 2: 训练阶段（获得分层经验）${NC}"
echo "========================================================================"
echo "Agent 将玩 30 局游戏，自动提取 L0/L1/L2 经验..."
echo ""

uv run python scripts/run_training_free_GRPO.py \
    --config_name word_puzzle_hierarchical_experiment

echo ""
echo -e "${GREEN}✓ 训练完成，经验已保存${NC}"
echo ""

# 显示生成的经验统计
if [ -f "workspace/hierarchical_experiences/word_puzzle_exp.json" ]; then
    echo "生成的经验统计:"
    python3 << 'EOF'
import json
with open("workspace/hierarchical_experiences/word_puzzle_exp.json", "r") as f:
    data = json.load(f)
    print(f"  L0 经验: {len(data.get('l0_experiences', []))} 个")
    print(f"  L1 经验: {len(data.get('l1_experiences', []))} 个")
    print(f"  L2 经验: {len(data.get('l2_experiences', []))} 个")
EOF
fi

echo ""
read -p "按 Enter 继续增强评估..."

# 步骤 3: 增强评估（有经验）
echo ""
echo -e "${BLUE}步骤 3: 增强评估（有经验 Agent）${NC}"
echo "========================================================================"
echo "使用增强后的 Agent（包含分层经验）评估表现..."
echo ""

uv run python scripts/run_korgym_eval.py \
    --config_name korgym/word_puzzle_enhanced

echo ""
echo -e "${GREEN}✓ 增强评估完成${NC}"

# 步骤 4: 对比分析
echo ""
echo -e "${BLUE}步骤 4: 结果对比分析${NC}"
echo "========================================================================"
echo ""

uv run python scripts/compare_korgym_results.py \
    --baseline word_puzzle_baseline_eval \
    --enhanced word_puzzle_enhanced_eval

echo ""
echo "========================================================================"
echo -e "${GREEN}✓ 实验完成！${NC}"
echo "========================================================================"
echo ""
echo "查看详细结果:"
echo "  • 经验文件: workspace/hierarchical_experiences/word_puzzle_exp.json"
echo "  • 增强 Agent: configs/agents/practice/word_puzzle_exp_agent.yaml"
echo "  • 数据库: database.db (使用 view_training_results.py 查看)"
echo ""

