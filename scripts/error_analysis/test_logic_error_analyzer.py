#!/usr/bin/env python3
"""
Test script for Logic Error Analyzer

This script tests the error detection capabilities of the LogicErrorAnalyzer
with various types of logical errors commonly found in ZebraLogic reasoning.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from scripts.logic_error_analyzer import LogicErrorAnalyzer, verify_func_with_error_analysis


def test_constraint_violation():
    """Test detection of constraint violations (duplicate assignments)."""
    print("\n" + "="*70)
    print("Test 1: Constraint Violation Detection")
    print("="*70)
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response="""
Let me solve this step by step:

1. From the clues, I determine:
   - House 1: Peter, Red
   - House 2: Alice, Red  (ERROR: Red already assigned to House 1!)
   - House 3: Eric, Green

<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Peter", "Red"], 
          ["2", "Alice", "Red"], 
          ["3", "Eric", "Green"]]}
</answer>
""",
        correct_answer=json.dumps({
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Blue"],
                ["3", "Eric", "Green"]
            ]
        })
    )
    
    analyzer = LogicErrorAnalyzer()
    result = analyzer.analyze_reasoning(sample)
    
    print(f"✓ Errors detected: {result['total_errors']}")
    print(f"✓ Constraint violations: {len(result['errors_by_type']['constraint_violations'])}")
    print(f"\n{result['error_summary']}")
    
    assert result['has_errors'], "Should detect constraint violations"
    assert len(result['errors_by_type']['constraint_violations']) > 0, "Should find duplicate assignments"
    print("\n✅ Test passed!")


def test_contradiction_detection():
    """Test detection of contradictory statements."""
    print("\n" + "="*70)
    print("Test 2: Contradiction Detection")
    print("="*70)
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response="""
Reasoning process:

1. Peter is in house 1.
2. From clue 3, Alice is in house 2.
3. Therefore, Peter is in house 2.  (CONTRADICTION with step 1!)

The solution is:
<answer>
{"header": ["House", "Name"], 
 "rows": [["1", "Alice"], ["2", "Peter"]]}
</answer>
""",
        correct_answer=json.dumps({
            "header": ["House", "Name"],
            "rows": [["1", "Peter"], ["2", "Alice"]]
        })
    )
    
    analyzer = LogicErrorAnalyzer()
    result = analyzer.analyze_reasoning(sample)
    
    print(f"✓ Errors detected: {result['total_errors']}")
    print(f"✓ Contradictions found: {len(result['errors_by_type']['contradictions'])}")
    print(f"\n{result['error_summary']}")
    
    assert result['has_errors'], "Should detect contradictions"
    print("\n✅ Test passed!")


def test_incomplete_reasoning():
    """Test detection of incomplete reasoning."""
    print("\n" + "="*70)
    print("Test 3: Incomplete Reasoning Detection")
    print("="*70)
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response="""
Quick solution:

Therefore, the answer is:
<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Peter", "Red"], ["2", "Alice", "Blue"], ["3", "Eric", "Green"]]}
</answer>

(Note: No reasoning steps shown, no verification, no clue references)
""",
        correct_answer=json.dumps({
            "header": ["House", "Name", "Color"],
            "rows": [["1", "Peter", "Red"], ["2", "Alice", "Blue"], ["3", "Eric", "Green"]]
        })
    )
    
    analyzer = LogicErrorAnalyzer()
    result = analyzer.analyze_reasoning(sample)
    
    print(f"✓ Errors detected: {result['total_errors']}")
    print(f"✓ Incomplete reasoning issues: {len(result['errors_by_type']['incomplete_reasoning'])}")
    print(f"\n{result['error_summary']}")
    
    assert result['has_errors'], "Should detect incomplete reasoning"
    assert len(result['errors_by_type']['incomplete_reasoning']) > 0, "Should find missing verification"
    print("\n✅ Test passed!")


def test_assignment_errors():
    """Test detection of incorrect assignments."""
    print("\n" + "="*70)
    print("Test 4: Assignment Error Detection")
    print("="*70)
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response="""
After careful analysis:

1. Peter is in house 1 with red color
2. Alice is in house 2 with green color  (Should be blue!)
3. Eric is in house 3 with blue color    (Should be green!)

<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Peter", "Red"], 
          ["2", "Alice", "Green"], 
          ["3", "Eric", "Blue"]]}
</answer>
""",
        correct_answer=json.dumps({
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Blue"],
                ["3", "Eric", "Green"]
            ]
        })
    )
    
    analyzer = LogicErrorAnalyzer()
    result = analyzer.analyze_reasoning(sample)
    
    print(f"✓ Errors detected: {result['total_errors']}")
    print(f"✓ Assignment errors: {len(result['errors_by_type']['assignment_errors'])}")
    print(f"\n{result['error_summary']}")
    
    assert result['has_errors'], "Should detect assignment errors"
    assert len(result['errors_by_type']['assignment_errors']) >= 2, "Should find 2 incorrect assignments"
    print("\n✅ Test passed!")


def test_enhanced_verify_function():
    """Test the enhanced verify function with error analysis."""
    print("\n" + "="*70)
    print("Test 5: Enhanced Verify Function")
    print("="*70)
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response="""
Solution with errors:
House 1: Peter, Red
House 2: Alice, Red  (Duplicate!)

<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Peter", "Red"], ["2", "Alice", "Red"]]}
</answer>
""",
        correct_answer=json.dumps({
            "header": ["House", "Name", "Color"],
            "rows": [["1", "Peter", "Red"], ["2", "Alice", "Blue"]]
        })
    )
    
    # Test with error analysis enabled
    result = verify_func_with_error_analysis(sample, enable_error_reasoning=True)
    
    print(f"✓ Reward: {result['reward']}")
    print(f"✓ Reasoning provided: {result['reasoning'] is not None}")
    
    if result['reasoning']:
        print(f"\nError Analysis:")
        print(result['reasoning'])
    
    assert result['reward'] == 0.0, "Should return 0 reward for incorrect answer"
    assert result['reasoning'] is not None, "Should provide error reasoning"
    print("\n✅ Test passed!")


def test_correct_answer_no_error_analysis():
    """Test that correct answers don't trigger error analysis."""
    print("\n" + "="*70)
    print("Test 6: Correct Answer (No Error Analysis)")
    print("="*70)
    
    ground_truth = {
        "header": ["House", "Name", "Color"],
        "rows": [["1", "Peter", "Red"], ["2", "Alice", "Blue"], ["3", "Eric", "Green"]]
    }
    
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response=f"""
Perfect reasoning:

1. Carefully analyzed all clues
2. Verified each constraint
3. Solution is correct

<answer>
{json.dumps(ground_truth)}
</answer>
""",
        correct_answer=json.dumps(ground_truth)
    )
    
    result = verify_func_with_error_analysis(sample)
    
    print(f"✓ Reward: {result['reward']}")
    print(f"✓ No error analysis needed: {result['reasoning'] is None}")
    
    assert result['reward'] == 1.0, "Should return 1.0 reward for correct answer"
    print("\n✅ Test passed!")


async def test_experience_generation():
    """Test LLM-based experience generation from errors (requires LLM config)."""
    print("\n" + "="*70)
    print("Test 7: Experience Generation (Optional - requires LLM)")
    print("="*70)
    
    try:
        from utu.config import AgentConfig
        from utu.utils import load_config
        
        # Try to load config (this may fail if not properly set up)
        config = load_config("simple/base")
        llm_config = config.agent.model.model_provider.model_dump()
        
        analyzer = LogicErrorAnalyzer(llm_config=llm_config)
        
        sample = EvaluationSample(
            dataset="ZebraLogic-Test",
            response="""
House 1: Peter, Red
House 2: Alice, Red  (Error: duplicate color)

<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Peter", "Red"], ["2", "Alice", "Red"]]}
</answer>
""",
            correct_answer=json.dumps({
                "header": ["House", "Name", "Color"],
                "rows": [["1", "Peter", "Red"], ["2", "Alice", "Blue"]]
            })
        )
        
        error_analysis = analyzer.analyze_reasoning(sample)
        experience = await analyzer.generate_experience_from_errors(
            error_analysis,
            "Solve the logic puzzle..."
        )
        
        print("✓ Experience generated:")
        print(experience)
        print("\n✅ Test passed!")
        
    except Exception as e:
        print(f"⚠️  Test skipped: {e}")
        print("   (This is expected if LLM is not configured)")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("Testing Logic Error Analyzer")
    print("="*70)
    
    try:
        # Run synchronous tests
        test_constraint_violation()
        test_contradiction_detection()
        test_incomplete_reasoning()
        test_assignment_errors()
        test_enhanced_verify_function()
        test_correct_answer_no_error_analysis()
        
        # Run async test
        asyncio.run(test_experience_generation())
        
        print("\n" + "="*70)
        print("✅ All tests passed!")
        print("="*70)
        print("\nThe Logic Error Analyzer is working correctly.")
        print("You can now use it in your ZebraLogic training!")
        
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


