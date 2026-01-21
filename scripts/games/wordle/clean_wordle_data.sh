#!/bin/bash
# ============================================================================
# 清理Wordle实验相关的所有数据
# ============================================================================

set -e

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${YELLOW}警告: 此脚本将删除所有Wordle相关的数据！${NC}"
echo -e "${YELLOW}包括：${NC}"
echo "  - 数据库中的 KORGym-Wordle-* 数据集"
echo "  - 数据库中的 wordle_* 评估结果"
echo "  - workspace/korgym_eval/wordle_*.json"
echo "  - configs/agents/practice/wordle_qwen_grpo_agent.yaml"
echo ""
read -p "确认删除？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo -e "${GREEN}开始清理...${NC}"

# 从数据库删除数据集
echo "清理数据库中的Wordle数据集..."
uv run python << 'PYEOF'
from utu.db.eval_datapoint import DatasetSample, EvaluationSample
from utu.utils import SQLModelUtils
from sqlmodel import select

with SQLModelUtils.create_session() as session:
    # 删除数据集
    datasets = session.exec(
        select(DatasetSample).where(
            DatasetSample.dataset.like("KORGym-Wordle-%")
        )
    ).all()
    for ds in datasets:
        session.delete(ds)
    print(f"  删除了 {len(datasets)} 个数据集样本")
    
    # 删除评估结果
    evals = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id.like("wordle_%")
        )
    ).all()
    for ev in evals:
        session.delete(ev)
    print(f"  删除了 {len(evals)} 个评估样本")
    
    session.commit()
    print("✓ 数据库清理完成")
PYEOF

# 删除评估结果文件
echo "删除评估结果文件..."
rm -f workspace/korgym_eval/wordle_*.json
echo "✓ 评估结果文件已删除"

# 删除生成的agent配置
echo "删除生成的agent配置..."
rm -f configs/agents/practice/wordle_qwen_grpo_agent.yaml
echo "✓ Agent配置已删除"

echo ""
echo -e "${GREEN}清理完成！${NC}"

