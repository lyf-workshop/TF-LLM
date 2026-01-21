#!/usr/bin/env python3
"""调试 logic.py 验证函数"""

import json
from sqlmodel import select

from utu.db.eval_datapoint import EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils
from utu.practice.verify.logic import (
    _extract_answer_from_response,
    _parse_ground_truth,
    _compare_answers,
)


def debug_verification():
    """调试验证逻辑"""
    
    print("\n" + "="*80)
    print("调试 logic.py 验证函数")
    print("="*80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        # 获取一些评估样本
        statement = select(EvaluationSample).where(
            EvaluationSample.exp_id == "logic_zebralogic_test_eval"
        ).limit(5)
        samples = list(session.exec(statement))
        
        if not samples:
            print("❌ 未找到评估数据")
            return
        
        print(f"找到 {len(samples)} 个样本，开始调试...\n")
        
        for i, sample in enumerate(samples, 1):
            print(f"{'='*80}")
            print(f"样本 #{i}")
            print(f"{'='*80}\n")
            
            print(f"📊 基本信息:")
            print(f"  数据集: {sample.dataset}")
            print(f"  索引: {sample.dataset_index}")
            print(f"  当前 reward: {sample.reward}")
            print()
            
            # 检查字段是否存在
            print(f"🔍 字段检查:")
            print(f"  sample.response 存在: {hasattr(sample, 'response')}")
            print(f"  sample.response 为空: {sample.response is None or sample.response == ''}")
            print(f"  sample.correct_answer 存在: {hasattr(sample, 'correct_answer')}")
            print(f"  sample.correct_answer 为空: {sample.correct_answer is None or sample.correct_answer == ''}")
            print()
            
            if not sample.response:
                print("⚠️ 模型输出为空！")
                print("-"*80 + "\n")
                continue
            
            if not sample.correct_answer:
                print("⚠️ 标准答案为空！")
                print("-"*80 + "\n")
                continue
            
            # 显示原始数据（截断）
            print(f"📝 模型输出（前500字符）:")
            print(f"{sample.response[:500]}")
            if len(sample.response) > 500:
                print(f"... (还有 {len(sample.response) - 500} 字符)")
            print()
            
            print(f"✅ 标准答案（前300字符）:")
            print(f"{sample.correct_answer[:300]}")
            if len(sample.correct_answer) > 300:
                print(f"... (还有 {len(sample.correct_answer) - 300} 字符)")
            print()
            
            # 步骤1: 提取答案
            print(f"🔧 步骤1: 提取模型答案")
            extracted = _extract_answer_from_response(sample.response)
            print(f"  提取结果: {extracted[:200]}")
            if len(extracted) > 200:
                print(f"  ... (还有 {len(extracted) - 200} 字符)")
            print()
            
            # 步骤2: 解析标准答案
            print(f"🔧 步骤2: 解析标准答案")
            parsed_gt = _parse_ground_truth(sample.correct_answer)
            print(f"  类型: {type(parsed_gt)}")
            if isinstance(parsed_gt, dict):
                print(f"  字典内容:")
                print(f"    keys: {list(parsed_gt.keys())}")
                if "header" in parsed_gt:
                    print(f"    header: {parsed_gt['header']}")
                if "rows" in parsed_gt:
                    print(f"    rows 数量: {len(parsed_gt['rows'])}")
                    print(f"    第一行: {parsed_gt['rows'][0] if parsed_gt['rows'] else 'N/A'}")
            else:
                print(f"  内容: {str(parsed_gt)[:200]}")
            print()
            
            # 步骤3: 尝试解析提取的答案为 JSON
            print(f"🔧 步骤3: 尝试将提取的答案解析为 JSON")
            try:
                extracted_json = json.loads(extracted)
                print(f"  ✅ 成功解析为 JSON")
                print(f"  类型: {type(extracted_json)}")
                if isinstance(extracted_json, dict):
                    print(f"  keys: {list(extracted_json.keys())}")
            except json.JSONDecodeError as e:
                print(f"  ❌ 无法解析为 JSON: {e}")
                print(f"  将使用字符串比较")
            print()
            
            # 步骤4: 比较
            print(f"🔧 步骤4: 比较答案")
            is_correct = _compare_answers(extracted, parsed_gt)
            print(f"  结果: {'✅ 正确' if is_correct else '❌ 错误'}")
            print()
            
            print("-"*80 + "\n")


if __name__ == "__main__":
    debug_verification()

