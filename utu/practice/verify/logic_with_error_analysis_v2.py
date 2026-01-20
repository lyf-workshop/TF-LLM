"""
重新设计的逻辑谜题错误分析验证器 (V2)

改进重点：
1. 专注于推理过程分析，而不是答案对比
2. 简洁、准确的错误提示
3. 避免误报和过度复杂的分析
"""

import json
import re
from typing import Any, Dict, List

from utu.db import EvaluationSample
from utu.utils import get_logger

# Import the original verify function
from utu.practice.verify.logic import verify_func as original_verify_func

logger = get_logger(__name__)


class SimplifiedLogicErrorAnalyzer:
    """
    简化的逻辑错误分析器
    
    只关注高价值的错误类型：
    1. 推理过程缺失或过于简单
    2. 明显的约束违反（在推理文本中）
    3. 推理策略问题
    """
    
    def __init__(self):
        pass
    
    def analyze_reasoning(self, sample: EvaluationSample) -> Dict[str, Any]:
        """
        分析推理过程，返回简洁的错误提示
        
        Args:
            sample: EvaluationSample
            
        Returns:
            Dict with 'has_useful_critique' and 'critique' fields
        """
        response = sample.response
        
        if not response:
            return {
                "has_useful_critique": False,
                "critique": None
            }
        
        # 收集错误提示
        issues = []
        
        # 1. 检查是否有推理过程
        reasoning_quality = self._assess_reasoning_quality(response)
        if reasoning_quality["issue"]:
            issues.append(reasoning_quality["issue"])
        
        # 2. 检查是否有约束处理
        constraint_handling = self._check_constraint_handling(response)
        if constraint_handling["issue"]:
            issues.append(constraint_handling["issue"])
        
        # 3. 检查推理策略
        strategy_issues = self._check_reasoning_strategy(response)
        if strategy_issues:
            issues.extend(strategy_issues)
        
        # 生成critique
        if issues:
            critique = self._format_critique(issues)
            return {
                "has_useful_critique": True,
                "critique": critique
            }
        else:
            return {
                "has_useful_critique": False,
                "critique": None
            }
    
    def _assess_reasoning_quality(self, response: str) -> Dict[str, str]:
        """
        评估推理过程的质量
        
        Returns:
            Dict with 'quality' and optional 'issue'
        """
        # 提取<answer>之前的内容作为推理过程
        answer_match = re.search(r'<answer>', response, re.IGNORECASE)
        if answer_match:
            reasoning_text = response[:answer_match.start()]
        else:
            reasoning_text = response
        
        # 检查推理长度
        reasoning_length = len(reasoning_text.strip())
        
        # 检查是否有步骤标记
        has_steps = bool(re.search(r'(?:^|\n)\s*(?:\d+[\.\)]|步骤\s*\d+|Step\s+\d+)', 
                                   reasoning_text, re.IGNORECASE | re.MULTILINE))
        
        # 检查是否有推理关键词
        reasoning_keywords = [
            'because', 'therefore', 'thus', 'since', 'so',
            '因为', '所以', '因此', '由于', '从而',
            'from.*clue', 'based on', '根据', '依据'
        ]
        has_reasoning_keywords = any(
            re.search(keyword, reasoning_text, re.IGNORECASE) 
            for keyword in reasoning_keywords
        )
        
        # 判断推理质量
        if reasoning_length < 50:
            return {
                "quality": "very_poor",
                "issue": "推理过程过于简短，缺少详细的推导步骤"
            }
        elif not has_steps and not has_reasoning_keywords:
            return {
                "quality": "poor",
                "issue": "推理过程缺少结构化的步骤和逻辑连接词"
            }
        elif not has_steps:
            return {
                "quality": "fair",
                "issue": "推理过程缺少清晰的步骤标记（如1. 2. 3.）"
            }
        else:
            return {
                "quality": "good",
                "issue": None
            }
    
    def _check_constraint_handling(self, response: str) -> Dict[str, str]:
        """
        检查约束处理
        
        Returns:
            Dict with optional 'issue'
        """
        # 检查是否提到clue/线索/约束
        constraint_keywords = [
            r'clue\s*\d+', r'constraint\s*\d+', r'线索\s*\d+', 
            r'约束\s*\d+', r'条件\s*\d+'
        ]
        
        mentions_constraints = any(
            re.search(keyword, response, re.IGNORECASE) 
            for keyword in constraint_keywords
        )
        
        if not mentions_constraints:
            return {
                "issue": "推理过程中没有明确引用问题中的线索或约束条件"
            }
        
        # 检查是否有验证步骤
        verification_keywords = [
            'verify', 'check', 'validate', 'confirm', 'ensure',
            '验证', '检查', '确认', '确保'
        ]
        
        has_verification = any(
            re.search(keyword, response, re.IGNORECASE) 
            for keyword in verification_keywords
        )
        
        if not has_verification:
            return {
                "issue": "推理过程缺少对解决方案的验证步骤"
            }
        
        return {"issue": None}
    
    def _check_reasoning_strategy(self, response: str) -> List[str]:
        """
        检查推理策略问题
        
        Returns:
            List of issues
        """
        issues = []
        
        # 检查是否有系统化方法的迹象
        systematic_keywords = [
            'table', 'matrix', 'grid', 'chart',
            '表格', '矩阵', '网格',
            'list.*all', 'enumerate',
            '列出.*所有', '枚举'
        ]
        
        has_systematic_approach = any(
            re.search(keyword, response, re.IGNORECASE) 
            for keyword in systematic_keywords
        )
        
        # 检查推理长度 - 如果很长但没有系统化方法，可能策略有问题
        if len(response) > 1000 and not has_systematic_approach:
            issues.append("推理过程冗长但缺少系统化的方法（如使用表格、矩阵等工具）")
        
        return issues
    
    def _format_critique(self, issues: List[str]) -> str:
        """
        格式化critique为简洁的提示
        
        Args:
            issues: List of issue descriptions
            
        Returns:
            Formatted critique string
        """
        if not issues:
            return None
        
        # 只保留最重要的2-3个问题
        top_issues = issues[:3]
        
        critique_parts = ["推理过程存在以下问题："]
        for i, issue in enumerate(top_issues, 1):
            critique_parts.append(f"{i}. {issue}")
        
        return "\n".join(critique_parts)


def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    增强的验证函数，使用简化的错误分析 (V2)
    
    改进：
    - 专注于推理过程质量
    - 简洁的错误提示
    - 避免误报
    
    Args:
        sample: EvaluationSample containing the question, response, and ground truth
        timeout_score: Score to return on timeout (default: 0)
        **kwargs: Additional arguments
            - enable_error_analysis: Whether to perform error analysis (default: True)
        
    Returns:
        Dictionary with:
        - 'reward' (float 0.0-1.0): Score for the answer
        - 'reasoning' (str or None): Error analysis for incorrect answers
    """
    # Get standard verification result
    result = original_verify_func(sample, timeout_score, **kwargs)
    
    # Check if error analysis should be performed
    enable_error_analysis = kwargs.get("enable_error_analysis", True)
    
    # If answer is correct, no need for error analysis
    if result["reward"] >= 1.0:
        return result
    
    # If error analysis is disabled, return standard result
    if not enable_error_analysis:
        return result
    
    # Perform simplified error analysis for incorrect answers
    try:
        analyzer = SimplifiedLogicErrorAnalyzer()
        analysis = analyzer.analyze_reasoning(sample)
        
        if analysis["has_useful_critique"]:
            result["reasoning"] = analysis["critique"]
        else:
            # 如果没有检测到具体问题，给一个通用但有用的提示
            result["reasoning"] = "答案不正确。建议在推理过程中：1) 明确引用每个线索；2) 使用系统化的方法（如表格）；3) 验证最终答案。"
            
    except Exception as e:
        # If error analysis fails, log warning but don't fail the verification
        logger.warning(f"Error during error analysis: {e}")
        result["reasoning"] = None
    
    return result


def verify_func_detailed(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    详细模式的验证函数，包含分析细节
    
    用于调试和分析
    """
    result = verify_func(sample, timeout_score, **kwargs)
    
    # 添加分析细节
    if result["reward"] < 1.0 and kwargs.get("enable_error_analysis", True):
        try:
            analyzer = SimplifiedLogicErrorAnalyzer()
            analysis = analyzer.analyze_reasoning(sample)
            result["analysis_details"] = analysis
        except Exception as e:
            logger.warning(f"Error during detailed analysis: {e}")
    
    return result







































































