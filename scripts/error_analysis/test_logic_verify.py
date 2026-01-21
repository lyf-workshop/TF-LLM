#!/usr/bin/env python3
"""
Test script for logic verification functions.

This script provides a simple way to test both basic and enhanced logic verifiers
without requiring pytest setup.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.practice.verify.logic import verify_func as basic_verify_func
from utu.practice.verify.logic_with_error_analysis import verify_func as enhanced_verify_func


def test_basic_verifier():
    """Test the basic logic verifier."""
    print("\n" + "="*70)
    print("Testing Basic Logic Verifier (logic.py)")
    print("="*70)
    
    # Test 1: Correct JSON table answer
    print("\n[Test 1] Correct JSON table answer")
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Alice", "Red"],
            ["2", "Bob", "Blue"],
            ["3", "Charlie", "Green"]
        ]
    }
    
    correct_response = f"""
    <answer>
    {json.dumps(ground_truth, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="test",
        response=correct_response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result = basic_verify_func(sample)
    print(f"  Result: reward={result['reward']}, reasoning={result.get('reasoning')}")
    assert result['reward'] == 1.0, "Should return reward=1.0 for correct answer"
    print("  ✓ Passed")
    
    # Test 2: Incorrect JSON table answer
    print("\n[Test 2] Incorrect JSON table answer")
    wrong_answer = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Alice", "Blue"],  # Wrong color
            ["2", "Bob", "Red"],
            ["3", "Charlie", "Green"]
        ]
    }
    
    wrong_response = f"<answer>{json.dumps(wrong_answer)}</answer>"
    sample_wrong = EvaluationSample(
        dataset="test",
        response=wrong_response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result_wrong = basic_verify_func(sample_wrong)
    print(f"  Result: reward={result_wrong['reward']}")
    assert result_wrong['reward'] == 0.0, "Should return reward=0.0 for wrong answer"
    print("  ✓ Passed")
    
    # Test 3: Boxed format
    print("\n[Test 3] Boxed format extraction")
    response_boxed = r"After analysis: \boxed{42}"
    sample_boxed = EvaluationSample(
        dataset="test",
        response=response_boxed,
        correct_answer="42"
    )
    
    result_boxed = basic_verify_func(sample_boxed)
    print(f"  Result: reward={result_boxed['reward']}")
    assert result_boxed['reward'] == 1.0, "Should extract from \\boxed{}"
    print("  ✓ Passed")
    
    # Test 4: Empty response
    print("\n[Test 4] Empty response handling")
    sample_empty = EvaluationSample(
        dataset="test",
        response="",
        correct_answer="42"
    )
    
    result_empty = basic_verify_func(sample_empty)
    print(f"  Result: reward={result_empty['reward']}")
    assert result_empty['reward'] == 0.0, "Should handle empty response"
    print("  ✓ Passed")
    
    print("\n✅ All basic verifier tests passed!")


def test_enhanced_verifier():
    """Test the enhanced logic verifier with error analysis."""
    print("\n" + "="*70)
    print("Testing Enhanced Logic Verifier (logic_with_error_analysis.py)")
    print("="*70)
    
    # Test 1: Correct answer (no error analysis needed)
    print("\n[Test 1] Correct answer (no error analysis)")
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Blue"],
            ["3", "Eric", "Green"]
        ]
    }
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=f"<answer>{json.dumps(ground_truth)}</answer>",
        correct_answer=json.dumps(ground_truth)
    )
    
    result = enhanced_verify_func(sample, enable_error_analysis=True)
    print(f"  Result: reward={result['reward']}, reasoning={result.get('reasoning')}")
    assert result['reward'] == 1.0, "Should return 1.0 for correct answer"
    print("  ✓ Passed")
    
    # Test 2: Incorrect answer with error analysis
    print("\n[Test 2] Incorrect answer with error analysis")
    wrong_answer = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Peter", "Red"],
            ["2", "Alice", "Red"],  # Duplicate color
            ["3", "Eric", "Green"]
        ]
    }
    
    sample_wrong = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=f"""
        House 1: Peter, Red
        House 2: Alice, Red  (Duplicate!)
        
        <answer>
        {json.dumps(wrong_answer)}
        </answer>
        """,
        correct_answer=json.dumps(ground_truth)
    )
    
    result_wrong = enhanced_verify_func(sample_wrong, enable_error_analysis=True)
    print(f"  Result: reward={result_wrong['reward']}")
    print(f"  Reasoning: {result_wrong.get('reasoning', 'None')[:100]}...")
    assert result_wrong['reward'] == 0.0, "Should return 0.0 for wrong answer"
    
    # Error analysis may or may not be available
    if result_wrong.get('reasoning'):
        print(f"  ✓ Error analysis provided ({len(result_wrong['reasoning'])} chars)")
    else:
        print("  ⚠ Error analysis not available (LogicErrorAnalyzer may not be configured)")
    print("  ✓ Passed")
    
    # Test 3: Error analysis disabled
    print("\n[Test 3] Error analysis disabled")
    result_disabled = enhanced_verify_func(sample_wrong, enable_error_analysis=False)
    print(f"  Result: reward={result_disabled['reward']}, reasoning={result_disabled.get('reasoning')}")
    assert result_disabled['reward'] == 0.0
    print("  ✓ Passed")
    
    # Test 4: Detailed errors flag
    print("\n[Test 4] Detailed errors flag")
    result_detailed = enhanced_verify_func(
        sample_wrong,
        enable_error_analysis=True,
        detailed_errors=True
    )
    print(f"  Result: reward={result_detailed['reward']}")
    if result_detailed.get('detailed_errors'):
        print(f"  ✓ Detailed errors provided: {len(result_detailed['detailed_errors'])} error types")
    if result_detailed.get('total_errors'):
        print(f"  ✓ Total errors: {result_detailed['total_errors']}")
    print("  ✓ Passed")
    
    print("\n✅ All enhanced verifier tests passed!")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("Logic Verification Functions Test Suite")
    print("="*70)
    
    try:
        test_basic_verifier()
        test_enhanced_verifier()
        
        print("\n" + "="*70)
        print("✅ All tests passed!")
        print("="*70)
        print("\nBoth verification functions are working correctly.")
        print("You can now use them in your ZebraLogic training pipeline.")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()










































































