import abc
import hashlib
import json
from pathlib import Path
from typing import Literal

from sqlmodel import select

from ...config import EvalConfig
from ...db import DatasetSample, EvaluationSample
from ...utils import SQLModelUtils, get_logger, redact_sensitive_data

logger = get_logger(__name__)

EvaluationStage = Literal["init", "rollout", "judged", "infra_error"]

EVALUATION_IDENTITY_SCHEMA = "tf-llm-eval-cache-v1"
EVALUATION_IDENTITY_KEY = "evaluation_identity_sha256"
DATASET_SNAPSHOT_KEY = "evaluation_dataset_sha256"
IDENTITY_SCHEMA_KEY = "evaluation_identity_schema"


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalise_meta(value: object) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"source_meta": value}
        if isinstance(parsed, dict):
            return parsed
    if value is None:
        return {}
    return {"source_meta": value}


def _experience_source_sha256(config: EvalConfig) -> str | None:
    # PracticeRuntimeConfig intentionally removes evaluation-only experience
    # filtering.  Treat the absent filter as disabled instead of forcing
    # practice to carry a dead duplicate field.
    filter_config = getattr(config, "experience_filter", None)
    if filter_config is None:
        return None
    if not filter_config.enabled or not filter_config.experience_source:
        return None
    source_path = Path(filter_config.experience_source)
    if not source_path.is_file():
        raise FileNotFoundError(
            "Configured experience_source does not exist or is not a file: "
            f"{source_path}. Refusing to create or reuse evaluation rows."
        )
    return hashlib.sha256(source_path.read_bytes()).hexdigest()


def _endpoint_fingerprints(value: object, path: tuple[str, ...] = ()) -> dict[str, str]:
    """Hash model endpoints without persisting their potentially sensitive URLs."""

    if isinstance(value, dict):
        result: dict[str, str] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized = key_text.lower().replace("-", "_")
            item_path = (*path, key_text)
            if normalized == "base_url" or normalized.endswith("_base_url"):
                if item is not None:
                    result[".".join(item_path)] = hashlib.sha256(
                        str(item).encode("utf-8")
                    ).hexdigest()
            else:
                result.update(_endpoint_fingerprints(item, item_path))
        return result
    if isinstance(value, (list, tuple)):
        result = {}
        for index, item in enumerate(value):
            result.update(_endpoint_fingerprints(item, (*path, str(index))))
        return result
    return {}


def evaluation_identity_sha256(config: EvalConfig) -> str:
    """Hash every result-affecting evaluation option plus experience content.

    Operational identifiers and parallelism are deliberately excluded: they
    do not change the requested samples or model behaviour.  Secrets are
    redacted before hashing so rotating an API key does not invalidate a run.
    """

    payload = config.model_dump(mode="python")
    for field in (
        "exp_id",
        "db_url",
        "concurrency",
        "judge_concurrency",
        "log_trajectory_to_db",
        "allow_legacy_cache_reuse",
    ):
        payload.pop(field, None)
    payload["runtime_endpoint_sha256_by_path"] = _endpoint_fingerprints(payload)
    payload["experience_source_sha256"] = _experience_source_sha256(config)
    return _canonical_sha256(redact_sensitive_data(payload))


def dataset_snapshot_sha256(datapoints: list[DatasetSample]) -> str:
    """Hash the exact source rows used to seed an evaluation run."""

    return _canonical_sha256(
        [
            {
                "dataset": row.dataset,
                "index": row.index,
                "source": row.source,
                "source_index": row.source_index,
                "question": row.question,
                "answer": row.answer,
                "level": row.level,
                "file_name": row.file_name,
                "meta": row.meta,
            }
            for row in datapoints
        ]
    )


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
        with SQLModelUtils.create_session() as session:
            datapoints = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == self.config.data.dataset)
            ).all()
            datapoints = self._order_datapoints(list(datapoints))
            logger.info(f"Loaded {len(datapoints)} samples from {self.config.data.dataset}.")
            identity_sha256 = evaluation_identity_sha256(self.config)
            dataset_sha256 = dataset_snapshot_sha256(datapoints)

            if self._check_exp_id():
                logger.warning(f"exp_id {self.config.exp_id} already exists in db")
                samples = self.get_samples()
                self._validate_cached_samples(
                    samples,
                    datapoints=datapoints,
                    identity_sha256=identity_sha256,
                    dataset_sha256=dataset_sha256,
                )
                return samples

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
                    trial_meta = {
                        **_normalise_meta(dp.meta),
                        "trial_index": trial_index,
                        IDENTITY_SCHEMA_KEY: EVALUATION_IDENTITY_SCHEMA,
                        EVALUATION_IDENTITY_KEY: identity_sha256,
                        DATASET_SNAPSHOT_KEY: dataset_sha256,
                    }
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

    def _validate_cached_samples(
        self,
        samples: list[EvaluationSample],
        *,
        datapoints: list[DatasetSample],
        identity_sha256: str,
        dataset_sha256: str,
    ) -> None:
        """Reject an exp_id whose persisted contract differs from this run."""

        if not samples:
            raise ValueError(
                f"exp_id {self.config.exp_id!r} exists but has no readable evaluation rows"
            )
        metas = [_normalise_meta(sample.meta) for sample in samples]
        stored_identities = {meta.get(EVALUATION_IDENTITY_KEY) for meta in metas}
        stored_datasets = {meta.get(DATASET_SNAPSHOT_KEY) for meta in metas}
        stored_schemas = {meta.get(IDENTITY_SCHEMA_KEY) for meta in metas}
        has_complete_fingerprint = (
            None not in stored_identities
            and None not in stored_datasets
            and stored_schemas == {EVALUATION_IDENTITY_SCHEMA}
        )

        if has_complete_fingerprint:
            if stored_identities != {identity_sha256}:
                raise ValueError(
                    f"exp_id {self.config.exp_id!r} was created with a different evaluation "
                    "config/model/prompt/pass_k/experience snapshot. Use a new exp_id."
                )
            if stored_datasets != {dataset_sha256}:
                raise ValueError(
                    f"exp_id {self.config.exp_id!r} was created from a different dataset "
                    "snapshot. Use a new exp_id."
                )
        elif self._matches_signed_protocol(metas):
            logger.warning(
                "Resuming legacy rows validated by the signed experiment protocol; "
                "generic cache fingerprints were not present."
            )
        elif not self.config.allow_legacy_cache_reuse:
            raise ValueError(
                f"exp_id {self.config.exp_id!r} contains legacy rows without an evaluation "
                "fingerprint. Refusing silent reuse because the original model/prompt/config "
                "cannot be verified. Use a new exp_id, or explicitly set "
                "allow_legacy_cache_reuse=true for a one-off legacy recovery."
            )
        else:
            logger.warning(
                "Explicitly reusing legacy exp_id %s without a verifiable model/prompt "
                "fingerprint.",
                self.config.exp_id,
            )

        expected_rows = len(datapoints) * self.config.pass_k
        if len(samples) != expected_rows:
            raise ValueError(
                f"Cached exp_id {self.config.exp_id!r} has {len(samples)} rows, expected "
                f"{expected_rows} for dataset={self.config.data.dataset!r}, pass_k={self.config.pass_k}."
            )
        if {sample.dataset for sample in samples} != {self.config.data.dataset}:
            raise ValueError(
                f"Cached exp_id {self.config.exp_id!r} belongs to a different dataset"
            )
        expected_pairs = {
            (row.index, trial_index)
            for row in datapoints
            for trial_index in range(self.config.pass_k)
        }
        actual_pairs = {(row.dataset_index, _trial_index(row)) for row in samples}
        if actual_pairs != expected_pairs or len(actual_pairs) != len(samples):
            raise ValueError(
                f"Cached exp_id {self.config.exp_id!r} has missing or duplicate "
                "dataset_index/trial_index rows. Use a new exp_id."
            )

    def _matches_signed_protocol(self, metas: list[dict]) -> bool:
        expected = self.config.data.protocol_metadata or {}
        if not expected.get("experiment_protocol_sha256"):
            return False
        return all(all(meta.get(key) == value for key, value in expected.items()) for meta in metas)

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
                merged_rows = []
                for sample in samples:
                    merged_rows.append(session.merge(sample))
                session.commit()
                # merge() returns a managed copy and leaves a transient input
                # unchanged. Propagate generated IDs so subsequent saves
                # update these rows instead of inserting duplicates.
                for original, merged in zip(samples, merged_rows, strict=True):
                    session.refresh(merged)
                    original.id = merged.id
        else:
            with SQLModelUtils.create_session() as session:
                merged = session.merge(samples)
                session.commit()
                session.refresh(merged)
                samples.id = merged.id

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
