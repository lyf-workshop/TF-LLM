import importlib.util
import inspect
import json
from collections import defaultdict
from pathlib import Path

from ...config import EvalConfig
from ...db import EvaluationSample
from ...utils import FileUtils, get_logger
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
            curr_experience = recorder.experiences or {}
            formatted_experiences = "\n".join([f"[{i}]. {e}" for i, e in curr_experience.items()])
            augmented_question = FileUtils.get_jinja_template_str(
                self.prompts["PROBLEM_WITH_EXPERIENCE_TEMPLATE"]
            ).render(
                problem=sample.raw_question,
                experiences=formatted_experiences if formatted_experiences else "None",
            )
        sample.update(
            augmented_question=augmented_question,
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
        """Load the verification function from the given path."""
        if not self.config.verify_filename or not self.config.verify_func_name:
            logger.warning(
                "verify_filename or verify_func_name not specified in config. "
                "Will use LLM judging method."
            )
            return None
        
        try:
            verify_path = VERIFY_DIR / self.config.verify_filename
            if not verify_path.exists():
                logger.error(
                    f"Verification file not found: {verify_path}. "
                    f"Expected path: {verify_path.absolute()}. "
                    "Will use LLM judging method."
                )
                return None
            
            spec = importlib.util.spec_from_file_location("verify_module", str(verify_path))
            if spec is None or spec.loader is None:
                logger.error(
                    f"Failed to create module spec from '{verify_path}'. "
                    "Will use LLM judging method."
                )
                return None
            
            verify_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(verify_module)
            
            if not hasattr(verify_module, self.config.verify_func_name):
                logger.error(
                    f"Function '{self.config.verify_func_name}' not found in module '{verify_path}'. "
                    f"Available attributes: {dir(verify_module)}. "
                    "Will use LLM judging method."
                )
                return None
            
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
                exc_info=True
            )
            return None
