#!/usr/bin/env python3
"""
Logic Error Analyzer for ZebraLogic Training

This script analyzes reasoning processes during ZebraLogic training to detect logical errors,
constraint violations, and inconsistencies. It provides detailed error reports that can be used
by the LLM to generate better experiences.

Features:
- Detects constraint violations
- Identifies logical contradictions
- Finds incomplete reasoning
- Analyzes reasoning patterns
- Generates error reports for LLM summarization
"""

import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import EvaluationSample
from utu.utils import SimplifiedAsyncOpenAI, get_logger

logger = get_logger(__name__)


class LogicErrorAnalyzer:
    """Analyzes logic puzzle reasoning for errors and inconsistencies."""
    
    def __init__(self, llm_config: Optional[Dict] = None):
        """
        Initialize the analyzer.
        
        Args:
            llm_config: Optional LLM configuration for experience summarization
        """
        self.llm = None
        if llm_config:
            self.llm = SimplifiedAsyncOpenAI(**llm_config)
    
    def analyze_reasoning(self, sample: EvaluationSample) -> Dict[str, Any]:
        """
        Analyze a reasoning sample for logical errors.
        
        Args:
            sample: EvaluationSample with response and trajectories
            
        Returns:
            Dictionary containing error analysis results
        """
        response = sample.response
        ground_truth = self._parse_ground_truth(sample.correct_answer)
        
        # Extract reasoning steps
        reasoning_steps = self._extract_reasoning_steps(response)
        
        # Detect various types of errors
        errors = {
            "constraint_violations": self._detect_constraint_violations(response, ground_truth),
            "contradictions": self._detect_contradictions(reasoning_steps),
            "incomplete_reasoning": self._detect_incomplete_reasoning(response, ground_truth),
            "logical_inconsistencies": self._detect_logical_inconsistencies(reasoning_steps),
            "assignment_errors": self._detect_assignment_errors(response, ground_truth),
        }
        
        # Count total errors
        total_errors = sum(len(v) for v in errors.values())
        
        # Generate error summary
        error_summary = self._generate_error_summary(errors)
        
        return {
            "has_errors": total_errors > 0,
            "total_errors": total_errors,
            "errors_by_type": errors,
            "error_summary": error_summary,
            "reasoning_steps": reasoning_steps,
            "response": response,
            "ground_truth": ground_truth,
        }
    
    def _extract_reasoning_steps(self, response: str) -> List[str]:
        """Extract individual reasoning steps from the response."""
        steps = []
        
        # Try to find numbered steps
        numbered_pattern = r"(?:^|\n)\s*(\d+[\.\)])\s*(.+?)(?=\n\s*\d+[\.\)]|\n\n|$)"
        matches = re.findall(numbered_pattern, response, re.DOTALL | re.MULTILINE)
        
        if matches:
            steps = [match[1].strip() for match in matches]
        else:
            # Split by sentences or paragraphs as fallback
            paragraphs = response.split("\n\n")
            steps = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 20]
        
        return steps
    
    def _detect_constraint_violations(self, response: str, ground_truth: Any) -> List[Dict]:
        """
        Detect violations of problem constraints.
        
        Examples:
        - Assigning the same attribute to multiple entities
        - Violating uniqueness constraints
        - Breaking positional constraints
        """
        violations = []
        
        # Extract assignments from response
        assignments = self._extract_assignments(response)
        
        # Check for duplicate assignments
        attribute_to_entities = defaultdict(list)
        for entity, attrs in assignments.items():
            for attr_type, attr_value in attrs.items():
                if attr_value:
                    attribute_to_entities[f"{attr_type}:{attr_value}"].append(entity)
        
        # Find duplicates
        for attr_key, entities in attribute_to_entities.items():
            if len(entities) > 1:
                violations.append({
                    "type": "duplicate_assignment",
                    "attribute": attr_key,
                    "entities": entities,
                    "description": f"Attribute '{attr_key}' assigned to multiple entities: {', '.join(entities)}",
                })
        
        # Check for missing mandatory attributes
        if isinstance(ground_truth, dict) and "header" in ground_truth:
            expected_attributes = set(ground_truth["header"][1:])  # Skip "House"
            for entity, attrs in assignments.items():
                missing_attrs = expected_attributes - set(attrs.keys())
                if missing_attrs:
                    violations.append({
                        "type": "missing_attributes",
                        "entity": entity,
                        "missing": list(missing_attrs),
                        "description": f"Entity '{entity}' is missing attributes: {', '.join(missing_attrs)}",
                    })
        
        return violations
    
    def _detect_contradictions(self, reasoning_steps: List[str]) -> List[Dict]:
        """
        Detect contradictions in the reasoning process.
        
        Examples:
        - "X is in house 1" followed by "X is in house 2"
        - "A has color red" followed by "A has color blue"
        """
        contradictions = []
        
        # Extract assertions from each step
        assertions = []
        for i, step in enumerate(reasoning_steps):
            step_assertions = self._extract_assertions(step)
            for assertion in step_assertions:
                assertions.append((i, assertion))
        
        # Check for contradicting assertions
        for i, (step_idx1, assertion1) in enumerate(assertions):
            for step_idx2, assertion2 in assertions[i+1:]:
                if self._are_contradicting(assertion1, assertion2):
                    contradictions.append({
                        "type": "contradiction",
                        "step1": step_idx1 + 1,
                        "step2": step_idx2 + 1,
                        "assertion1": assertion1,
                        "assertion2": assertion2,
                        "description": f"Contradiction found between step {step_idx1 + 1} and step {step_idx2 + 1}",
                    })
        
        return contradictions
    
    def _detect_incomplete_reasoning(self, response: str, ground_truth: Any) -> List[Dict]:
        """
        Detect incomplete reasoning steps.
        
        Examples:
        - Making conclusions without sufficient justification
        - Skipping necessary deductive steps
        - Not verifying the solution against all constraints
        """
        issues = []
        
        # Check if solution verification is present
        verification_keywords = ["verify", "check", "confirm", "validate", "ensure"]
        has_verification = any(keyword in response.lower() for keyword in verification_keywords)
        
        if not has_verification:
            issues.append({
                "type": "missing_verification",
                "description": "No explicit verification of the solution against constraints",
            })
        
        # Check if all clues are referenced
        clue_pattern = r"(?:clue|constraint|given|condition)\s+(\d+)"
        mentioned_clues = set(re.findall(clue_pattern, response.lower()))
        
        if mentioned_clues:
            # If clues are numbered, check for gaps
            clue_numbers = sorted([int(c) for c in mentioned_clues])
            if clue_numbers:
                expected_range = range(1, max(clue_numbers) + 1)
                missing_clues = [i for i in expected_range if i not in clue_numbers]
                if missing_clues:
                    issues.append({
                        "type": "unaddressed_clues",
                        "missing_clues": missing_clues,
                        "description": f"Clues {missing_clues} were not explicitly addressed",
                    })
        
        # Check for unjustified conclusions
        conclusion_keywords = ["therefore", "thus", "hence", "so", "conclude"]
        for keyword in conclusion_keywords:
            pattern = rf"{keyword}\s+([^.]+)\."
            matches = re.findall(pattern, response.lower())
            for match in matches[:3]:  # Check first few conclusions
                # Simple heuristic: check if there's supporting reasoning nearby
                context_start = max(0, response.lower().find(match) - 200)
                context = response[context_start:response.lower().find(match)]
                
                # Count reasoning indicators
                reasoning_indicators = ["because", "since", "given", "from", "as"]
                support_count = sum(1 for ind in reasoning_indicators if ind in context.lower())
                
                if support_count == 0:
                    issues.append({
                        "type": "unjustified_conclusion",
                        "conclusion": match.strip(),
                        "description": f"Conclusion lacks clear supporting reasoning: '{match.strip()}'",
                    })
        
        return issues
    
    def _detect_logical_inconsistencies(self, reasoning_steps: List[str]) -> List[Dict]:
        """
        Detect logical inconsistencies in the reasoning flow.
        
        Examples:
        - Using eliminated possibilities
        - Violating established orderings
        - Invalid logical inferences
        """
        inconsistencies = []
        
        # Track eliminated possibilities
        eliminated = set()
        used = set()
        
        for i, step in enumerate(reasoning_steps):
            # Find eliminations
            elim_patterns = [
                r"(?:cannot|can't|not|isn't|aren't)\s+(?:be|have)\s+([a-z\s]+)",
                r"eliminate[ds]?\s+([a-z\s]+)",
                r"rule[ds]?\s+out\s+([a-z\s]+)",
            ]
            for pattern in elim_patterns:
                matches = re.findall(pattern, step.lower())
                for match in matches:
                    eliminated.add(match.strip())
            
            # Find uses
            use_patterns = [
                r"(?:must|has to|is|are|have)\s+(?:be|have)?\s*([a-z\s]+)",
                r"assign[ed]?\s+([a-z\s]+)",
            ]
            for pattern in use_patterns:
                matches = re.findall(pattern, step.lower())
                for match in matches:
                    used.add(match.strip())
        
        # Check for eliminated items being used
        conflicts = eliminated.intersection(used)
        for conflict in conflicts:
            inconsistencies.append({
                "type": "using_eliminated_possibility",
                "item": conflict,
                "description": f"Item '{conflict}' was eliminated but later used in the solution",
            })
        
        return inconsistencies
    
    def _detect_assignment_errors(self, response: str, ground_truth: Any) -> List[Dict]:
        """
        Detect errors in final assignments compared to ground truth.
        """
        errors = []
        
        if not isinstance(ground_truth, dict) or "rows" not in ground_truth:
            return errors
        
        # Extract predicted assignments
        predicted = self._extract_final_answer(response)
        
        if not predicted or not isinstance(predicted, dict) or "rows" not in predicted:
            return errors
        
        # Compare each row
        for i, (pred_row, gt_row) in enumerate(zip(predicted.get("rows", []), ground_truth["rows"])):
            for j, (pred_val, gt_val) in enumerate(zip(pred_row, gt_row)):
                if self._normalize_value(pred_val) != self._normalize_value(gt_val):
                    header = ground_truth["header"][j] if j < len(ground_truth["header"]) else f"column_{j}"
                    errors.append({
                        "type": "incorrect_assignment",
                        "row": i + 1,
                        "attribute": header,
                        "predicted": pred_val,
                        "expected": gt_val,
                        "description": f"Row {i+1}, {header}: expected '{gt_val}', got '{pred_val}'",
                    })
        
        return errors
    
    def _extract_assignments(self, response: str) -> Dict[str, Dict[str, str]]:
        """Extract entity-attribute assignments from response."""
        assignments = defaultdict(dict)
        
        # Pattern: "House 1: name, attribute1, attribute2..."
        house_pattern = r"[Hh]ouse\s+(\d+):\s*([^;\n]+)"
        matches = re.findall(house_pattern, response)
        
        for house_num, attrs_str in matches:
            entity = f"House {house_num}"
            attrs = [a.strip() for a in attrs_str.split(",")]
            # Simple heuristic: assign attributes by position
            for i, attr in enumerate(attrs):
                assignments[entity][f"attr_{i}"] = attr
        
        return dict(assignments)
    
    def _extract_assertions(self, step: str) -> List[str]:
        """Extract logical assertions from a reasoning step."""
        assertions = []
        
        # Pattern: "X is/has Y" or "X in position Y"
        patterns = [
            r"([A-Z][a-z]+)\s+(?:is|has)\s+([a-z]+(?:\s+[a-z]+)?)",
            r"([A-Z][a-z]+)\s+in\s+(?:house|position)\s+(\d+)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, step)
            for match in matches:
                assertions.append(f"{match[0]} -> {match[1]}")
        
        return assertions
    
    def _are_contradicting(self, assertion1: str, assertion2: str) -> bool:
        """Check if two assertions contradict each other."""
        # Simple check: same entity, different attributes
        if "->" in assertion1 and "->" in assertion2:
            entity1, attr1 = assertion1.split("->", 1)
            entity2, attr2 = assertion2.split("->", 1)
            
            # Same entity, different values for what might be the same attribute
            return entity1.strip() == entity2.strip() and attr1.strip() != attr2.strip()
        
        return False
    
    def _extract_final_answer(self, response: str) -> Optional[Dict]:
        """Extract the final answer structure from response."""
        # Try to find JSON answer
        answer_pattern = r"<answer>\s*(.+?)\s*</answer>"
        match = re.search(answer_pattern, response, re.DOTALL | re.IGNORECASE)
        
        if match:
            content = match.group(1).strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Try with single quotes
                try:
                    return json.loads(content.replace("'", '"'))
                except json.JSONDecodeError:
                    pass
        
        return None
    
    def _parse_ground_truth(self, ground_truth: str) -> Any:
        """Parse ground truth (may be JSON string)."""
        try:
            return json.loads(ground_truth)
        except (json.JSONDecodeError, TypeError):
            return ground_truth
    
    def _normalize_value(self, value: str) -> str:
        """Normalize a value for comparison."""
        if value is None:
            return ""
        return str(value).lower().strip()
    
    def _generate_error_summary(self, errors: Dict[str, List[Dict]]) -> str:
        """Generate a human-readable error summary."""
        if not any(errors.values()):
            return "No errors detected."
        
        summary_parts = []
        
        for error_type, error_list in errors.items():
            if error_list:
                summary_parts.append(f"\n{error_type.replace('_', ' ').title()} ({len(error_list)}):")
                for i, error in enumerate(error_list[:3], 1):  # Show first 3
                    summary_parts.append(f"  {i}. {error.get('description', str(error))}")
                if len(error_list) > 3:
                    summary_parts.append(f"  ... and {len(error_list) - 3} more")
        
        return "\n".join(summary_parts)
    
    async def generate_experience_from_errors(
        self, 
        error_analysis: Dict[str, Any],
        question: str,
    ) -> Optional[str]:
        """
        Use LLM to generate learning experiences from error analysis.
        
        Args:
            error_analysis: Results from analyze_reasoning
            question: Original question
            
        Returns:
            Generated experience string or None if LLM not configured
        """
        if not self.llm:
            logger.warning("LLM not configured, cannot generate experiences")
            return None
        
        # Prepare prompt
        system_prompt = """You are an expert in logic puzzles and reasoning analysis.
Your task is to analyze errors made during logical reasoning and extract valuable learning experiences.

Focus on:
1. What went wrong in the reasoning process
2. Which constraints were violated or missed
3. What deductive steps were skipped or incorrect
4. General strategies to avoid similar errors

Provide concise, actionable insights that can help improve future reasoning."""

        user_prompt = f"""Analyze the following logic puzzle reasoning errors and extract key learning experiences.

Question: {question}

Error Analysis:
{error_analysis['error_summary']}

Detailed Errors:
{json.dumps(error_analysis['errors_by_type'], indent=2, ensure_ascii=False)}

Generate 1-3 concise learning experiences that address these errors. Format each experience as:
- Clear, actionable guidance
- Focused on preventing similar errors
- General enough to apply to multiple problems

Experiences:"""

        try:
            response = await self.llm.query_one(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
            )
            return response
        except Exception as e:
            logger.error(f"Error generating experience: {e}")
            return None


def verify_func_with_error_analysis(
    sample: EvaluationSample, 
    timeout_score: float = 0,
    provide_error_reasoning: bool = True,
    **kwargs
) -> Dict:
    """
    Enhanced verify function that includes detailed error analysis.
    
    This can be used as a drop-in replacement for the standard verify_func
    in utu/practice/verify/logic.py.
    
    Args:
        sample: EvaluationSample to verify
        timeout_score: Score to return on timeout
        provide_error_reasoning: Whether to include detailed error analysis in reasoning
        **kwargs: Additional arguments
        
    Returns:
        Dictionary with 'reward' and 'reasoning' (with error analysis if enabled)
    """
    # Import the original verify function
    from utu.practice.verify.logic import verify_func as original_verify_func
    
    # Get the standard verification result
    result = original_verify_func(sample, timeout_score, **kwargs)
    
    # If answer is correct or error reasoning not requested, return as-is
    if result["reward"] >= 1.0 or not provide_error_reasoning:
        return result
    
    # Perform error analysis on incorrect answers
    try:
        analyzer = LogicErrorAnalyzer()
        error_analysis = analyzer.analyze_reasoning(sample)
        
        # Add error analysis to reasoning
        if error_analysis["has_errors"]:
            result["reasoning"] = error_analysis["error_summary"]
            result["detailed_errors"] = error_analysis["errors_by_type"]
    except Exception as e:
        logger.warning(f"Error during error analysis: {e}")
    
    return result


async def main():
    """Example usage of the Logic Error Analyzer."""
    print("="*70)
    print("Logic Error Analyzer for ZebraLogic Training")
    print("="*70)
    
    # Example: Create a sample with errors
    sample = EvaluationSample(
        dataset="ZebraLogic-Test",
        response="""
Let me solve this step by step:

1. From clue 1, Eric is in house 3.
2. From clue 2, Peter has birthday in April.
3. I'll assume Alice is in house 1 with the bird. (This is wrong)
4. Then Peter must be in house 1. (Contradiction!)
5. Wait, that means Alice and Peter are both in house 1. (Constraint violation!)

Therefore, the solution is:

<answer>
{"header": ["House", "Name", "Color"], 
 "rows": [["1", "Alice", "Red"], 
          ["2", "Alice", "Blue"],  
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
    
    # Analyze errors
    analyzer = LogicErrorAnalyzer()
    error_analysis = analyzer.analyze_reasoning(sample)
    
    # Print results
    print("\n📊 Error Analysis Results:")
    print(f"   Total errors found: {error_analysis['total_errors']}")
    print(f"\n{error_analysis['error_summary']}")
    
    print("\n" + "="*70)
    print("✅ Analysis complete!")
    print("\nTo use this analyzer in training:")
    print("1. Import LogicErrorAnalyzer in your verification module")
    print("2. Call analyzer.analyze_reasoning(sample) for each sample")
    print("3. Use the error analysis in experience generation")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())


