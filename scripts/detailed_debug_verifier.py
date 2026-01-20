#!/usr/bin/env python3
"""详细调试验证函数的每一步"""

import json
from sqlmodel import select

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def detailed_debug():
    """详细调试每一步"""
    
    print("\n" + "="*80)
    print("详细调试验证流程")
    print("="*80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        # 只获取第一个样本进行详细分析
        statement = select(EvaluationSample).where(
            EvaluationSample.exp_id == "logic_zebralogic_test_eval"
        ).limit(1)
        samples = list(session.exec(statement))
        
        if not samples:
            print("❌ 未找到评估数据")
            return
        
        sample = samples[0]
        
        print("📝 完整的模型输出:")
        print("-"*80)
        print(sample.response)
        print("-"*80)
        print()
        
        print("✅ 标准答案:")
        print(sample.correct_answer)
        print()
        
        # 手动测试提取
        from utu.practice.verify.logic import (
            _extract_answer_from_response,
            _parse_ground_truth,
            _compare_answers,
            _extract_table_from_text,
        )
        
        print("🔧 步骤1: 提取答案")
        extracted = _extract_answer_from_response(sample.response)
        print(f"  类型: {type(extracted)}")
        print(f"  内容: {str(extracted)[:500]}")
        print()
        
        print("🔧 步骤2: 解析标准答案")
        parsed_gt = _parse_ground_truth(sample.correct_answer)
        print(f"  类型: {type(parsed_gt)}")
        if isinstance(parsed_gt, dict):
            print(f"  Headers: {parsed_gt.get('header', [])}")
            print(f"  Rows: {len(parsed_gt.get('rows', []))} rows")
            print(f"  Row 1: {parsed_gt.get('rows', [[]])[0]}")
        print()
        
        print("🔧 步骤3: 尝试从文本提取表格")
        if isinstance(extracted, str):
            table = _extract_table_from_text(extracted, parsed_gt)
            if table:
                print(f"  ✅ 成功提取表格!")
                print(f"  Headers: {table.get('header', [])}")
                print(f"  Rows: {len(table.get('rows', []))} rows")
                for i, row in enumerate(table.get('rows', []), 1):
                    print(f"  Row {i}: {row}")
            else:
                print(f"  ❌ 无法提取表格")
                
                # 尝试找到包含 "House" 的行
                print(f"\n  尝试手动查找...")
                import re
                pattern = r"[Hh]ouse\s+(\d+):\s*([^{};\n]+?)(?=(?:[Hh]ouse\s+\d+:|[;}]|$))"
                matches = re.findall(pattern, str(extracted), re.DOTALL)
                print(f"  找到 {len(matches)} 个匹配:")
                for house_num, house_data in matches[:4]:
                    print(f"    House {house_num}: {house_data[:100]}")
        print()
        
        print("🔧 步骤4: 比较答案")
        is_correct = _compare_answers(extracted, parsed_gt)
        print(f"  结果: {'✅ 正确' if is_correct else '❌ 错误'}")
        print()


if __name__ == "__main__":
    detailed_debug()

