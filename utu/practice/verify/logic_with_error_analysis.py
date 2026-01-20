"""
Enhanced logic puzzle answer verifier with error analysis for ZebraLogic dataset.

This module extends the standard logic verifier to provide detailed error analysis
for incorrect answers. The error information is passed to the experience generation
system to help the LLM learn from mistakes.
"""

import sys
from pathlib import Path

# Add scripts directory to path for the analyzer
scripts_dir = Path(__file__).parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from utu.db import EvaluationSample
from utu.utils import get_logger

# Import the original verify function
from utu.practice.verify.logic import verify_func as original_verify_func

# Import the error analyzer
try:
    from logic_error_analyzer import LogicErrorAnalyzer
    ERROR_ANALYSIS_AVAILABLE = True
except ImportError:
    ERROR_ANALYSIS_AVAILABLE = False
    print("Warning: LogicErrorAnalyzer not available. Error analysis will be disabled.")

logger = get_logger(__name__)


def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    Enhanced verify function with error analysis for Training-Free GRPO.
    
    This function:
    1. Verifies the answer using the standard logic verifier
    2. If incorrect, performs detailed error analysis
    3. Returns reward score with error analysis in 'reasoning' field
    
    The error analysis helps the LLM generate better experiences by understanding
    what went wrong in the reasoning process.
    
    Args:
        sample: EvaluationSample containing the question, response, and ground truth
        timeout_score: Score to return on timeout (default: 0)
        **kwargs: Additional arguments
            - enable_error_analysis: Whether to perform error analysis (default: True)
            - detailed_errors: Whether to include detailed error breakdown (default: False)
        
    Returns:
        Dictionary with:
        - 'reward' (float 0.0-1.0): Score for the answer
        - 'reasoning' (str or None): Error analysis summary for incorrect answers
        - 'detailed_errors' (dict, optional): Detailed error breakdown if requested
    """
    # Get standard verification result
    result = original_verify_func(sample, timeout_score, **kwargs)
    
    # Check if error analysis should be performed
    enable_error_analysis = kwargs.get("enable_error_analysis", True)
    detailed_errors = kwargs.get("detailed_errors", False)
    
    # If answer is correct, no need for error analysis
    if result["reward"] >= 1.0:
        return result
    
    # If error analysis is disabled or not available, return standard result
    if not enable_error_analysis or not ERROR_ANALYSIS_AVAILABLE:
        return result
    
    # Perform error analysis for incorrect answers
    try:
        analyzer = LogicErrorAnalyzer()
        error_analysis = analyzer.analyze_reasoning(sample)
        
        if error_analysis["has_errors"]:
            # Add error summary to reasoning field
            result["reasoning"] = _format_error_reasoning(error_analysis)
            
            # Optionally include detailed error breakdown
            if detailed_errors:
                result["detailed_errors"] = error_analysis["errors_by_type"]
                result["total_errors"] = error_analysis["total_errors"]
        else:
            # Answer is wrong but no specific errors detected
            result["reasoning"] = "Answer is incorrect but no specific logical errors were detected in the reasoning process."
            
    except Exception as e:
        # If error analysis fails, log warning but don't fail the verification
        logger.warning(f"Error during error analysis: {e}")
        result["reasoning"] = f"Answer is incorrect. Error analysis failed: {str(e)}"
    
    return result


def _format_error_reasoning(error_analysis: dict) -> str:
    """
    Format error analysis into a concise reasoning string for the experience generator.
    
    Args:
        error_analysis: Error analysis results from LogicErrorAnalyzer
        
    Returns:
        Formatted error reasoning string
    """
    parts = []
    
    # Add high-level summary
    parts.append(f"Found {error_analysis['total_errors']} logical errors in reasoning:")
    
    # Add specific error types with examples
    errors_by_type = error_analysis["errors_by_type"]
    
    # Constraint violations (most critical)
    if errors_by_type.get("constraint_violations"):
        violations = errors_by_type["constraint_violations"]
        parts.append(f"\n• Constraint Violations ({len(violations)}): ")
        for i, v in enumerate(violations[:2], 1):
            parts.append(f"  {i}. {v.get('description', str(v))}")
        if len(violations) > 2:
            parts.append(f"  ... and {len(violations) - 2} more violations")
    
    # Contradictions
    if errors_by_type.get("contradictions"):
        contradictions = errors_by_type["contradictions"]
        parts.append(f"\n• Contradictions ({len(contradictions)}): ")
        for i, c in enumerate(contradictions[:2], 1):
            parts.append(f"  {i}. {c.get('description', str(c))}")
        if len(contradictions) > 2:
            parts.append(f"  ... and {len(contradictions) - 2} more contradictions")
    
    # Assignment errors
    if errors_by_type.get("assignment_errors"):
        errors = errors_by_type["assignment_errors"]
        parts.append(f"\n• Incorrect Assignments ({len(errors)}): ")
        for i, e in enumerate(errors[:2], 1):
            parts.append(f"  {i}. {e.get('description', str(e))}")
        if len(errors) > 2:
            parts.append(f"  ... and {len(errors) - 2} more assignment errors")
    
    # Incomplete reasoning
    if errors_by_type.get("incomplete_reasoning"):
        issues = errors_by_type["incomplete_reasoning"]
        parts.append(f"\n• Incomplete Reasoning ({len(issues)}): ")
        for i, issue in enumerate(issues[:2], 1):
            parts.append(f"  {i}. {issue.get('description', str(issue))}")
        if len(issues) > 2:
            parts.append(f"  ... and {len(issues) - 2} more issues")
    
    # Logical inconsistencies
    if errors_by_type.get("logical_inconsistencies"):
        inconsistencies = errors_by_type["logical_inconsistencies"]
        parts.append(f"\n• Logical Inconsistencies ({len(inconsistencies)}): ")
        for i, inc in enumerate(inconsistencies[:2], 1):
            parts.append(f"  {i}. {inc.get('description', str(inc))}")
        if len(inconsistencies) > 2:
            parts.append(f"  ... and {len(inconsistencies) - 2} more inconsistencies")
    
    return "\n".join(parts)


