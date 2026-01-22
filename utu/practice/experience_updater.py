"""
Experience updater for training-free GRPO.
"""

import asyncio
import copy
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from agents import custom_span
from tqdm import tqdm

from ..config import AgentConfig
from ..db import EvaluationSample
from ..utils import FileUtils, SimplifiedAsyncOpenAI, get_logger
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
                        return {"trajectory_summary": response, **item.model_dump()}
                    except Exception as e:
                        error_str = str(e)
                        is_rate_limit = "429" in error_str or "rate limit" in error_str.lower() or "TPM limit" in error_str
                        
                        if is_rate_limit and attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt) + (attempt * 0.5)
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
                            sp = FileUtils.get_jinja_template_str(self.prompts["SINGLE_QUERY_GROUP_ADVANTAGE_SP"]).render(
                                agent_objective=self.agent_objective,
                                learning_objective=self.learning_objective,
                                num_experiences=num_experiences,
                            )
                            up = FileUtils.get_jinja_template_str(self.prompts["SINGLE_QUERY_GROUP_ADVANTAGE_UP"]).render(
                                question=rollouts_per_problem[0]["raw_question"],
                                answer=rollouts_per_problem[0]["correct_answer"] if given_ground_truth else "[REDACTED]",
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
                        is_rate_limit = "429" in error_str or "rate limit" in error_str.lower() or "TPM limit" in error_str
                        
                        if is_rate_limit and attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt) + (attempt * 0.5)
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
        max_retries = 5
        base_delay = 2.0  # Base delay in seconds

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
                        is_rate_limit = "429" in error_str or "rate limit" in error_str.lower() or "TPM limit" in error_str
                        
                        if is_rate_limit and attempt < max_retries - 1:
                            # Exponential backoff with jitter
                            delay = base_delay * (2 ** attempt) + (attempt * 0.5)
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
        """Batch update experiences based on critiques."""
        # get current experiences from recorder
        logger.info("Batch update")
        # collect operations
        all_operations = []
        for each in critiques:
            all_operations.extend(each["operations"])
        print("- Num of operations to process:", len(all_operations))

        # use LLM to get the revision plan
        experiences = recorder.experiences or {}
        revision_plan = []
        for _ in range(max_retries):
            try:
                sp = FileUtils.get_jinja_template_str(self.prompts["BATCH_EXPERIENCE_UPDATE_TEMPLATE_SP"]).render(
                    agent_objective=self.agent_objective,
                    learning_objective=self.learning_objective,
                )
                up = FileUtils.get_jinja_template_str(self.prompts["BATCH_EXPERIENCE_UPDATE_TEMPLATE_UP"]).render(
                    experiences_and_operations=self._format_exp_and_ops(experiences, all_operations)
                )
                response = await self.llm.query_one(
                    messages=[
                        {"role": "system", "content": sp},
                        {"role": "user", "content": up},
                    ],
                    **self.config.model.model_params.model_dump(),
                )
                # parse response
                revision_plan = json.loads(response.split("```json")[-1].split("```")[0])
                break
            except Exception:
                print("Warning: failed to decode in updating general experiences")

        # apply revision plan to get new experiences
        max_ID = len(experiences)
        new_experiences = copy.deepcopy(experiences)
        for plan in revision_plan:
            operation = plan.get("operation", "ADD")
            content = plan.get("content", "")
            target_id = plan.get("id", None)
            if not content:
                continue

            if operation == "ADD":
                new_experiences[f"{max_ID}"] = content
                max_ID += 1
            elif operation == "UPDATE":
                if target_id in new_experiences:
                    new_experiences[target_id] = content
                else:
                    # directly add new experience
                    new_experiences[f"{max_ID}"] = content
                    max_ID += 1
            elif operation == "DELETE":
                if target_id in new_experiences:
                    del new_experiences[target_id]
        print("- Num of candidate experiences:", len(new_experiences))
        return new_experiences

    def _format_exp_and_ops(self, experiences: dict[str, str], operations: list[dict]) -> str:
        """Format experiences and operations."""
        if not operations:
            return "No batch operations."

        # Format existing experiences and their related operations
        formatted_res = []
        for id, exp in experiences.items():
            curr_str = f"Experience {id}:\nContent: {exp}\n"
            related_ops = [op for op in operations if op.get("id") == id]
            if related_ops:
                curr_str += "Related Operations:\n"
                op_str = []
                for op in related_ops:
                    op_str.append(f"{json.dumps(op, ensure_ascii=False, indent=2)}")
                op_str = "\n".join(op_str)
                curr_str += op_str
            else:
                curr_str += "No related operations."
            formatted_res.append(curr_str)

        # Format operations without specific IDs
        no_id_ops = [op for op in operations if not op.get("id", None)]
        if no_id_ops:
            curr_str = "Operations without specific Experience ID:\n"
            op_str = []
            for op in no_id_ops:
                op_str.append(f"{json.dumps(op, ensure_ascii=False, indent=2)}")
            op_str = "\n".join(op_str)
            curr_str += op_str
            formatted_res.append(curr_str)

        return "\n\n".join(formatted_res)

    def _safe_reward(self, reward: Any) -> float:
        try:
            if reward is None:
                return 0.0
            return float(reward)
        except Exception:
            return 0.0

    def _group_stats(self, rollouts: Iterable[EvaluationSample | dict[str, Any]]) -> _RolloutGroupStats:
        rewards = [
            self._safe_reward(getattr(r, "reward", None) if not isinstance(r, dict) else r.get("reward")) for r in rollouts
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

    def _select_representative_rollouts(self, rollouts: list[EvaluationSample], max_items: int = 4) -> list[EvaluationSample]:
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

    def _select_counterfactual_summaries(self, summaries: list[dict[str, Any]], max_items: int = 4) -> list[dict[str, Any]]:
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

    def _format_counterfactual_trajectories(self, rollouts_per_problem: list[dict[str, Any]], given_ground_truth: bool) -> str:
        if not rollouts_per_problem:
            return ""
        rewards = [self._safe_reward(each.get("reward")) for each in rollouts_per_problem]
        best_reward = max(rewards) if rewards else 0.0
        worst_reward = min(rewards) if rewards else 0.0
        has_contrast = (best_reward - worst_reward) > 1e-9

        lines: list[str] = []
        lines.append(
            f"Group Stats: n={len(rollouts_per_problem)}, best={best_reward}, worst={worst_reward}, contrast={has_contrast}"
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
