"""
SkillsBench verify function for TF-LLM.

In the normal harbor-based flow the reward comes from the task's
``tests/test.sh`` verifier and is written into ``sample.reward`` during
rollout.  This verify function therefore simply reads back that pre-computed
reward rather than calling an LLM judge.

It is wired up via the eval YAML fields:
    verify_filename: "skillsbench.py"
    verify_func_name: "verify_func"

If for some reason the harbor reward is missing (e.g. a dry-run without
Docker), the function falls back to a lightweight LLM judge that checks
whether the agent's response plausibly addresses the task.
"""

from __future__ import annotations

import json

from ...utils import get_logger

logger = get_logger(__name__)

_FALLBACK_JUDGE_PROMPT = """\
You are evaluating an AI agent's attempt to complete a software engineering task.

Task description:
{task}

Agent's response / actions:
{response}

Does the agent's response demonstrate a plausible and correct approach to \
completing the task?  Reply with:
  correct: yes   (if the response is a genuine, plausible solution)
  correct: no    (if the response is wrong, incomplete, or irrelevant)
  reasoning: <one sentence>
"""


async def verify_func(sample, llm=None, **kwargs) -> dict:
    """
    Verify a SkillsBench task result.

    1. If ``sample.reward`` is already set (by the harbor verifier during
       rollout), use it directly – this is the common path.
    2. Otherwise, fall back to a simple LLM judge (useful for testing
       without Docker/harbor).

    Args:
        sample: ``EvaluationSample`` with ``raw_question``, ``response``,
                and optionally ``reward`` pre-filled by harbor.
        llm:    ``SimplifiedAsyncOpenAI`` client (injected by the processor).

    Returns:
        dict with keys ``reward`` (float) and ``reasoning`` (str).
    """
    # --- Path 1: harbor verifier already computed reward ---
    if sample.reward is not None:
        reward = float(sample.reward)
        return {
            "reward": reward,
            "reasoning": f"harbor verifier reward: {reward}",
        }

    # --- Path 2: LLM fallback judge ---
    if llm is None:
        logger.warning("No LLM client available for fallback judge; returning 0.0")
        return {"reward": 0.0, "reasoning": "No reward from harbor and no LLM available"}

    task = sample.raw_question or ""
    response = sample.response or ""

    if not response.strip():
        return {"reward": 0.0, "reasoning": "Agent produced no response"}

    prompt = _FALLBACK_JUDGE_PROMPT.format(task=task[:2000], response=response[:3000])

    try:
        judge_response = await llm.query_one(
            messages=[
                {"role": "system", "content": "You are a strict but fair evaluator."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as exc:
        logger.error(f"LLM judge call failed: {exc}")
        return {"reward": 0.0, "reasoning": f"LLM judge error: {exc}"}

    # Parse "correct: yes/no" from response
    reward = 0.0
    reasoning = judge_response.strip()
    lower = judge_response.lower()
    if "correct: yes" in lower or "correct:yes" in lower:
        reward = 1.0
    elif "correct: no" in lower or "correct:no" in lower:
        reward = 0.0
    else:
        # Ambiguous – give partial credit
        reward = 0.3
        reasoning = f"Ambiguous judge response: {judge_response[:200]}"

    return {"reward": reward, "reasoning": reasoning}
