"""
Logic puzzle answer verifier for ZebraLogic dataset (Training-Free GRPO)

This module provides verification functionality for logic puzzles during training.
It extracts answers from model responses and compares them with ground truth.
"""

import json
import re
from typing import Any, Dict

from utu.db import EvaluationSample


def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    Verify logic puzzle answer and return reward score for Training-Free GRPO.
    
    Args:
        sample: EvaluationSample containing the question, response, and ground truth
        timeout_score: Score to return on timeout (default: 0)
        **kwargs: Additional arguments (unused)
        
    Returns:
        Dictionary with 'reward' (float 0.0-1.0) and 'reasoning' (str or None)
    """
    try:
        model_output = sample.response
        ground_truth = sample.correct_answer
        
        # Extract answer from model output
        extracted_answer = _extract_answer_from_response(model_output)
        
        # Parse ground truth (may be JSON string)
        parsed_ground_truth = _parse_ground_truth(ground_truth)
        
        # Compare answers
        is_correct = _compare_answers(extracted_answer, parsed_ground_truth)
        
        return {
            "reward": 1.0 if is_correct else 0.0,
            "reasoning": None  # Can add detailed reasoning if needed
        }
        
    except Exception as e:
        # On any error, return timeout score
        print(f"Warning: Error in logic verification: {e}")
        return {
            "reward": timeout_score,
            "reasoning": f"Verification error: {str(e)}"
        }


def _extract_answer_from_response(response: str) -> Any:
    """
    Extract the final answer from model response.
    
    Supports multiple formats:
    - \\boxed{...}
    - <answer>...</answer>
    - JSON table format
    - Python dict format (with single quotes)
    - Natural language descriptions
    
    Args:
        response: Model response text
        
    Returns:
        Extracted answer string or dict
    """
    if not response:
        return ""
    
    # Try to extract from \boxed{} format (LaTeX style)
    # Use greedy matching to handle nested braces
    boxed_pattern = r"\\boxed\{(.+)\}"
    boxed_match = re.search(boxed_pattern, response, re.DOTALL)
    if boxed_match:
        content = boxed_match.group(1).strip()
        # Try to parse as dict/JSON
        parsed = _try_parse_dict_or_json(content)
        return parsed if parsed is not None else content
    
    # Try to extract from <answer>...</answer> tags
    answer_pattern = r"<answer>\s*(.+?)\s*</answer>"
    answer_match = re.search(answer_pattern, response, re.DOTALL | re.IGNORECASE)
    if answer_match:
        content = answer_match.group(1).strip()
        # Try to parse as dict/JSON
        parsed = _try_parse_dict_or_json(content)
        return parsed if parsed is not None else content
    
    # Try to find JSON-like content with double quotes
    # Look for table patterns: {"header": [...], "rows": [...]}
    json_pattern = r'\{[^{}]*"header"[^{}]*"rows"[^{}]*\}'
    json_match = re.search(json_pattern, response, re.DOTALL)
    if json_match:
        content = json_match.group(0).strip()
        parsed = _try_parse_dict_or_json(content)
        return parsed if parsed is not None else content
    
    # Try to find Python dict-like content with single quotes
    # Pattern: {'House 1: ...', 'House 2: ...'}
    dict_pattern = r"\{[^{}]*'[Hh]ouse\s+\d+:[^{}]*\}"
    dict_match = re.search(dict_pattern, response, re.DOTALL)
    if dict_match:
        content = dict_match.group(0).strip()
        parsed = _try_parse_dict_or_json(content)
        return parsed if parsed is not None else content
    
    # Fallback: return the entire response for natural language extraction
    return response


def _try_parse_dict_or_json(text: str) -> Any:
    """
    Try to parse text as JSON or Python dict (with single quotes).
    
    Args:
        text: Text to parse
        
    Returns:
        Parsed data or None if parsing fails
    """
    if not text:
        return None
    
    # Try JSON first (double quotes)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Try Python dict format (single quotes) by replacing quotes
    try:
        # Replace single quotes with double quotes for JSON parsing
        json_text = text.replace("'", '"')
        return json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        pass
    
    return None


def _parse_ground_truth(ground_truth: str) -> Any:
    """
    Parse ground truth, which may be a JSON string or plain text.
    
    Args:
        ground_truth: Ground truth answer (possibly JSON)
        
    Returns:
        Parsed data (dict if JSON, str otherwise)
    """
    if not ground_truth:
        return ""
    
    # Try to parse as JSON
    try:
        return json.loads(ground_truth)
    except (json.JSONDecodeError, TypeError):
        # If not valid JSON, return as-is
        return ground_truth


def _compare_answers(predicted: Any, ground_truth: Any) -> bool:
    """
    Compare predicted answer with ground truth.
    
    Handles multiple formats:
    - JSON table comparison (for ZebraLogic)
    - Natural language extraction and comparison
    - String comparison (with normalization)
    
    Args:
        predicted: Predicted answer (string, dict, or parsed data)
        ground_truth: Ground truth (dict or string)
        
    Returns:
        True if answers match, False otherwise
    """
    # If predicted is already a dict (parsed in extraction)
    if isinstance(predicted, dict) and isinstance(ground_truth, dict):
        return _compare_tables(predicted, ground_truth)
    
    # If ground truth is a dict (JSON table), try to parse predicted
    if isinstance(ground_truth, dict):
        # If predicted is string, try multiple parsing strategies
        if isinstance(predicted, str):
            # Strategy 1: Try to parse as JSON/dict
            predicted_dict = _try_parse_dict_or_json(predicted)
            if predicted_dict and isinstance(predicted_dict, dict):
                return _compare_tables(predicted_dict, ground_truth)
            
            # Strategy 2: Try to extract table from natural language
            extracted_table = _extract_table_from_text(predicted, ground_truth)
            if extracted_table:
                return _compare_tables(extracted_table, ground_truth)
        
        # Fallback: strict string comparison (unlikely to match)
        return False
    
    # Both are strings: normalize and compare
    gt_normalized = _normalize_text(str(ground_truth))
    pred_normalized = _normalize_text(str(predicted))
    
    # Direct match
    if gt_normalized == pred_normalized:
        return True
    
    # Check if prediction contains the ground truth
    if gt_normalized in pred_normalized:
        return True
    
    # Check if ground truth contains the prediction (for concise answers)
    if pred_normalized in gt_normalized and len(pred_normalized) > 3:
        return True
    
    return False


def _extract_table_from_text(text: str, ground_truth: Dict) -> Dict | None:
    """
    Extract table data from natural language text.
    
    Tries to parse formats like:
    - "House 1: Peter, Bird, White, Craftsman, Samsung Galaxy S21; House 2: ..."
    - Dict values containing house descriptions
    - Markdown tables
    - Other natural language descriptions
    
    Args:
        text: Natural language text containing the answer
        ground_truth: Ground truth table (for structure reference)
        
    Returns:
        Extracted table dict or None
    """
    if not text or not isinstance(ground_truth, dict):
        return None
    
    if "header" not in ground_truth or "rows" not in ground_truth:
        return None
    
    headers = ground_truth["header"]
    num_houses = len(ground_truth["rows"])
    
    # Convert text to string if it's not already
    text = str(text)
    
    # Clean up text: remove extra quotes and braces
    text = text.strip().strip("'\"{}").replace("'}", "").replace("}'", "")
    
    # Try to extract house-based descriptions from the text
    # Pattern: "House 1: value1, value2, ...; House 2: ..." or "House 1: value1, value2, ..."
    # More flexible pattern to handle different separators
    house_pattern = r"[Hh]ouse\s+(\d+):\s*([^{};\n]+?)(?=(?:[Hh]ouse\s+\d+:|[;}]|$))"
    matches = re.findall(house_pattern, text, re.DOTALL)
    
    if matches and len(matches) >= num_houses:
        rows = []
        for house_num, house_data in sorted(matches[:num_houses], key=lambda x: int(x[0])):
            # Clean up the data
            house_data = house_data.strip().rstrip(';,').strip("'\"")
            
            # Split by comma
            values = [v.strip().strip("'\"") for v in house_data.split(',') if v.strip()]
            
            # Normalize values
            values = [_normalize_text(v) for v in values]
            
            # Build row with reordering to match ground truth header
            row = _build_row_with_reordering(house_num, values, headers, ground_truth["rows"])
            
            if row:
                rows.append(row)
        
        if len(rows) == num_houses:
            return {"header": headers, "rows": rows}
    
    return None


def _build_row_with_reordering(house_num: str, values: list, headers: list, gt_rows: list) -> list:
    """
    Build a row by intelligently matching values to header fields.
    
    Uses the ground truth rows to identify patterns and field types.
    
    Args:
        house_num: House number (e.g., "1")
        values: Extracted values from model output
        headers: Expected header fields
        gt_rows: Ground truth rows (for pattern matching)
        
    Returns:
        Ordered row matching the headers, or None if failed
    """
    if not values or not headers:
        return None
    
    # Find the corresponding ground truth row
    gt_row = None
    for row in gt_rows:
        if str(row[0]) == str(house_num):
            gt_row = row
            break
    
    if not gt_row:
        return None
    
    # Create result row starting with house number
    result = [house_num]
    
    # For each header field (skip first which is House), find matching value
    for i, header in enumerate(headers[1:], 1):
        matched_value = ""
        gt_value_norm = _normalize_text(str(gt_row[i]))
        
        # Try to find exact match
        for val in values:
            if val == gt_value_norm:
                matched_value = val
                break
        
        # If no exact match, try partial match
        if not matched_value:
            for val in values:
                # Check if this value contains or is contained by ground truth
                if (gt_value_norm in val or val in gt_value_norm) and len(val) > 2:
                    matched_value = val
                    break
        
        # If still no match, use heuristics based on field type
        if not matched_value:
            matched_value = _guess_field_value(header, values, gt_value_norm)
        
        result.append(matched_value)
    
    return result


def _guess_field_value(header: str, values: list, gt_value: str) -> str:
    """
    Guess which value matches a header field based on patterns.
    
    Args:
        header: Header name (e.g., "Name", "Animal", "PhoneModel")
        values: Available values
        gt_value: Ground truth value (normalized)
        
    Returns:
        Best matching value or empty string
    """
    header_lower = header.lower()
    
    # Common names
    if header_lower in ["name", "person"]:
        names = ["peter", "alice", "eric", "arnold", "bob"]
        for val in values:
            if val in names:
                return val
    
    # Animals
    if header_lower in ["animal", "pet"]:
        animals = ["bird", "cat", "dog", "fish", "horse"]
        for val in values:
            if val in animals:
                return val
    
    # Phone models (usually longer strings with numbers/brand names)
    if header_lower in ["phonemodel", "phone"]:
        phone_keywords = ["iphone", "samsung", "google", "pixel", "galaxy", "oneplus"]
        for val in values:
            if any(keyword in val for keyword in phone_keywords):
                return val
    
    # Colors
    if header_lower in ["color", "colour"]:
        colors = ["red", "blue", "green", "yellow", "white", "black", "orange", "purple"]
        for val in values:
            if val in colors:
                return val
    
    # House styles
    if header_lower in ["housestyle", "style"]:
        styles = ["colonial", "craftsman", "victorian", "ranch", "modern"]
        for val in values:
            if val in styles:
                return val
    
    # If no pattern match, return empty
    return ""


def _compare_tables(predicted: Dict, ground_truth: Dict) -> bool:
    """
    Compare two table structures (for ZebraLogic format).
    
    Expected format: {"header": [...], "rows": [[...], ...]}
    
    Args:
        predicted: Predicted table
        ground_truth: Ground truth table
        
    Returns:
        True if tables match, False otherwise
    """
    # Check if both have required keys
    if "header" not in predicted or "rows" not in predicted:
        return False
    if "header" not in ground_truth or "rows" not in ground_truth:
        return False
    
    # Compare headers (order-sensitive)
    pred_header = [str(h).lower().strip() for h in predicted["header"]]
    gt_header = [str(h).lower().strip() for h in ground_truth["header"]]
    if pred_header != gt_header:
        return False
    
    # Compare rows (order-sensitive, element-wise)
    pred_rows = predicted["rows"]
    gt_rows = ground_truth["rows"]
    
    if len(pred_rows) != len(gt_rows):
        return False
    
    for pred_row, gt_row in zip(pred_rows, gt_rows):
        # Normalize each cell
        pred_row_norm = [str(cell).lower().strip() for cell in pred_row]
        gt_row_norm = [str(cell).lower().strip() for cell in gt_row]
        
        if pred_row_norm != gt_row_norm:
            return False
    
    return True


def _normalize_text(text: str) -> str:
    """
    Normalize text for comparison.
    
    - Remove extra whitespace
    - Convert to lowercase
    - Strip leading/trailing spaces
    
    Args:
        text: Input text
        
    Returns:
        Normalized text
    """
    if text is None:
        return ""
    
    # Convert to string if not already
    text = str(text)
    
    # Remove extra whitespace
    text = " ".join(text.split())
    
    # Convert to lowercase
    text = text.lower().strip()
    
    return text

