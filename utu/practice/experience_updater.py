"""
Experience updater for training-free GRPO.
"""

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from agents import custom_span
from tqdm import tqdm

from ..config import AgentConfig
from ..db import EvaluationSample
from ..utils import FileUtils, SimplifiedAsyncOpenAI, get_logger
from .experience_models import FailureMode, TaskStage
from .experience_pool import consolidate_and_apply, split_experiences
from .utils import TaskRecorder

logger = get_logger(__name__)


@dataclass(frozen=True)
class _RolloutGroupStats:
    min_reward: float
    max_reward: float
    mean_reward: float
    has_reward_contrast: bool


class ExperienceUpdater:
    def __init__(self, config: AgentConfig, agent_objective: str, learning_objective: str):
        self.config = config
        self.agent_objective = agent_objective
        self.learning_objective = learning_objective
        self.prompts = FileUtils.load_prompts("practice/experience.yaml")
        self.llm = SimplifiedAsyncOpenAI(**config.model.model_provider.model_dump())
        # Raw, per-problem case insights from the most recent run() — consumed by
        # the hierarchical manager as L0 candidates (set at the end of run()).
        self.last_l0_candidates: list[dict[str, Any]] = []
        self.last_l0_metadata_coverage: dict[str, dict[str, float | int]] = {}

    async def run(
        self,
        rollouts: list[EvaluationSample],
        recorder: TaskRecorder,
        concurrency: int = 16,
        given_ground_truth: bool = True,
        num_experiences: int = 2,
    ) -> None:
        """Update experiences based on rollouts."""
        # 1. Summarize trajectory for each rollout
        with custom_span("Trajectory Summarization"):
            problem_to_summarized_rollouts = await self._single_rollout_summary(
                rollouts=rollouts, concurrency=concurrency, given_ground_truth=given_ground_truth
            )

        # 2. Generate semantic group advantages based on summarized rollouts
        with custom_span("Semantic Group Advantage"):
            new_experiences = await self._group_advantage(
                problem_to_summarized_rollouts=problem_to_summarized_rollouts,
                concurrency=concurrency,
                given_ground_truth=given_ground_truth,
                num_experiences=num_experiences,
            )

        # Stash the raw, pre-merge per-problem insights as L0 candidates.
        # These are the most concrete/primitive lessons, before the flat pool's
        # LLM merge abstracts/consolidates them.
        l0_candidates: list[dict[str, Any]] = []
        for item in new_experiences:
            metadata = self._l0_source_metadata(item.get("rollouts", []))
            for content in split_experiences(item.get("experiences", "")):
                l0_candidates.append({"content": content, **metadata})
        self.last_l0_candidates = l0_candidates
        self.last_l0_metadata_coverage = self._metadata_coverage(l0_candidates)
        logger.info(
            "Generated L0 metadata coverage: %s",
            json.dumps(self.last_l0_metadata_coverage, sort_keys=True),
        )

        # 3. group update experiences
        with custom_span("Group update"):
            critiques = await self._group_update(
                recorder=recorder,
                new_experiences=new_experiences,
                concurrency=concurrency,
            )

        # 4. batch update experiences
        with custom_span("Batch update"):
            new_experiences = await self._batch_update(
                recorder=recorder,
                critiques=critiques,
            )

        # 5. assign new experience IDs
        new_experiences = {f"G{i}": exp for i, exp in enumerate(new_experiences.values())}
        recorder.experiences_update(new_experiences)
        return new_experiences

    @staticmethod
    def _stable_task_id(rollout: dict[str, Any]) -> str:
        meta = ExperienceUpdater._rollout_meta(rollout)
        explicit_task_id = meta.get("task_id")
        source = str(rollout.get("source") or "").strip()
        if explicit_task_id is not None and str(explicit_task_id).strip():
            prefix = source or "task"
            return f"{prefix}:{explicit_task_id}"
        dataset = str(rollout.get("dataset") or "").strip()
        dataset_index = rollout.get("dataset_index")
        if dataset and dataset_index is not None:
            return f"{dataset}:{dataset_index}"
        question = str(rollout.get("raw_question") or "").strip()
        digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
        return f"task:{digest}"

    @staticmethod
    def _rollout_meta(rollout: dict[str, Any]) -> dict[str, Any]:
        meta = rollout.get("meta")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                return {}
        return meta if isinstance(meta, dict) else {}

    @staticmethod
    def _metadata_coverage(candidates: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
        fields = ("domain", "task_family", "failure_mode", "tool_type", "strategy_type", "task_stage")
        total = len(candidates)
        result: dict[str, dict[str, float | int]] = {}
        for field_name in fields:
            known = sum(
                item.get(field_name) is not None
                and str(getattr(item.get(field_name), "value", item.get(field_name))).strip().lower()
                not in {"", "unknown"}
                for item in candidates
            )
            result[field_name] = {
                "known": known,
                "total": total,
                "ratio": known / total if total else 0.0,
            }
        return result

    @staticmethod
    def _normalised_explicit_stage(rollouts: list[dict[str, Any]]) -> TaskStage:
        values = {
            str(ExperienceUpdater._rollout_meta(rollout).get("task_stage") or "").strip().lower()
            for rollout in rollouts
        }
        values.discard("")
        if len(values) != 1:
            return TaskStage.UNKNOWN
        try:
            return TaskStage(next(iter(values)))
        except ValueError:
            return TaskStage.UNKNOWN

    @staticmethod
    def _failure_mode_from_evidence(rollouts: list[dict[str, Any]]) -> FailureMode:
        metas = [ExperienceUpdater._rollout_meta(rollout) for rollout in rollouts]
        infra_error_types = {str(meta.get("infra_error_type") or "").strip().lower() for meta in metas}
        error_types = {str(meta.get("error_type") or "").strip().lower() for meta in metas}
        infra_error_types.discard("")
        error_types.discard("")
        outcomes = {
            str(meta.get("trial_outcome") or meta.get("outcome") or "").strip().lower()
            for meta in metas
        }
        outcomes.discard("")
        if any("timeout" in value for value in infra_error_types | error_types | outcomes):
            return FailureMode.TIMEOUT
        if infra_error_types or outcomes & {"infra_error", "fatal_error"}:
            return FailureMode.INFRASTRUCTURE_ERROR
        if error_types or outcomes & {"agent_error", "execution_error", "tool_error"}:
            return FailureMode.EXECUTION_ERROR
        rewards = [
            ExperienceUpdater._safe_reward(rollout.get("reward"))
            for rollout in rollouts
            if rollout.get("reward") is not None
        ]
        has_success = any(reward > 0.0 for reward in rewards)
        has_failure = any(reward <= 0.0 for reward in rewards)
        if has_success and has_failure:
            return FailureMode.MIXED_OUTCOME
        if rewards and has_success:
            return FailureMode.NONE
        if rewards and has_failure:
            return FailureMode.VERIFIER_FAILURE
        return FailureMode.UNKNOWN

    def _l0_source_metadata(self, rollouts: list[dict[str, Any]]) -> dict[str, Any]:
        """Preserve the source evidence available at L0 generation time.

        Tool/strategy/stage are intentionally left empty when the rollout does
        not expose trustworthy structured values.  The hierarchy schema keeps
        those fields for later extractors instead of guessing from prose.
        """

        if not rollouts:
            return {
                "source_task_ids": [],
                "source_rollout_ids": [],
                "domain": None,
                "task_family": None,
                "failure_mode": FailureMode.UNKNOWN.value,
                "strategy_type": None,
                "tool_type": None,
                "task_stage": TaskStage.UNKNOWN.value,
            }
        task_ids = sorted({self._stable_task_id(rollout) for rollout in rollouts})
        rollout_ids = []
        for rollout in rollouts:
            rollout_id = rollout.get("trace_id") or rollout.get("id")
            if rollout_id is None:
                evidence = json.dumps(
                    {
                        "task": self._stable_task_id(rollout),
                        "response": rollout.get("response"),
                        "trajectory": rollout.get("trajectories") or rollout.get("trajectory"),
                        "reward": rollout.get("reward"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()[:16]
                rollout_id = f"rollout:{digest}"
            rollout_ids.append(str(rollout_id))
        metas = [self._rollout_meta(rollout) for rollout in rollouts]
        domains = {str(meta.get("domain")).strip() for meta in metas if meta.get("domain")}
        task_families = {
            str(meta.get("task_family")).strip() for meta in metas if meta.get("task_family")
        }
        strategy_types = {
            str(meta.get("strategy_type")).strip() for meta in metas if meta.get("strategy_type")
        }
        tool_sets = []
        for meta in metas:
            tools = meta.get("required_tools") or meta.get("tool_type") or []
            if isinstance(tools, str):
                tools = [tools]
            if tools:
                tool_sets.append("|".join(sorted({str(tool).strip() for tool in tools if str(tool).strip()})))
        tool_types = set(tool_sets)
        return {
            "source_task_ids": task_ids,
            "source_rollout_ids": sorted(set(rollout_ids)),
            "domain": next(iter(domains)) if len(domains) == 1 else None,
            "task_family": next(iter(task_families)) if len(task_families) == 1 else None,
            "failure_mode": self._failure_mode_from_evidence(rollouts).value,
            "strategy_type": next(iter(strategy_types)) if len(strategy_types) == 1 else None,
            "tool_type": next(iter(tool_types)) if len(tool_types) == 1 else None,
            "task_stage": self._normalised_explicit_stage(rollouts).value,
        }

    async def _single_rollout_summary(
        self,
        rollouts: list[EvaluationSample],
        concurrency: int,
        given_ground_truth: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        """Summarize each rollout's trajectory.

        This method is designed to be environment-agnostic:
        - Do not assume rewards are in (0, 1). Rewards can be 0/1 (sparse) or > 1.
        - Learn from all-success and all-failure groups as well.
        - Summarize only a representative subset per problem to enable counterfactual
          comparisons (best vs worst) while controlling cost.
        """
        # group by problems
        problems_to_rollouts = defaultdict(list)
        for rollout in rollouts:
            if not rollout.raw_question:
                continue
            problems_to_rollouts[rollout.raw_question].append(rollout)

        all_rollouts_to_process: list[EvaluationSample] = []
        for grouped_rollouts in problems_to_rollouts.values():
            all_rollouts_to_process.extend(self._select_representative_rollouts(grouped_rollouts, max_items=4))

        semaphore = asyncio.Semaphore(concurrency)

        async def summarize_with_semaphore(item: EvaluationSample):
            async with semaphore:
                max_retries = 5
                base_delay = 2.0
                for attempt in range(max_retries):
                    try:
                        with custom_span("summary single rollout"):
                            sp = FileUtils.get_jinja_template_str(
                                self.prompts["SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP"]
                            ).render(
                                agent_objective=self.agent_objective,
                                learning_objective=self.learning_objective,
                            )
                            trajectory_data = self._extract_trajectory_for_prompt(item)

                            up = FileUtils.get_jinja_template_str(
                                self.prompts["SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP"]
                            ).render(
                                question=item.raw_question,
                                trajectory=trajectory_data,
                                answer=item.correct_answer if given_ground_truth else "[REDACTED]",
                                critique=item.reasoning or "[No critique provided]",
                                reward=item.reward,
                                response=item.response or "",
                            )
                            response = await self.llm.query_one(
                                messages=[
                                    {"role": "system", "content": sp},
                                    {"role": "user", "content": up},
                                ],
                                **self.config.model.model_params.model_dump(),
                            )
                        return {"trajectory_summary": response, "meta": item.meta, **item.model_dump()}
                    except Exception as e:
                        error_str = str(e)
                        is_rate_limit = (
                            "429" in error_str or "rate limit" in error_str.lower() or "TPM limit" in error_str
                        )

                        if is_rate_limit and attempt < max_retries - 1:
                            delay = base_delay * (2**attempt) + (attempt * 0.5)
                            logger.warning(
                                f"Rate limit hit in summary (attempt {attempt + 1}/{max_retries}), "
                                f"retrying after {delay:.1f}s"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.warning(f"Warning: failed in single rollout summary, {e}")
                            return None
                return None

        # parallel running
        tasks = [summarize_with_semaphore(item) for item in all_rollouts_to_process]
        results = defaultdict(list)
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Single rollout summary"):
            result = await task
            if result is not None:
                problem = result["raw_question"]
                results[problem].append(result)
        return results

    async def _group_advantage(
        self,
        problem_to_summarized_rollouts: dict[str, list[dict[str, Any]]],
        concurrency: int,
        given_ground_truth: bool,
        num_experiences: int,
    ) -> list[dict[str, Any]]:
        """Generate experiences for each query based on summarized rollouts.

        Environment-agnostic behavior:
        - Learn from all-failure, all-success, and mixed groups.
        - Prefer counterfactual comparisons (best vs worst) when rewards differ.
        """
        all_rollouts: list[list[dict[str, Any]]] = []
        for grouped in problem_to_summarized_rollouts.values():
            selected = self._select_counterfactual_summaries(grouped, max_items=4)
            if selected:
                all_rollouts.append(selected)

        semaphore = asyncio.Semaphore(concurrency)

        async def critique_with_semaphore(rollouts_per_problem: list[dict]):
            async with semaphore:
                max_retries = 10
                base_delay = 10.0
                for attempt in range(max_retries):
                    try:
                        with custom_span("single query group advantage"):
                            formatted_trajectories = self._format_counterfactual_trajectories(
                                rollouts_per_problem=rollouts_per_problem,
                                given_ground_truth=given_ground_truth,
                            )
                            sp = FileUtils.get_jinja_template_str(
                                self.prompts["SINGLE_QUERY_GROUP_ADVANTAGE_SP"]
                            ).render(
                                agent_objective=self.agent_objective,
                                learning_objective=self.learning_objective,
                                num_experiences=num_experiences,
                            )
                            up = FileUtils.get_jinja_template_str(
                                self.prompts["SINGLE_QUERY_GROUP_ADVANTAGE_UP"]
                            ).render(
                                question=rollouts_per_problem[0]["raw_question"],
                                answer=rollouts_per_problem[0]["correct_answer"]
                                if given_ground_truth
                                else "[REDACTED]",
                                trajectories=formatted_trajectories,
                            )
                            response = await self.llm.query_one(
                                messages=[
                                    {"role": "system", "content": sp},
                                    {"role": "user", "content": up},
                                ],
                                **self.config.model.model_params.model_dump(),
                            )

                            # extract experiences from the response
                            pattern = re.compile(r"<Experiences>\s*(.*?)\s*</Experiences>", re.DOTALL | re.IGNORECASE)
                            match = pattern.search(response)
                            experiences = match.group(1).strip() if match else ""
                        return {"rollouts": rollouts_per_problem, "critique": response, "experiences": experiences}
                    except Exception as e:
                        error_str = str(e)
                        is_rate_limit = (
                            "429" in error_str or "rate limit" in error_str.lower() or "TPM limit" in error_str
                        )

                        if is_rate_limit and attempt < max_retries - 1:
                            delay = base_delay * (2**attempt) + (attempt * 0.5)
                            logger.warning(
                                f"Rate limit hit in group advantage (attempt {attempt + 1}/{max_retries}), "
                                f"retrying after {delay:.1f}s"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.warning(f"Warning: failed in single group advantage, {e}")
                            return None
                return None

        # parallel running
        results = []
        tasks = [critique_with_semaphore(rollouts_per_problem) for rollouts_per_problem in all_rollouts]
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Single query group advantage"):
            result = await task
            if result is not None:
                results.append(result)

        return results

    async def _group_update(
        self,
        recorder: TaskRecorder,
        new_experiences: list[dict],
        concurrency: int,
    ) -> dict[str, str]:
        """Group update experiences based on critiques."""
        semaphore = asyncio.Semaphore(concurrency)
        max_retries = 10
        base_delay = 10.0  # Base delay in seconds

        async def group_update_with_semaphore(new_experience: dict):
            async with semaphore:
                for attempt in range(max_retries):
                    try:
                        with custom_span("single group update"):
                            # get current experiences from recorder
                            curr_experiences = recorder.experiences or {}
                            formatted_experiences = (
                                "\n".join([f"[{i}]. {e}" for i, e in curr_experiences.items()])
                                if curr_experiences
                                else "None"
                            )
                            sp = FileUtils.get_jinja_template_str(
                                self.prompts["GROUP_EXPERIENCE_UPDATE_TEMPLATE_SP"]
                            ).render(
                                agent_objective=self.agent_objective,
                                learning_objective=self.learning_objective,
                            )
                            up = FileUtils.get_jinja_template_str(
                                self.prompts["GROUP_EXPERIENCE_UPDATE_TEMPLATE_UP"]
                            ).render(
                                existing_experiences=formatted_experiences,
                                new_experiences=new_experience["experiences"],
                            )
                            response = await self.llm.query_one(
                                messages=[
                                    {"role": "system", "content": sp},
                                    {"role": "user", "content": up},
                                ],
                                **self.config.model.model_params.model_dump(),
                            )
                            # parse response
                            response = response.split("```json")[-1].split("```")[0]
                            operations = json.loads(response)
                        return {"operations": operations, **new_experience}
                    except Exception as e:
                        error_str = str(e)
                        # Check if it's a rate limit error (429)
                        is_rate_limit = (
                            "429" in error_str or "rate limit" in error_str.lower() or "TPM limit" in error_str
                        )

                        if is_rate_limit and attempt < max_retries - 1:
                            # Exponential backoff with jitter
                            delay = base_delay * (2**attempt) + (attempt * 0.5)
                            logger.warning(
                                f"Rate limit hit (attempt {attempt + 1}/{max_retries}), "
                                f"retrying after {delay:.1f}s: {e}"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.warning(f"Warning: failed in group update experience, {e}")
                            return None
                return None

        # parallel running
        results = []
        tasks = [group_update_with_semaphore(new_experience) for new_experience in new_experiences]
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Group update"):
            result = await task
            if result is not None:
                results.append(result)
        return results

    async def _batch_update(
        self, recorder: TaskRecorder, critiques: list[dict], max_retries: int = 3
    ) -> dict[str, dict]:
        """Batch update experiences based on critiques.

        Delegates the consolidation + apply to the shared ``pool_merge`` machinery
        (see ``experience_pool.consolidate_and_apply``) so the flat pool and the
        hierarchical L0/L1/L2 pools share one merge implementation.
        """
        logger.info("Batch update")
        all_operations = []
        for each in critiques:
            all_operations.extend(each["operations"])
        print("- Num of operations to process:", len(all_operations))

        experiences = recorder.experiences or {}
        new_experiences = await consolidate_and_apply(
            self.llm,
            self.prompts,
            self.agent_objective,
            self.learning_objective,
            existing=experiences,
            operations=all_operations,
            model_params=self.config.model.model_params.model_dump(),
            id_prefix="",
            max_retries=max_retries,
        )
        print("- Num of candidate experiences:", len(new_experiences))
        return new_experiences

    @staticmethod
    def _safe_reward(reward: Any) -> float:
        try:
            if reward is None:
                return 0.0
            return float(reward)
        except Exception:
            return 0.0

    def _group_stats(self, rollouts: Iterable[EvaluationSample | dict[str, Any]]) -> _RolloutGroupStats:
        rewards = [
            self._safe_reward(getattr(r, "reward", None) if not isinstance(r, dict) else r.get("reward"))
            for r in rollouts
        ]
        if not rewards:
            return _RolloutGroupStats(min_reward=0.0, max_reward=0.0, mean_reward=0.0, has_reward_contrast=False)
        min_r = min(rewards)
        max_r = max(rewards)
        mean_r = sum(rewards) / len(rewards)
        return _RolloutGroupStats(
            min_reward=min_r,
            max_reward=max_r,
            mean_reward=mean_r,
            has_reward_contrast=(max_r - min_r) > 1e-9,
        )

    def _select_representative_rollouts(
        self, rollouts: list[EvaluationSample], max_items: int = 4
    ) -> list[EvaluationSample]:
        if not rollouts:
            return []
        if len(rollouts) <= max_items:
            return rollouts

        rewards = [self._safe_reward(r.reward) for r in rollouts]
        best_idx = max(range(len(rollouts)), key=lambda i: rewards[i])
        worst_idx = min(range(len(rollouts)), key=lambda i: rewards[i])
        selected_indices = [best_idx] if best_idx == worst_idx else [best_idx, worst_idx]
        for i in range(len(rollouts)):
            if len(selected_indices) >= max_items:
                break
            if i not in selected_indices:
                selected_indices.append(i)
        return [rollouts[i] for i in selected_indices]

    def _select_counterfactual_summaries(
        self, summaries: list[dict[str, Any]], max_items: int = 4
    ) -> list[dict[str, Any]]:
        if not summaries:
            return []
        if len(summaries) <= max_items:
            return summaries
        rewards = [self._safe_reward(s.get("reward")) for s in summaries]
        best_idx = max(range(len(summaries)), key=lambda i: rewards[i])
        worst_idx = min(range(len(summaries)), key=lambda i: rewards[i])
        selected_indices = [best_idx] if best_idx == worst_idx else [best_idx, worst_idx]
        for i in range(len(summaries)):
            if len(selected_indices) >= max_items:
                break
            if i not in selected_indices:
                selected_indices.append(i)
        return [summaries[i] for i in selected_indices]

    def _format_counterfactual_trajectories(
        self, rollouts_per_problem: list[dict[str, Any]], given_ground_truth: bool
    ) -> str:
        if not rollouts_per_problem:
            return ""
        rewards = [self._safe_reward(each.get("reward")) for each in rollouts_per_problem]
        best_reward = max(rewards) if rewards else 0.0
        worst_reward = min(rewards) if rewards else 0.0
        has_contrast = (best_reward - worst_reward) > 1e-9

        lines: list[str] = []
        lines.append(
            f"Group Stats: n={len(rollouts_per_problem)}, best={best_reward}, "
            f"worst={worst_reward}, contrast={has_contrast}"
        )
        lines.append("")

        best_idx = max(range(len(rollouts_per_problem)), key=lambda i: rewards[i])
        worst_idx = min(range(len(rollouts_per_problem)), key=lambda i: rewards[i])

        for i, each in enumerate(rollouts_per_problem):
            if i == best_idx and i == worst_idx:
                label = "ONLY"
            elif i == best_idx:
                label = "BEST"
            elif i == worst_idx:
                label = "WORST"
            else:
                label = "OTHER"

            reward_str = each.get("reward") if given_ground_truth else "[REDACTED]"
            lines.append(f"[{label}] Attempt {i + 1} (Reward {reward_str}):")
            lines.append(each.get("trajectory_summary", ""))
            lines.append("")

        if not has_contrast:
            lines.append(
                "Note: Rewards are identical across attempts. Extract robust success patterns (if all succeed) "
                "or root-cause failure modes + recovery strategies (if all fail), focusing on the learning objective."
            )
        return "\n".join(lines).strip()

    def _extract_trajectory_for_prompt(self, item: EvaluationSample, max_chars: int = 8000) -> str:
        """Extract a human-readable trajectory string from various trajectory encodings."""
        if not item.trajectories:
            return "No trajectory available"
        try:
            parsed = json.loads(item.trajectories)
        except Exception as e:
            logger.warning(f"Failed to parse trajectories JSON: {e}")
            return "Trajectory parsing failed"

        extracted: Any = parsed
        if isinstance(parsed, list) and parsed:
            first = parsed[0]
            if isinstance(first, dict) and "trajectory" in first:
                extracted = first.get("trajectory")

        try:
            text = json.dumps(extracted, ensure_ascii=False, indent=2)
        except Exception:
            text = str(extracted)

        if len(text) > max_chars:
            text = text[: max_chars - 20] + "\n... [truncated]"
        return text
