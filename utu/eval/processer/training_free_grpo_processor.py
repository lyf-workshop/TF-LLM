import importlib.util
import inspect
import json
from collections import defaultdict
from pathlib import Path

from ...config import EvalConfig
from ...db import EvaluationSample
from ...utils import FileUtils, get_logger
from ...utils.experience_injection import INJECTED_EXPERIENCE_IDS_META_KEY
from .base_llm_processor import BaseLLMJudgeProcesser

logger = get_logger(__name__)

VERIFY_DIR = Path(__file__).parent.parent.parent / "practice" / "verify"


class TrainingFreeGRPOProcesser(BaseLLMJudgeProcesser):
    """Processer for training-free GRPO datasets."""

    name = "training_free_grpo"
    config: EvalConfig = None

    def __init__(self, config: EvalConfig) -> None:
        super().__init__(config)
        self.verify_func = self._load_verify_func()
        self.prompts = FileUtils.load_prompts("practice/processor.yaml")
        from ...practice.experience_retriever import ExperienceRetriever

        self._experience_retriever = ExperienceRetriever()
        self._indexed_l0_experiences: tuple[tuple[str, str], ...] = ()

    def _select_experiences(self, query: str, recorder) -> dict[str, str]:
        experiences = recorder.experiences or {}
        top_k = max(0, int(getattr(recorder, "l0_injection_top_k", 0) or 0))
        if top_k == 0:
            return dict(experiences)

        global_experiences = {
            experience_id: content
            for experience_id, content in experiences.items()
            if not experience_id.startswith("L0_")
        }
        l0_experiences = {
            experience_id: content
            for experience_id, content in experiences.items()
            if experience_id.startswith("L0_")
        }
        index_signature = tuple(l0_experiences.items())
        if index_signature != self._indexed_l0_experiences:
            self._experience_retriever.index(l0_experiences)
            self._indexed_l0_experiences = index_signature

        retrieved = self._experience_retriever.retrieve(
            query,
            top_k=top_k,
            min_score=1e-12,
        )
        selected = dict(global_experiences)
        selected.update({item.exp_id: item.content for item in retrieved})
        return selected

    @staticmethod
    def _meta_with_injected_ids(meta, experience_ids: list[str]) -> dict:
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {"source_meta": meta}
        elif isinstance(meta, dict):
            meta = dict(meta)
        elif meta is None:
            meta = {}
        else:
            meta = {"source_meta": meta}
        meta[INJECTED_EXPERIENCE_IDS_META_KEY] = experience_ids
        return meta

    def preprocess_one(self, sample: EvaluationSample, recorder=None) -> EvaluationSample:
        """Preprocess a single sample with optional experience recorder.

        Args:
            sample: EvaluationSample to preprocess
            recorder: Optional TaskRecorder with experiences

        Returns:
            Updated EvaluationSample
        """
        if recorder is None:
            augmented_question = sample.raw_question
        else:
            curr_experience = self._select_experiences(sample.raw_question, recorder)
            formatted_experiences = "\n".join([f"[{i}]. {e}" for i, e in curr_experience.items()])
            augmented_question = FileUtils.get_jinja_template_str(
                self.prompts["PROBLEM_WITH_EXPERIENCE_TEMPLATE"]
            ).render(
                problem=sample.raw_question,
                experiences=formatted_experiences if formatted_experiences else "None",
            )
        sample.update(
            augmented_question=augmented_question,
            meta=self._meta_with_injected_ids(sample.meta, list(curr_experience))
            if recorder is not None
            else sample.meta,
        )
        return sample

    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        """Judge a single sample using the loaded verify function."""
        if self.verify_func is None:
            # directly use the default LLM judging method
            return await super().judge_one(data)

        # Check if verify_func is async or sync and call accordingly
        if inspect.iscoroutinefunction(self.verify_func):
            res = await self.verify_func(sample=data, llm=self.judge_client)
        else:
            res = self.verify_func(sample=data, llm=self.judge_client)

        reward = res.get("reward", 0.0)
        reasoning = res.get("reasoning", None)
        data.update(
            judged_response="Correct" if reward == 1.0 else "Incorrect",
            correct=reward == 1.0,
            reward=reward,
            reasoning=reasoning,
        )
        return data

    def calculate_metrics(self, samples: list[EvaluationSample]) -> dict:
        """Calculate metrics from the judged data."""
        all_rewards = []
        problem_to_scores = defaultdict(list)
        num_tool_calls = []
        # calculate tool calls and rewards
        for sample in samples:
            # Skip samples with None reward (failed verification)
            reward = sample.reward if sample.reward is not None else 0.0
            all_rewards.append(reward)
            problem_to_scores[sample.raw_question].append(reward)
            if sample.trajectories:
                try:
                    trajectories = json.loads(sample.trajectories)
                    if trajectories and isinstance(trajectories, list) and len(trajectories) > 0:
                        num_tool_calls.append(
                            len([each for each in trajectories[0].get("trajectory", []) if each.get("role") == "tool"])
                        )
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass

        # Filter out None values and calculate max score for each problem
        problem_to_max_score = {
            problem: max((s for s in scores if s is not None), default=0.0)
            for problem, scores in problem_to_scores.items()
        }
        max_K = max((len(scores) for scores in problem_to_scores.values()), default=0)
        stats = {
            f"Mean@{max_K}": sum(all_rewards) / len(all_rewards) if all_rewards else 0,
            f"Pass@{max_K}": sum(max_reward for max_reward in problem_to_max_score.values()) / len(problem_to_max_score)
            if problem_to_max_score
            else 0,
            "avg_tool_call": sum(num_tool_calls) / len(num_tool_calls) if num_tool_calls else 0,
        }
        return stats

    def _load_verify_func(self):
        """Load the configured verifier, failing closed when it is explicit.

        An absent verifier configuration deliberately selects LLM judging.
        Once a verifier is named, however, silently falling back can both
        change the experiment's scoring protocol and incur unexpected API
        charges. Treat file, symbol, and dependency failures as fatal.
        """
        if not self.config.verify_filename or not self.config.verify_func_name:
            logger.warning(
                "verify_filename or verify_func_name not specified in config. "
                "Will use LLM judging method."
            )
            return None

        try:
            verify_path = VERIFY_DIR / self.config.verify_filename
            if not verify_path.exists():
                raise FileNotFoundError(
                    f"Verification file not found: {verify_path.absolute()}"
                )

            spec = importlib.util.spec_from_file_location("verify_module", str(verify_path))
            if spec is None or spec.loader is None:
                raise ImportError(f"Failed to create module spec from '{verify_path}'")

            verify_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(verify_module)

            if not hasattr(verify_module, self.config.verify_func_name):
                raise AttributeError(
                    f"Function '{self.config.verify_func_name}' not found in module '{verify_path}'"
                )

            func = getattr(verify_module, self.config.verify_func_name)
            logger.info(
                f"Successfully loaded verification function '{self.config.verify_func_name}' "
                f"from '{verify_path}'"
            )
            return func

        except Exception as e:
            logger.error(
                f"Failed to load verification function '{self.config.verify_func_name}' "
                f"from '{self.config.verify_filename}': {e}",
                exc_info=True,
            )
            raise RuntimeError(
                f"Configured verifier '{self.config.verify_filename}:{self.config.verify_func_name}' "
                "could not be loaded; refusing to fall back to LLM judging"
            ) from e
