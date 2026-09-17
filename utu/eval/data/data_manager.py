import abc
import hashlib
import json
from typing import Literal

from sqlmodel import select

from ...config import EvalConfig
from ...db import DatasetSample, EvaluationSample
from ...utils import SQLModelUtils, get_logger

logger = get_logger(__name__)

EvaluationStage = Literal["init", "rollout", "judged", "infra_error"]


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _task_key(sample: DatasetSample | EvaluationSample) -> str:
    """Return the protocol identity used to order both source and trial rows."""

    meta = sample.meta
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    raw_id = meta.get("task_id") if isinstance(meta, dict) else None
    if raw_id is None:
        raw_id = sample.index if isinstance(sample, DatasetSample) else sample.dataset_index
    return f"{sample.dataset}:{raw_id}"


def _trial_index(sample: EvaluationSample) -> int:
    meta = sample.meta
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            return 0
    if isinstance(meta, dict):
        value = meta.get("trial_index", 0)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


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

    def _task_order_rank(self) -> dict[str, int] | None:
        order = self.config.data.task_order
        if order is None:
            return None
        if not order or len(order) != len(set(order)):
            raise ValueError("Evaluation task_order must be non-empty and contain unique task IDs")
        expected_hash = self.config.data.task_order_sha256
        if not expected_hash or _canonical_sha256(order) != expected_hash:
            raise ValueError("Evaluation task_order does not match task_order_sha256")
        return {task_id: index for index, task_id in enumerate(order)}

    def _order_datapoints(self, datapoints: list[DatasetSample]) -> list[DatasetSample]:
        rank = self._task_order_rank()
        if rank is None:
            # Do not rely on an implementation-defined SQL row order.
            return sorted(datapoints, key=lambda item: (item.index is None, item.index))
        keys = [_task_key(item) for item in datapoints]
        if len(keys) != len(set(keys)):
            raise ValueError("Evaluation dataset contains duplicate protocol task IDs")
        actual = set(keys)
        expected = set(rank)
        if actual != expected:
            raise ValueError(
                "Evaluation dataset differs from signed task_order: "
                f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
            )
        return sorted(datapoints, key=lambda item: rank[_task_key(item)])

    def _order_evaluation_samples(
        self, samples: list[EvaluationSample]
    ) -> list[EvaluationSample]:
        rank = self._task_order_rank()
        if rank is None:
            return samples
        unexpected = sorted({_task_key(item) for item in samples} - set(rank))
        if unexpected:
            raise ValueError(f"Stored evaluation rows contain tasks outside signed task_order: {unexpected}")
        return sorted(
            samples,
            key=lambda item: (rank[_task_key(item)], _trial_index(item), str(item.id or "")),
        )

    def load(self) -> list[EvaluationSample]:
        if self._check_exp_id():
            logger.warning(f"exp_id {self.config.exp_id} already exists in db")
            return self.get_samples()

        with SQLModelUtils.create_session() as session:
            datapoints = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == self.config.data.dataset)
            ).all()
            datapoints = self._order_datapoints(list(datapoints))
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
                    if self.config.data.protocol_metadata:
                        if not isinstance(trial_meta, dict):
                            trial_meta = {"source_meta": trial_meta}
                        trial_meta.update(self.config.data.protocol_metadata)
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
            return self._order_evaluation_samples(list(samples))

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
