#!/bin/bash
# 清理所有Word Puzzle相关的数据，用于重新开始实验

set -e

echo "================================================================================"
echo "清理 Word Puzzle 实验数据"
echo "================================================================================"

cd /mnt/f/youtu-agent

# 1. 清理数据库
echo ""
echo "[1/4] 清理数据库数据..."
python << 'EOF'
from utu.utils import SQLModelUtils, EnvUtils
from utu.db.eval_datapoint import DatasetSample, EvaluationSample
from sqlmodel import select, delete

# 获取数据库URL
db_url = EnvUtils.get_env("UTU_DB_URL")
if db_url:
    print(f"Database: {db_url}")
else:
    print("Using default database")

with SQLModelUtils.create_session() as session:
    # 删除数据集
    for dataset_name in [
        "KORGym-WordPuzzle-Train-100",
        "KORGym-WordPuzzle-Eval-120"
    ]:
        result = session.exec(
            delete(DatasetSample).where(DatasetSample.dataset == dataset_name)
        )
        session.commit()
        print(f"Deleted {result.rowcount} samples from {dataset_name}")
    
    # 删除评估数据
    result = session.exec(
        delete(EvaluationSample).where(
            EvaluationSample.exp_id.like("word_puzzle_qwen72b%")
        )
    )
    session.commit()
    print(f"Deleted {result.rowcount} evaluation samples")

print("✓ 数据库清理完成")
EOF

# 2. 清理评估结果
echo ""
echo "[2/4] 清理评估结果..."
rm -f workspace/korgym_eval/word_puzzle_qwen72b_*.json
echo "✓ 评估结果清理完成"

# 3. 清理经验文件
echo ""
echo "[3/4] 清理经验文件..."
rm -f workspace/practice/word_puzzle_qwen72b_grpo/experiences*.txt
rm -rf workspace/practice/word_puzzle_qwen72b_grpo/
echo "✓ 经验文件清理完成"

# 4. 清理生成的agent配置
echo ""
echo "[4/4] 清理生成的agent配置..."
rm -f configs/agents/practice/word_puzzle_qwen72b_grpo_*_agent.yaml
rm -f workspace/agents/word_puzzle_qwen72b_*.yaml
echo "✓ Agent配置清理完成"

echo ""
echo "================================================================================"
echo "✅ Word Puzzle 数据清理完成！"
echo "================================================================================"
echo ""
echo "现在可以重新运行实验："
echo "  bash scripts/run_word_puzzle_72b_full_experiment.sh"
echo ""


