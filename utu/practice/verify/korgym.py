"""
Verification function for KORGym games.

This function verifies game results by calling KORGym game server's /verify API,
which is consistent with KORGym's eval_lib verification mechanism.
"""

import json
import re
import requests
from typing import Dict, Any

from utu.db import EvaluationSample


def normalize_response(response: str) -> str:
    """
    Cleans up the response string by removing LaTeX formatting and special characters.
    (From KORGym eval_lib/eval.py)
    
    Args:
        response: The raw output string from the model.
    
    Returns:
        str: A simplified and normalized version of the response.
    """
    return (
        response.replace("**", "")
                .replace("$\\boxed{", "")
                .replace("}$", "")
                .replace("\\$", "")
                .replace("$\\text{", "")
                .replace("$", "")
                .replace("\\mathrm{", "")
                .replace("\\{", "")
                .replace("\\text", "")
                .replace("\\(", "")
                .replace("\\mathbf{", "")
                .replace("{", "")
                .replace("\\boxed", "")
    )


def extract_action_from_response(response: str) -> str:
    """
    Extracts the final action/answer from a model's response.
    Looks for the last occurrence of 'Answer:' pattern.
    (Based on KORGym eval_lib/eval.py get_prompt0_response)
    
    Args:
        response: The original model response string.
    
    Returns:
        str: The extracted action/answer string (or empty string if not found).
    """
    if response is None:
        return ""
    
    gen = normalize_response(response)
    pos = gen.lower().rfind("answer")
    if pos == -1:
        return ""
    
    gen = gen[pos:]
    pattern = r"(?i)Answer\s*:\s*(.*)"
    match = re.findall(pattern, gen)
    return match[-1].strip() if match else ""


def call_korgym_verify_api(
    game_server_url: str,
    game_state: Dict[str, Any],
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Calls KORGym game server's /verify API to verify the action.
    (Based on KORGym eval_lib/eval.py verify function)
    
    Args:
        game_server_url: Base URL of the KORGym game server (e.g., "http://localhost:8775")
        game_state: Game state dict containing action and other fields
        timeout: Request timeout in seconds
    
    Returns:
        dict: Updated game state with verification result and score
    """
    try:
        resp = requests.post(
            f"{game_server_url}/verify",
            json=game_state,
            timeout=timeout
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        # If verification fails, return state with score 0
        game_state['score'] = 0
        game_state['verification_error'] = str(e)
        return game_state


def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    Verify the correctness of a KORGym game result using the game server's /verify API.
    This follows the same verification logic as KORGym's eval_lib.
    
    Args:
        sample: EvaluationSample containing:
            - raw_question: Game state/prompt
            - response: Agent's response string
            - metadata: Should contain:
                - game_server_url: URL of the KORGym game server
                - game_state: Current game state dict
                - game_name: Name of the game
        timeout_score: Score to assign when verification times out
        **kwargs: Additional arguments including:
            - game_server_url: Override game server URL
            - verify_timeout: Verification API timeout (default: 30s)
        
    Returns:
        dict: {
          "reward": float,          # 0.0 to 1.0 based on game score
          "reasoning": str | None   # Detailed explanation of the result
        }
    """
    try:
        # Get game server URL from kwargs or metadata
        game_server_url = kwargs.get('game_server_url')
        if not game_server_url and hasattr(sample, 'metadata'):
            metadata = sample.metadata if isinstance(sample.metadata, dict) else {}
            game_server_url = metadata.get('game_server_url', 'http://localhost:8775')
        if not game_server_url:
            game_server_url = 'http://localhost:8775'
        
        # Get game state from metadata
        if hasattr(sample, 'metadata') and isinstance(sample.metadata, dict):
            game_state = sample.metadata.get('game_state', {})
        else:
            game_state = {}
        
        # Extract action from agent's response
        action = extract_action_from_response(sample.response)
        if not action:
            # If no action found, try to use the entire response
            action = sample.response.strip()
        
        # Update game state with the action
        game_state['action'] = action
        
        # Call KORGym verify API
        verify_timeout = kwargs.get('verify_timeout', 30)
        verified_state = call_korgym_verify_api(
            game_server_url,
            game_state,
            timeout=verify_timeout
        )
        
        # Calculate reward based on score
        score = verified_state.get('score', 0)
        is_end = verified_state.get('is_end', False)
        epoch = verified_state.get('epoch', 1)
        
        # For single-turn games, score is typically 0-1 (accuracy)
        # For multi-turn games, score is cumulative points
        # Normalize reward to 0-1 range
        if score >= 1:
            # Multi-turn game with cumulative score
            # Consider it successful if score > 0
            reward = 1.0 if score > 0 else 0.0
        else:
            # Single-turn game or normalized score (0-1)
            reward = float(score)
        
        # Build reasoning
        reasoning_parts = [
            f"Game verification completed.",
            f"Action: {action}",
            f"Score: {score}",
        ]
        
        if 'verification_error' in verified_state:
            reasoning_parts.append(f"Verification error: {verified_state['verification_error']}")
            reward = timeout_score
        
        if is_end:
            reasoning_parts.append(f"Game ended at epoch {epoch}.")
        
        reasoning = " ".join(reasoning_parts)
        
        return {
            "reward": reward,
            "reasoning": reasoning
        }
        
    except Exception as e:
        # If any error occurs, return timeout score
        return {
            "reward": timeout_score,
            "reasoning": f"Verification error: {str(e)}"
        }

