#!/bin/bash
# 清理根目录下已整合到 docs/korgym/ 的无用文档
# 
# 使用方法:
#   bash scripts/clean_obsolete_docs.sh --dry-run  # 预览要删除的文件
#   bash scripts/clean_obsolete_docs.sh            # 实际删除

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为 dry-run 模式
DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo -e "${YELLOW}=== DRY RUN MODE ===${NC}"
    echo "将显示要删除的文件，但不会实际删除"
    echo ""
fi

# 创建备份目录
BACKUP_DIR="backup/obsolete_docs_$(date +%Y%m%d_%H%M%S)"

# 要删除的文件列表（已完全整合到 docs/korgym/ 的临时文档）
FILES_TO_DELETE=(
    # Wordle 相关（已整合到 docs/korgym/wordle_guide.md）
    "WORDLE_QUICK_START.md"
    "WORDLE_GAME_ANALYSIS.md"
    "WORDLE_MULTIROUND_TEST_GUIDE.md"
    
    # Word Puzzle 相关（已整合到 docs/korgym/word_puzzle_guide.md）
    "Word_Puzzle完整指南.md"
    "WORD_PUZZLE_DIAGNOSIS.md"
    
    # Alphabetical Sorting 相关（已整合到 docs/korgym/alphabetical_sorting_guide.md）
    "Alphabetical_Sorting快速命令.md"
    "ALPHABETICAL_SORTING_STRATEGY_UPDATE.md"
    
    # 重复的快速开始和使用指南（已整合到 docs/korgym/index.md 和 quick_reference.md）
    "KORGYM_QUICK_START.md"
    "KORGYM_CLEANUP_AND_RERUN.md"
    "KORGYM_VIEW_RESULTS_GUIDE.md"
    "KORGYM_SCORING_GUIDE.md"
    "KORGym_Usage_Guide.md"
    "KORGym快速使用指南.md"
    "KORGym集成指南.md"
    "KORGYM_THREE_GAMES_GUIDE.md"
    "KORGYM_THREE_GAMES_SUMMARY.md"
    "KORGYM_COMMANDS_SUMMARY.md"
    "KORGYM_SETUP_COMPLETE.md"
    
    # 多轮游戏相关（功能已实现，文档已整合）
    "MULTI_ROUND_GAME_SUPPORT_ANALYSIS.md"
    "MULTI_ROUND_GAME_EVAL_GUIDE.md"
    "MULTI_ROUND_EVAL_TODO.md"
    "MULTI_ROUND_EVAL_IMPLEMENTATION.md"
    "MULTI_ROUND_EVAL_IMPLEMENTATION_SUMMARY.md"
    
    # 环境配置（可选：如果已整合到 docs）
    "KORGYM_WSL_SETUP.md"
    
    # 其他
    "GRPO无关文件清单.md"
    "KORGym评估指南.md"
)

# 要归档的文件列表（问题修复记录，保留作为历史）
FILES_TO_ARCHIVE=(
    # 问题修复文档（已整合到 docs/korgym/troubleshooting.md）
    "ALPHABETICAL_SORTING_CACHE_ISSUE.md"
    "HIERARCHICAL_LEARNING_FIX.md"
    "WORD_PUZZLE_ZERO_ACCURACY_FIX.md"
    "PREPARE_KORGYM_DATA_FIX.md"
    "WORDLE_TRAJECTORIES_FIX.md"
    "THREE_GAMES_CONFIG_FIX_SUMMARY.md"
    "KORGYM_SERVER_500_ERROR_FIX.md"
    "WORD_PUZZLE_CACHE_CLEANUP.md"
    
    # Bug 修复记录
    "KORGYM_BUGFIX_PROCESSER_MATCHING.md"
    "KORGYM_BUGFIX_DATABASE.md"
    "KORGYM_BUGFIX_CIRCULAR_IMPORT.md"
    "KORGYM_ALL_BUGFIXES_SUMMARY.md"
    "KORGYM_VERIFY_FUNCTION_UPGRADE.md"
    
    # 经验总结相关
    "KORGym经验总结流程图.md"
    "KORGym经验总结机制详解.md"
    "经验生成机制详解.md"
    "经验库使用机制说明.md"
    "KORGym分层经验学习适配方案.md"
    "分层经验学习-完整运行指南.md"
    
    # 集成和适配文档
    "KORGYM_INTEGRATION_README.md"
    "KORGym适配修改说明.md"
    "Training-Free_GRPO完整流程详解.md"
    
    # WSL 环境配置（详细版保留一个）
    "KORGym_WSL环境配置完整指南.md"
)

# 统计
deleted_count=0
archived_count=0
not_found_count=0

echo -e "${GREEN}=== 清理根目录无用文档 ===${NC}"
echo ""

# 1. 删除已完全整合的文档
echo -e "${YELLOW}[1/2] 删除已完全整合的文档${NC}"
echo "以下文档的内容已完全整合到 docs/korgym/ 中，将被删除："
echo ""

for file in "${FILES_TO_DELETE[@]}"; do
    if [[ -f "$file" ]]; then
        if $DRY_RUN; then
            echo -e "  ${RED}[删除]${NC} $file"
        else
            # 创建备份
            mkdir -p "$BACKUP_DIR"
            cp "$file" "$BACKUP_DIR/"
            # 删除文件
            rm "$file"
            echo -e "  ${RED}[已删除]${NC} $file (已备份)"
        fi
        ((deleted_count++))
    else
        echo -e "  ${YELLOW}[未找到]${NC} $file"
        ((not_found_count++))
    fi
done

echo ""
echo -e "${YELLOW}[2/2] 归档问题修复和历史文档${NC}"
echo "以下文档包含有价值的历史信息，将被归档到 docs/archive/korgym/："
echo ""

# 2. 归档问题修复文档
for file in "${FILES_TO_ARCHIVE[@]}"; do
    if [[ -f "$file" ]]; then
        if $DRY_RUN; then
            echo -e "  ${YELLOW}[归档]${NC} $file"
        else
            # 创建归档目录
            mkdir -p "docs/archive/korgym"
            # 移动文件
            mv "$file" "docs/archive/korgym/"
            echo -e "  ${YELLOW}[已归档]${NC} $file -> docs/archive/korgym/"
        fi
        ((archived_count++))
    else
        echo -e "  ${YELLOW}[未找到]${NC} $file"
        ((not_found_count++))
    fi
done

echo ""
echo -e "${GREEN}=== 清理统计 ===${NC}"
echo "删除文件: $deleted_count"
echo "归档文件: $archived_count"
echo "未找到: $not_found_count"

if $DRY_RUN; then
    echo ""
    echo -e "${YELLOW}这是预览模式，没有实际删除或移动文件${NC}"
    echo -e "要执行清理，请运行: ${GREEN}bash scripts/clean_obsolete_docs.sh${NC}"
else
    echo ""
    echo -e "${GREEN}✅ 清理完成！${NC}"
    if [[ $deleted_count -gt 0 ]]; then
        echo -e "备份位置: ${GREEN}$BACKUP_DIR${NC}"
    fi
    echo ""
    echo "归档的文档可在 docs/archive/korgym/ 中查看"
fi

echo ""
echo -e "${YELLOW}注意：以下文档被保留（作为详细参考）：${NC}"
echo "  ✅ KORGYM_THREE_GAMES_COMMANDS.md - 详细命令参考"
echo "  ✅ PRACTICE_RETRY_MECHANISM_GUIDE.md - 重试机制详解"
echo "  ✅ PRACTICE_RETRY_QUICK_REFERENCE.md - 重试机制快速参考"
echo ""











