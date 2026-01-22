#!/usr/bin/env python3
"""
调试脚本：检查 Wordle 评估是否正确保存了多轮交互的最终结果

这个脚本会检查数据库中的样本数据，验证：
1. meta 中是否有 multiround_result
2. multiround_result 是否包含完整的游戏信息（rounds, final_score, success）
3. correct 和 reward 是否正确设置为最终结果
4. 是否只记录了第一轮的结果（错误情况）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.utils import SQLModelUtils, get_logger
from utu.db import EvaluationSample
from sqlmodel import select
import json
import argparse

logger = get_logger(__name__)


def debug_multiround_results(exp_id: str, sample_limit: int = 5):
    """
    调试多轮交互结果的存储
    
    Args:
        exp_id: 实验ID
        sample_limit: 检查的样本数量
    """
    print("=" * 80)
    print("🔍 Wordle 多轮交互结果调试")
    print("=" * 80)
    print(f"实验ID: {exp_id}")
    print(f"检查样本数: {sample_limit}")
    print()
    
    with SQLModelUtils.create_session() as session:
        # 获取样本
        samples = session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id
            ).order_by(EvaluationSample.id).limit(sample_limit)
        ).all()
        
        if not samples:
            print(f"❌ 未找到实验结果: {exp_id}\n")
            return
        
        print(f"✓ 找到 {len(samples)} 个样本")
        print()
        
        # 检查每个样本
        issues_found = []
        
        for i, sample in enumerate(samples, 1):
            print("=" * 80)
            print(f"样本 {i} (ID: {sample.id})")
            print("=" * 80)
            
            # 基本信息
            print(f"✓ exp_id: {sample.exp_id}")
            print(f"✓ correct: {sample.correct}")
            print(f"✓ reward: {sample.reward}")
            print()
            
            # 检查 meta
            if not sample.meta:
                print("❌ 错误: meta 为空！")
                issues_found.append(f"样本 {i}: meta 为空")
                continue
            
            meta = sample.meta
            print(f"✓ meta 存在")
            
            # 检查 game_name
            game_name = meta.get('game_name', 'Unknown')
            print(f"  - game_name: {game_name}")
            
            if game_name != '33-wordle':
                print(f"  ⚠️  游戏不是 Wordle")
            
            # 检查 seed
            seed = meta.get('seed') or meta.get('game_seed')
            print(f"  - seed: {seed}")
            
            # 🔥 关键检查：是否有 multiround_result
            if 'multiround_result' not in meta:
                print()
                print("❌ 严重错误: meta 中没有 'multiround_result'！")
                print("   这意味着可能没有执行完整的多轮交互！")
                issues_found.append(f"样本 {i}: 缺少 multiround_result")
                print()
                
                # 检查是否只有第一轮的 response
                if sample.response:
                    print(f"  - response 长度: {len(sample.response)} 字符")
                    print(f"  - response 预览: {sample.response[:100]}...")
                
                continue
            
            # 检查 multiround_result 的内容
            multiround_result = meta['multiround_result']
            print()
            print("✓ multiround_result 存在")
            print(f"  - final_score: {multiround_result.get('final_score')}")
            print(f"  - success: {multiround_result.get('success')}")
            print(f"  - rounds: {multiround_result.get('rounds')}")
            print(f"  - is_end: {multiround_result.get('is_end')}")
            
            # 检查 responses（多轮响应）
            responses = multiround_result.get('responses', [])
            print(f"  - responses 数量: {len(responses)}")
            
            if len(responses) == 0:
                print("    ⚠️  没有 responses！")
                issues_found.append(f"样本 {i}: 没有 responses")
            elif len(responses) == 1:
                print("    ⚠️  只有 1 个 response - 可能只执行了第一轮！")
                issues_found.append(f"样本 {i}: 只有 1 个 response")
            else:
                print(f"    ✓ 有 {len(responses)} 个 responses - 多轮交互正常")
                
                # 显示每轮的响应摘要
                for j, resp in enumerate(responses[:3], 1):  # 只显示前3轮
                    resp_preview = resp[:50] if isinstance(resp, str) else str(resp)[:50]
                    print(f"      Round {j}: {resp_preview}...")
            
            # 检查 trajectory
            trajectory = multiround_result.get('trajectory', [])
            print(f"  - trajectory 长度: {len(trajectory)}")
            
            if len(trajectory) == 0:
                print("    ⚠️  没有 trajectory！")
            elif len(trajectory) == 1:
                print("    ⚠️  只有 1 个 trajectory - 可能只执行了第一轮！")
            else:
                print(f"    ✓ 有 {len(trajectory)} 个 trajectory - 多轮交互正常")
            
            # 🔥 核心验证：final_score 是否等于 reward
            final_score = multiround_result.get('final_score', 0)
            if abs(final_score - sample.reward) > 0.001:
                print()
                print(f"❌ 不一致: final_score ({final_score}) != reward ({sample.reward})")
                issues_found.append(f"样本 {i}: final_score 和 reward 不一致")
            else:
                print(f"  ✓ final_score 和 reward 一致")
            
            # 检查 success 和 correct 是否一致
            success = multiround_result.get('success', False)
            if success != sample.correct:
                print(f"❌ 不一致: success ({success}) != correct ({sample.correct})")
                issues_found.append(f"样本 {i}: success 和 correct 不一致")
            else:
                print(f"  ✓ success 和 correct 一致")
            
            # 检查 trajectories 字段（JSON字符串）
            print()
            if sample.trajectories:
                try:
                    traj_data = json.loads(sample.trajectories)
                    print(f"✓ trajectories 字段存在 (长度: {len(traj_data)})")
                except json.JSONDecodeError:
                    print(f"⚠️  trajectories 字段存在但无法解析")
            else:
                print(f"⚠️  trajectories 字段为空")
            
            print()
        
        # 总结
        print("=" * 80)
        print("🔍 检查总结")
        print("=" * 80)
        
        if not issues_found:
            print("✅ 所有样本都正确保存了多轮交互的最终结果！")
            print()
            print("这意味着：")
            print("  - 多轮交互正常执行")
            print("  - final_score 是 10 轮交互后的最终得分")
            print("  - correct 和 reward 反映的是最终结果")
            print("  - analyze_wordle_top20.py 和 view_korgym_results.py 读取的是正确的最终结果")
        else:
            print(f"❌ 发现 {len(issues_found)} 个问题：")
            for issue in issues_found:
                print(f"  - {issue}")
            print()
            print("这可能意味着：")
            print("  - 多轮交互没有正常执行")
            print("  - 只保存了第一轮的结果")
            print("  - 需要检查 rollout 和 judge 阶段的代码")
        
        print("=" * 80)
        print()


def main():
    parser = argparse.ArgumentParser(
        description="调试 Wordle 多轮交互结果的存储",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--exp_id", "-e",
        type=str,
        required=True,
        help="实验ID (例如: wordle_practice_20_eval)"
    )
    
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=5,
        help="检查的样本数量 (默认: 5)"
    )
    
    args = parser.parse_args()
    
    debug_multiround_results(args.exp_id, args.limit)


if __name__ == "__main__":
    main()

