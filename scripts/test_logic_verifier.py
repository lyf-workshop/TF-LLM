#!/usr/bin/env python3
"""
Test script for logic puzzle verifier
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.practice.verify.logic import verify_func


def test_json_table_answer():
    """Test verification with JSON table format (ZebraLogic style)"""
    print("\n" + "="*60)
    print("Test 1: JSON Table Answer")
    print("="*60)
    
    # Ground truth in JSON format
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Alice", "Red"],
            ["2", "Bob", "Blue"],
            ["3", "Charlie", "Green"]
        ]
    }
    
    # Correct prediction
    correct_response = f"""
    Let me solve this step by step...
    
    <answer>
    {json.dumps(ground_truth, ensure_ascii=False)}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="test",
        response=correct_response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result = verify_func(sample)
    print(f"Correct answer test: reward={result['reward']}")
    assert result['reward'] == 1.0, "Should return reward=1.0 for correct answer"
    
    # Incorrect prediction (wrong data)
    wrong_ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [
            ["1", "Alice", "Blue"],  # Wrong color
            ["2", "Bob", "Red"],
            ["3", "Charlie", "Green"]
        ]
    }
    
    wrong_response = f"""
    <answer>
    {json.dumps(wrong_ground_truth, ensure_ascii=False)}
    </answer>
    """
    
    sample_wrong = EvaluationSample(
        dataset="test",
        response=wrong_response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result_wrong = verify_func(sample_wrong)
    print(f"Wrong answer test: reward={result_wrong['reward']}")
    assert result_wrong['reward'] == 0.0, "Should return reward=0.0 for wrong answer"
    
    print("✓ JSON table tests passed!")


def test_boxed_format():
    """Test extraction from \\boxed{} format"""
    print("\n" + "="*60)
    print("Test 2: Boxed Format")
    print("="*60)
    
    ground_truth = "42"
    
    response = r"""
    After careful analysis, the answer is:
    \boxed{42}
    """
    
    sample = EvaluationSample(
        dataset="test",
        response=response,
        correct_answer=ground_truth
    )
    
    result = verify_func(sample)
    print(f"Boxed format test: reward={result['reward']}")
    assert result['reward'] == 1.0, "Should extract answer from \\boxed{}"
    
    print("✓ Boxed format test passed!")


def test_simple_text_comparison():
    """Test simple text comparison"""
    print("\n" + "="*60)
    print("Test 3: Simple Text Comparison")
    print("="*60)
    
    ground_truth = "The answer is Paris"
    
    # Exact match (case-insensitive)
    response1 = "<answer>the answer is paris</answer>"
    sample1 = EvaluationSample(
        dataset="test",
        response=response1,
        correct_answer=ground_truth
    )
    result1 = verify_func(sample1)
    print(f"Case-insensitive match: reward={result1['reward']}")
    assert result1['reward'] == 1.0, "Should match case-insensitively"
    
    # Partial match (answer contains ground truth)
    response2 = "<answer>After analysis, the answer is Paris, the capital of France</answer>"
    sample2 = EvaluationSample(
        dataset="test",
        response=response2,
        correct_answer=ground_truth
    )
    result2 = verify_func(sample2)
    print(f"Partial match test: reward={result2['reward']}")
    assert result2['reward'] == 1.0, "Should match when answer contains ground truth"
    
    # Wrong answer
    response3 = "<answer>London</answer>"
    sample3 = EvaluationSample(
        dataset="test",
        response=response3,
        correct_answer=ground_truth
    )
    result3 = verify_func(sample3)
    print(f"Wrong answer test: reward={result3['reward']}")
    assert result3['reward'] == 0.0, "Should not match wrong answer"
    
    print("✓ Text comparison tests passed!")


def test_error_handling():
    """Test error handling"""
    print("\n" + "="*60)
    print("Test 4: Error Handling")
    print("="*60)
    
    # Empty response
    sample1 = EvaluationSample(
        dataset="test",
        response="",
        correct_answer="42"
    )
    result1 = verify_func(sample1)
    print(f"Empty response: reward={result1['reward']}")
    
    # Malformed JSON
    sample2 = EvaluationSample(
        dataset="test",
        response='<answer>{"invalid json"</answer>',
        correct_answer='{"valid": "json"}'
    )
    result2 = verify_func(sample2)
    print(f"Malformed JSON: reward={result2['reward']}")
    
    print("✓ Error handling tests passed!")


def test_real_zebralogic_example():
    """Test with real ZebraLogic-style example"""
    print("\n" + "="*60)
    print("Test 5: Real ZebraLogic Example")
    print("="*60)
    
    # Simulated ground truth from ZebraLogic
    ground_truth = {
        "header": ["House", "Name", "Vacation", "Birthday", "Nationality"],
        "rows": [
            ["1", "Peter", "city", "april", "brit"],
            ["2", "Alice", "mountain", "feb", "norwegian"],
            ["3", "Eric", "cruise", "jan", "swede"],
            ["4", "Arnold", "beach", "sept", "dane"]
        ]
    }
    
    # Model response with reasoning and table
    response = """
    Based on the clues provided, I can deduce the following:
    
    1. Eric is in the third house (clue 9)
    2. Peter's birthday is in April (clue 10)
    3. The Dane's birthday is in September (clue 11)
    
    After working through all clues systematically, the solution is:
    
    <answer>
    {"header": ["House", "Name", "Vacation", "Birthday", "Nationality"], 
     "rows": [["1", "Peter", "city", "april", "brit"], 
              ["2", "Alice", "mountain", "feb", "norwegian"], 
              ["3", "Eric", "cruise", "jan", "swede"], 
              ["4", "Arnold", "beach", "sept", "dane"]]}
    </answer>
    """
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=response,
        correct_answer=json.dumps(ground_truth)
    )
    
    result = verify_func(sample)
    print(f"Real ZebraLogic example: reward={result['reward']}")
    assert result['reward'] == 1.0, "Should verify real ZebraLogic answer correctly"
    
    print("✓ Real ZebraLogic test passed!")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Testing Logic Puzzle Verifier")
    print("="*60)
    
    try:
        test_json_table_answer()
        test_boxed_format()
        test_simple_text_comparison()
        test_error_handling()
        test_real_zebralogic_example()
        
        print("\n" + "="*60)
        print("✅ All tests passed!")
        print("="*60)
        
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

