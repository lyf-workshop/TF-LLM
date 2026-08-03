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

        # In pure eval mode there is no recorder, so the trained experiences live
        # in the agent YAML's ``agent.instructions`` field instead of the
        # ``experiences`` dict. Surface them as ``agent_instructions`` so the
        # harbor agent can use them as its system prompt (otherwise the baked
        # experiences would never reach the agent and practice == baseline).
        agent_instructions = ""
        try:
            agent_cfg = getattr(self.config, "agent", None)
            inner = getattr(agent_cfg, "agent", None) if agent_cfg else None
            agent_instructions = (getattr(inner, "instructions", "") or "") if inner else ""
        except AttributeError:
            agent_instructions = ""

        # Payload consumed by _rollout_skillsbench_harbor in BaseBenchmark
        payload = {
            "original_instruction": sample.raw_question,
            "experiences": experiences,
            "inject_curated_skills": inject_skills,
            "agent_instructions": agent_instructions,
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
        meta = data.meta if isinstance(data.meta, dict) else {}
        if data.stage == "infra_error" or meta.get("eval_status") == "infra_error":
            data.update(correct=None, reward=None, judged_response="infra_error")
            return data

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
          - Paper-aligned task-macro pass rate:
            average rewards within each task's trials, then average across tasks.
          - Strict task-macro pass rate (reward >= 1.0) for debugging.
          - Domain / difficulty breakdowns using paper metadata when available.
          - Coverage against config.pass_k.
        """
        if not samples:
            return {
                "publishable": False,
                "pass_rate": None,
                "task_macro_pass_rate": None,
                "mean_reward": None,
                "coverage": 0.0,
            }

        task_rewards: dict[str, list[float]] = defaultdict(list)
        task_strict: dict[str, list[float]] = defaultdict(list)
        task_trial_indices: dict[str, list[int]] = defaultdict(list)
        task_meta: dict[str, dict] = {}
        infra_error_types: dict[str, int] = defaultdict(int)
        infra_error_trials = 0
        pending_trials = 0
        valid_trials = 0
        is_v4_protocol = False

        for s in samples:
            meta: dict = {}
            if s.meta:
                try:
                    meta = s.meta if isinstance(s.meta, dict) else json.loads(s.meta)
                except (json.JSONDecodeError, TypeError):
                    pass

            task_id = meta.get("task_id") or str(s.dataset_index)
            task_meta.setdefault(task_id, meta)
            eval_status = meta.get("eval_status")
            is_v4_protocol = is_v4_protocol or (
                meta.get("evaluation_protocol") == "skillsbench_v4"
                or eval_status in {"pending", "pending_retry", "valid", "infra_error"}
            )
            if s.stage == "infra_error" or eval_status == "infra_error":
                infra_error_trials += 1
                error_type = meta.get("infra_error_type") or "unknown"
                infra_error_types[str(error_type)] += 1
                continue

            is_legacy_valid = eval_status is None and s.stage == "judged" and s.reward is not None
            is_v4_valid = eval_status == "valid" and s.stage == "judged" and s.reward is not None
            if not (is_legacy_valid or is_v4_valid):
                pending_trials += 1
                continue

            r = float(s.reward)
            valid_trials += 1
            task_rewards[task_id].append(r)
            task_strict[task_id].append(1.0 if r >= 1.0 else 0.0)
            task_trial_indices[task_id].append(int(meta.get("trial_index", 0)))

        task_means = {task_id: mean(values) for task_id, values in task_rewards.items()}
        strict_task_means = {task_id: mean(values) for task_id, values in task_strict.items()}

        by_domain: dict[str, list[float]] = defaultdict(list)
        by_difficulty: dict[str, list[float]] = defaultdict(list)
        for task_id, task_score in task_means.items():
            meta = task_meta.get(task_id, {})
            domain = meta.get("paper_domain") or meta.get("domain") or "unknown"
            difficulty = meta.get("paper_diff") or meta.get("difficulty") or "unknown"
            by_domain[domain].append(task_score)
            by_difficulty[difficulty].append(task_score)

        expected_trials_per_task = max(1, int(getattr(self.config, "pass_k", 1) or 1))
        skillsbench_cfg = getattr(self.config, "skillsbench", None)
        configured_tasks = getattr(skillsbench_cfg, "expected_num_tasks", None)
        expected_num_tasks = int(configured_tasks) if configured_tasks else len(task_meta)
        expected_trials = expected_num_tasks * expected_trials_per_task
        expected_trial_indices = set(range(expected_trials_per_task))
        full_tasks = sum(
            len(values) == expected_trials_per_task
            and (
                not is_v4_protocol
                or set(task_trial_indices[task_id]) == expected_trial_indices
            )
            for task_id, values in task_rewards.items()
        )
        invalid_trial_index_tasks = sorted(
            task_id
            for task_id, values in task_rewards.items()
            if is_v4_protocol
            if len(values) == expected_trials_per_task
            and set(task_trial_indices[task_id]) != expected_trial_indices
        )
        incomplete_tasks = {
            task_id: len(task_rewards.get(task_id, []))
            for task_id in sorted(task_meta)
            if len(task_rewards.get(task_id, [])) != expected_trials_per_task
        }
        coverage_complete = (
            len(task_meta) == expected_num_tasks
            and valid_trials == expected_trials
            and full_tasks == expected_num_tasks
            and infra_error_trials == 0
            and pending_trials == 0
        )
        require_complete = getattr(skillsbench_cfg, "require_complete_coverage", True)
        publishable = coverage_complete or not require_complete

        provisional_task_macro = mean(task_means.values()) if task_means else 0.0
        provisional_strict_macro = mean(strict_task_means.values()) if strict_task_means else 0.0
        valid_sample_rewards = [reward for rewards in task_rewards.values() for reward in rewards]
        headline_task_macro = provisional_task_macro if publishable else None
        headline_strict_macro = provisional_strict_macro if publishable else None

        metrics: dict = {
            "publishable": publishable,
            "status": "COMPLETE" if publishable else "INCOMPLETE",
            "pass_rate": headline_task_macro,
            "task_macro_pass_rate": headline_task_macro,
            "strict_task_macro_pass_rate": headline_strict_macro,
            "mean_reward": headline_task_macro,
            "provisional_task_macro_pass_rate": provisional_task_macro,
            "provisional_strict_task_macro_pass_rate": provisional_strict_macro,
            "sample_mean_reward": mean(valid_sample_rewards) if valid_sample_rewards else 0.0,
            "sample_strict_pass_rate": (
                mean(1.0 if r >= 1.0 else 0.0 for r in valid_sample_rewards)
                if valid_sample_rewards
                else 0.0
            ),
            "num_tasks": len(task_meta),
            "expected_num_tasks": expected_num_tasks,
            "tasks_with_full_valid_trials": full_tasks,
            "num_trials": len(samples),
            "valid_trials": valid_trials,
            "infra_error_trials": infra_error_trials,
            "pending_trials": pending_trials,
            "expected_trials": expected_trials,
            "coverage": round(valid_trials / expected_trials, 4) if expected_trials else 0.0,
            "valid_coverage": round(valid_trials / expected_trials, 4) if expected_trials else 0.0,
            "infra_error_types": dict(sorted(infra_error_types.items())),
            "invalid_trial_index_tasks": invalid_trial_index_tasks,
            "incomplete_tasks": incomplete_tasks,
            "by_domain": {d: round(mean(v), 4) for d, v in sorted(by_domain.items())},
            "by_difficulty": {d: round(mean(v), 4) for d, v in sorted(by_difficulty.items())},
        }
        return metrics
