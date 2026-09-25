"""
Main module for experience generation. Control the process of Training-free GRPO.
"""

import hashlib
import json
import os

import yaml
from agents import custom_span, function_span, gen_trace_id, trace

from ..config import EvalConfig, TrainingFreeGRPOConfig
from ..config.eval_config import DataConfig
from ..skillsbench_data import assert_datasets_disjoint
from ..utils import DIR_ROOT, get_logger
from ..utils.experience_cache import ExperienceCache
from ..utils.experience_injection import INJECTED_EXPERIENCE_IDS_META_KEY
from .application import candidate_cache
from .data_manager import TrainingFreeGRPODataManager
from .dataset_manifest_guard import validate_practice_dataset_manifest
from .experience_quality_tracker import ExperienceQualityTracker
from .experience_updater import ExperienceUpdater
from .hierarchical_experience_manager import HierarchicalExperienceManager
from .rollout_manager import RolloutManager
from .utils import TaskRecorder

logger = get_logger(__name__)

HIERARCHICAL_CANDIDATE_CACHE_KIND = candidate_cache.HIERARCHICAL_CANDIDATE_CACHE_KIND
HIERARCHICAL_FLAT_CACHE_KIND = candidate_cache.HIERARCHICAL_FLAT_CACHE_KIND

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
        self.recorder: TaskRecorder = TaskRecorder(
            experiment_name=config.exp_id,
            l0_injection_top_k=(
                config.practice.hierarchical_learning.l0_injection_top_k
                if config.practice.hierarchical_learning.enabled
                else 0
            ),
        )

    def _make_practice_eval_config(self):
        """Build the evaluation adapter used by the practice rollout pipeline."""

        runtime = self.config.runtime
        agent = runtime.agent.model_copy(deep=True) if runtime.agent is not None else None
        if agent is None:
            raise ValueError("runtime.agent is required for practice rollouts")
        self.original_temperature = agent.model.model_settings.temperature
        agent.model.model_settings.temperature = self.config.practice.rollout_temperature
        practice_eval_config = EvalConfig(
            exp_id=self.config.exp_id,
            db_url=runtime.db_url,
            data=DataConfig(dataset=self.config.data.practice_dataset_name),
            agent=agent,
            concurrency=self.config.practice.rollout_concurrency,
            pass_k=self.config.practice.grpo_n,
            log_trajectory_to_db=False,
            judge_model=runtime.judge_model.model_copy(deep=True),
            judge_concurrency=runtime.judge_concurrency,
            verify_filename=runtime.verify_filename,
            verify_func_name=runtime.verify_func_name,
            korgym=runtime.korgym.model_copy(deep=True),
            skillsbench=runtime.skillsbench.model_copy(deep=True),
        )
        return practice_eval_config

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
        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        """Release runtime resources so repeated experiments do not leak clients."""

        components = (
            self.practice_rollout_manager,
            self.eval_rollout_manager,
            self.experience_updater,
            self.hierarchical_experience_manager,
        )
        for component in components:
            cleanup = getattr(component, "cleanup", None)
            if cleanup is None:
                continue
            try:
                await cleanup()
            except Exception as exc:  # pragma: no cover - external resources
                logger.warning("Training-free GRPO component cleanup failed: %s", exc)

        # A subsequent run rebuilds fresh HTTP clients and reloads hierarchy
        # state from the durable snapshot.
        self.practice_rollout_manager = None
        self.eval_rollout_manager = None
        self.experience_updater = None
        self.hierarchical_experience_manager = None

    async def build(self):
        """Build all components needed for training-free GRPO."""

        # 0. A measured snapshot is verified before constructing any rollout,
        # model-backed updater, or hierarchical manager.  This is deliberately
        # fail-closed: a renamed/mutated DB snapshot must never spend API calls.
        if self.config.data.require_practice_manifest:
            evaluation_dataset = (
                self.config.runtime.data.dataset
                if self.config.runtime.data is not None
                else None
            )
            evidence = validate_practice_dataset_manifest(
                practice_dataset=self.config.data.practice_dataset_name,
                manifest_path=self.config.data.practice_manifest_path,
                split_name=self.config.data.practice_manifest_split,
                expected_record_count=self.config.data.practice_manifest_expected_records,
                evaluation_dataset=evaluation_dataset,
                db_url=self.config.runtime.db_url,
            )
            logger.info("Strict practice dataset manifest assertion passed: %s", evidence)

        # 1. Load dataset
        # check if dataset exists
        data_manager = TrainingFreeGRPODataManager(
            self.config.runtime,
            mistake_focus_ratio=self.config.practice.mistake_focus_ratio,
            data_seed=self.config.practice.data_seed,
        )
        # load practice dataset if not exists
        if not data_manager.check_dataset(self.config.data.practice_dataset_name):
            raise ValueError(
                f"Practice dataset {self.config.data.practice_dataset_name} does not exist in db. Please load it first."
            )
        # load eval dataset if not exists
        if (
            self.config.runtime.data
            and self.config.runtime.data.dataset
            and not data_manager.check_dataset(self.config.runtime.data.dataset)
        ):
            raise ValueError(
                f"Evaluation dataset {self.config.runtime.data.dataset} does not exist in db. Please load it first."
            )

        skillsbench = getattr(self.config.runtime, "skillsbench", None)
        if (
            skillsbench
            and getattr(skillsbench, "enabled", False)
            and getattr(skillsbench, "require_disjoint_train_eval", True)
            and self.config.runtime.data
            and self.config.runtime.data.dataset
        ):
            evidence = assert_datasets_disjoint(
                self.config.data.practice_dataset_name,
                self.config.runtime.data.dataset,
                db_url=self.config.runtime.db_url,
                split_manifest_path=getattr(skillsbench, "task_split_manifest_path", None),
                split_name=getattr(skillsbench, "task_split_name", None),
            )
            logger.info("SkillsBench train/eval overlap assertion passed: %s", evidence)

        # 2. Create practice rollout manager
        practice_eval_config = self._make_practice_eval_config()

        self.practice_rollout_manager = RolloutManager(
            config=practice_eval_config,
            batch_size=self.config.practice.batch_size,
            task_timeout=self.config.practice.task_timeout,
            max_retries=self.config.practice.rollout_max_retries,
            mistake_focus_ratio=self.config.practice.mistake_focus_ratio,
            data_seed=self.config.practice.data_seed,
            data_layout_context={
                "batch_size": self.config.practice.batch_size,
                "require_practice_manifest": self.config.data.require_practice_manifest,
                "practice_manifest_path": self.config.data.practice_manifest_path,
                "practice_manifest_split": self.config.data.practice_manifest_split,
                "practice_manifest_expected_records": (
                    self.config.data.practice_manifest_expected_records
                ),
            },
            allow_legacy_epoch_cache=self.config.practice.resume_from_hierarchy,
        )
        logger.info(
            "Practice rollout controls: concurrency=%s max_retries=%s "
            "task_timeout=%ss data_seed=%s mistake_focus_ratio=%.3f",
            practice_eval_config.concurrency,
            self.config.practice.rollout_max_retries,
            self.config.practice.task_timeout,
            self.config.practice.data_seed,
            self.config.practice.mistake_focus_ratio,
        )

        # 3. Create eval rollout manager (if different from practice)
        self.eval_rollout_manager = None
        if self.config.practice.do_eval:
            runtime = self.config.runtime
            if runtime.data is None or runtime.agent is None:
                raise ValueError("runtime.data and runtime.agent are required for in-run evaluation")
            eval_agent = runtime.agent.model_copy(deep=True)
            eval_eval_config = EvalConfig(
                exp_id=self.config.exp_id + "_eval",
                db_url=runtime.db_url,
                data=runtime.data.model_copy(deep=True),
                agent=eval_agent,
                concurrency=self.config.practice.eval_concurrency or self.config.practice.rollout_concurrency,
                pass_k=self.config.practice.eval_pass_k or self.config.practice.grpo_n,
                judge_model=runtime.judge_model.model_copy(deep=True),
                judge_concurrency=(
                    self.config.practice.eval_judge_concurrency or runtime.judge_concurrency
                ),
                verify_filename=runtime.verify_filename,
                verify_func_name=runtime.verify_func_name,
                korgym=runtime.korgym.model_copy(deep=True),
                skillsbench=runtime.skillsbench.model_copy(deep=True),
            )
            self.eval_rollout_manager = RolloutManager(
                config=eval_eval_config,
                batch_size=self.config.practice.batch_size,
                task_timeout=self.config.practice.task_timeout,
            )

        # 4. Create experience updater
        # 使用环境无关的经验提取逻辑（支持所有 reward 类型：0/1、连续、>1 等）
        experience_output_language = getattr(
            self.config.practice.hierarchical_learning,
            "experience_output_language",
            "same_as_input",
        )
        self.experience_updater = ExperienceUpdater(
            self.config.runtime.agent,
            self.config.practice.agent_objective,
            self.config.practice.learning_objective,
            experience_output_language=experience_output_language,
            generation_cache_path=str(
                DIR_ROOT / "workspace" / "cache" / "experience_generation"
                / (hashlib.sha256(self.config.exp_id.encode()).hexdigest() + ".sqlite3")
            ),
        )

        # 5. Create hierarchical experience manager if enabled
        self.hierarchical_experience_manager = None
        if self.config.practice.hierarchical_learning.enabled:
            logger.info("Initializing hierarchical experience manager (L0/L1/L2)...")
            self.hierarchical_experience_manager = HierarchicalExperienceManager(
                config=self.config.runtime.agent,
                hierarchical_config=self.config.practice.hierarchical_learning,
                agent_objective=self.config.practice.agent_objective,
                learning_objective=self.config.practice.learning_objective,
            )
            if self.config.practice.restart_step is not None:
                self.hierarchical_experience_manager.assert_restart_step_safe(
                    self.config.practice.restart_step
                )
            self._sync_hierarchical_recorder()
            logger.info("Hierarchical experience manager initialized")

        # 6. Create experience quality tracker
        self.experience_quality_tracker = ExperienceQualityTracker(
            experiment_name=self.config.exp_id,
        )
        logger.info("Experience quality tracker initialized")

        logger.info("Training-free GRPO components built successfully")

    def _uses_candidate_review(self) -> bool:
        if self.hierarchical_experience_manager is None:
            return False
        return bool(
            getattr(
                self.config.practice.hierarchical_learning,
                "l0_candidate_review_enabled",
                False,
            )
        )

    def _sync_hierarchical_recorder(self) -> dict[str, str]:
        """Make the hierarchy's injectable view the only rollout experience pool."""

        if self.hierarchical_experience_manager is None:
            return dict(self.recorder.experiences or {})
        experiences = self.hierarchical_experience_manager.get_injectable_experience_pool()
        self.recorder.experiences_update(experiences)
        return experiences

    @staticmethod
    def _candidate_cache_payload(candidates: list[dict], *, batch_fingerprint: str) -> dict:
        return candidate_cache.candidate_cache_payload(
            candidates,
            batch_fingerprint=batch_fingerprint,
        )

    @staticmethod
    def _flat_experiences_from_cache(payload: object) -> dict[str, str] | None:
        """Accept only the legacy flat cache shape, never an unknown envelope."""

        return candidate_cache.flat_experiences_from_cache(payload)

    @classmethod
    def _hierarchical_flat_cache_payload(
        cls,
        experiences: dict[str, str],
        candidates: list[dict],
        *,
        batch_fingerprint: str,
    ) -> dict:
        return candidate_cache.hierarchical_flat_cache_payload(
            experiences,
            candidates,
            batch_fingerprint=batch_fingerprint,
        )

    @classmethod
    def _hierarchical_flat_from_cache(
        cls,
        payload: object,
        *,
        expected_batch_fingerprint: str,
    ) -> tuple[dict[str, str], list[dict]] | None:
        """Decode the review-off hierarchy cache needed for crash-safe replay."""

        return candidate_cache.hierarchical_flat_from_cache(
            payload,
            expected_batch_fingerprint=expected_batch_fingerprint,
        )

    @staticmethod
    def _candidates_from_cache(
        payload: object,
        *,
        expected_batch_fingerprint: str | None = None,
        expected_run_id: str | None = None,
        expected_epoch: int | None = None,
        expected_batch: int | None = None,
    ) -> list[dict] | None:
        return candidate_cache.candidates_from_cache(
            payload,
            expected_batch_fingerprint=expected_batch_fingerprint,
            expected_run_id=expected_run_id,
            expected_epoch=expected_epoch,
            expected_batch=expected_batch,
        )

    @staticmethod
    def _rollout_batch_fingerprint(rollouts: list) -> str:
        """Bind a candidate cache entry to the exact unordered rollout batch."""

        return candidate_cache.rollout_batch_fingerprint(rollouts)

    def _candidate_generation_fingerprint(self, rollouts: list) -> str:
        return candidate_cache.candidate_generation_fingerprint(
            self.config,
            self.experience_updater,
            rollouts,
        )

    def _recover_hierarchical_candidates(
        self,
        *,
        step: int,
        run_id: str,
        epoch: int,
        batch: int,
        batch_fingerprint: str,
        cached_experiences: object,
        cache_reuse_allowed: bool,
    ) -> tuple[list[dict] | None, bool]:
        """Choose an exact persisted candidate batch before regenerating it.

        Candidate staging and review share the hierarchy JSON transaction, so
        that snapshot is the crash-recovery authority. The database row is an
        auxiliary cache and is used only when the hierarchy has not staged the
        step yet. ``None`` means generation is required. Empty candidate
        envelopes are invalid because every practice batch contains rollouts
        and the generator itself rejects an empty result.
        """

        persisted_fingerprints = (
            self.hierarchical_experience_manager.get_l0_candidate_fingerprints_for_batch(
                run_id=run_id,
                epoch=epoch,
                batch=batch,
            )
        )
        if persisted_fingerprints and persisted_fingerprints != {batch_fingerprint}:
            raise RuntimeError(
                "L0 candidate generation fingerprint changed for an already persisted "
                f"batch run={run_id!r} epoch={epoch} batch={batch}: "
                f"stored={sorted(str(item) for item in persisted_fingerprints)} "
                f"current={batch_fingerprint}. Use a new exp_id and experience_save_path."
            )
        if not cache_reuse_allowed:
            return None, True
        cached_candidates = self._candidates_from_cache(
            cached_experiences,
            expected_batch_fingerprint=batch_fingerprint,
            expected_run_id=run_id,
            expected_epoch=epoch,
            expected_batch=batch,
        )
        persisted_candidates = (
            self.hierarchical_experience_manager.get_l0_candidate_inputs_for_step(
                step,
                run_id=run_id,
                epoch=epoch,
                batch=batch,
                batch_fingerprint=batch_fingerprint,
            )
        )
        if persisted_candidates:
            logger.info(
                "Recovering %d L0 candidates for step %s from the hierarchy snapshot",
                len(persisted_candidates),
                step,
            )
            return persisted_candidates, cached_candidates != persisted_candidates
        if cached_candidates is not None:
            return cached_candidates, False
        if cached_experiences is not None:
            logger.warning(
                "Regenerating L0 candidates for hierarchical step %s because its cache "
                "is legacy or malformed; the flat payload will not be injected",
                step,
            )
        return None, True

    def _hierarchy_resume_checkpoints(self) -> dict[tuple[int, int], dict]:
        """Load the immutable contiguous-prefix evidence used by resume mode.

        The hierarchy snapshot, rather than the derived numeric step or the
        auxiliary experience cache, is authoritative.  Structural checks that
        require the current epoch size are completed after epoch rows are
        loaded, before any batch is preprocessed.
        """

        if not self.config.practice.resume_from_hierarchy:
            return {}
        if self.hierarchical_experience_manager is None:
            raise RuntimeError(
                "resume_from_hierarchy requires an initialized hierarchical experience manager"
            )

        checkpoints: dict[tuple[int, int], dict] = {}
        for raw_checkpoint in self.hierarchical_experience_manager.get_l0_batch_checkpoints(
            run_id=self.recorder.experiment_name
        ):
            try:
                epoch = int(raw_checkpoint["epoch"])
                batch = int(raw_checkpoint["batch"])
                step = int(raw_checkpoint["step"])
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError(
                    f"Cannot resume from hierarchy: malformed batch checkpoint {raw_checkpoint!r}"
                ) from error
            if epoch < 0 or batch < 0 or step < 0:
                raise RuntimeError(
                    f"Cannot resume from hierarchy: negative batch checkpoint {raw_checkpoint!r}"
                )
            if epoch >= self.config.practice.epochs:
                raise RuntimeError(
                    "Cannot resume from hierarchy: snapshot contains epoch "
                    f"{epoch}, but the configured run has only {self.config.practice.epochs} epoch(s)"
                )
            key = (epoch, batch)
            if key in checkpoints:
                raise RuntimeError(
                    "Cannot resume from hierarchy: duplicate checkpoint for "
                    f"epoch={epoch} batch={batch}"
                )
            checkpoints[key] = dict(raw_checkpoint)

        logger.info(
            "Hierarchy prefix resume enabled: loaded %d committed batch checkpoint(s)",
            len(checkpoints),
        )
        return checkpoints

    def _resolve_hierarchical_resume_step(
        self,
        num_batches: int,
        *,
        checkpoints: dict[tuple[int, int], dict] | None = None,
    ) -> int:
        """Validate snapshot checkpoints and return the first uncommitted step."""

        if num_batches < 1:
            raise ValueError("num_batches must be positive")
        recorder = getattr(self, "recorder", None)
        run_id = getattr(recorder, "experiment_name", None) or self.config.exp_id
        if checkpoints is None:
            if self.hierarchical_experience_manager is None:
                raise RuntimeError("Cannot resolve hierarchy resume without a hierarchy manager")
            checkpoints = {}
            for checkpoint in self.hierarchical_experience_manager.get_l0_batch_checkpoints(
                run_id=run_id
            ):
                key = (int(checkpoint["epoch"]), int(checkpoint["batch"]))
                checkpoints[key] = dict(checkpoint)

        ordered = sorted(checkpoints.values(), key=lambda item: int(item["step"]))
        for expected_step, checkpoint in enumerate(ordered):
            epoch = int(checkpoint["epoch"])
            batch = int(checkpoint["batch"])
            stored_step = int(checkpoint["step"])
            expected_epoch = expected_step // num_batches
            expected_batch = expected_step % num_batches
            if (epoch, batch) != (expected_epoch, expected_batch):
                raise RuntimeError(
                    "Cannot resume from hierarchy: checkpoints are not a contiguous prefix; "
                    f"expected epoch={expected_epoch} batch={expected_batch}, "
                    f"found epoch={epoch} batch={batch}"
                )
            layout_step = epoch * num_batches + batch
            if stored_step != layout_step:
                raise RuntimeError(
                    "Cannot resume from hierarchy: checkpoint step does not match the current "
                    f"batch layout for epoch={epoch} batch={batch}: "
                    f"stored={stored_step} expected={layout_step}"
                )

        resume_step = len(ordered)
        # Epoch-boundary transitions are verified and, if missing, completed
        # in `_finish_epoch_hierarchy`.  Checkpoints prove only the immutable
        # rollout/candidate prefix and must not prevent that recovery path.
        return resume_step

    @staticmethod
    def _validate_epoch_resume_checkpoints(
        checkpoints: dict[tuple[int, int], dict],
        *,
        epoch: int,
        num_batches: int,
    ) -> None:
        """Reject checkpoints produced with an incompatible batch layout."""

        for (checkpoint_epoch, batch), checkpoint in checkpoints.items():
            if checkpoint_epoch != epoch:
                continue
            if batch >= num_batches:
                raise RuntimeError(
                    "Cannot resume from hierarchy: checkpoint batch "
                    f"epoch={epoch} batch={batch} is outside the configured {num_batches} batches"
                )
            expected_step = epoch * num_batches + batch
            if checkpoint["step"] != expected_step:
                raise RuntimeError(
                    "Cannot resume from hierarchy: checkpoint step does not match the current "
                    f"batch layout for epoch={epoch} batch={batch}: "
                    f"stored={checkpoint['step']} expected={expected_step}. "
                    "Keep epochs, batch_size, grpo_n, and truncation unchanged."
                )

    def _validate_resume_batch_fingerprints(
        self,
        checkpoints: dict[tuple[int, int], dict],
        *,
        epoch: int,
    ) -> None:
        """Bind every skipped hierarchy checkpoint to its exact judged DB batch."""

        read_batch = getattr(self.practice_rollout_manager, "get_committed_batch_for_resume", None)
        epoch_checkpoints = sorted(
            (
                (batch, checkpoint)
                for (checkpoint_epoch, batch), checkpoint in checkpoints.items()
                if checkpoint_epoch == epoch
            ),
            key=lambda item: item[0],
        )
        if epoch_checkpoints and read_batch is None:
            raise RuntimeError(
                "Cannot resume from hierarchy: rollout manager cannot validate committed DB batches"
            )
        for batch, checkpoint in epoch_checkpoints:
            rollouts = read_batch(batch)
            actual_fingerprint = self._candidate_generation_fingerprint(rollouts)
            expected_fingerprint = checkpoint.get("batch_fingerprint")
            if actual_fingerprint != expected_fingerprint:
                raise RuntimeError(
                    "Cannot resume from hierarchy: judged DB batch does not match its hierarchy "
                    f"checkpoint for epoch={epoch} batch={batch}: "
                    f"stored={expected_fingerprint} current={actual_fingerprint}"
                )

    async def _finish_epoch_hierarchy(self, epoch: int, *, fully_skipped: bool) -> None:
        """Complete only hierarchy work not already proven at an epoch boundary."""

        manager = self.hierarchical_experience_manager
        if manager is None:
            return
        recovered_l0_review_work = False
        if self._uses_candidate_review():
            # A hierarchy checkpoint proves candidate staging, not that the
            # immediately following L0 review completed.  A crash in between
            # must not turn the skipped batch into a permanently pending L0
            # queue entry.
            review_counts = await manager.review_pending_candidates(candidate_level="L0")
            # ``skipped`` means no durable transition happened (for example an
            # exhausted automatic retry budget), so it must not invalidate an
            # otherwise sound epoch audit by itself.
            recovered_l0_review_work = any(
                review_counts.get(name, 0) > 0
                for name in ("committed", "failed", "stale")
            )
            if recovered_l0_review_work:
                logger.info(
                    "Epoch %s recovered staged L0 candidate review work: %s",
                    epoch,
                    review_counts,
                )

        if (
            not self.config.practice.resume_from_hierarchy
            or not fully_skipped
            or recovered_l0_review_work
        ):
            logger.info("Aggregating hierarchical experiences at end of epoch %s...", epoch)
            await manager.aggregate_epoch(
                epoch,
                run_id=self.recorder.experiment_name,
            )
        else:
            l0_to_l1_audited = manager.has_aggregation_audit(
                epoch=epoch,
                source_level="L0",
                target_level="L1",
                run_id=self.recorder.experiment_name,
                allow_legacy=True,
            )
            if not l0_to_l1_audited:
                logger.info(
                    "Resuming missing epoch %s L0->L1 transition",
                    epoch,
                )
                await manager.aggregate_levels(
                    ("L1",),
                    epoch=epoch,
                    run_id=self.recorder.experiment_name,
                )
            else:
                logger.info(
                    "Skipping epoch %s L0->L1 transition; bound audit exists",
                    epoch,
                )

            # L1->L2 is a separate durable transition.  In particular, a
            # process can crash after writing the L0->L1 audit and before L2.
            l1_to_l2_audited = manager.has_aggregation_audit(
                epoch=epoch,
                source_level="L1",
                target_level="L2",
                run_id=self.recorder.experiment_name,
                allow_legacy=True,
            )
            if not l1_to_l2_audited:
                logger.info(
                    "Resuming missing epoch %s L1->L2 transition",
                    epoch,
                )
                await manager.aggregate_levels(
                    ("L2",),
                    epoch=epoch,
                    run_id=self.recorder.experiment_name,
                )
            else:
                logger.info(
                    "Skipping epoch %s L1->L2 transition; bound audit exists",
                    epoch,
                )

        if self._uses_candidate_review():
            self._sync_hierarchical_recorder()

    async def practice(self):
        """Run practice process."""
        resume_checkpoints = self._hierarchy_resume_checkpoints()
        resume_prefix_open = bool(self.config.practice.resume_from_hierarchy)
        seen_resume_checkpoints: set[tuple[int, int]] = set()
        for epoch in range(self.config.practice.epochs):
            logger.info(f"Start Epoch {epoch}")

            epoch_has_checkpoints = any(
                checkpoint_epoch == epoch for checkpoint_epoch, _ in resume_checkpoints
            )
            has_epoch_data = getattr(self.practice_rollout_manager, "has_epoch_data", None)
            if epoch_has_checkpoints and has_epoch_data is not None and not has_epoch_data(epoch):
                raise RuntimeError(
                    "Cannot resume from hierarchy: committed hierarchy checkpoints exist for "
                    f"epoch {epoch}, but its rollout rows are missing from the database"
                )

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
            self._validate_epoch_resume_checkpoints(
                resume_checkpoints,
                epoch=epoch,
                num_batches=num_batches,
            )
            if self.config.practice.resume_from_hierarchy:
                self._validate_resume_batch_fingerprints(
                    resume_checkpoints,
                    epoch=epoch,
                )
            if epoch == 0 and self.config.practice.resume_from_hierarchy:
                self._resolve_hierarchical_resume_step(
                    num_batches,
                    checkpoints=resume_checkpoints,
                )
            skipped_batches = 0
            for batch_idx in range(num_batches):
                step = epoch * num_batches + batch_idx
                checkpoint_key = (epoch, batch_idx)
                checkpoint = resume_checkpoints.get(checkpoint_key)
                if self.config.practice.resume_from_hierarchy:
                    if checkpoint is not None:
                        if not resume_prefix_open:
                            raise RuntimeError(
                                "Cannot resume from hierarchy: checkpoints are not a contiguous "
                                f"prefix; found committed epoch={epoch} batch={batch_idx} after a gap"
                            )
                        seen_resume_checkpoints.add(checkpoint_key)
                        skipped_batches += 1
                        logger.info(
                            "Skipping committed hierarchy prefix step %s (epoch=%s batch=%s, "
                            "candidates=%s); rollout and preprocessing will not run",
                            step,
                            epoch,
                            batch_idx,
                            checkpoint.get("candidate_count"),
                        )
                        continue
                    resume_prefix_open = False
                logger.info(f"Step {step} (Epoch {epoch}, Batch {batch_idx})")
                # set tracing
                step_trace_id = gen_trace_id()
                with trace(f"[{self.recorder.experiment_name}] Step {step} practice", trace_id=step_trace_id):
                    # get current stat
                    stats = self.recorder.stats or {}
                    if f"step_{step}" not in stats:
                        stats[f"step_{step}"] = {"epoch": epoch, "batch": batch_idx, "complete": False}

                    # 1. Rollout batch data
                    with custom_span("Process the batch data"):
                        rollouts, stat = await self.practice_rollout_manager.main(
                            batch_idx=batch_idx,
                            recorder=self.recorder,
                            use_cache=self._should_use_cache(step),
                        )
                        stats[f"step_{step}"]["rollout"] = stat

                    if self.experience_quality_tracker is not None:
                        rollouts_by_experience: dict[str, list] = {}
                        fallback_ids = list((self.recorder.experiences or {}).keys())
                        for rollout in rollouts:
                            meta = rollout.meta
                            if isinstance(meta, str):
                                try:
                                    meta = json.loads(meta)
                                except json.JSONDecodeError:
                                    meta = None
                            selected_ids = (
                                meta.get(INJECTED_EXPERIENCE_IDS_META_KEY)
                                if isinstance(meta, dict)
                                else None
                            )
                            if not isinstance(selected_ids, list):
                                selected_ids = fallback_ids
                            for experience_id in selected_ids:
                                if isinstance(experience_id, str):
                                    rollouts_by_experience.setdefault(experience_id, []).append(rollout)
                        injected_ids = sorted(rollouts_by_experience)
                        if injected_ids:
                            self.experience_quality_tracker.record_injection(injected_ids, step)
                            self.experience_quality_tracker.record_outcomes_by_experience(
                                rollouts_by_experience,
                                step,
                            )

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
                        cache_reuse_allowed = self._should_use_cache(step)
                        self.experience_updater.reuse_generation_cache = cache_reuse_allowed
                        use_cached = cached_experiences is not None and cache_reuse_allowed
                        experience_concurrency = min(self.config.practice.rollout_concurrency, 16)
                        batch_fingerprint = self._candidate_generation_fingerprint(rollouts)

                        if self._uses_candidate_review():
                            l0_candidates, repair_candidate_cache = (
                                self._recover_hierarchical_candidates(
                                    step=step,
                                    run_id=self.recorder.experiment_name,
                                    epoch=epoch,
                                    batch=batch_idx,
                                    batch_fingerprint=batch_fingerprint,
                                    cached_experiences=cached_experiences,
                                    cache_reuse_allowed=cache_reuse_allowed,
                                )
                            )
                            if l0_candidates is None:
                                l0_candidates = await self.experience_updater.generate_l0_candidates(
                                    rollouts=rollouts,
                                    concurrency=experience_concurrency,
                                    given_ground_truth=self.config.practice.given_ground_truth,
                                    num_experiences=self.config.practice.num_experiences_per_query,
                                )

                            await self.hierarchical_experience_manager.process_step_experiences(
                                l0_candidates=l0_candidates or [],
                                step=step,
                                run_id=self.recorder.experiment_name,
                                epoch=epoch,
                                batch=batch_idx,
                                batch_fingerprint=batch_fingerprint,
                            )
                            new_experiences = self._sync_hierarchical_recorder()
                            if repair_candidate_cache:
                                canonical_candidates = (
                                    self.hierarchical_experience_manager.get_l0_candidate_inputs_for_step(
                                        step,
                                        run_id=self.recorder.experiment_name,
                                        epoch=epoch,
                                        batch=batch_idx,
                                        batch_fingerprint=batch_fingerprint,
                                    )
                                )
                                cache_saved = ExperienceCache.save_experiences(
                                    experiment_name=self.recorder.experiment_name,
                                    step=step,
                                    experiences=self._candidate_cache_payload(
                                        canonical_candidates,
                                        batch_fingerprint=batch_fingerprint,
                                    ),
                                    epoch=epoch,
                                    batch=batch_idx,
                                )
                                if not cache_saved:
                                    logger.warning(
                                        "Hierarchy is committed, but candidate cache save failed for step %s; "
                                        "a restart may regenerate summaries",
                                        step,
                                    )
                            logger.info(
                                "Step %s candidate review complete: raw=%d active hierarchy=%d",
                                step,
                                len(l0_candidates or []),
                                len(new_experiences),
                            )
                        else:
                            # Compatibility path for non-hierarchical runs and
                            # explicit review-off ablations.
                            l0_candidates: list[dict] = []
                            cached_flat: dict[str, str] | None = None
                            if use_cached and self.hierarchical_experience_manager is not None:
                                decoded = self._hierarchical_flat_from_cache(
                                    cached_experiences,
                                    expected_batch_fingerprint=batch_fingerprint,
                                )
                                if decoded is not None:
                                    cached_flat, l0_candidates = decoded
                            elif use_cached:
                                cached_flat = self._flat_experiences_from_cache(
                                    cached_experiences
                                )

                            if use_cached and cached_flat is None:
                                logger.warning(
                                    "Ignoring malformed, stale, or incompatible experience cache "
                                    "for review-off step %s; regenerating the legacy flat pool",
                                    step,
                                )
                                use_cached = False
                            if use_cached:
                                logger.info(
                                    "Experiences for step %s already exist in database, skipping update.",
                                    step,
                                )
                                new_experiences = cached_flat
                                self.recorder.experiences_update(new_experiences)
                            else:
                                new_experiences = await self.experience_updater.run(
                                    rollouts=rollouts,
                                    recorder=self.recorder,
                                    concurrency=experience_concurrency,
                                    given_ground_truth=self.config.practice.given_ground_truth,
                                    num_experiences=self.config.practice.num_experiences_per_query,
                                )
                                l0_candidates = list(
                                    getattr(self.experience_updater, "last_l0_candidates", []) or []
                                )

                            if not use_cached:
                                cache_payload: dict = new_experiences
                                if self.hierarchical_experience_manager is not None:
                                    cache_payload = self._hierarchical_flat_cache_payload(
                                        new_experiences,
                                        l0_candidates,
                                        batch_fingerprint=batch_fingerprint,
                                    )
                                cache_saved = ExperienceCache.save_experiences(
                                    experiment_name=self.recorder.experiment_name,
                                    step=step,
                                    experiences=cache_payload,
                                    epoch=epoch,
                                    batch=batch_idx,
                                )
                                if not cache_saved:
                                    if self.hierarchical_experience_manager is not None:
                                        raise RuntimeError(
                                            "Could not persist the replayable sequential-ablation "
                                            f"cache for step {step}; hierarchy was not modified"
                                        )
                                    logger.warning("Flat experience cache save failed for step %s", step)

                            # For the sequential hierarchy ablation, the cache
                            # stores both the pre-hierarchy flat result and raw
                            # candidates first. If hierarchy persistence then
                            # fails, restart can restore the same flat baseline
                            # and idempotently replay those candidates.
                            if self.hierarchical_experience_manager is not None:
                                await self.hierarchical_experience_manager.process_step_experiences(
                                    l0_candidates=l0_candidates,
                                    step=step,
                                    run_id=self.recorder.experiment_name,
                                    epoch=epoch,
                                    batch=batch_idx,
                                    batch_fingerprint=batch_fingerprint,
                                )

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

            # End of epoch: aggregate L1 (from new L0) and L2 (from L1). A
            # completely skipped prefix epoch resumes only a transition that
            # was not durably audited before the crash.
            await self._finish_epoch_hierarchy(
                epoch,
                fully_skipped=(skipped_batches == num_batches),
            )

        unseen_checkpoints = sorted(set(resume_checkpoints) - seen_resume_checkpoints)
        if unseen_checkpoints:
            raise RuntimeError(
                "Cannot resume from hierarchy: configured run did not visit checkpoint(s) "
                f"{unseen_checkpoints}"
            )

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

    def _create_agent_config_with_experiences(
        self,
        experiences: dict[str, str],
        *,
        output_path: str | os.PathLike[str] | None = None,
    ) -> str:
        """Create an Agent configuration with experiences integrated into instructions.

        ``output_path`` is an explicit artifact override for offline
        regeneration. Normal training keeps the canonical path derived from
        the root experiment ID.
        """
        # Load the original agent config
        base_config = self.config.runtime.agent
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
        #           controlled by the explicit export_max_l0 artifact limit.
        #
        # This layout exploits the U-shaped attention distribution in long
        # prompts: important meta-knowledge lands at the top, where attention
        # is highest, rather than being buried after the base instructions.
        if self.hierarchical_experience_manager is not None:
            logger.info("Using hierarchical experiences (L0/L1/L2)")
            all_l2 = self.hierarchical_experience_manager.get_injectable_l2_experiences()
            all_l1 = self.hierarchical_experience_manager.get_injectable_l1_experiences()

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
            hierarchy_config = self.config.practice.hierarchical_learning
            if hierarchy_config.export_include_l0 and hierarchy_config.export_max_l0 != 0:
                if hierarchy_config.export_max_l0 is None:
                    recent_l0 = self.hierarchical_experience_manager.get_injectable_l0_experiences()
                else:
                    recent_l0 = self.hierarchical_experience_manager.get_recent_injectable_l0_experiences(
                        hierarchy_config.export_max_l0
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
        if output_path is None:
            config_filename = f"{self.config.exp_id}_agent.yaml"
            config_dir = str(DIR_ROOT / "configs" / "agents" / "practice")
            full_path = os.path.join(config_dir, os.path.basename(config_filename))
        else:
            full_path = os.path.abspath(os.fspath(output_path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(config_header + yaml_config)
        return full_path
