import abc
import json
from typing import Literal

from sqlmodel import select

from ...config import EvalConfig
from ...db import DatasetSample, EvaluationSample
from ...utils import SQLModelUtils, get_logger

logger = get_logger(__name__)

EvaluationStage = Literal["init", "rollout", "judged", "infra_error"]


class BaseDataManager(abc.ABC):
    """Base data manager for loading and saving data."""

    data: list[EvaluationSample]

    def __init__(self, config: EvalConfig) -> None:
        self.config = config
        # EvalConfig.db_url is authoritative. Previously the data manager
        # ignored it and always used the process environment's URL.
        SQLModelUtils.configure(config.db_url)

    @abc.abstractmethod
    def load(self) -> list[EvaluationSample]:
        """Load the dataset."""
        raise NotImplementedError

    @abc.abstractmethod
    def save(self, **kwargs) -> None:
        """Save the dataset."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_samples(self, stage: EvaluationStage | None = None) -> list[EvaluationSample]:
        """Get samples of specified stage from the dataset."""
        raise NotImplementedError


class DBDataManager(BaseDataManager):
    """Database data manager for loading and saving data."""

    def __init__(self, config: EvalConfig) -> None:
        super().__init__(config)

    def load(self) -> list[EvaluationSample]:
        if self._check_exp_id():
            logger.warning(f"exp_id {self.config.exp_id} already exists in db")
            return self.get_samples()

        with SQLModelUtils.create_session() as session:
            datapoints = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == self.config.data.dataset)
            ).all()
            logger.info(f"Loaded {len(datapoints)} samples from {self.config.data.dataset}.")
            samples = []
            logger.info(f"Duplicate {self.config.pass_k} times for each sample.")
            skillsbench_cfg = getattr(self.config, "skillsbench", None)
            is_skillsbench_v4 = bool(
                skillsbench_cfg and getattr(skillsbench_cfg, "enabled", False)
            )
            expected_num_tasks = (
                getattr(skillsbench_cfg, "expected_num_tasks", None) or len(datapoints)
            )
            for dp in datapoints:
                for trial_index in range(self.config.pass_k):
                    source_meta = dp.meta
                    if isinstance(source_meta, str):
                        try:
                            source_meta = json.loads(source_meta)
                        except json.JSONDecodeError:
                            pass
                    if isinstance(source_meta, dict):
                        trial_meta = {**source_meta, "trial_index": trial_index}
                    elif dp.meta is None:
                        trial_meta = {"trial_index": trial_index}
                    else:
                        trial_meta = source_meta
                    if is_skillsbench_v4:
                        if not isinstance(trial_meta, dict):
                            trial_meta = {"source_meta": trial_meta}
                        trial_meta.update(
                            evaluation_protocol="skillsbench_v4",
                            eval_status="pending",
                            trial_index=trial_index,
                            expected_num_tasks=int(expected_num_tasks),
                            expected_trials_per_task=int(self.config.pass_k),
                        )
                    sample = EvaluationSample(
                        dataset=dp.dataset,
                        dataset_index=dp.index,
                        source=dp.source,
                        raw_question=dp.question,
                        level=dp.level,
                        correct_answer=dp.answer,
                        file_name=dp.file_name,
                        meta=trial_meta,
                        exp_id=self.config.exp_id,  # add exp_id
                    )
                    samples.append(sample)
            logger.info(f"Created {len(samples)} samples for exp_id {self.config.exp_id}.")

            self.data = samples
            self.save(self.data)  # save to db
            return self.data

    def get_samples(
        self, stage: EvaluationStage | None = None, limit: int = None
    ) -> list[EvaluationSample]:
        """Get samples from exp_id with specified stage."""
        with SQLModelUtils.create_session() as session:
            samples = session.exec(
                select(EvaluationSample)
                .where(
                    EvaluationSample.exp_id == self.config.exp_id,
                    EvaluationSample.stage == stage if stage else True,
                )
                .order_by(EvaluationSample.dataset_index)
                .limit(limit)
            ).all()
            # Explicitly access meta field to ensure it's loaded before session closes
            for sample in samples:
                _ = sample.meta
            return samples

    def save(self, samples: list[EvaluationSample] | EvaluationSample) -> None:
        """Update or add sample(s) to db."""
        if isinstance(samples, list):
            with SQLModelUtils.create_session() as session:
                for sample in samples:
                    session.merge(sample)  # merge instead of add to properly update existing objects
                session.commit()
        else:
            with SQLModelUtils.create_session() as session:
                session.merge(samples)  # merge instead of add to properly update existing objects
                session.commit()

    def delete_samples(self, samples: list[EvaluationSample] | EvaluationSample) -> None:
        """Delete sample(s) from db."""
        if isinstance(samples, list):
            with SQLModelUtils.create_session() as session:
                for sample in samples:
                    session.delete(sample)
                session.commit()
        else:
            with SQLModelUtils.create_session() as session:
                session.delete(samples)
                session.commit()

    def _check_exp_id(self) -> bool:
        # check if any record has the same exp_id
        with SQLModelUtils.create_session() as session:
            has_exp_id = session.exec(
                select(EvaluationSample).where(EvaluationSample.exp_id == self.config.exp_id)
            ).first()
        return has_exp_id is not None
