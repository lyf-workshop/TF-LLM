#!/bin/bash
# WSL中运行论文实验的脚本 - 使用纯文本推理（不使用工具）
# Script to run paper experiment in WSL - Pure text reasoning (no tools)

set -e  # 遇到错误立即退出

echo "=========================================================================="
echo "论文实验复现 - WSL版本 (DeepSeek V3.1)"
echo "Paper Experiment Reproduction - WSL Version (DeepSeek V3.1)"
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
UTU_LLM_TYPE=openai
UTU_LLM_MODEL=deepseek-chat
UTU_LLM_BASE_URL=https://api.deepseek.com
UTU_LLM_API_KEY=your-api-key-here

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
        # 显示当前配置的模型
        if grep -q "UTU_LLM_MODEL" .env; then
            echo "✓ 当前模型: $(grep UTU_LLM_MODEL .env | cut -d= -f2)"
        fi
    fi
}

# 检查math-verify包
check_math_verify() {
    echo ""
    echo "检查math-verify包..."
    if python -c "import math_verify" 2>/dev/null; then
        echo "✓ math-verify已安装"
    else
        echo "警告: math-verify未安装"
        read -p "是否现在安装？(y/n): " install_response
        if [[ "$install_response" == "y" ]]; then
            uv pip install math-verify
            echo "✓ math-verify安装完成"
        else
            echo "警告: 没有math-verify可能导致验证失败"
        fi
    fi
}

echo "实验配置（按论文设置）:"
echo "- 数据集: DAPO-100 (从DAPO-Math-17k采样100个问题)"
echo "- 轮次: 3 epochs"
echo "- 批次大小: 100 (每个epoch单批次)"
echo "- 群体大小: 5 (grpo_n=5)"
echo "- 学习温度: 0.7"
echo "- 评估温度: 0.3"
echo "- Agent类型: 纯文本推理（不使用Python工具）"
echo ""

check_venv
check_env
check_math_verify

echo ""
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
echo "步骤 1/5: 准备数据集"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "下载并准备 AIME24, AIME25, DAPO-Math-17k 数据集..."
uv run python scripts/data/process_training_free_GRPO_data.py

if [[ $? -eq 0 ]]; then
    echo ""
    echo "✓ 基础数据集准备完成"
else
    echo ""
    echo "✗ 数据准备失败，请检查网络连接或HuggingFace访问"
    exit 1
fi

echo ""
echo "从 DAPO-Math-17k 创建 DAPO-100 采样数据集..."
uv run python scripts/data/create_dapo_100.py

if [[ $? -eq 0 ]]; then
    echo ""
    echo "✓ DAPO-100 数据集创建成功"
else
    echo ""
    echo "✗ DAPO-100 创建失败"
    exit 1
fi

# ============================================================================
# 步骤2: Baseline评估 - AIME24
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 2/5: Baseline评估 - AIME 2024（训练前）"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "评估 AIME24 baseline..."
uv run python scripts/run_eval.py --config_name math/math_paper_exp_AIME24
baseline_aime24=$?

if [[ $baseline_aime24 -eq 0 ]]; then
    echo ""
    echo "✓ AIME24 Baseline评估完成"
else
    echo ""
    echo "警告: AIME24 Baseline评估可能失败"
    read -p "是否继续实验？(y/n): " continue_exp
    if [[ "$continue_exp" != "y" ]]; then
        exit 1
    fi
fi

# ============================================================================
# 步骤3: Baseline评估 - AIME25
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 3/5: Baseline评估 - AIME 2025（训练前）"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "评估 AIME25 baseline..."
uv run python scripts/run_eval.py --config_name math/math_paper_exp_AIME25
baseline_aime25=$?

if [[ $baseline_aime25 -eq 0 ]]; then
    echo ""
    echo "✓ AIME25 Baseline评估完成"
else
    echo ""
    echo "警告: AIME25 Baseline评估可能失败"
fi

# ============================================================================
# 步骤4: Training-Free GRPO
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 4/5: 运行 Training-Free GRPO"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "训练配置:"
echo "- 3 个 epochs"
echo "- 每个 epoch 100 个样本（单批次）"
echo "- 每个问题生成 5 个 rollout（grpo_n=5）"
echo "- Rollout 温度: 0.7"
echo ""
echo "预计时间: 3-5 小时（取决于API速度）"
echo "预计API调用: 约1500次"
echo ""

read -p "开始训练？(y/n): " start_train
if [[ "$start_train" != "y" ]]; then
    echo "训练取消。"
    exit 0
fi

uv run python scripts/run_training_free_GRPO.py --config_name math_reasoning_paper_exp

if [[ $? -eq 0 ]]; then
    echo ""
    echo "✓ 训练成功完成"
    echo "✓ 增强的agent配置已保存: configs/agents/practice/math_practice_paper_exp_agent.yaml"
else
    echo ""
    echo "✗ 训练失败，请检查日志"
    exit 1
fi

# ============================================================================
# 步骤5: 训练后评估
# ============================================================================
echo ""
echo "████████████████████████████████████████████████████████████████████████"
echo "步骤 5/5: 评估增强Agent（训练后）"
echo "████████████████████████████████████████████████████████████████████████"
echo ""

echo "评估 AIME24 (训练后)..."
uv run python scripts/run_eval.py --config_name math/math_practice_paper_exp_AIME24
practice_aime24=$?

if [[ $practice_aime24 -eq 0 ]]; then
    echo ""
    echo "✓ AIME24 训练后评估完成"
fi

echo ""
echo "评估 AIME25 (训练后)..."
uv run python scripts/run_eval.py --config_name math/math_practice_paper_exp_AIME25
practice_aime25=$?

if [[ $practice_aime25 -eq 0 ]]; then
    echo ""
    echo "✓ AIME25 训练后评估完成"
fi

# ============================================================================
# 总结
# ============================================================================
echo ""
echo "=========================================================================="
echo "🎉 实验完成！"
echo "=========================================================================="
echo ""

if [[ $baseline_aime24 -eq 0 ]] && [[ $baseline_aime25 -eq 0 ]] && [[ $practice_aime24 -eq 0 ]] && [[ $practice_aime25 -eq 0 ]]; then
    echo "✓ 所有步骤成功完成"
else
    echo "! 某些步骤可能失败，请检查日志"
fi

echo ""
echo "📊 实验结果:"
echo "- Baseline AIME24: $(if [[ $baseline_aime24 -eq 0 ]]; then echo '✓'; else echo '✗'; fi)"
echo "- Baseline AIME25: $(if [[ $baseline_aime25 -eq 0 ]]; then echo '✓'; else echo '✗'; fi)"
echo "- Practice AIME24: $(if [[ $practice_aime24 -eq 0 ]]; then echo '✓'; else echo '✗'; fi)"
echo "- Practice AIME25: $(if [[ $practice_aime25 -eq 0 ]]; then echo '✓'; else echo '✗'; fi)"
echo ""

echo "📁 生成的文件:"
echo "- 增强agent配置: configs/agents/practice/math_practice_paper_exp_agent.yaml"
echo "- 日志文件: logs/"
echo "- 数据库: test.db (包含所有评估结果)"
echo ""

echo "🔍 查看结果:"
echo "- 如果启用了Phoenix: http://127.0.0.1:6006"
echo "- 查看数据库中的评估记录"
echo "- 比较 exp_id:"
echo "  * math_paper_exp_AIME24_eval (baseline)"
echo "  * math_practice_paper_exp_AIME24_eval (after practice)"
echo "  * math_paper_exp_AIME25_eval (baseline)"
echo "  * math_practice_paper_exp_AIME25_eval (after practice)"
echo ""

echo "🎯 下一步:"
echo "1. 分析评估结果，对比训练前后的性能"
echo "2. 查看提取的经验（experiences）"
echo "3. 如需重新运行，使用 --restart_step 参数"
echo ""

echo "感谢使用！实验结果已保存。"

