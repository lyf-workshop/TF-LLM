#!/bin/bash
# WSL中运行论文实验的脚本
# Script to run paper experiment in WSL

set -e  # 遇到错误立即退出

echo "=========================================================================="
echo "论文实验复现 - WSL版本"
echo "Paper Experiment Reproduction - WSL Version"
echo "=========================================================================="
echo ""

# 检查是否在虚拟环境中
check_venv() {
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "警告: 未检测到虚拟环境"
        echo "正在激活虚拟环境..."
        if [[ -f ".venv/bin/activate" ]]; then
            source .venv/bin/activate
            echo "✓ 虚拟环境已激活"
        else
            echo "错误: 找不到虚拟环境，请先运行: uv sync --all-extras"
            exit 1
        fi
    else
        echo "✓ 虚拟环境已激活: $VIRTUAL_ENV"
    fi
}

# 检查.env文件
check_env() {
    if [[ ! -f ".env" ]]; then
        echo ""
        echo "=========================================================================="
        echo "警告: 未找到.env文件！"
        echo "=========================================================================="
        echo ""
        echo "请创建.env文件并配置以下环境变量："
        echo ""
        cat << 'EOF'
LLM_TYPE=deepseek
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your-api-key-here

# 可选：Phoenix tracing
# PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
# PHOENIX_PROJECT_NAME=Youtu-Agent
EOF
        echo ""
        read -p "已经配置好.env文件了吗？(y/n): " response
        if [[ "$response" != "y" ]]; then
            echo "请先配置.env文件后再运行此脚本。"
            exit 1
        fi
    else
        echo "✓ .env文件存在"
    fi
}

echo "实验配置:"
echo "- 数据集: DAPO-100 (从DAPO-Math-17K采样100个问题)"
echo "- 轮次: 3 epochs"
echo "- 群体大小: 5"
echo "- 学习温度: 0.7"
echo "- 评估温度: 0.3"
echo "- Agent: 无工具的纯文本推理"
echo ""

check_venv
check_env

read -p "是否开始实验？(y/n): " start_exp
if [[ "$start_exp" != "y" ]]; then
    echo "实验取消。"
    exit 0
fi

# ============================================================================
# 步骤1: 准备数据集
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 1/4: 准备数据集"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "下载并准备AIME24, AIME25, DAPO-Math-17k数据集..."
uv run python scripts/data/process_training_free_GRPO_data.py

if [[ $? -eq 0 ]]; then
    echo ""
    echo "✓ 数据准备成功完成"
else
    echo ""
    echo "✗ 数据准备失败，请检查网络连接或HuggingFace访问"
    exit 1
fi

# ============================================================================
# 步骤2: Baseline评估
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 2/4: Baseline评估（训练前）"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "评估AIME24 baseline..."
uv run python scripts/run_eval.py --config_name math/math_AIME24_no_tools
baseline_aime24=$?

echo ""
echo "跳过AIME25 baseline评估（根据用户要求）..."

if [[ $baseline_aime24 -eq 0 ]]; then
    echo ""
    echo "✓ Baseline评估成功完成"
else
    echo ""
    echo "警告: Baseline评估可能失败"
    read -p "是否继续训练？(y/n): " continue_train
    if [[ "$continue_train" != "y" ]]; then
        exit 1
    fi
fi

# ============================================================================
# 步骤3: Training-Free GRPO
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 3/4: 运行Training-Free GRPO"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "开始训练3个epochs，每个epoch包含100个样本..."
uv run python scripts/run_training_free_GRPO.py --config_name math_reasoning_paper_exp

if [[ $? -eq 0 ]]; then
    echo ""
    echo "✓ 训练成功完成"
else
    echo ""
    echo "✗ 训练失败，请检查日志"
    exit 1
fi

# ============================================================================
# 步骤4: 训练后评估
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 4/4: 评估增强Agent（训练后）"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "评估AIME24 (训练后)..."
uv run python scripts/run_eval.py --config_name math/math_AIME24_no_tools_practice
practice_aime24=$?

echo ""
echo "跳过AIME25训练后评估（根据用户要求）..."
practice_aime25=0

# ============================================================================
# 总结
# ============================================================================
echo ""
echo "=========================================================================="
echo "实验完成！"
echo "=========================================================================="
echo ""

if [[ $practice_aime24 -eq 0 ]] && [[ $practice_aime25 -eq 0 ]]; then
    echo "✓ 所有步骤成功完成"
else
    echo "! 某些评估步骤可能失败"
fi

echo ""
echo "查看结果:"
echo "- 训练后的agent配置: configs/agents/practice/math_agent_no_tools_practice.yaml"
echo "- 如果启用了Phoenix: http://127.0.0.1:6006"
echo "- 日志文件: logs/"
echo ""

