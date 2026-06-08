"""
验证经验提取的筛选问题

检查 Wordle 训练中有多少问题因为 0/1 评分而被筛选掉
"""

import argparse
import json
from collections import defaultdict

from utu.eval.eval_types import EvaluationSample
from utu.utils import get_db_session, get_logger

logger = get_logger(__name__)


def analyze_filtering(exp_id: str, grpo_n: int = 3):
    """分析经验提取的筛选情况"""
    
    print(f"\n{'='*80}")
    print(f"经验提取筛选分析")
    print(f"{'='*80}\n")
    
    with get_db_session() as session:
        samples = session.query(EvaluationSample).filter(
            EvaluationSample.experiment_name == exp_id
        ).all()
    
    if not samples:
        print(f"❌ 未找到实验 '{exp_id}' 的样本")
        return
    
    # 按问题分组
    problems = defaultdict(list)
    for s in samples:
        problems[s.raw_question].append(s.reward if s.reward is not None else 0)
    
    print(f"实验 ID：{exp_id}")
    print(f"总问题数：{len(problems)}")
    print(f"总样本数：{len(samples)}")
    print(f"每问题样本数（GRPO-N）：{grpo_n}")
    print()
    
    # 统计各种情况
    all_zero = 0      # 全部失败
    all_one = 0       # 全部成功
    partial = 0       # 部分成功（会提取经验）
    
    details = []
    
    for q, scores in problems.items():
        avg = sum(scores) / len(scores) if scores else 0
        
        if avg == 0:
            all_zero += 1
            status = "❌ 全部失败"
            will_extract = False
        elif avg == 1:
            all_one += 1
            status = "✅ 全部成功"
            will_extract = False
        else:
            partial += 1
            status = f"⚠️ 部分成功"
            will_extract = True
        
        details.append({
            'question': q[:80],
            'scores': scores,
            'avg': avg,
            'status': status,
            'will_extract': will_extract
        })
    
    # 按是否提取经验排序
    details.sort(key=lambda x: (not x['will_extract'], x['avg']))
    
    print(f"{'='*80}")
    print("问题详情（按是否提取经验排序）")
    print(f"{'='*80}\n")
    
    for i, d in enumerate(details, 1):
        extract_mark = "✅ 提取经验" if d['will_extract'] else "❌ 过滤掉"
        print(f"{i:2d}. {d['status']} | avg={d['avg']:.2f} | {extract_mark}")
        print(f"    问题: {d['question']}...")
        print(f"    分数: {d['scores']}")
        print()
    
    print(f"{'='*80}")
    print("统计结果")
    print(f"{'='*80}\n")
    
    total = len(problems)
    print(f"全部失败（avg=0.0）：{all_zero:2d} 个 ({all_zero/total*100:5.1f}%)")
    print(f"全部成功（avg=1.0）：{all_one:2d} 个 ({all_one/total*100:5.1f}%)")
    print(f"部分成功（0<avg<1）：{partial:2d} 个 ({partial/total*100:5.1f}%)")
    print()
    
    filtered = all_zero + all_one
    print(f"{'='*80}")
    print(f"🚨 当前筛选逻辑：只提取 0 < avg_score < 1 的问题")
    print(f"{'='*80}\n")
    print(f"✅ 会生成经验的问题：{partial} 个 ({partial/total*100:.1f}%)")
    print(f"❌ 被过滤掉的问题：{filtered} 个 ({filtered/total*100:.1f}%)")
    print()
    print(f"🔥 损失率：{filtered/total*100:.1f}% 的问题无法学习！")
    print()
    
    # 评估影响
    if filtered / total > 0.5:
        print("⚠️ 严重问题：超过 50% 的问题被过滤，严重影响学习效果！")
    elif filtered / total > 0.3:
        print("⚠️ 显著问题：超过 30% 的问题被过滤，明显影响学习效果")
    else:
        print("✅ 轻微影响：少于 30% 的问题被过滤")
    
    print()
    print(f"{'='*80}")
    print("建议")
    print(f"{'='*80}\n")
    
    if filtered / total > 0.5:
        print("1. 立即修改经验提取逻辑，允许处理所有样本（包括全对和全错）")
        print("2. 重新训练以获得完整的经验库")
        print("3. 预期改善：经验样本量增加 {:.1f}x，准确率提升 10-20%".format(total / partial if partial > 0 else 1))
    else:
        print("当前筛选逻辑影响较小，可以继续使用")
    
    print()


def main():
    parser = argparse.ArgumentParser(description="分析经验提取的筛选情况")
    parser.add_argument(
        "--exp_id",
        type=str,
        required=True,
        help="实验 ID（例如：wordle_practice_20_3）"
    )
    parser.add_argument(
        "--grpo_n",
        type=int,
        default=3,
        help="GRPO-N 值（每个问题的样本数，默认 3）"
    )
    
    args = parser.parse_args()
    
    analyze_filtering(args.exp_id, args.grpo_n)


if __name__ == "__main__":
    main()
