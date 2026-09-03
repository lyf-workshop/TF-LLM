"""
Main module for experience generation. Control the process of Training-free GRPO.
"""

import os

import yaml
from agents import custom_span, function_span, gen_trace_id, trace

from ..config import TrainingFreeGRPOConfig
from ..config.eval_config import DataConfig
from ..skillsbench_data import assert_datasets_disjoint
from ..utils import DIR_ROOT, get_logger
from ..utils.experience_cache import ExperienceCache
from .data_manager import TrainingFreeGRPODataManager
from .experience_quality_tracker import ExperienceQualityTracker
from .experience_updater import ExperienceUpdater
from .hierarchical_experience_manager import HierarchicalExperienceManager
from .rollout_manager import RolloutManager
from .utils import TaskRecorder

logger = get_logger(__name__)


class TrainingFreeGRPO:
    config: TrainingFreeGRPOConfig = None
    practice_rollout_manager: RolloutManager = None
    eval_rollout_manager: RolloutManager = None
    experience_updater: ExperienceUpdater = None
    hierarchical_experience_manager: HierarchicalExperienceManager = None
    experience_quality_tracker: ExperienceQualityTracker = None
    recorder: TaskRecorder = None

    def __init__(self, config: TrainingFreeGRPOConfig):
        """Initialize TrainingFreeGRPO with unified configuration."""
        self.config = config
        self.recorder: TaskRecorder = TaskRecorder(experiment_name=config.exp_id)

    async def run(self) -> str:
        """Run the complete experience generation process.

        Returns:
            str: Agent configuration file content in YAML format with experiences integrated
        """
        logger.info("Starting experience generation...")

        # Stage 0: Load components if not already built
        if self.practice_rollout_manager is None:
            logger.info("Stage 0: Building Training-free GRPO components...")
            await self.build()

        try:
            # Stage 1: Run training-free GRPO process
            logger.info("Stage 1: Running training-free GRPO process...")
            await self.practice()

            # Stage 2: Extract and process experiences
            logger.info("Stage 2: Extracting and processing experiences...")
            experiences = self.recorder.experiences or {}
            logger.info(f"Extracted {len(experiences)} experiences")
            agent_config_path = self._create_agent_config_with_experiences(experiences)
            return agent_config_path

        except Exception as e:
            logger.error(f"Error during experience generation: {e}", exc_info=True)
            raise

    async def build(self):
        """Build all components needed for training-free GRPO."""

        # 1. Load dataset
        # check if dataset exists
        data_manager = TrainingFreeGRPODataManager(self.config.evaluation)
        # load practice dataset if not exists
        if not data_manager.check_dataset(self.config.data.practice_dataset_name):
            raise ValueError(
                f"Practice dataset {self.config.data.practice_dataset_name} does not exist in db. Please load it first."
            )
        # load eval dataset if not exists
        if (
            self.config.evaluation.data
            and self.config.evaluation.data.dataset
            and not data_manager.check_dataset(self.config.evaluation.data.dataset)
        ):
            raise ValueError(
                f"Evaluation dataset {self.config.evaluation.data.dataset} does not exist in db. Please load it first."
            )

        skillsbench = getattr(self.config.evaluation, "skillsbench", None)
        if (
            skillsbench
            and getattr(skillsbench, "enabled", False)
            and getattr(skillsbench, "require_disjoint_train_eval", True)
            and self.config.evaluation.data
            and self.config.evaluation.data.dataset
        ):
            evidence = assert_datasets_disjoint(
                self.config.data.practice_dataset_name,
                self.config.evaluation.data.dataset,
                db_url=self.config.evaluation.db_url,
                split_manifest_path=getattr(skillsbench, "task_split_manifest_path", None),
                split_name=getattr(skillsbench, "task_split_name", None),
            )
            logger.info("SkillsBench train/eval overlap assertion passed: %s", evidence)

        # 2. Create practice rollout manager
        practice_eval_config = self.config.evaluation.model_copy()
        practice_eval_config.pass_k = self.config.practice.grpo_n
        self.original_temperature = practice_eval_config.agent.model.model_settings.temperature
        practice_eval_config.agent.model.model_settings.temperature = self.config.practice.rollout_temperature
        practice_eval_config.data = DataConfig(dataset=self.config.data.practice_dataset_name)

        # Pass KORGym configuration to practice eval config
        logger.info(f"TrainingFreeGRPO build: hasattr(self.config, 'korgym')={hasattr(self.config, 'korgym')}")
        if hasattr(self.config, "korgym"):
            logger.info(f"TrainingFreeGRPO build: self.config.korgym={self.config.korgym}")
            if self.config.korgym:
                practice_eval_config.korgym = self.config.korgym
                logger.info(f"✓ Passed korgym config to practice_eval_config: {self.config.korgym}")

        self.practice_rollout_manager = RolloutManager(
            config=practice_eval_config,
            batch_size=self.config.practice.batch_size,
            task_timeout=self.config.practice.task_timeout,
        )

        # 3. Create eval rollout manager (if different from practice)
        self.eval_rollout_manager = None
        if self.config.practice.do_eval:
            eval_eval_config = self.config.evaluation.model_copy()
            eval_eval_config.exp_id = eval_eval_config.exp_id + "_eval"
            # eval_eval_config.data = DataConfig(dataset=self.config.data.eval_dataset_name)
            # Pass KORGym configuration to eval eval config
            if hasattr(self.config, "korgym") and self.config.korgym:
                eval_eval_config.korgym = self.config.korgym
            self.eval_rollout_manager = RolloutManager(
                config=eval_eval_config,
                batch_size=self.config.practice.batch_size,
                task_timeout=self.config.practice.task_timeout,
            )

        # 4. Create experience updater
        # 使用环境无关的经验提取逻辑（支持所有 reward 类型：0/1、连续、>1 等）
        self.experience_updater = ExperienceUpdater(
            self.config.evaluation.agent, self.config.practice.agent_objective, self.config.practice.learning_objective
        )

        # 5. Create hierarchical experience manager if enabled
        self.hierarchical_experience_manager = None
        if self.config.practice.hierarchical_learning.enabled:
            logger.info("Initializing hierarchical experience manager (L0/L1/L2)...")
            self.hierarchical_experience_manager = HierarchicalExperienceManager(
                config=self.config.evaluation.agent,
                hierarchical_config=self.config.practice.hierarchical_learning,
                agent_objective=self.config.practice.agent_objective,
                learning_objective=self.config.practice.learning_objective,
            )
            logger.info("Hierarchical experience manager initialized")

        # 6. Create experience quality tracker
        self.experience_quality_tracker = ExperienceQualityTracker(
            experiment_name=self.config.exp_id,
        )
        logger.info("Experience quality tracker initialized")

        logger.info("Training-free GRPO components built successfully")

    async def practice(self):
        """Run practice process."""
        for epoch in range(self.config.practice.epochs):
            logger.info(f"Start Epoch {epoch}")

            # Prepare epoch data
            epoch_data = self.practice_rollout_manager.load_epoch_data(
                epoch, shuffle=self.config.practice.shuffle_data, truncate=self.config.practice.rollout_data_truncate
            )

            # check the batch size
            assert len(epoch_data) % self.config.practice.grpo_n == 0, (
                f"Epoch data size {len(epoch_data)} is not divisible by grpo_n {self.config.practice.grpo_n}"
            )
            if len(epoch_data) < self.config.practice.batch_size * self.config.practice.grpo_n:
                raise ValueError(
                    f"Epoch {epoch} data size {len(epoch_data) // self.config.practice.grpo_n} is smaller than "
                    f"batch size {self.config.practice.batch_size}."
                )
            if len(epoch_data) % (self.config.practice.batch_size * self.config.practice.grpo_n) != 0:
                logger.warning(
                    f"Epoch {epoch} data size {len(epoch_data) // self.config.practice.grpo_n} is not divisible by "
                    f"batch size {self.config.practice.batch_size}. Some data will be dropped."
                )

            # inner loop for each batch
            num_batches = len(epoch_data) // (self.config.practice.batch_size * self.config.practice.grpo_n)
            for batch_idx in range(num_batches):
                step = epoch * num_batches + batch_idx
                logger.info(f"Step {step} (Epoch {epoch}, Batch {batch_idx})")
                # set tracing
                step_trace_id = gen_trace_id()
                with trace(f"[{self.recorder.experiment_name}] Step {step} practice", trace_id=step_trace_id):
                    # get current stat
                    stats = self.recorder.stats or {}
                    if f"step_{step}" not in stats:
                        stats[f"step_{step}"] = {"epoch": epoch, "batch": batch_idx, "complete": False}

                    # 1. Rollout batch data
                    injected_ids = list((self.recorder.experiences or {}).keys())
                    if self.experience_quality_tracker is not None and injected_ids:
                        self.experience_quality_tracker.record_injection(injected_ids, step)

                    with custom_span("Process the batch data"):
                        rollouts, stat = await self.practice_rollout_manager.main(
                            batch_idx=batch_idx,
                            recorder=self.recorder,
                            use_cache=self._should_use_cache(step),
                        )
                        stats[f"step_{step}"]["rollout"] = stat

                    if self.experience_quality_tracker is not None and injected_ids:
                        self.experience_quality_tracker.record_outcomes(rollouts, step, injected_ids)

                    # 2. Update experiences based on rollouts
                    with custom_span("Generate batch experiences"):
                        # Check database cache first — use (epoch, batch) as the stable key
                        # so that changing num_batches across restarts never reuses wrong cache.
                        cached_experiences = ExperienceCache.load_experiences(
                            experiment_name=self.recorder.experiment_name,
                            step=step,
                            epoch=epoch,
                            batch=batch_idx,
                        )
                        # Raw L0 candidates (pre-merge per-problem insights) for the
                        # hierarchical manager. Only available on a fresh run; cached
                        # steps were already folded into L0 on the original run.
                        l0_candidates: list[dict] = []
                        if cached_experiences is not None and self._should_use_cache(step):
                            logger.info(
                                f"Experiences for step {step} already exist in database, skipping experience update."
                            )
                            new_experiences = cached_experiences
                            self.recorder.experiences_update(new_experiences)
                        else:
                            # If not cached, run experience updater
                            # Use lower concurrency for experience updates to avoid rate limiting
                            # Experience updates involve LLM calls which are more rate-limited than rollouts
                            experience_concurrency = min(self.config.practice.rollout_concurrency, 16)
                            new_experiences = await self.experience_updater.run(
                                rollouts=rollouts,
                                recorder=self.recorder,
                                concurrency=experience_concurrency,
                                given_ground_truth=self.config.practice.given_ground_truth,
                                num_experiences=self.config.practice.num_experiences_per_query,
                            )

                            # Save to database cache
                            ExperienceCache.save_experiences(
                                experiment_name=self.recorder.experiment_name,
                                step=step,
                                experiences=new_experiences,
                                epoch=epoch,
                                batch=batch_idx,
                            )
                            logger.info(f"Step {step} completed. New experiences added: {len(new_experiences)}")
                            # Raw, pre-merge insights produced by this step's updater run.
                            l0_candidates = list(getattr(self.experience_updater, "last_l0_candidates", []) or [])

                        # Per-step: accumulate L0 only. L1/L2 are aggregated at epoch end.
                        if self.hierarchical_experience_manager is not None:
                            logger.info(f"Merging L0 candidates for step {step} ({len(l0_candidates)} candidates)...")
                            await self.hierarchical_experience_manager.process_step_experiences(
                                l0_candidates=l0_candidates,
                                step=step,
                            )
                            logger.info(f"L0 pool size: {len(self.hierarchical_experience_manager.l0)}")

                        stats[f"step_{step}"]["complete"] = True
                        self.recorder.stat_update({f"step_{step}": stats[f"step_{step}"]})

                    # 3. Evaluation based on strategy
                    if self.eval_rollout_manager and self._should_evaluate(step, batch_idx, num_batches):
                        eval_trace_id = gen_trace_id()
                        with trace(f"[{self.recorder.experiment_name}] Step {step} evaluation", trace_id=eval_trace_id):
                            logger.info(f"Running evaluation at step {step}")
                            eval_data = self.eval_rollout_manager.load_epoch_data(
                                epoch=epoch, shuffle=False, truncate=self.config.practice.eval_data_truncate
                            )
                            logger.info(f"Evaluation dataset loaded with {len(eval_data)} records")
                            _, eval_stats = await self.eval_rollout_manager.main(
                                recorder=self.recorder, use_cache=self._should_use_cache(step)
                            )
                            with function_span("Record evaluation stats") as eval_stat_span:
                                eval_stat_span.span_data.output = eval_stats
                            stats[f"step_{step}"]["eval"] = eval_stats
                            self.recorder.stat_update({f"step_{step}": stats[f"step_{step}"]})

                    # 4. record stats and experiences to tracing
                    with function_span("Record current stats") as stat_span:
                        stat_span.span_data.output = stats[f"step_{step}"]
                    with function_span("Record current experiences") as exp_span:
                        exp_span.span_data.output = new_experiences

            # End of epoch: aggregate L1 (from new L0) and L2 (from L1), refining
            # any stale entries across epochs via the shared LLM merge.
            if self.hierarchical_experience_manager is not None:
                logger.info(f"Aggregating hierarchical experiences at end of epoch {epoch}...")
                await self.hierarchical_experience_manager.aggregate_epoch(epoch)

    def _should_use_cache(self, step: int) -> bool:
        """Determine if cached results should be used for current step.

        Restart behavior:
        - restart_step=None: Use cache for all steps (if available)
        - restart_step=N: Use cache for steps < N, execute fresh from step N onwards
        - restart_step=0: Execute all steps fresh (no caching)
        """
        restart_step = self.config.practice.restart_step
        return restart_step is None or step < restart_step

    def _should_evaluate(self, total_steps: int, batch_idx: int, num_batches: int) -> bool:
        """Determine if evaluation should be performed at current step."""
        if self.config.practice.eval_strategy == "epoch":
            # Evaluate at the end of each epoch
            return batch_idx == num_batches - 1
        elif self.config.practice.eval_strategy == "steps":
            # Evaluate every eval_steps
            return total_steps % self.config.practice.eval_steps == 0
        return False

    def _create_agent_config_with_experiences(self, experiences: dict[str, str]) -> str:
        """Create agent configuration with experiences integrated into instructions."""
        # Load the original agent config
        base_config = self.config.evaluation.agent
        # Convert to dict for manipulation
        config_dict = base_config.model_dump(exclude_none=True)

        # Format and inject experiences using a three-zone strategy:
        #
        #   ZONE 1 (top of system prompt): L2 meta-principles, written as
        #           first-person internalized knowledge.  Highest model attention.
        #
        #   ZONE 2 (middle of system prompt): L1 pattern guidelines, listed as
        #           actionable bullet points.
        #
        #   ZONE 3 (appended after base instructions): L0 case lessons — the
        #           most specific layer.  Kept brief; the full case library is
        #           available via max_l0_recent config.
        #
        # This layout exploits the U-shaped attention distribution in long
        # prompts: important meta-knowledge lands at the top, where attention
        # is highest, rather than being buried after the base instructions.
        if self.hierarchical_experience_manager is not None:
            logger.info("Using hierarchical experiences (L0/L1/L2)")
            all_l2 = self.hierarchical_experience_manager.get_all_l2_experiences()
            all_l1 = self.hierarchical_experience_manager.get_all_l1_experiences()

            current_instructions = config_dict.get("agent", {}).get("instructions", "You are a helpful assistant.")

            # --- ZONE 1: L2 meta-strategies prepended to the system prompt ---
            if all_l2:
                l2_bullets = "\n".join(f"• {exp['content']}" for exp in all_l2)
                l2_block = (
                    "You have developed the following principles through experience "
                    "completing similar tasks. Apply them proactively:\n"
                    f"{l2_bullets}\n\n"
                )
                current_instructions = l2_block + current_instructions

            # --- ZONE 2: L1 patterns appended as an operational guideline section ---
            if all_l1:
                l1_bullets = "\n".join(f"• {exp['content']}" for exp in all_l1)
                l1_block = f"\n\nProven patterns from past tasks:\n{l1_bullets}"
                current_instructions = current_instructions + l1_block

            # --- ZONE 3: L0 case lessons (optional, kept brief) ---
            if self.config.practice.hierarchical_learning.include_l0_in_prompt:
                recent_l0 = self.hierarchical_experience_manager.get_recent_l0_experiences(
                    self.config.practice.hierarchical_learning.max_l0_recent
                )
                if recent_l0:
                    l0_bullets = "\n".join(f"• {exp['content']}" for exp in recent_l0)
                    l0_block = f"\n\nSpecific lessons from recent tasks:\n{l0_bullets}"
                    current_instructions = current_instructions + l0_block
            else:
                recent_l0 = []

            if all_l2 or all_l1 or recent_l0:
                config_dict["agent"]["instructions"] = current_instructions
                config_dict["model"]["model_settings"]["temperature"] = self.original_temperature
                logger.info(
                    f"Injected experiences — L2={len(all_l2)} (top/zone-1), "
                    f"L1={len(all_l1)} (middle/zone-2), "
                    f"L0={len(recent_l0)} (bottom/zone-3)"
                )

        elif experiences:
            # Flat experiences (no hierarchical manager): prepend as internalized knowledge.
            current_instructions = config_dict.get("agent", {}).get("instructions", "You are a helpful assistant.")
            exp_bullets = "\n".join(f"• {e}" for e in experiences.values())
            exp_block = (
                "You have developed the following principles through experience "
                "completing similar tasks. Apply them proactively:\n"
                f"{exp_bullets}\n\n"
            )
            config_dict["agent"]["instructions"] = exp_block + current_instructions
            config_dict["model"]["model_settings"]["temperature"] = self.original_temperature

        # Remove unnecessary fields
        remain_default_keys = ["type", "model", "agent", "toolkits"]
        for key in list(config_dict.keys()):
            if key not in remain_default_keys:
                del config_dict[key]

        # Convert to YAML format
        yaml_config = yaml.dump(config_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
        config_header = "# @package _global_\ndefaults:\n  - _self_\n\n"
        # save to file
        config_filename = f"{self.config.evaluation.exp_id}_agent.yaml"
        config_dir = str(DIR_ROOT / "configs" / "agents" / "practice")
        full_path = os.path.join(config_dir, os.path.basename(config_filename))
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(config_header + yaml_config)
        return full_path
