"""Batch benchmark for practice with sample batching support."""

import asyncio
import json

from agents import custom_span
from agents.exceptions import MaxTurnsExceeded
from tqdm import tqdm

from ..config import ConfigLoader, EvalConfig
from ..eval.benchmarks.base_benchmark import BaseBenchmark
from ..eval.data import EvaluationSample
from ..skillsbench_reliability import FatalSkillsBenchError
from ..utils import get_logger
from .data_manager import TrainingFreeGRPODataManager
from .mistake_bank import MistakeBank
from .utils import TaskRecorder

logger = get_logger(__name__, "INFO")


class RolloutManager(BaseBenchmark):
    """Rollout manager that supports processing samples in batches.

    This class extends BaseBenchmark to support batch processing of samples.
    It splits samples into batches during initialization and allows processing
    specific batches through the batch_idx parameter.

    Attributes:
        batch_size (int): Size of each batch
        batches (list[list[EvaluationSample]]): List of sample batches
        num_batches (int): Total number of batches
    """

    dataset: TrainingFreeGRPODataManager
    curr_epoch: int
    batch_size: int

    def __init__(
        self,
        config: EvalConfig,
        batch_size: int,
        task_timeout: int = 3600,
        max_retries: int = 2,
        mistake_focus_ratio: float | None = None,
        data_seed: int = 42,
        data_layout_context: dict | None = None,
        allow_legacy_epoch_cache: bool = False,
    ) -> None:
        """Initialize RolloutManager with batching support."""
        # config
        if isinstance(config, str):
            config = ConfigLoader.load_eval_config(name=config)
        self.config = config
        # rollout
        if max_retries < 1:
            raise ValueError("max_retries must include at least the initial rollout attempt")
        self.task_timeout = task_timeout
        self.max_retries = max_retries
        # BaseBenchmark.__init__ is intentionally not used because practice
        # owns a different data manager.  Keep its mutable runtime state
        # instance-local nevertheless; otherwise judge processors leak across
        # runs through BaseBenchmark's compatibility class attribute.
        self._source_to_processer = {}
        self.experience_filter = None

        # dataset
        self.dataset = TrainingFreeGRPODataManager(
            config,
            mistake_focus_ratio=mistake_focus_ratio,
            data_seed=data_seed,
            data_layout_context=data_layout_context,
            allow_legacy_epoch_cache=allow_legacy_epoch_cache,
        )
        self.batch_size = batch_size

    def has_epoch_data(self, epoch: int) -> bool:
        """Return whether the immutable DB rows for an epoch already exist."""

        return self.dataset._check_exp_id(f"{self.config.exp_id}_epoch_{epoch}")

    def get_committed_batch_for_resume(self, batch_idx: int) -> list[EvaluationSample]:
        """Read and validate one already judged batch without preprocessing it."""

        samples = self._get_batch_samples(batch_idx=batch_idx)
        expected = self.batch_size * self.config.pass_k
        if len(samples) != expected:
            raise RuntimeError(
                "Cannot resume from hierarchy: DB batch is incomplete for "
                f"epoch={self.curr_epoch} batch={batch_idx}: rows={len(samples)} expected={expected}"
            )
        invalid_stages = sorted({str(sample.stage) for sample in samples if sample.stage != "judged"})
        if invalid_stages:
            raise RuntimeError(
                "Cannot resume from hierarchy: committed checkpoint batch contains non-judged "
                f"rows for epoch={self.curr_epoch} batch={batch_idx}: {invalid_stages}"
            )
        return samples

    def load_epoch_data(self, epoch: int, shuffle: bool = True, truncate: int = None) -> None:
        """Prepare data for a specific epoch."""
        epoch_data = self.dataset.load_epoch_data(epoch, shuffle=shuffle, truncate=truncate)
        self.curr_epoch = epoch
        return epoch_data

    async def main(
        self, batch_idx: int | None = None, recorder: TaskRecorder | None = None, use_cache: bool = True
    ) -> tuple[list[EvaluationSample], dict]:
        """Run the full evaluation pipeline for a specific batch or all batches.

        Args:
            batch_idx (int, optional): Index of the batch to process. If None, processes all batches.
            recorder (TaskRecorder, optional): Recorder to record the task progress.
            use_cache (bool, optional): Whether to use cached results. Defaults to True.
        """
        try:
            return await self._run_batch(batch_idx, recorder, use_cache)
        finally:
            logger.info("> Cleaning up...")
            await self.cleanup()

    async def _run_batch(
        self, batch_idx: int | None, recorder: TaskRecorder | None = None, use_cache: bool = True
    ) -> tuple[list[EvaluationSample], dict]:
        """Run the complete pipeline for a specific batch."""
        logger.info(f"> Running batch {batch_idx}...")

        # Run the pipeline phases
        self.preprocess_batch(batch_idx, recorder, use_cache)
        with custom_span("Rollout batch samples"):
            await self.rollout_batch(batch_idx)
        with custom_span("Judge batch samples"):
            await self.judge_batch(batch_idx)
        logger.info(f"> Running stat for batch {batch_idx}...")
        stat = await self.stat_batch(batch_idx)

        # return rollouts that have been judged in this batch
        rollouts = self._get_batch_samples(batch_idx=batch_idx, stage="judged")
        return rollouts, stat[0]["metrics"]

    def preprocess_batch(
        self, batch_idx: int | None, recorder: TaskRecorder | None = None, use_cache: bool = True
    ) -> list[EvaluationSample]:
        """Preprocess samples in a specific batch."""
        # Filter samples that are in 'init' stage
        samples_to_process = self._get_batch_samples(
            batch_idx=batch_idx,
            # if use_cache, only preprocess samples not yet preprocessed, otherwise preprocess all samples
            stage="init" if use_cache else None,
        )
        logger.info(f"Preprocessing {len(samples_to_process)} samples in batch...")

        results = []
        for sample in tqdm(samples_to_process, desc="Preprocessing batch"):
            processed_sample = self.preprocess_one(sample, recorder)
            if processed_sample is not None:
                results.append(processed_sample)
        logger.info(f"Successfully preprocessed {len(results)} samples in batch. Updated to db.")
        return results

    def preprocess_one(self, sample: EvaluationSample, recorder: TaskRecorder | None = None) -> EvaluationSample:
        processer = self._get_processer(sample.source)
        processed_sample = processer.preprocess_one(sample, recorder)
        if processed_sample is None:
            return None

        # Use processed_sample (which has updates from processer) instead of original sample
        processed_sample.update(
            # make sure stage is set to 'init' after preprocessing, for resuming purposes
            stage="init",
        )

        self.dataset.save(processed_sample)
        return processed_sample

    async def rollout_batch(self, batch_idx: int | None = None) -> list[EvaluationSample]:
        """Rollout samples in a specific batch."""
        # Filter samples that are in 'init' stage (ready for rollout)
        samples_to_process = self._get_batch_samples(batch_idx=batch_idx, stage="init")
        logger.info(f"Rolling out {len(samples_to_process)} samples in batch...")

        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def rollout_with_semaphore(item: EvaluationSample):
            async with semaphore:
                last_error: BaseException | None = None
                for attempt in range(self.max_retries):
                    try:
                        # Apply timeout to rollout_one call
                        result = await asyncio.wait_for(self.rollout_one(item), timeout=self.task_timeout)
                        return result
                    except FatalSkillsBenchError:
                        # Configuration failures (invalid credentials, exhausted
                        # quota, unsupported endpoint, etc.) affect the whole run.
                        # Retrying them per sample only creates more invalid trials.
                        raise
                    except MaxTurnsExceeded as exc:
                        # More turns cannot repair a deterministic agent-loop
                        # failure; retrying it only holds a concurrency slot.
                        logger.warning("Rollout stopped without retry after max turns: %s", exc)
                        return None
                    except TimeoutError as error:
                        last_error = error
                        logger.warning(
                            f"Rollout timeout ({self.task_timeout}s) on attempt {attempt + 1}/{self.max_retries}"
                        )
                    except Exception as e:  # pylint: disable=broad-except
                        last_error = e
                        logger.warning(f"Rollout error on attempt {attempt + 1}/{self.max_retries} for sample: {e}")
                # All retries failed
                logger.error(
                    f">>>>>>>>>>>>>\nRollout failed after {self.max_retries} attempts "
                    f"for sample '{item.raw_question}': {last_error!r}\n<<<<<<<<<<<<",
                )
                return None

        tasks = [asyncio.create_task(rollout_with_semaphore(item)) for item in samples_to_process]
        results = []
        try:
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Rolling out batch"):
                result = await task
                if result is not None:
                    results.append(result)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        logger.info(f"Successfully rolled out {len(results)} samples in batch. Updated to db.")
        return results

    async def judge_batch(self, batch_idx: int | None = None) -> list[EvaluationSample]:
        """Judge samples in a specific batch."""
        # Filter samples that are in 'rollout' stage (ready for judging)
        samples_to_process = self._get_batch_samples(batch_idx=batch_idx, stage="rollout")
        logger.info(f"Judging {len(samples_to_process)} samples in batch...")

        semaphore = asyncio.Semaphore(self.config.judge_concurrency)

        async def judge_with_semaphore(item: EvaluationSample):
            async with semaphore:
                try:
                    return await self.judge_one(item)
                except Exception as e:  # pylint: disable=broad-except
                    logger.error(f">>>>>>>>>>>>>\nError judging sample '{item}': {e}\n<<<<<<<<<<<<<", exc_info=True)
                    return None

        tasks = [asyncio.create_task(judge_with_semaphore(item)) for item in samples_to_process]
        results = []
        try:
            for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Judging batch"):
                result = await task
                if result is not None:
                    results.append(result)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        # Update mistake bank based on judged results (for curriculum-like sampling in next epoch).
        try:
            bank = MistakeBank(exp_id=self.config.exp_id)
            bank.update_from_judged_samples(results)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f"Failed to update mistake bank: {e}")

        logger.info(f"Successfully judged {len(results)} samples in batch. Updated to db.")
        return results

    async def stat_batch(self, batch_idx: int | None = None) -> list[dict]:
        """Generate statistics for samples in a specific batch."""
        # Filter samples that are in 'judged' stage
        judged_samples = self._get_batch_samples(batch_idx=batch_idx, stage="judged")
        logger.info(f"Generating stats from {len(judged_samples)} samples in batch:")

        data_by_benchmark = self._group_data_by_benchmark(judged_samples)
        overall_results: list[dict] = []
        for benchmark, data in data_by_benchmark.items():
            evaluator = self._get_processer(benchmark)
            result = await evaluator.stat(data)
            overall_results.append(result)

        logger.info(json.dumps(overall_results, indent=4, ensure_ascii=False))
        return overall_results

    def _get_batch_samples(self, batch_idx: int | None = None, stage: str = None) -> list[EvaluationSample]:
        """Get samples for a specific batch."""
        samples = self.dataset.get_batch_samples(
            epoch=self.curr_epoch,
            batch_idx=batch_idx,  # if None, return all samples
            stage=stage,
            batch_size=self.batch_size,
        )
        return samples
