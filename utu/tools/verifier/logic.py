"""
Logic puzzle answer verifier for ZebraLogic dataset
"""


def verify_func(ground_truth: str, predicted_answer: str) -> bool:
    """
    Verify if the predicted answer matches the ground truth for logic puzzles.
    
    Args:
        ground_truth: The correct answer
        predicted_answer: The predicted answer from the agent
        
    Returns:
        True if the answers match, False otherwise
    """
    # Normalize answers by removing extra whitespace and converting to lowercase
    def normalize(text: str) -> str:
        if text is None:
            return ""
        # Remove extra whitespace
        text = " ".join(text.split())
        # Convert to lowercase for case-insensitive comparison
        return text.lower().strip()
    
    gt_normalized = normalize(ground_truth)
    pred_normalized = normalize(predicted_answer)
    
    # Direct match
    if gt_normalized == pred_normalized:
        return True
    
    # Check if prediction contains the ground truth (for longer explanations)
    if gt_normalized in pred_normalized:
        return True
    
    # Check if ground truth contains the prediction (for short answers)
    if pred_normalized in gt_normalized and len(pred_normalized) > 3:
        return True
    
    return False

