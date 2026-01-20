#!/usr/bin/env python3
"""分析基线评估的失败原因"""
import json
import sys

def analyze_failures(json_file):
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    print("=" * 80)
    print("失败分析（前10个案例）")
    print("=" * 80)
    
    for i, case in enumerate(data['detailed_results'][:10]):
        action = case['action']
        score = case['score']
        seed = case['seed']
        
        length = len(action) if action else 0
        status = "✓" if score > 0 else "✗"
        
        print(f"\n{status} Seed {seed}: '{action}' ({length}字母) - Score: {score}")
    
    # 统计错误类型
    wrong_len = sum(1 for c in data['detailed_results'] if c['action'] and len(c['action']) != 9)
    no_answer = sum(1 for c in data['detailed_results'] if not c['action'])
    correct_len = sum(1 for c in data['detailed_results'] if c['action'] and len(c['action']) == 9 and c['score'] == 0)
    success = sum(1 for c in data['detailed_results'] if c['score'] > 0)
    
    total = len(data['detailed_results'])
    
    print("\n" + "=" * 80)
    print("错误统计")
    print("=" * 80)
    print(f"✓ 成功: {success}/{total} ({success/total*100:.1f}%)")
    print(f"✗ 长度错误: {wrong_len} ({wrong_len/total*100:.1f}%)")
    print(f"✗ 没答案: {no_answer} ({no_answer/total*100:.1f}%)")
    print(f"✗ 长度对但验证失败: {correct_len} ({correct_len/total*100:.1f}%)")
    
    # 查看一个成功案例的response
    if success > 0:
        success_case = [c for c in data['detailed_results'] if c['score'] > 0][0]
        print("\n" + "=" * 80)
        print("✓ 成功案例分析")
        print("=" * 80)
        print(f"Seed: {success_case['seed']}")
        print(f"答案: {success_case['action']}")
        print(f"\nResponse最后300字符:")
        print(success_case['response'][-300:])
    
    # 查看一个长度对但失败的案例
    if correct_len > 0:
        failed_9letter = [c for c in data['detailed_results'] if c['action'] and len(c['action']) == 9 and c['score'] == 0][0]
        print("\n" + "=" * 80)
        print("✗ 9字母但失败案例（可能是假词或路径错误）")
        print("=" * 80)
        print(f"Seed: {failed_9letter['seed']}")
        print(f"答案: {failed_9letter['action']}")
        print(f"\nResponse最后300字符:")
        print(failed_9letter['response'][-300:])
    
    # 查看一个长度错误的案例
    if wrong_len > 0:
        wrong_case = [c for c in data['detailed_results'] if c['action'] and len(c['action']) != 9][0]
        print("\n" + "=" * 80)
        print("✗ 长度错误案例")
        print("=" * 80)
        print(f"Seed: {wrong_case['seed']}")
        print(f"答案: {wrong_case['action']} ({len(wrong_case['action'])}字母，应该是9)")
        print(f"\nResponse最后300字符:")
        print(wrong_case['response'][-300:])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        json_file = 'workspace/korgym_eval/alphabetical_sorting_baseline_50.json'
    
    analyze_failures(json_file)





