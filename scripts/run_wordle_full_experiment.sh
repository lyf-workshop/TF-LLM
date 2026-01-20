#!/bin/bash
# ============================================================================
# Wordle游戏完整实验流程
# 
# 功能：
# 1. 创建训练数据集（100题）
# 2. 创建评估数据集（120题）
# 3. 基线评估（未学习）
# 4. GRPO训练（总结经验）
# 5. 增强评估（使用学习到的经验）
# 6. 对比结果
# ============================================================================

set -e  # 遇到错误立即退出

# ============================================================================
# 颜色定义
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# 日志函数
# ============================================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# 步骤1：创建数据集
# ============================================================================
step_create_datasets() {
    log_info "================================================"
    log_info "步骤1：创建Wordle数据集"
    log_info "================================================"
    
    log_info "创建训练数据集（100题）..."
    uv run python scripts/init_korgym_eval_dataset.py \
        --dataset_name "KORGym-Wordle-Train-100" \
        --num_samples 100
    
    log_success "训练数据集创建完成！"
    
    log_info "创建评估数据集（120题）..."
    uv run python scripts/init_korgym_eval_dataset.py \
        --dataset_name "KORGym-Wordle-Eval-120" \
        --num_samples 120
    
    log_success "评估数据集创建完成！"
    echo ""
}

# ============================================================================
# 步骤2：基线评估
# ============================================================================
step_baseline_eval() {
    log_info "================================================"
    log_info "步骤2：基线评估（未学习经验）"
    log_info "================================================"
    
    log_warning "请确保Wordle游戏服务器已启动！"
    log_warning "如未启动，请在另一个终端运行："
    log_warning "  cd KORGym/game_lib/33-wordle && python game_lib.py -p 8765"
    echo ""
    
    read -p "按Enter继续基线评估..." dummy
    
    log_info "开始基线评估（120题）..."
    uv run python scripts/eval_korgym_with_dataset.py \
        --agent_config practice/wordle_agent \
        --dataset_name "KORGym-Wordle-Eval-120" \
        --exp_id wordle_baseline_120 \
        --game_port 8765
    
    log_success "基线评估完成！"
    log_info "结果保存在: workspace/korgym_eval/wordle_baseline_120.json"
    echo ""
}

# ============================================================================
# 步骤3：GRPO训练
# ============================================================================
step_training() {
    log_info "================================================"
    log_info "步骤3：GRPO训练（100题，2 epochs）"
    log_info "================================================"
    
    log_info "开始训练..."
    uv run python scripts/run_training_free_GRPO.py \
        --config_name wordle_qwen_grpo
    
    log_success "训练完成！"
    log_info "新的agent配置已保存，包含学到的经验"
    echo ""
}

# ============================================================================
# 步骤4：增强评估
# ============================================================================
step_enhanced_eval() {
    log_info "================================================"
    log_info "步骤4：增强评估（使用学习到的经验）"
    log_info "================================================"
    
    # 查找训练后生成的agent配置文件
    ENHANCED_CONFIG="practice/wordle_qwen_grpo_agent"
    
    log_info "使用增强agent进行评估（120题）..."
    uv run python scripts/eval_korgym_with_dataset.py \
        --agent_config "$ENHANCED_CONFIG" \
        --dataset_name "KORGym-Wordle-Eval-120" \
        --exp_id wordle_enhanced_120 \
        --game_port 8765
    
    log_success "增强评估完成！"
    log_info "结果保存在: workspace/korgym_eval/wordle_enhanced_120.json"
    echo ""
}

# ============================================================================
# 步骤5：对比结果
# ============================================================================
step_compare_results() {
    log_info "================================================"
    log_info "步骤5：对比学习前后的结果"
    log_info "================================================"
    
    python scripts/compare_korgym_scores.py \
        workspace/korgym_eval/wordle_baseline_120.json \
        workspace/korgym_eval/wordle_enhanced_120.json
    
    log_success "实验完成！"
    echo ""
}

# ============================================================================
# 主函数
# ============================================================================
main() {
    echo ""
    log_info "========================================================"
    log_info "    Wordle游戏 - Training-Free GRPO 完整实验流程"
    log_info "========================================================"
    echo ""
    
    log_info "实验配置："
    log_info "  - 训练数据集: 100题"
    log_info "  - 评估数据集: 120题"
    log_info "  - 训练轮数: 2 epochs"
    log_info "  - 游戏端口: 8765"
    echo ""
    
    read -p "按Enter开始实验，或Ctrl+C取消..." dummy
    echo ""
    
    # 执行各步骤
    step_create_datasets
    step_baseline_eval
    step_training
    step_enhanced_eval
    step_compare_results
    
    log_success "========================================================"
    log_success "    全部实验流程执行完毕！"
    log_success "========================================================"
}

# 运行主函数
main



