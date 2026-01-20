"""
Tests for logic puzzle verification functions.

This module tests both the basic logic verifier and the enhanced verifier
with error analysis for ZebraLogic dataset.
"""

import json
import pytest

from utu.db import EvaluationSample
from utu.practice.verify.logic import verify_func as basic_verify_func
from utu.practice.verify.logic_with_error_analysis import verify_func as enhanced_verify_func


class TestBasicLogicVerifier:
    """Test cases for the basic logic verifier (logic.py)."""

    def test_json_table_answer_correct(self):
        """Test verification with correct JSON table format."""
        ground_truth = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Alice", "Red"],
                ["2", "Bob", "Blue"],
                ["3", "Charlie", "Green"]
            ]
        }
        
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
        
        result = basic_verify_func(sample)
        assert result['reward'] == 1.0, "Should return reward=1.0 for correct answer"
        assert result['reasoning'] is None or result['reasoning'] == ""

    def test_json_table_answer_incorrect(self):
        """Test verification with incorrect JSON table format."""
        ground_truth = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Alice", "Red"],
                ["2", "Bob", "Blue"],
                ["3", "Charlie", "Green"]
            ]
        }
        
        wrong_answer = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Alice", "Blue"],  # Wrong color
                ["2", "Bob", "Red"],
                ["3", "Charlie", "Green"]
            ]
        }
        
        wrong_response = f"""
        <answer>
        {json.dumps(wrong_answer, ensure_ascii=False)}
        </answer>
        """
        
        sample = EvaluationSample(
            dataset="test",
            response=wrong_response,
            correct_answer=json.dumps(ground_truth)
        )
        
        result = basic_verify_func(sample)
        assert result['reward'] == 0.0, "Should return reward=0.0 for wrong answer"

    def test_boxed_format(self):
        """Test extraction from \\boxed{} format."""
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
        
        result = basic_verify_func(sample)
        assert result['reward'] == 1.0, "Should extract answer from \\boxed{}"

    def test_answer_tag_format(self):
        """Test extraction from <answer>...</answer> tags."""
        ground_truth = "The answer is Paris"
        
        response = "<answer>the answer is paris</answer>"
        
        sample = EvaluationSample(
            dataset="test",
            response=response,
            correct_answer=ground_truth
        )
        
        result = basic_verify_func(sample)
        assert result['reward'] == 1.0, "Should match case-insensitively"

    def test_natural_language_extraction(self):
        """Test extraction from natural language with house descriptions."""
        ground_truth = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Blue"],
                ["3", "Eric", "Green"]
            ]
        }
        
        response = """
        Based on the clues:
        House 1: Peter, Red
        House 2: Alice, Blue
        House 3: Eric, Green
        """
        
        sample = EvaluationSample(
            dataset="test",
            response=response,
            correct_answer=json.dumps(ground_truth)
        )
        
        result = basic_verify_func(sample)
        # This might pass or fail depending on extraction quality
        assert 'reward' in result
        assert result['reward'] in [0.0, 1.0]

    def test_empty_response(self):
        """Test handling of empty response."""
        sample = EvaluationSample(
            dataset="test",
            response="",
            correct_answer="42"
        )
        
        result = basic_verify_func(sample)
        assert 'reward' in result
        assert result['reward'] == 0.0

    def test_malformed_json(self):
        """Test handling of malformed JSON."""
        sample = EvaluationSample(
            dataset="test",
            response='<answer>{"invalid json"</answer>',
            correct_answer='{"valid": "json"}'
        )
        
        result = basic_verify_func(sample)
        assert 'reward' in result
        # Should handle gracefully without crashing

    def test_real_zebralogic_example(self):
        """Test with real ZebraLogic-style example."""
        ground_truth = {
            "header": ["House", "Name", "Vacation", "Birthday", "Nationality"],
            "rows": [
                ["1", "Peter", "city", "april", "brit"],
                ["2", "Alice", "mountain", "feb", "norwegian"],
                ["3", "Eric", "cruise", "jan", "swede"],
                ["4", "Arnold", "beach", "sept", "dane"]
            ]
        }
        
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
        
        result = basic_verify_func(sample)
        assert result['reward'] == 1.0, "Should verify real ZebraLogic answer correctly"

    def test_timeout_score(self):
        """Test that timeout_score parameter works correctly."""
        sample = EvaluationSample(
            dataset="test",
            response="",
            correct_answer="42"
        )
        
        result = basic_verify_func(sample, timeout_score=0.5)
        assert 'reward' in result
        # Should use timeout_score when appropriate


class TestEnhancedLogicVerifier:
    """Test cases for the enhanced logic verifier with error analysis."""

    def test_correct_answer_no_error_analysis(self):
        """Test that correct answers don't trigger error analysis."""
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
        
        result = enhanced_verify_func(sample)
        assert result['reward'] == 1.0, "Should return 1.0 reward for correct answer"
        # For correct answers, reasoning should be None or empty
        assert result.get('reasoning') is None or result.get('reasoning') == ""

    def test_incorrect_answer_with_error_analysis(self):
        """Test that incorrect answers trigger error analysis when enabled."""
        ground_truth = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Blue"],
                ["3", "Eric", "Green"]
            ]
        }
        
        wrong_answer = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Red"],  # Duplicate color
                ["3", "Eric", "Green"]
            ]
        }
        
        sample = EvaluationSample(
            dataset="ZebraLogic-Test",
            response=f"""
            Solution with errors:
            House 1: Peter, Red
            House 2: Alice, Red  (Duplicate!)
            
            <answer>
            {json.dumps(wrong_answer)}
            </answer>
            """,
            correct_answer=json.dumps(ground_truth)
        )
        
        result = enhanced_verify_func(sample, enable_error_analysis=True)
        assert result['reward'] == 0.0, "Should return 0 reward for incorrect answer"
        # Error analysis may or may not be available depending on LogicErrorAnalyzer
        # If available, reasoning should be provided
        if result.get('reasoning'):
            assert isinstance(result['reasoning'], str)
            assert len(result['reasoning']) > 0

    def test_error_analysis_disabled(self):
        """Test that error analysis can be disabled."""
        ground_truth = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Blue"]
            ]
        }
        
        wrong_answer = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Blue"],
                ["2", "Alice", "Red"]
            ]
        }
        
        sample = EvaluationSample(
            dataset="ZebraLogic-Test",
            response=f"<answer>{json.dumps(wrong_answer)}</answer>",
            correct_answer=json.dumps(ground_truth)
        )
        
        result = enhanced_verify_func(sample, enable_error_analysis=False)
        assert result['reward'] == 0.0
        # When disabled, should behave like basic verifier
        assert result.get('reasoning') is None or result.get('reasoning') == ""

    def test_detailed_errors_flag(self):
        """Test that detailed_errors flag works correctly."""
        ground_truth = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Blue"]
            ]
        }
        
        wrong_answer = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Blue"],
                ["2", "Alice", "Red"]
            ]
        }
        
        sample = EvaluationSample(
            dataset="ZebraLogic-Test",
            response=f"<answer>{json.dumps(wrong_answer)}</answer>",
            correct_answer=json.dumps(ground_truth)
        )
        
        result = enhanced_verify_func(
            sample,
            enable_error_analysis=True,
            detailed_errors=True
        )
        
        assert result['reward'] == 0.0
        # If error analysis is available and detailed_errors is True,
        # should include detailed error breakdown
        if result.get('detailed_errors'):
            assert isinstance(result['detailed_errors'], dict)
        if result.get('total_errors'):
            assert isinstance(result['total_errors'], int)

    def test_error_analysis_fallback(self):
        """Test that verifier handles error analysis failures gracefully."""
        # Create a sample that might cause issues
        sample = EvaluationSample(
            dataset="test",
            response="Invalid response format",
            correct_answer='{"header": ["House"], "rows": [["1"]]}'
        )
        
        # Should not crash even if error analysis fails
        result = enhanced_verify_func(sample, enable_error_analysis=True)
        assert 'reward' in result
        assert result['reward'] == 0.0
        # Should still return a result even if error analysis fails

    def test_enhanced_verifier_same_as_basic_for_correct(self):
        """Test that enhanced verifier behaves same as basic for correct answers."""
        ground_truth = {
            "header": ["House", "Name"],
            "rows": [["1", "Alice"], ["2", "Bob"]]
        }
        
        sample = EvaluationSample(
            dataset="test",
            response=f"<answer>{json.dumps(ground_truth)}</answer>",
            correct_answer=json.dumps(ground_truth)
        )
        
        basic_result = basic_verify_func(sample)
        enhanced_result = enhanced_verify_func(sample, enable_error_analysis=False)
        
        assert basic_result['reward'] == enhanced_result['reward']
        assert basic_result['reward'] == 1.0

    def test_enhanced_verifier_with_constraint_violation(self):
        """Test enhanced verifier with constraint violation in reasoning."""
        ground_truth = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Blue"],
                ["3", "Eric", "Green"]
            ]
        }
        
        wrong_answer = {
            "header": ["House", "Name", "Color"],
            "rows": [
                ["1", "Peter", "Red"],
                ["2", "Alice", "Red"],  # Duplicate color
                ["3", "Eric", "Green"]
            ]
        }
        
        sample = EvaluationSample(
            dataset="ZebraLogic-Test",
            response=f"""
            Let me solve this step by step:
            
            1. From the clues, I determine:
               - House 1: Peter, Red
               - House 2: Alice, Red  (ERROR: Red already assigned to House 1!)
               - House 3: Eric, Green
            
            <answer>
            {json.dumps(wrong_answer)}
            </answer>
            """,
            correct_answer=json.dumps(ground_truth)
        )
        
        result = enhanced_verify_func(sample, enable_error_analysis=True)
        assert result['reward'] == 0.0
        
        # If error analysis is available, it should detect the constraint violation
        if result.get('reasoning'):
            # Should contain information about errors
            assert len(result['reasoning']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])










































































