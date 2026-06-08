"""
诊断 ZebraLogic 评估问题
Diagnose ZebraLogic evaluation issues
"""

import sys
from pathlib import Path
from sqlmodel import select

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def diagnose_evaluation(exp_id="logic_zebralogic_test_eval"):
    """诊断评估结果"""
    with SQLModelUtils.create_session() as session:
        samples = session.exec(
            select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
        ).all()
        
        if not samples:
            print(f"❌ 未找到实验 '{exp_id}' 的数据")
            return
        
        print(f"\n{'=' * 70}")
        print(f"诊断实验: {exp_id}")
        print(f"{'=' * 70}\n")
        
        # 检查总体情况
        print(f"📊 总体情况:")
        print(f"  总样本数: {len(samples)}")
        
        # 检查 reward 分布
        reward_none = sum(1 for s in samples if s.reward is None)
        reward_zero = sum(1 for s in samples if s.reward == 0.0)
        reward_positive = sum(1 for s in samples if s.reward and s.reward > 0)
        
        print(f"\n📈 Reward 分布:")
        print(f"  reward = None:     {reward_none} ({reward_none/len(samples)*100:.1f}%)")
        print(f"  reward = 0.0:      {reward_zero} ({reward_zero/len(samples)*100:.1f}%)")
        print(f"  reward > 0:        {reward_positive} ({reward_positive/len(samples)*100:.1f}%)")
        
        # 检查 correct 字段
        correct_true = sum(1 for s in samples if s.correct is True)
        correct_false = sum(1 for s in samples if s.correct is False)
        correct_none = sum(1 for s in samples if s.correct is None)
        
        print(f"\n✅ Correct 分布:")
        print(f"  correct = True:    {correct_true} ({correct_true/len(samples)*100:.1f}%)")
        print(f"  correct = False:   {correct_false} ({correct_false/len(samples)*100:.1f}%)")
        print(f"  correct = None:    {correct_none} ({correct_none/len(samples)*100:.1f}%)")
        
        # 检查是否有响应
        no_response = sum(1 for s in samples if not s.response)
        
        print(f"\n📝 响应情况:")
        print(f"  有响应:            {len(samples) - no_response}")
        print(f"  无响应:            {no_response}")
        
        # 抽样检查几个样本
        print(f"\n🔍 样本抽查 (前 3 个):")
        for i, sample in enumerate(samples[:3], 1):
            print(f"\n--- 样本 {i} ---")
            print(f"问题: {sample.raw_question[:100]}...")
            print(f"正确答案: {sample.correct_answer[:100] if sample.correct_answer else 'None'}...")
            print(f"模型响应: {sample.response[:200] if sample.response else 'None'}...")
            print(f"Reward: {sample.reward}")
            print(f"Correct: {sample.correct}")
            print(f"Judged Response: {sample.judged_response}")
        
        # 检查判断响应
        judged_correct = sum(1 for s in samples if s.judged_response == "Correct")
        judged_incorrect = sum(1 for s in samples if s.judged_response == "Incorrect")
        judged_other = len(samples) - judged_correct - judged_incorrect
        
        print(f"\n📊 Judged Response 分布:")
        print(f"  'Correct':         {judged_correct} ({judged_correct/len(samples)*100:.1f}%)")
        print(f"  'Incorrect':       {judged_incorrect} ({judged_incorrect/len(samples)*100:.1f}%)")
        print(f"  其他:              {judged_other} ({judged_other/len(samples)*100:.1f}%)")
        
        print(f"\n{'=' * 70}\n")
        
        # 诊断问题
        print("🔧 问题诊断:")
        
        if reward_positive == 0:
            print("\n❌ 问题: 所有 reward 都是 0 或 None")
            print("   可能原因:")
            print("   1. 验证函数加载失败（使用了 LLM judge）")
            print("   2. 模型输出格式不匹配验证函数期望")
            print("   3. 验证函数逻辑有问题")
            print("   4. Ground truth 格式不匹配")
            
            print("\n   建议排查:")
            print("   1. 检查评估日志中是否有 'Successfully loaded verification function'")
            print("   2. 查看模型响应格式是否包含 \\boxed{} 或 <answer> 标签")
            print("   3. 检查 ground truth 是否是 JSON 字符串")
            print("   4. 手动测试验证函数:")
            print("      uv run python scripts/test_logic_verifier.py")
        
        if no_response > 0:
            print(f"\n⚠️  有 {no_response} 个样本没有模型响应")
            print("   可能原因: 模型 API 调用失败或超时")
        
        if reward_none > 0:
            print(f"\n⚠️  有 {reward_none} 个样本的 reward 是 None")
            print("   可能原因: 验证函数返回了 None 或判断过程失败")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="诊断 ZebraLogic 评估问题")
    parser.add_argument(
        "--exp_id",
        type=str,
        default="logic_zebralogic_test_eval",
        help="实验 ID"
    )
    
    args = parser.parse_args()
    diagnose_evaluation(args.exp_id)

