#!/bin/bash
#
# ZebraLogic Training-Free GRPO 完整实验流程
# 自动运行从数据准备到结果分析的全部步骤
#

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置参数
TRAIN_SIZE=100
TEST_SIZE=30
TRAIN_NAME="ZebraLogic-Train-100"
TEST_NAME="ZebraLogic-Test-30"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  ZebraLogic Training-Free GRPO${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 显示配置
echo -e "${YELLOW}实验配置:${NC}"
echo "  训练集: $TRAIN_SIZE 题 (难度稍高)"
echo "  测试集: $TEST_SIZE 题 (难度中等)"
echo "  Epochs: 3"
echo "  Batch Size: 100"
echo "  GRPO Group Size: 5"
echo "  学习温度: 0.7"
echo "  评估温度: 0.3"
echo ""

# 询问是否继续
read -p "是否继续? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${RED}已取消${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 1/5: 准备数据集${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 先分析数据集
echo -e "${YELLOW}分析 ZebraLogic 数据集...${NC}"
uv run python scripts/data/prepare_zebralogic_samples.py --analyze_only

echo ""
read -p "是否继续创建训练/测试数据集? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${RED}已取消${NC}"
    exit 1
fi

# 创建数据集
echo ""
echo -e "${YELLOW}创建训练集和测试集...${NC}"
uv run python scripts/data/prepare_zebralogic_samples.py \
  --train_size $TRAIN_SIZE \
  --test_size $TEST_SIZE \
  --train_name "$TRAIN_NAME" \
  --test_name "$TEST_NAME"

echo ""
echo -e "${GREEN}✓ 数据集准备完成${NC}"
sleep 2

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 2/5: 基线评估（训练前）${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo -e "${YELLOW}运行基线评估...${NC}"
uv run python scripts/run_eval.py --config eval/logic/logic_zebralogic_test.yaml

echo ""
echo -e "${GREEN}✓ 基线评估完成${NC}"
sleep 2

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 3/5: Training-Free GRPO${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo -e "${YELLOW}开始训练 (预计 30-90 分钟)...${NC}"
echo "  - 3 epochs"
echo "  - 每个 epoch: $TRAIN_SIZE samples"
echo "  - 并发数: 128"
echo ""

uv run python scripts/run_practice.py --config practice/logic_reasoning_zebralogic.yaml

echo ""
echo -e "${GREEN}✓ 训练完成${NC}"
sleep 2

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 4/5: 评估增强后的 Agent${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo -e "${YELLOW}运行训练后评估...${NC}"
uv run python scripts/run_eval.py --config eval/logic/logic_practice_zebralogic_test.yaml

echo ""
echo -e "${GREEN}✓ 训练后评估完成${NC}"
sleep 2

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}步骤 5/5: 结果分析${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

echo -e "${YELLOW}生成结果对比...${NC}"
uv run python scripts/view_training_results.py

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  实验完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo "查看经验库:"
echo "  cat configs/agents/practice/logic_practice_zebralogic_agent.yaml"
echo ""
echo "导出结果:"
echo "  uv run python scripts/view_training_results.py --export zebralogic_results.json"
echo ""
echo "查看所有实验:"
echo "  uv run python scripts/clean_experiment_data.py --list"
echo ""

