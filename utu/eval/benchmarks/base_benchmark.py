import asyncio
import json
import time

from agents import gen_trace_id, trace
from tqdm import tqdm

from ...agents import get_agent
from ...config import ConfigLoader, EvalConfig
from ...utils import AgentsUtils, get_logger
from ..data import DBDataManager, EvaluationSample
from ..experience_filter import ExperienceFilter
from ..processer import PROCESSER_FACTORY, BaseProcesser

logger = get_logger(__name__, "INFO")


class BaseBenchmark:
    """Base class for benchmarks.

    Evaluation phases:
      - preprocess: load and preprocess the data
      - rollout: rollout the predictions
      - judge: judge the correctness of a batch of predictions
      - stat: get metrics.
    """

    dataset: DBDataManager
    _source_to_processer: dict[str, BaseProcesser] = {}

    def __init__(self, config: EvalConfig | str) -> None:
        # config
        if isinstance(config, str):
            config = ConfigLoader.load_eval_config(name=config)
        self.config = config

        # dataset
        self.dataset = DBDataManager(config)
        _samples = self.dataset.load()
        if len(_samples) == 0:
            raise ValueError(f"No samples found for data config '{self.config.data}'! Please check the data config.")
        
        # Initialize experience filter
        self.experience_filter = None
        self._experience_filter_applied = False
        if hasattr(self.config, 'experience_filter') and self.config.experience_filter.enabled:
            logger.info(f"Experience filtering enabled: strategy={self.config.experience_filter.strategy}")
            if self.config.experience_filter.experience_source:
                logger.info(f"  Experience source: {self.config.experience_filter.experience_source}")
            if self.config.experience_filter.strategy == "llm_rerank":
                logger.info(f"  LLM reranking: model={self.config.experience_filter.llm_rerank.model}, "
                           f"top_k={self.config.experience_filter.llm_rerank.final_top_k}")
            self.experience_filter = ExperienceFilter(self.config.experience_filter)
        else:
            logger.info("Experience filtering disabled or not configured")

    async def main(self):
        with trace(f"[{self.config.exp_id}] Evaluation", trace_id=gen_trace_id()):
            logger.info(
                f"> Running with config: \n{json.dumps(self.config.model_dump(), indent=2, ensure_ascii=False)}"
            )
            
            # Apply experience filtering (async)
            await self._apply_experience_filter()
            
            self.preprocess()
            await self.rollout()
            await self.judge()
            logger.info("> Running stat...")
            await self.stat()
            logger.info("> Cleaning up...")
            await self.cleanup()
    
    async def _apply_experience_filter(self):
        """Apply experience filtering to agent instructions (async operation)."""
        if self.experience_filter and not self._experience_filter_applied:
            if self.config.agent and self.config.agent.agent and self.config.agent.agent.instructions:
                logger.info("Applying experience filtering to agent instructions...")
                original_instructions = self.config.agent.agent.instructions
                original_length = len(original_instructions)
                
                # Determine task context for LLM reranking
                task_context = self._get_task_context()
                
                # Apply filtering (async)
                start_time = time.time()
                self.config.agent.agent.instructions = await self.experience_filter.apply(
                    original_instructions,
                    query=task_context
                )
                elapsed = time.time() - start_time
                
                filtered_length = len(self.config.agent.agent.instructions)
                logger.info(f"Experience filtering completed in {elapsed:.2f}s: "
                           f"{original_length} → {filtered_length} chars "
                           f"(reduced by {original_length - filtered_length} chars)")
                
                self._experience_filter_applied = True
    
    def _get_task_context(self) -> str:
        """Get task context description for LLM-based experience filtering.
        
        Returns:
            Task context string
        """
        # For KORGym games, build context from game config
        if hasattr(self.config, 'korgym') and self.config.korgym.enabled:
            game_name = self.config.korgym.game_name
            level = self.config.korgym.level
            max_rounds = self.config.korgym.max_rounds
            
            if "wordle" in game_name.lower():
                return (f"Wordle game: Guess a {level}-letter hidden word within {max_rounds} attempts. "
                       f"Use feedback (GREEN=correct position, YELLOW=wrong position, GRAY=not in word) "
                       f"to refine guesses through constraint satisfaction and information gain.")
            elif "2048" in game_name:
                return f"2048 game: Combine tiles to reach 2048 on a {level}x{level} grid."
            elif "puzzle" in game_name.lower():
                return f"Word puzzle game: Solve word-based puzzles at level {level}."
            else:
                return f"{game_name} game at level {level} with max {max_rounds} rounds."
        
        # Default context
        return "General problem-solving task requiring strategic decision-making and constraint satisfaction."

    def preprocess(self) -> None:
        """Preprocess the dataset before rollout."""
        samples = self.dataset.get_samples(stage="init")
        logger.info(f"Preprocessing {len(samples)} samples...")
        results = []
        for sample in tqdm(samples, desc="Preprocessing"):
            processed_sample = self.preprocess_one(sample)
            if processed_sample is not None:
                results.append(processed_sample)
        logger.info(f"Successfully preprocessed {len(results)} samples. Updated to db.")
        return results

    def preprocess_one(self, sample: EvaluationSample) -> EvaluationSample:
        processer = self._get_processer(sample.source)
        processed_sample = processer.preprocess_one(sample)
        if processed_sample is None:
            return None
        self.dataset.save(processed_sample)
        return processed_sample

    async def rollout(self, max_retries: int = 3) -> None:
        """Rollout the datapoints."""
        samples = self.dataset.get_samples(stage="init")
        logger.info(f"Rollout {len(samples)} samples...")

        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def rollout_with_semaphore(item: EvaluationSample):
            async with semaphore:
                for i in range(max_retries):
                    if i > 0:
                        logger.warning(f"Retrying rollout for sample '{item.raw_question}', attempt {i + 1}")
                    try:
                        return await self.rollout_one(item)
                    except Exception as e:  # pylint: disable=broad-except
                        logger.error(
                            f">>>>>>>>>>>>>\nError running rollout on sample '{item.raw_question}': {e}\n<<<<<<<<<<<<<",
                            exc_info=True,
                        )

        tasks = [rollout_with_semaphore(item) for item in samples]
        results = []
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Rolling out"):
            result = await task
            if result is not None:
                results.append(result)
        logger.info(f"Successfully rollout {len(results)} samples. Updated to db.")
        return results

    async def rollout_one(self, sample: EvaluationSample) -> EvaluationSample:
        agent = get_agent(self.config.agent)
        if hasattr(agent, "build"):  # hack, should be removed!
            await agent.build()
        
        # Check if this is a KORGym multi-round game
        if self._should_use_korgym_multiround(sample):
            return await self._rollout_korgym_multiround(agent, sample)
        
        # Original logic: single-turn rollout
        trace_id = AgentsUtils.gen_trace_id()
        start_time = time.time()
        result = await agent.run(sample.augmented_question, trace_id=trace_id)
        end_time = time.time()

        # Update the sample with the predicted answer and trajectory
        sample.update(
            trace_id=trace_id,
            response=result.final_output,
            time_cost=end_time - start_time,
            trajectories=json.dumps(result.trajectories, ensure_ascii=False),
            stage="rollout",  # update stage to rollout!
        )
        
        self.dataset.save(sample)
        return sample

    def _should_use_korgym_multiround(self, sample: EvaluationSample) -> bool:
        """Check if this sample requires KORGym multi-round game handling.
        
        Args:
            sample: The evaluation sample
            
        Returns:
            True if this is a KORGym multi-round game, False otherwise
        """
        # Check if KORGym config exists and is enabled
        if not hasattr(self.config, 'korgym') or not self.config.korgym:
            return False
        
        if not self.config.korgym.enabled:
            return False
        
        # Check game type
        try:
            from ...practice.korgym_adapter import KORGymGameClassifier
            game_type = KORGymGameClassifier.get_game_type(self.config.korgym.game_name)
            is_multiround = (game_type == 'multiple')
            
            if is_multiround:
                logger.info(f"Detected KORGym multi-round game: {self.config.korgym.game_name}")
            
            return is_multiround
        except Exception as e:
            logger.warning(f"Failed to check KORGym game type: {e}")
            return False
    
    async def _rollout_korgym_multiround(self, agent, sample: EvaluationSample) -> EvaluationSample:
        """Execute complete multi-round KORGym game rollout.
        
        This method is used for multi-turn games like Wordle, 2048, etc.
        It uses the KORGymAdapter to handle multiple rounds of interaction.
        
        Args:
            agent: The agent to play the game
            sample: The evaluation sample
            
        Returns:
            Updated sample with complete game results
        """
        try:
            from ...practice.korgym_adapter import KORGymAdapter
            
            # Initialize adapter from config
            korgym_config = self.config.korgym
            adapter = KORGymAdapter(
                game_name=korgym_config.game_name,
                game_host=korgym_config.game_host,
                game_port=korgym_config.game_port,
                level=korgym_config.level,
                max_rounds=korgym_config.max_rounds
            )
            
            # Get seed from meta
            meta = sample.meta or {}
            seed = meta.get('seed') or meta.get('game_seed', 0)
            
            # Execute complete multi-round game
            logger.info(f"Starting multi-round game for seed {seed}")
            start_time = time.time()
            game_result = await adapter.play_game(agent, seed)
            end_time = time.time()
            
            logger.info(
                f"Multi-round game completed: seed={seed}, "
                f"rounds={game_result.get('rounds', 0)}, "
                f"score={game_result.get('final_score', 0)}, "
                f"success={game_result.get('success', False)}"
            )
            
            # Get all responses (for multi-round, we have multiple responses)
            responses = game_result.get('responses', [])
            final_response = responses[-1] if responses else ''
            
            # Update sample with complete game results
            sample.update(
                trace_id=game_result.get('round_id', ''),
                response=final_response,
                time_cost=end_time - start_time,
                trajectories=json.dumps(game_result.get('trajectory', []), ensure_ascii=False),
                meta={
                    **meta,
                    'multiround_result': game_result,
                    'final_score': game_result.get('final_score', 0),
                    'success': game_result.get('success', False),
                    'rounds': game_result.get('rounds', 0),
                    'all_responses': responses
                },
                stage="rollout"
            )
            
            self.dataset.save(sample)
            return sample
            
        except Exception as e:
            logger.error(f"Failed to execute multi-round game: {e}", exc_info=True)
            # Fallback: mark as failed
            sample.update(
                response=f"Multi-round game failed: {str(e)}",
                stage="rollout"
            )
            self.dataset.save(sample)
            return sample
    
    async def judge(self, stage: str | None = "rollout") -> list[EvaluationSample]:
        """Judge samples.

        Args:
            stage (str|None, optional): The stage of samples to judge. If set to None, you can rejudge all samples.
        """
        if stage == "rollout":
            num_init_samples = len(self.dataset.get_samples(stage="init"))
            if num_init_samples > 0:
                logger.error(
                    f"There are {num_init_samples} samples might failed unexpectedly in rollout stage."
                    "Please rerun the benchmarking to continue for final results."
                )
                exit(1)
        samples = self.dataset.get_samples(stage=stage)
        logger.info(f"Judging {len(samples)} samples...")

        semaphore = asyncio.Semaphore(self.config.judge_concurrency)

        async def judge_with_semaphore(item: EvaluationSample):
            async with semaphore:
                try:
                    return await self.judge_one(item)
                except Exception as e:  # pylint: disable=broad-except
                    logger.error(f">>>>>>>>>>>>>\nError judging sample '{item}': {e}\n<<<<<<<<<<<<<", exc_info=True)
                    return None

        tasks = [judge_with_semaphore(item) for item in samples]
        results = []
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Judging"):
            result = await task
            if result is not None:
                results.append(result)
        logger.info(f"Successfully judged {len(results)} samples. Updated to db.")
        return results

    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        judger = self._get_processer(data.source)
        result = await judger.judge_one(data)
        result.update(stage="judged")  # update stage to judged
        self.dataset.save(result)
        return result

    async def stat(self) -> list[dict]:
        # TODO: wrap the data like @verl / @torch
        # TODO: log to wandb
        judged_samples = self.dataset.get_samples(stage="judged")
        logger.info(f"Stat from {len(judged_samples)} samples:")

        data_by_benchmark = self._group_data_by_benchmark(judged_samples)
        overall_results: list[dict] = []
        for benchmark, data in data_by_benchmark.items():
            evaluator = self._get_processer(benchmark)
            result = await evaluator.stat(data)
            overall_results.append(result)

        logger.info(json.dumps(overall_results, indent=4, ensure_ascii=False))
        return overall_results

    def _get_processer(self, source: str) -> BaseProcesser:
        if source not in self._source_to_processer:
            processer = PROCESSER_FACTORY.get(source, self.config)
            self._source_to_processer[source] = processer
        return self._source_to_processer[source]

    def _group_data_by_benchmark(self, predict_data: list[EvaluationSample]) -> dict[str, list[EvaluationSample]]:
        # group data by benchmark
        data_by_benchmark: dict[str, list[EvaluationSample]] = {}
        for data in predict_data:
            benchmark = data.source
            if benchmark not in data_by_benchmark:
                data_by_benchmark[benchmark] = []
            data_by_benchmark[benchmark].append(data)
        return data_by_benchmark

    async def cleanup(self):
        pass
