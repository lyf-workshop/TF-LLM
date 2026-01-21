#!/usr/bin/env python3
"""测试改进后的 logic.py 验证函数"""

import json
from sqlmodel import select

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils
from utu.practice.verify.logic import verify_func


def test_verification():
    """测试完整的验证流程"""
    
    print("\n" + "="*80)
    print("测试改进后的验证函数")
    print("="*80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        # 获取一些评估样本
        statement = select(EvaluationSample).where(
            EvaluationSample.exp_id == "logic_zebralogic_test_eval"
        ).limit(10)
        samples = list(session.exec(statement))
        
        if not samples:
            print("❌ 未找到评估数据")
            return
        
        print(f"找到 {len(samples)} 个样本，开始测试验证函数...\n")
        
        correct_count = 0
        
        for i, sample in enumerate(samples, 1):
            print(f"样本 #{i}:")
            print(f"  索引: {sample.dataset_index}")
            print(f"  当前 reward: {sample.reward}")
            
            # 调用验证函数
            result = verify_func(sample)
            
            new_reward = result.get("reward", 0.0)
            reasoning = result.get("reasoning")
            
            print(f"  验证结果:")
            print(f"    新 reward: {new_reward}")
            if reasoning:
                print(f"    reasoning: {reasoning}")
            
            if new_reward > 0.5:
                print(f"  ✅ 正确!")
                correct_count += 1
            else:
                print(f"  ❌ 错误")
                
                # 显示更多调试信息
                if sample.response:
                    # 尝试找到答案部分
                    response_lines = sample.response.split('\n')
                    # 找包含 "House" 的行
                    house_lines = [line for line in response_lines if 'House' in line and ':' in line]
                    if house_lines:
                        print(f"  模型输出中的关键行:")
                        for line in house_lines[:5]:  # 只显示前5行
                            print(f"    {line[:100]}")
                
                # 显示标准答案
                if sample.correct_answer:
                    try:
                        gt = json.loads(sample.correct_answer)
                        print(f"  标准答案 (第一行): {gt['rows'][0] if 'rows' in gt and gt['rows'] else 'N/A'}")
                    except:
                        pass
            
            print()
        
        print("="*80)
        print(f"总结: {correct_count}/{len(samples)} 正确 ({correct_count/len(samples)*100:.1f}%)")
        print("="*80 + "\n")


if __name__ == "__main__":
    test_verification()

