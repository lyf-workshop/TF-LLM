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
from .experience_models import (
    FailureMode,
    TaskStage,
    experience_output_language_instruction,
    validate_experience_output_language,
)
from .experience_pool import consolidate_and_apply, split_experiences
from .generation.recovery import GenerationOutputError, GenerationRecovery, error_detail
from .utils import TaskRecorder

logger = get_logger(__name__)
L0_CANDIDATE_GENERATOR_VERSION = "l0-summary-v3-language-contract"


class L0CandidateGenerationError(RuntimeError):
    """A parallel summary stage failed, so no partial candidate batch is safe."""


@dataclass(frozen=True)
class _RolloutGroupStats:
    min_reward: float
    max_reward: float
    mean_reward: float
    has_reward_contrast: bool


class ExperienceUpdater:
    def __init__(
        self,
        config: AgentConfig,
        agent_objective: str,
        learning_objective: str,
        *,
        experience_output_language: str = "same_as_input",
        generation_cache_path: str | None = None,
    ):
        self.config = config
        self.agent_objective = agent_objective
        self.learning_objective = learning_objective
        self.experience_output_language = experience_output_language
        self.experience_output_language_instruction = experience_output_language_instruction(
            experience_output_language
        )
        self.prompts = FileUtils.load_prompts("practice/experience.yaml")
        self.llm = SimplifiedAsyncOpenAI(**config.model.model_provider.model_dump())
        self.llm.max_retries = 0  # The recovery layer owns the bounded retry budget.
        self.generation_recovery = GenerationRecovery(generation_cache_path)
        self.reuse_generation_cache = True
        # Raw, per-problem case insights from the most recent run() — consumed by
        # the hierarchical manager as L0 candidates (set at the end of run()).
        self.last_l0_candidates: list[dict[str, Any]] = []
        self.last_generated_experience_groups: list[dict[str, Any]] = []
        self.last_l0_metadata_coverage: dict[str, dict[str, float | int]] = {}

    async def cleanup(self) -> None:
        await self.llm.close()

    async def _query_generation(self, *, stage: str, source_ids: list[str], messages: list[dict]) -> str:
        recovery = getattr(self, "generation_recovery", None)
        if recovery is None:
            recovery = self.generation_recovery = GenerationRecovery()

        def validate(response: str) -> None:
            if not isinstance(response, str) or not response.strip():
                raise GenerationOutputError(f"{stage} returned empty content")
            if stage == "group_advantage":
                match = re.search(r"<Experiences>\s*(.*?)\s*</Experiences>", response, re.DOTALL | re.IGNORECASE)
                if not match or not split_experiences(match.group(1)):
                    raise GenerationOutputError("group advantage returned no parseable <Experiences> items")
                try:
                    for candidate in split_experiences(match.group(1)):
                        validate_experience_output_language(
                            candidate,
                            self._configured_output_language(),
                            label="generated L0 candidate",
                        )
                except ValueError as error:
                    raise GenerationOutputError(str(error)) from error

        return await recovery.query(
            self.llm,
            request={"messages": messages, **self.config.model.model_params.model_dump()},
            identity={"generator": L0_CANDIDATE_GENERATOR_VERSION, "stage": stage, "source_ids": source_ids},
            validate=validate,
            reuse_cache=getattr(self, "reuse_generation_cache", True),
        )

    def _configured_output_language(self) -> str:
        """Return the language while tolerating legacy ``__new__`` test fixtures."""

        return getattr(self, "experience_output_language", "same_as_input")

    def _output_language_instruction(self) -> str:
        return getattr(
            self,
            "experience_output_language_instruction",
            experience_output_language_instruction(self._configured_output_language()),
        )

    async def run(
        self,
        rollouts: list[EvaluationSample],
        recorder: TaskRecorder,
        concurrency: int = 16,
        given_ground_truth: bool = True,
        num_experiences: int = 2,
        maintain_flat_pool: bool = True,
    ) -> dict[str, str]:
        """Generate candidates and optionally run the legacy flat-pool merge.

        Hierarchical callers pass ``maintain_flat_pool=False`` (or call
        :meth:`generate_l0_candidates` directly) so an unreviewed summary can
        never enter a second, flat experience pool.
        """
        await self.generate_l0_candidates(
            rollouts=rollouts,
            concurrency=concurrency,
            given_ground_truth=given_ground_truth,
            num_experiences=num_experiences,
        )
        if not maintain_flat_pool:
            return dict(recorder.experiences or {})

        new_experiences = self.last_generated_experience_groups

        # Legacy non-hierarchical path: group then batch update.
        with custom_span("Group update"):
            critiques = await self._group_update(
                recorder=recorder,
                new_experiences=new_experiences,
                concurrency=concurrency,
            )

        with custom_span("Batch update"):
            new_experiences = await self._batch_update(
                recorder=recorder,
                critiques=critiques,
            )

        new_experiences = {f"G{i}": exp for i, exp in enumerate(new_experiences.values())}
        recorder.experiences_update(new_experiences)
        return new_experiences

    async def generate_l0_candidates(
        self,
        rollouts: list[EvaluationSample],
        concurrency: int = 16,
        given_ground_truth: bool = True,
        num_experiences: int = 2,
    ) -> list[dict[str, Any]]:
        """Generate raw per-task candidates in parallel without changing a pool."""

        # Never expose data from a previous call after a partial generation
        # failure. A failed batch raises below and remains wholly retryable.
        self.last_l0_candidates = []
        self.last_generated_experience_groups = []
        self.last_l0_metadata_coverage = {}

        with custom_span("Trajectory Summarization"):
            problem_to_summarized_rollouts = await self._single_rollout_summary(
                rollouts=rollouts, concurrency=concurrency, given_ground_truth=given_ground_truth
            )
        if rollouts and not problem_to_summarized_rollouts:
            raise L0CandidateGenerationError(
                "non-empty rollout batch produced no task summaries; refusing an empty candidate cache"
            )

        with custom_span("Semantic Group Advantage"):
            new_experiences = await self._group_advantage(
                problem_to_summarized_rollouts=problem_to_summarized_rollouts,
                concurrency=concurrency,
                given_ground_truth=given_ground_truth,
                num_experiences=num_experiences,
            )
        self.last_generated_experience_groups = new_experiences

        l0_candidates: list[dict[str, Any]] = []
        for item in new_experiences:
            metadata = self._l0_source_metadata(item.get("rollouts", []))
            for content in split_experiences(item.get("experiences", "")):
                try:
                    validate_experience_output_language(
                        content,
                        self._configured_output_language(),
                        label="generated L0 candidate",
                    )
                except ValueError as error:
                    self.last_generated_experience_groups = []
                    raise L0CandidateGenerationError(str(error)) from error
                l0_candidates.append(
                    {
                        "content": content,
                        **metadata,
                        "generator_version": L0_CANDIDATE_GENERATOR_VERSION,
                    }
                )
        if rollouts and not l0_candidates:
            self.last_generated_experience_groups = []
            raise L0CandidateGenerationError(
                "non-empty rollout batch produced no L0 candidates; refusing an empty candidate cache"
            )
        self.last_l0_candidates = l0_candidates
        self.last_l0_metadata_coverage = self._metadata_coverage(l0_candidates)
        logger.info(
            "Generated L0 metadata coverage: %s",
            json.dumps(self.last_l0_metadata_coverage, sort_keys=True),
        )
        return l0_candidates

    @staticmethod
    def _stable_task_id(rollout: EvaluationSample | dict[str, Any]) -> str:
        meta = ExperienceUpdater._rollout_meta(rollout)
        explicit_task_id = meta.get("task_id")
        get_value = rollout.get if isinstance(rollout, dict) else lambda key: getattr(rollout, key, None)
        source = str(get_value("source") or "").strip()
        if explicit_task_id is not None and str(explicit_task_id).strip():
            prefix = source or "task"
            return f"{prefix}:{explicit_task_id}"
        dataset = str(get_value("dataset") or "").strip()
        dataset_index = get_value("dataset_index")
        if dataset and dataset_index is not None:
            return f"{dataset}:{dataset_index}"
        question = str(get_value("raw_question") or "").strip()
        digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
        return f"task:{digest}"

    @staticmethod
    def _rollout_meta(rollout: EvaluationSample | dict[str, Any]) -> dict[str, Any]:
        meta = rollout.get("meta") if isinstance(rollout, dict) else getattr(rollout, "meta", None)
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                return {}
        return meta if isinstance(meta, dict) else {}

    @staticmethod
    def _stable_rollout_id(rollout: EvaluationSample | dict[str, Any]) -> str:
        get_value = rollout.get if isinstance(rollout, dict) else lambda key: getattr(rollout, key, None)
        rollout_id = get_value("trace_id") or get_value("id")
        if rollout_id is not None:
            return str(rollout_id)
        evidence = json.dumps(
            {
                "task": ExperienceUpdater._stable_task_id(rollout),
                "response": get_value("response"),
                "trajectory": get_value("trajectories") or get_value("trajectory"),
                "reward": get_value("reward"),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(evidence.encode("utf-8")).hexdigest()[:16]
        return f"rollout:{digest}"

    @staticmethod
    def _compact_evidence_text(value: Any, limit: int = 2000) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return text if len(text) <= limit else f"{text[:limit]}..."

    def _source_evidence(self, rollouts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence_by_id: dict[str, dict[str, Any]] = {}
        for rollout in rollouts:
            meta = self._rollout_meta(rollout)
            reward = rollout.get("reward")
            if not isinstance(reward, (str, int, float, bool, type(None))):
                reward = str(reward)
            item = {
                "id": self._stable_rollout_id(rollout),
                "task_id": self._stable_task_id(rollout),
                "reward": reward,
                "outcome": self._compact_evidence_text(
                    meta.get("trial_outcome") or meta.get("outcome"), 200
                ),
                "error_type": self._compact_evidence_text(meta.get("error_type"), 200),
                "infra_error_type": self._compact_evidence_text(
                    meta.get("infra_error_type"), 200
                ),
                "trajectory_summary": self._compact_evidence_text(
                    rollout.get("trajectory_summary")
                ),
                "verifier_feedback": self._compact_evidence_text(
                    rollout.get("reasoning"), 1000
                ),
            }
            existing = evidence_by_id.get(item["id"])
            if existing is not None and existing != item:
                raise L0CandidateGenerationError(
                    f"rollout evidence ID collision with different payload: {item['id']}"
                )
            evidence_by_id[item["id"]] = item
        return [evidence_by_id[item_id] for item_id in sorted(evidence_by_id)]

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
                "source_evidence": [],
                "domain": None,
                "task_family": None,
                "failure_mode": FailureMode.UNKNOWN.value,
                "strategy_type": None,
                "tool_type": None,
                "task_stage": TaskStage.UNKNOWN.value,
            }
        task_ids = sorted({self._stable_task_id(rollout) for rollout in rollouts})
        rollout_ids = [self._stable_rollout_id(rollout) for rollout in rollouts]
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
            "source_evidence": self._source_evidence(rollouts),
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
        missing_questions = [
            self._stable_rollout_id(rollout)
            for rollout in rollouts
            if not str(rollout.raw_question or "").strip()
        ]
        if missing_questions:
            raise L0CandidateGenerationError(
                "rollouts missing raw_question; refusing a partial summary batch: "
                + json.dumps(sorted(missing_questions))
            )
        for rollout in rollouts:
            problems_to_rollouts[self._stable_task_id(rollout)].append(rollout)

        all_rollouts_to_process: list[EvaluationSample] = []
        for grouped_rollouts in problems_to_rollouts.values():
            all_rollouts_to_process.extend(self._select_representative_rollouts(grouped_rollouts, max_items=4))

        semaphore = asyncio.Semaphore(concurrency)

        async def summarize_with_semaphore(item: EvaluationSample):
            async with semaphore:
                try:
                    with custom_span("summary single rollout"):
                        sp = FileUtils.get_jinja_template_str(
                            self.prompts["SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP"]
                        ).render(
                            agent_objective=self.agent_objective,
                            learning_objective=self.learning_objective,
                            experience_output_language_instruction=(
                                self._output_language_instruction()
                            ),
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
                        response = await self._query_generation(
                            stage="summary",
                            source_ids=[self._stable_task_id(item), self._stable_rollout_id(item)],
                            messages=[
                                {"role": "system", "content": sp},
                                {"role": "user", "content": up},
                            ],
                        )
                        if not isinstance(response, str) or not response.strip():
                            raise GenerationOutputError("single-rollout summary returned empty content")
                    return {
                        "trajectory_summary": response,
                        **item.model_dump(),
                        # EvaluationSample.model_dump() deliberately omits
                        # both fields, but they are required for provenance
                        # and verifier-backed candidate review.
                        "meta": item.meta,
                        "reasoning": item.reasoning,
                        # UTU's EvaluationSample.model_dump() omits the DB
                        # primary key. Preserve it so trace-less rollouts do
                        # not collapse onto the same fallback evidence ID.
                        "id": item.id,
                    }
                except Exception as e:
                    return {
                        "_generation_error": error_detail(e),
                        "_stage": "single_rollout_summary",
                        "_task_id": self._stable_task_id(item),
                        "_rollout_id": self._stable_rollout_id(item),
                    }

        # parallel running
        tasks = [asyncio.create_task(summarize_with_semaphore(item)) for item in all_rollouts_to_process]
        results = defaultdict(list)
        failures: list[dict[str, Any]] = []
        try:
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Single rollout summary"):
                result = await task
                if result.get("_generation_error"):
                    failures.append(result)
                    continue
                task_id = self._stable_task_id(result)
                results[task_id].append(result)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        if failures:
            raise L0CandidateGenerationError(
                "single-rollout summary failed; refusing a partial candidate batch: "
                + json.dumps(
                    {"failed_count": len(failures), "examples": failures[:5]}, ensure_ascii=False, sort_keys=True
                )
            )
        return {
            task_id: sorted(items, key=self._stable_rollout_id)
            for task_id, items in sorted(results.items())
        }

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
                            experience_output_language_instruction=(
                                self._output_language_instruction()
                            ),
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
                        response = await self._query_generation(
                            stage="group_advantage",
                            source_ids=[self._stable_rollout_id(item) for item in rollouts_per_problem],
                            messages=[
                                {"role": "system", "content": sp},
                                {"role": "user", "content": up},
                            ],
                        )

                        # extract experiences from the response
                        pattern = re.compile(r"<Experiences>\s*(.*?)\s*</Experiences>", re.DOTALL | re.IGNORECASE)
                        match = pattern.search(response)
                        experiences = match.group(1).strip() if match else ""
                        if not experiences or not split_experiences(experiences):
                            raise GenerationOutputError("group advantage returned no parseable <Experiences> items")
                    return {"rollouts": rollouts_per_problem, "critique": response, "experiences": experiences}
                except Exception as e:
                    return {
                        "_generation_error": error_detail(e),
                        "_stage": "single_query_group_advantage",
                        "_task_id": self._stable_task_id(rollouts_per_problem[0]),
                    }

        # parallel running
        results = []
        failures: list[dict[str, Any]] = []
        tasks = [
            asyncio.create_task(critique_with_semaphore(rollouts_per_problem))
            for rollouts_per_problem in all_rollouts
        ]
        try:
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Single query group advantage"):
                result = await task
                if result.get("_generation_error"):
                    failures.append(result)
                    continue
                results.append(result)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        if failures:
            raise L0CandidateGenerationError(
                "group-advantage generation failed; refusing a partial candidate batch: "
                + json.dumps(
                    {"failed_count": len(failures), "examples": failures[:5]}, ensure_ascii=False, sort_keys=True
                )
            )

        return sorted(
            results,
            key=lambda item: (
                self._stable_task_id(item["rollouts"][0]),
                tuple(self._stable_rollout_id(rollout) for rollout in item["rollouts"]),
            ),
        )

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
                                experience_output_language_instruction=(
                                    self._output_language_instruction()
                                ),
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
        tasks = [asyncio.create_task(group_update_with_semaphore(item)) for item in new_experiences]
        try:
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Group update"):
                result = await task
                if result is not None:
                    results.append(result)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return results

    async def _batch_update(
        self, recorder: TaskRecorder, critiques: list[dict], max_retries: int = 3
    ) -> dict[str, dict]:
        """Batch update experiences based on critiques.

        Delegates consolidation to the legacy flat-pool helper. Hierarchical L0
        review intentionally bypasses this permissive numeric-ID path.
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
            experience_output_language_instruction=(
                self._output_language_instruction()
            ),
        )
        for experience_id, content in new_experiences.items():
            if experiences.get(experience_id) == content:
                continue
            validate_experience_output_language(
                content,
                self._configured_output_language(),
                label=f"reviewed flat experience {experience_id}",
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
        ordered = sorted(rollouts, key=self._stable_rollout_id)
        if len(ordered) <= max_items:
            return ordered

        best = min(
            ordered,
            key=lambda rollout: (-self._safe_reward(rollout.reward), self._stable_rollout_id(rollout)),
        )
        worst = min(
            ordered,
            key=lambda rollout: (self._safe_reward(rollout.reward), self._stable_rollout_id(rollout)),
        )
        selected = [best] if best is worst else [best, worst]
        for rollout in ordered:
            if len(selected) >= max_items:
                break
            if rollout not in selected:
                selected.append(rollout)
        return selected

    def _select_counterfactual_summaries(
        self, summaries: list[dict[str, Any]], max_items: int = 4
    ) -> list[dict[str, Any]]:
        if not summaries:
            return []
        ordered = sorted(summaries, key=self._stable_rollout_id)
        if len(ordered) <= max_items:
            return ordered
        best = min(
            ordered,
            key=lambda summary: (
                -self._safe_reward(summary.get("reward")),
                self._stable_rollout_id(summary),
            ),
        )
        worst = min(
            ordered,
            key=lambda summary: (
                self._safe_reward(summary.get("reward")),
                self._stable_rollout_id(summary),
            ),
        )
        selected = [best] if best is worst else [best, worst]
        for summary in ordered:
            if len(selected) >= max_items:
                break
            if summary not in selected:
                selected.append(summary)
        return selected

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
