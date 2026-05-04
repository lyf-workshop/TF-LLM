"""
SkillsBench Processer for TF-LLM evaluation pipeline.

Differences from other processers:
- ``preprocess_one`` stores experiences/Skills config in augmented_question
  so that ``BaseBenchmark._rollout_skillsbench_harbor`` can pick them up.
- ``judge_one`` reads the reward that was already set by the harbor verifier
  during the rollout phase – no LLM judge needed.
- ``calculate_metrics`` reports pass rate overall and broken down by domain
  and difficulty.
"""

from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean
from typing import TYPE_CHECKING

from ...config import EvalConfig
from ...utils import get_logger
from ..data import EvaluationSample
from .base_processor import BaseProcesser

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class SkillsBenchProcesser(BaseProcesser):
    """Processer for SkillsBench tasks executed via harbor."""

    name = "SkillsBench"

    def __init__(self, config: EvalConfig) -> None:
        super().__init__(config)

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    def preprocess_one(self, sample: EvaluationSample, recorder=None) -> EvaluationSample:
        """
        Store experiences (if any) and the Skills injection flag in
        ``augmented_question`` as a JSON payload.

        The actual prompt construction happens inside ``TFLLMHarborAgent``
        because the agent needs to communicate with the Docker environment
        directly.  We use ``augmented_question`` as the channel to pass
        runtime config through TF-LLM's DB-backed pipeline.
        """
        experiences: dict[str, str] = {}
        if recorder is not None and recorder.experiences:
            experiences = dict(recorder.experiences)

        inject_skills = False
        if hasattr(self.config, "skillsbench") and self.config.skillsbench:
            inject_skills = getattr(self.config.skillsbench, "inject_curated_skills", False)

        # Payload consumed by _rollout_skillsbench_harbor in BaseBenchmark
        payload = {
            "original_instruction": sample.raw_question,
            "experiences": experiences,
            "inject_curated_skills": inject_skills,
        }

        sample.update(augmented_question=json.dumps(payload, ensure_ascii=False))
        return sample

    # ------------------------------------------------------------------
    # Judging
    # ------------------------------------------------------------------

    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        """
        The harbor verifier already ran and the reward was written into
        ``data.reward`` by ``_rollout_skillsbench_harbor``.

        This method just normalises the fields expected by the rest of the
        pipeline (``correct``, ``judged_response``).
        """
        reward = data.reward if data.reward is not None else 0.0
        correct = reward >= 1.0

        data.update(
            correct=correct,
            reward=reward,
            judged_response="harbor_verifier_pass" if correct else "harbor_verifier_fail",
        )
        return data

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def calculate_metrics(self, samples: list[EvaluationSample]) -> dict:
        """
        Compute:
          - Overall pass rate
          - Pass rate by domain
          - Pass rate by difficulty
          - Mean reward (for partial-credit tasks)
        """
        if not samples:
            return {"pass_rate": 0.0, "mean_reward": 0.0}

        rewards = []
        by_domain: dict[str, list[float]] = defaultdict(list)
        by_difficulty: dict[str, list[float]] = defaultdict(list)

        for s in samples:
            r = float(s.reward) if s.reward is not None else 0.0
            rewards.append(r)

            meta: dict = {}
            if s.meta:
                try:
                    meta = s.meta if isinstance(s.meta, dict) else json.loads(s.meta)
                except (json.JSONDecodeError, TypeError):
                    pass

            domain = meta.get("domain", "unknown")
            difficulty = meta.get("difficulty", "unknown")
            by_domain[domain].append(r)
            by_difficulty[difficulty].append(r)

        metrics: dict = {
            "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in rewards),
            "mean_reward": mean(rewards),
            "num_tasks": len(samples),
            "by_domain": {d: round(mean(v), 4) for d, v in sorted(by_domain.items())},
            "by_difficulty": {d: round(mean(v), 4) for d, v in sorted(by_difficulty.items())},
        }
        return metrics
