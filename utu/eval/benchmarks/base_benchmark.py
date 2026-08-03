import asyncio
import hashlib
import json
import time

from agents import gen_trace_id, trace
from tqdm import tqdm

from ...agents import get_agent
from ...config import ConfigLoader, EvalConfig
from ...skillsbench_reliability import (
    OUTCOME_FATAL_ERROR,
    OUTCOME_INFRA_ERROR,
    OUTCOME_TASK_TIMEOUT,
    FatalSkillsBenchError,
    FixedCooldownCircuitBreaker,
)
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
        self._source_to_processer = {}
        config_json = json.dumps(config.model_dump(), sort_keys=True, default=str)
        self._config_fingerprint = hashlib.sha256(config_json.encode("utf-8")).hexdigest()[:16]

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

        self._skillsbench_adapter = None
        self._skillsbench_circuit_breaker = None
        self._skillsbench_healthchecked = False
        self._skillsbench_health_models: list[str] = []
        if getattr(getattr(self.config, "skillsbench", None), "enabled", False):
            from ...practice.skillsbench_adapter import SkillsBenchAdapter

            skillsbench_cfg = self.config.skillsbench
            self._skillsbench_adapter = SkillsBenchAdapter(skillsbench_cfg)
            if getattr(skillsbench_cfg, "circuit_breaker_enabled", True):
                self._skillsbench_circuit_breaker = FixedCooldownCircuitBreaker(
                    failure_threshold=getattr(
                        skillsbench_cfg, "circuit_breaker_failure_threshold", 3
                    ),
                    cooldown_sec=getattr(skillsbench_cfg, "circuit_breaker_cooldown_sec", 60.0),
                    recovery_probe=self._probe_skillsbench_once,
                )

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

    def _skillsbench_model_name(self) -> str:
        agent_config = getattr(self.config, "agent", None)
        model_config = getattr(agent_config, "model", None)
        provider = getattr(model_config, "model_provider", None)
        return str(getattr(provider, "model", None) or "")

    def _skillsbench_temperature(self) -> float:
        agent_config = getattr(self.config, "agent", None)
        model_config = getattr(agent_config, "model", None)
        settings = getattr(model_config, "model_settings", None)
        value = getattr(settings, "temperature", None)
        return float(value) if value is not None else 0.0

    def _skillsbench_runtime_metadata(self) -> dict:
        instructions = ""
        if self.config.agent and self.config.agent.agent:
            instructions = self.config.agent.agent.instructions or ""
        return {
            "evaluation_protocol": "skillsbench_v4",
            "config_fingerprint": self._config_fingerprint,
            "prompt_fingerprint": hashlib.sha256(instructions.encode("utf-8")).hexdigest()[:16],
            "requested_model": self._skillsbench_model_name(),
            "temperature": self._skillsbench_temperature(),
            "healthcheck_models": list(self._skillsbench_health_models),
            "expected_num_tasks": getattr(self.config.skillsbench, "expected_num_tasks", None),
            "expected_trials_per_task": self.config.pass_k,
        }

    async def _probe_skillsbench_once(self) -> None:
        if self._skillsbench_adapter is None:
            return
        models = await self._skillsbench_adapter.health_check(
            model_name=self._skillsbench_model_name(),
            temperature=self._skillsbench_temperature(),
            attempts=1,
        )
        self._skillsbench_health_models = sorted(
            set(self._skillsbench_health_models).union(models)
        )

    async def ensure_skillsbench_health(self, *, force: bool = False) -> None:
        cfg = getattr(self.config, "skillsbench", None)
        if (
            self._skillsbench_adapter is None
            or not getattr(cfg, "healthcheck_enabled", True)
            or (self._skillsbench_healthchecked and not force)
        ):
            return
        try:
            models = await self._skillsbench_adapter.health_check(
                model_name=self._skillsbench_model_name(),
                temperature=self._skillsbench_temperature(),
                attempts=getattr(cfg, "healthcheck_attempts", 3),
            )
        except Exception as exc:
            from ...skillsbench_reliability import classify_infra_error

            classification = classify_infra_error(exc, default_type="api_healthcheck_error")
            message = (
                "SkillsBench endpoint health check failed before measured trials "
                f"({classification.error_type}): {exc}"
            )
            if classification.fatal:
                raise FatalSkillsBenchError(message) from exc
            raise RuntimeError(message) from exc
        self._skillsbench_health_models = sorted(set(models))
        self._skillsbench_healthchecked = True
    
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
        if samples and self._skillsbench_adapter is not None:
            await self.ensure_skillsbench_health()

        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def rollout_with_semaphore(item: EvaluationSample):
            async with semaphore:
                for i in range(max_retries):
                    if i > 0:
                        logger.warning(f"Retrying rollout for sample '{item.raw_question}', attempt {i + 1}")
                    try:
                        return await self.rollout_sample(item)
                    except FatalSkillsBenchError:
                        raise
                    except Exception as e:  # pylint: disable=broad-except
                        logger.error(
                            f">>>>>>>>>>>>>\nError running rollout on sample '{item.raw_question}': {e}\n<<<<<<<<<<<<<",
                            exc_info=True,
                        )

        tasks = [asyncio.create_task(rollout_with_semaphore(item)) for item in samples]
        results = []
        try:
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Rolling out"):
                result = await task
                if result is not None:
                    results.append(result)
        except FatalSkillsBenchError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        logger.info(f"Successfully rollout {len(results)} samples. Updated to db.")
        return results

    async def rollout_sample(self, sample: EvaluationSample) -> EvaluationSample:
        """Run one sample after waiting for the shared SkillsBench circuit."""

        if self._should_use_skillsbench_harbor(sample) and self._skillsbench_circuit_breaker:
            await self._skillsbench_circuit_breaker.wait_until_ready()
        return await self.rollout_one(sample)

    def reset_infra(self) -> list[EvaluationSample]:
        """Reset only infrastructure-invalid trials back to the init stage."""

        samples = self.dataset.get_samples(stage="infra_error")
        if not samples:
            logger.info("No SkillsBench infra_error trials need resetting.")
            return []
        logger.info("Resetting %s infra_error trial(s) for a targeted rerun.", len(samples))
        for sample in samples:
            meta = sample.meta if isinstance(sample.meta, dict) else {}
            meta = {**meta, "eval_status": "pending_retry"}
            meta.pop("infra_error_type", None)
            meta.pop("infra_error_message", None)
            sample.update(
                meta=meta,
                reward=None,
                response="",
                trajectories=None,
                correct=None,
                judged_response=None,
                stage="init",
            )
        self.dataset.save(samples)
        return samples

    async def retry_infra(self) -> list[EvaluationSample]:
        """Reset and rerun only trials previously marked as infrastructure errors."""

        await self._apply_experience_filter()
        samples = self.reset_infra()
        if not samples:
            return []
        self.preprocess()
        await self.rollout()
        return samples

    async def rollout_one(self, sample: EvaluationSample) -> EvaluationSample:
        # SkillsBench tasks are executed entirely inside harbor/Docker –
        # no TF-LLM agent object is needed here.
        if self._should_use_skillsbench_harbor(sample):
            return await self._rollout_skillsbench_harbor(sample)

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
    
    # ------------------------------------------------------------------
    # SkillsBench harbor execution
    # ------------------------------------------------------------------

    def _should_use_skillsbench_harbor(self, sample: EvaluationSample) -> bool:
        """Return True when the sample should be executed via harbor/Docker."""
        cfg = getattr(self.config, "skillsbench", None)
        return cfg is not None and getattr(cfg, "enabled", False)

    async def _rollout_skillsbench_harbor(
        self, sample: EvaluationSample, recorder=None
    ) -> EvaluationSample:
        """
        Execute a SkillsBench task using the harbor sandbox and
        TFLLMHarborAgent, then record the verifier reward.

        Args:
            sample: Evaluation sample whose ``augmented_question`` carries a
                    JSON payload written by ``SkillsBenchProcesser.preprocess_one``.
            recorder: Optional ``TaskRecorder`` (supplied during TF-GRPO practice).
        """
        meta = sample.meta or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}

        task_path = meta.get("task_path", "")
        if not task_path:
            logger.error(f"No task_path in meta for sample: {sample.raw_question[:80]}")
            meta.update(
                eval_status=OUTCOME_INFRA_ERROR,
                infra_error_type="dataset_configuration_error",
                infra_error_message="No task_path in sample metadata",
            )
            sample.update(
                response="No task_path in meta",
                reward=None,
                meta=meta,
                stage="infra_error",
            )
            self.dataset.save(sample)
            raise FatalSkillsBenchError("SkillsBench sample is missing task_path")

        # Decode experiences / Skills config from augmented_question
        experiences: dict = {}
        inject_curated_skills = False
        agent_instructions = ""
        if sample.augmented_question:
            try:
                payload = json.loads(sample.augmented_question)
                experiences = payload.get("experiences", {})
                inject_curated_skills = payload.get("inject_curated_skills", False)
                agent_instructions = payload.get("agent_instructions", "")
            except (json.JSONDecodeError, AttributeError):
                pass

        # Also accept recorder experiences (practice mode)
        if recorder and recorder.experiences:
            experiences = {**dict(recorder.experiences), **experiences}

        # In eval mode the trained experiences arrive baked into the agent YAML's
        # instructions (carried via agent_instructions), not the experiences dict.
        # Prefer the live config value when available so experience filtering
        # (which rewrites config.agent.agent.instructions) is respected.
        if self.config.agent and self.config.agent.agent and self.config.agent.agent.instructions:
            agent_instructions = self.config.agent.agent.instructions

        skills_text = meta.get("skills_text", "")

        if self._skillsbench_adapter is None:
            raise FatalSkillsBenchError("SkillsBench adapter was not initialized")
        logger.info(f"Running SkillsBench task: {meta.get('task_id', task_path)}")
        start_time = time.time()
        result = await self._skillsbench_adapter.run_task(
            task_path=task_path,
            experiences=experiences,
            inject_curated_skills=inject_curated_skills,
            skills_text=skills_text,
            agent_instructions=agent_instructions,
            model_name=self._skillsbench_model_name(),
            model_temperature=self._skillsbench_temperature(),
        )
        elapsed = time.time() - start_time

        if result.error:
            logger.warning(
                f"Task {meta.get('task_id')} finished with error: {result.error}"
            )

        # Build a rich trajectory for the experience updater.
        # The sparse agent_trajectory.json only has cmd/rc pairs; we augment it
        # with the full agent_log (harbor stdout) so the LLM can see what each
        # command actually produced and extract meaningful experiences.
        enriched_trajectory = result.trajectory or "[]"
        if result.agent_log:
            try:
                traj_steps = json.loads(enriched_trajectory)
                enriched_trajectory = json.dumps(
                    [{"agent_log": result.agent_log[:6000], "steps": traj_steps}],
                    ensure_ascii=False,
                )
            except (json.JSONDecodeError, TypeError):
                pass

        # correct_answer is not meaningful for SkillsBench (verifier is a script).
        # Store the task description so experience_updater has something useful.
        if not sample.correct_answer:
            sample.update(correct_answer="[Verified by harbor verifier script]")

        runtime_meta = self._skillsbench_runtime_metadata()
        runtime_meta.update(result.metadata)
        history = list(meta.get("infra_attempt_history") or [])
        if result.outcome in {OUTCOME_INFRA_ERROR, OUTCOME_FATAL_ERROR}:
            history.append(
                {
                    "error_type": result.error_type,
                    "message": result.error[:1000],
                    "retryable": result.retryable,
                    "fatal": result.fatal,
                    "adapter_attempts": result.attempts,
                    "elapsed_sec": round(elapsed, 3),
                }
            )
            meta.update(
                runtime_meta,
                eval_status=OUTCOME_INFRA_ERROR,
                infra_error_type=result.error_type,
                infra_error_message=result.error[:1000],
                infra_attempt_history=history,
            )
            stage = "infra_error"
            reward = None
            if self._skillsbench_circuit_breaker:
                await self._skillsbench_circuit_breaker.record_failure(result.error_type)
        else:
            meta.update(
                runtime_meta,
                eval_status="valid",
                trial_outcome=result.outcome,
                adapter_attempts=result.attempts,
            )
            meta.pop("infra_error_type", None)
            meta.pop("infra_error_message", None)
            stage = "rollout"
            reward = result.reward
            if self._skillsbench_circuit_breaker:
                await self._skillsbench_circuit_breaker.record_success()

        response = result.agent_log[:4000] if result.agent_log else result.error
        if result.outcome == OUTCOME_TASK_TIMEOUT and not response:
            response = f"Task exhausted the {self.config.skillsbench.task_timeout_sec}s protocol budget"
        sample.update(
            response=response,
            reward=reward,
            time_cost=elapsed,
            trajectories=enriched_trajectory,
            meta=meta,
            correct=None,
            judged_response=None,
            stage=stage,
        )
        self.dataset.save(sample)
        if result.fatal:
            raise FatalSkillsBenchError(
                f"Fatal SkillsBench configuration error ({result.error_type}): {result.error}"
            )
        return sample

    async def judge(self, stage: str | None = "rollout") -> list[EvaluationSample]:
        """Judge samples.

        Args:
            stage (str|None, optional): The stage of samples to judge. If set to None, you can rejudge all samples.
        """
        if stage == "rollout":
            num_init_samples = len(self.dataset.get_samples(stage="init"))
            if num_init_samples > 0:
                raise RuntimeError(
                    f"There are {num_init_samples} samples might failed unexpectedly in rollout stage."
                    "Please rerun the benchmarking to continue for final results."
                )
            num_infra_samples = len(self.dataset.get_samples(stage="infra_error"))
            if num_infra_samples > 0:
                logger.warning(
                    "%s SkillsBench trial(s) remain infra_error; judging valid trials only.",
                    num_infra_samples,
                )
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
        if getattr(getattr(self.config, "skillsbench", None), "enabled", False):
            judged_samples = self.dataset.get_samples()
            logger.info(f"SkillsBench stat from {len(judged_samples)} total trial rows:")
        else:
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
