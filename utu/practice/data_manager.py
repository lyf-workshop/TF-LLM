import random
import os
import time
from typing import Literal

from sqlmodel import select

from ..config import EvalConfig
from ..db import DatasetSample, EvaluationSample
from ..eval import DBDataManager
from ..utils import SQLModelUtils, get_logger
from .mistake_bank import MistakeBank

logger = get_logger(__name__)
random.seed(42)


class TrainingFreeGRPODataManager(DBDataManager):
    """Data manager for training-free GRPO data.

    This class extends DBDataManager to handle training-free GRPO-specific data loading. Inludes
    the ability to duplicate samples based on pass_k configuration, shuffle epoch data,
    load batch data, etc.
    """

    def __init__(self, config: EvalConfig) -> None:
        super().__init__(config)

    def load_epoch_data(self, epoch: int, shuffle: bool = True, truncate: int = None) -> list:
        """Load data for a specific epoch."""
        epoch_exp_id = f"{self.config.exp_id}_epoch_{epoch}"
        # check if epoch data exists
        if self._check_exp_id(epoch_exp_id):
            logger.warning(f"exp_id {epoch_exp_id} already exists in db")
            return self.get_batch_samples(epoch)

        with SQLModelUtils.create_session() as session:
            # Load all datapoints from the dataset
            datapoints = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == self.config.data.dataset)
            ).all()
            logger.info(f"Loaded {len(datapoints)} samples from {self.config.data.dataset}.")

            desired_total = truncate or len(datapoints)

            # Bias sampling towards recent/high-value failures from the mistake bank (if any).
            # If no mistake bank exists yet, this falls back to uniform sampling.
            bank = MistakeBank(exp_id=self.config.exp_id)
            bank.load()
            failed_records = {k: rec for k, rec in bank.records.items() if rec.status == "failed"}

            if failed_records:
                now_ts = time.time()
                priority = []
                rest = []
                for dp in datapoints:
                    key = MistakeBank.problem_key(dp.dataset, int(dp.index))
                    (priority if key in failed_records else rest).append(dp)

                # High-value failures first (recent + low reward + repeated failures).
                priority.sort(
                    key=lambda dp: bank.score_for_sampling(
                        failed_records[MistakeBank.problem_key(dp.dataset, int(dp.index))],
                        now_ts=now_ts,
                    ),
                    reverse=True,
                )
                if shuffle:
                    random.shuffle(rest)

                # How much of the epoch should focus on mistakes (0.0~1.0).
                # Default: 0.3 (only effective once a mistake bank exists).
                try:
                    focus_ratio = float(os.getenv("UTU_MISTAKE_FOCUS_RATIO", "0.3"))
                except Exception:
                    focus_ratio = 0.3
                focus_ratio = max(0.0, min(1.0, focus_ratio))
                focus_n = int(desired_total * focus_ratio)

                sampled: list[DatasetSample] = []

                # Sample mistakes first (with replacement if needed).
                if focus_n > 0:
                    if len(priority) >= focus_n:
                        sampled.extend(priority[:focus_n])
                    else:
                        sampled.extend(priority)
                        while len(sampled) < focus_n and priority:
                            sampled.append(random.choice(priority))

                # Fill the rest from non-mistakes (without replacement).
                remaining_n = max(0, desired_total - len(sampled))
                if remaining_n > 0:
                    sampled.extend(rest[:remaining_n])

                # If still short (rare), backfill from priority with replacement.
                while len(sampled) < desired_total and priority:
                    sampled.append(random.choice(priority))

                datapoints = sampled[:desired_total]
                logger.info(
                    f"Mistake-bank sampling enabled: focus_ratio={focus_ratio}, "
                    f"selected={len(datapoints)}, priority_pool={len(priority)}, rest_pool={len(rest)}"
                )
            else:
                # Uniform sampling: shuffle first (to enable random sampling when truncating)
                if shuffle:
                    random.shuffle(datapoints)
                datapoints = datapoints[:desired_total]

            samples = []
            logger.info(f"Duplicate {self.config.pass_k} times for each sample.")
            # Create duplicates for each datapoint, keeping duplicates adjacent
            for dp in datapoints:
                for _ in range(self.config.pass_k):
                    sample = EvaluationSample(
                        dataset=dp.dataset,
                        dataset_index=dp.index,
                        source=dp.source,
                        raw_question=dp.question,
                        level=dp.level,
                        correct_answer=dp.answer,
                        file_name=dp.file_name,
                        meta=dp.meta,
                        exp_id=epoch_exp_id,  # add exp_id
                    )
                    samples.append(sample)
            logger.info(f"Created {len(samples)} samples for exp_id {epoch_exp_id} with duplicates kept adjacent.")
            self.data = samples
            self.save(self.data)  # save to db
            return self.data

    def get_batch_samples(
        self,
        epoch: int,
        stage: Literal["init", "rollout", "judged"] = None,
        limit: int = None,
        batch_size: int = 64,
        batch_idx: int | None = None,
    ) -> list[EvaluationSample]:
        """Get samples for a specific batch."""
        exp_id = f"{self.config.exp_id}_epoch_{epoch}"
        with SQLModelUtils.create_session() as session:
            samples = session.exec(
                select(EvaluationSample)
                .where(
                    EvaluationSample.exp_id == exp_id,
                )
                .order_by(EvaluationSample.dataset_index)
                .limit(limit)
            ).all()
            # Explicitly access meta field to ensure it's loaded before session closes
            for sample in samples:
                _ = sample.meta
        if batch_idx is not None:
            batch_size = self.config.pass_k * batch_size
            start_idx = batch_idx * batch_size
            end_idx = start_idx + batch_size
            samples = samples[start_idx:end_idx]
        # select by stage
        if stage:
            samples = [s for s in samples if s.stage == stage]
        return samples

    def _check_exp_id(self, exp_id: str) -> bool:
        # check if any record has the same exp_id
        with SQLModelUtils.create_session() as session:
            has_exp_id = session.exec(select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)).first()
        return has_exp_id is not None

    def check_dataset(self, dataset: str) -> bool:
        """Check if any record exists for the given dataset."""
        with SQLModelUtils.create_session() as session:
            has_exp_id = session.exec(select(DatasetSample).where(DatasetSample.dataset == dataset)).first()
        return has_exp_id is not None
