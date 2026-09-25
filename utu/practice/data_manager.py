import hashlib
import json
import os
import random
import time
from typing import Any, Literal

from sqlmodel import select

from ..config import EvalConfig
from ..db import DatasetSample, EvaluationSample
from ..eval import DBDataManager
from ..utils import SQLModelUtils, get_logger
from .mistake_bank import MistakeBank

logger = get_logger(__name__)

PRACTICE_DATA_LAYOUT_META_KEY = "_utu_practice_data_layout"
PRACTICE_DATA_LAYOUT_SCHEMA_VERSION = 1


class TrainingFreeGRPODataManager(DBDataManager):
    """Data manager for training-free GRPO data.

    This class extends DBDataManager to handle training-free GRPO-specific data loading. Inludes
    the ability to duplicate samples based on pass_k configuration, shuffle epoch data,
    load batch data, etc.
    """

    def __init__(
        self,
        config: EvalConfig,
        *,
        mistake_focus_ratio: float | None = None,
        data_seed: int = 42,
        data_layout_context: dict[str, Any] | None = None,
        allow_legacy_epoch_cache: bool = False,
    ) -> None:
        super().__init__(config)
        if mistake_focus_ratio is None:
            # Compatibility for direct/legacy DataManager construction. The
            # TrainingFreeGRPO runtime always passes its typed, resolved value.
            raw_ratio = os.getenv("UTU_MISTAKE_FOCUS_RATIO", "0.3")
            try:
                mistake_focus_ratio = float(raw_ratio)
            except (TypeError, ValueError):
                mistake_focus_ratio = 0.3
            mistake_focus_ratio = max(0.0, min(1.0, mistake_focus_ratio))
            if "UTU_MISTAKE_FOCUS_RATIO" in os.environ:
                logger.warning(
                    "Using legacy UTU_MISTAKE_FOCUS_RATIO=%s because no typed "
                    "mistake_focus_ratio was supplied",
                    mistake_focus_ratio,
                )
        if not 0.0 <= mistake_focus_ratio <= 1.0:
            raise ValueError("mistake_focus_ratio must be between 0 and 1")
        self.mistake_focus_ratio = float(mistake_focus_ratio)
        self.data_seed = int(data_seed)
        self.data_layout_context = dict(data_layout_context or {})
        self.allow_legacy_epoch_cache = bool(allow_legacy_epoch_cache)

    @staticmethod
    def _sha256(value: Any) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _source_dataset_fingerprint(cls, datapoints: list[DatasetSample]) -> str:
        records = [
            {
                "dataset": item.dataset,
                "index": item.index,
                "source": item.source,
                "question": item.question,
                "answer": item.answer,
                "level": item.level,
                "file_name": item.file_name,
                "meta": item.meta,
            }
            for item in datapoints
        ]
        records.sort(
            key=lambda item: (
                str(item["dataset"]),
                str(item["index"]),
                str(item["source"]),
                cls._sha256(item),
            )
        )
        return cls._sha256(records)

    @staticmethod
    def _selected_datapoint_identity(item: DatasetSample) -> dict[str, Any]:
        return {
            "dataset": item.dataset,
            "index": item.index,
            "source": item.source,
            "question": item.question,
            "answer": item.answer,
            "level": item.level,
            "file_name": item.file_name,
        }

    @staticmethod
    def _selected_sample_identity(item: EvaluationSample) -> dict[str, Any]:
        return {
            "dataset": item.dataset,
            "index": item.dataset_index,
            "source": item.source,
            "question": item.raw_question,
            "answer": item.correct_answer,
            "level": item.level,
            "file_name": item.file_name,
        }

    @classmethod
    def _selected_task_multiset_fingerprint(cls, identities: list[dict[str, Any]]) -> str:
        return cls._sha256(sorted(cls._sha256(identity) for identity in identities))

    def _layout_contract(
        self,
        *,
        epoch: int,
        shuffle: bool,
        truncate: int | None,
        datapoints: list[DatasetSample],
    ) -> dict[str, Any]:
        data_seed = int(getattr(self, "data_seed", 42))
        return {
            "schema_version": PRACTICE_DATA_LAYOUT_SCHEMA_VERSION,
            "dataset": self.config.data.dataset,
            "source_dataset_sha256": self._source_dataset_fingerprint(datapoints),
            "pass_k": self.config.pass_k,
            "epoch": epoch,
            "shuffle": bool(shuffle),
            "truncate": truncate,
            "data_seed": data_seed,
            "effective_epoch_seed": data_seed + epoch,
            "mistake_focus_ratio": float(getattr(self, "mistake_focus_ratio", 0.3)),
            **dict(getattr(self, "data_layout_context", {})),
        }

    @staticmethod
    def _meta_as_dict(meta: Any) -> dict[str, Any]:
        if isinstance(meta, dict):
            return dict(meta)
        if isinstance(meta, str):
            try:
                decoded = json.loads(meta)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                return decoded
        if meta is None:
            return {}
        return {"_utu_original_meta": meta}

    @classmethod
    def _meta_with_layout_marker(cls, meta: Any, marker: dict[str, Any]) -> dict[str, Any]:
        result = cls._meta_as_dict(meta)
        result[PRACTICE_DATA_LAYOUT_META_KEY] = marker
        return result

    def _validate_existing_epoch_rows(
        self,
        samples: list[EvaluationSample],
        *,
        contract: dict[str, Any],
        datapoints: list[DatasetSample],
        truncate: int | None,
    ) -> None:
        expected_fingerprint = self._sha256(contract)
        markers = [
            self._meta_as_dict(sample.meta).get(PRACTICE_DATA_LAYOUT_META_KEY)
            for sample in samples
        ]
        present_markers = [marker for marker in markers if isinstance(marker, dict)]
        if not present_markers:
            if not getattr(self, "allow_legacy_epoch_cache", False):
                raise RuntimeError(
                    "Existing practice epoch rows predate the data-layout contract. "
                    "Use a new exp_id, or use explicit hierarchy-prefix resume only for "
                    "a structurally compatible legacy recovery."
                )
            if any(sample.dataset != self.config.data.dataset for sample in samples):
                raise RuntimeError(
                    "Legacy practice epoch cache dataset does not match the configured dataset"
                )
            if not samples or len(samples) % self.config.pass_k != 0:
                raise RuntimeError(
                    "Legacy practice epoch cache row count is incompatible with configured pass_k"
                )
            expected_tasks = len(datapoints) if truncate is None else min(truncate, len(datapoints))
            if len(samples) != expected_tasks * self.config.pass_k:
                raise RuntimeError(
                    "Legacy practice epoch cache row count is incompatible with the configured "
                    f"dataset/truncate/pass_k contract: rows={len(samples)} "
                    f"expected={expected_tasks * self.config.pass_k}"
                )
            logger.warning(
                "Accepted legacy epoch rows without a data-layout fingerprint solely because "
                "hierarchy-prefix resume is enabled; dataset and row structure were verified"
            )
            return
        if len(present_markers) != len(samples):
            raise RuntimeError(
                "Practice epoch cache contains a mixture of fingerprinted and legacy rows"
            )

        marker_fingerprints = {marker.get("fingerprint") for marker in present_markers}
        marker_contracts = {self._sha256(marker.get("contract")) for marker in present_markers}
        marker_sample_counts = {marker.get("sample_count") for marker in present_markers}
        if marker_fingerprints != {expected_fingerprint} or marker_contracts != {
            self._sha256(contract)
        }:
            stored_contract = present_markers[0].get("contract")
            raise RuntimeError(
                "Practice epoch cache data-layout fingerprint mismatch. "
                f"stored={stored_contract!r} current={contract!r}. Use a new exp_id."
            )
        if marker_sample_counts != {len(samples)}:
            raise RuntimeError(
                "Practice epoch cache is incomplete or duplicated: stored sample_count="
                f"{sorted(str(value) for value in marker_sample_counts)} rows={len(samples)}"
            )

        by_position: dict[int, list[tuple[int, EvaluationSample]]] = {}
        for marker, sample in zip(present_markers, samples, strict=True):
            position = marker.get("selection_position")
            replica = marker.get("replica_index")
            if not isinstance(position, int) or position < 0:
                raise RuntimeError("Practice epoch cache row has invalid selection_position")
            if not isinstance(replica, int) or not 0 <= replica < self.config.pass_k:
                raise RuntimeError("Practice epoch cache row has invalid replica_index")
            by_position.setdefault(position, []).append((replica, sample))

        expected_positions = set(range(len(samples) // self.config.pass_k))
        if set(by_position) != expected_positions:
            raise RuntimeError("Practice epoch cache has missing or duplicate task positions")
        ordered_identities: list[dict[str, Any]] = []
        for position in sorted(by_position):
            replicas = sorted(by_position[position], key=lambda item: item[0])
            if [replica for replica, _ in replicas] != list(range(self.config.pass_k)):
                raise RuntimeError(
                    f"Practice epoch cache task position {position} has incomplete replicas"
                )
            identities = [self._selected_sample_identity(sample) for _, sample in replicas]
            if any(identity != identities[0] for identity in identities[1:]):
                raise RuntimeError(
                    f"Practice epoch cache task position {position} mixes different task rows"
                )
            ordered_identities.append(identities[0])

        actual_multiset = self._selected_task_multiset_fingerprint(ordered_identities)
        actual_order = self._sha256(ordered_identities)
        stored_multisets = {marker.get("selected_task_sha256") for marker in present_markers}
        stored_orders = {marker.get("selected_order_sha256") for marker in present_markers}
        if stored_multisets != {actual_multiset}:
            raise RuntimeError(
                "Practice epoch cache selected-task multiset fingerprint mismatch"
            )
        if stored_orders != {actual_order}:
            raise RuntimeError(
                "Practice epoch cache selected-task order fingerprint mismatch"
            )

    def load_epoch_data(self, epoch: int, shuffle: bool = True, truncate: int = None) -> list:
        """Load data for a specific epoch."""
        epoch_exp_id = f"{self.config.exp_id}_epoch_{epoch}"
        with SQLModelUtils.create_session() as session:
            # Load all datapoints from the dataset
            datapoints = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == self.config.data.dataset)
            ).all()
            logger.info(f"Loaded {len(datapoints)} samples from {self.config.data.dataset}.")

        contract = self._layout_contract(
            epoch=epoch,
            shuffle=shuffle,
            truncate=truncate,
            datapoints=datapoints,
        )
        if self._check_exp_id(epoch_exp_id):
            logger.warning(f"exp_id {epoch_exp_id} already exists in db")
            samples = self.get_batch_samples(epoch)
            self._validate_existing_epoch_rows(
                samples,
                contract=contract,
                datapoints=datapoints,
                truncate=truncate,
            )
            return samples

        desired_total = truncate if truncate is not None else len(datapoints)
        epoch_random = random.Random(int(getattr(self, "data_seed", 42)) + epoch)

        # Bias sampling towards recent/high-value failures from the mistake bank (if any).
        # If no mistake bank exists yet, this falls back to uniform sampling.
        bank = MistakeBank(exp_id=self.config.exp_id)
        bank.load()
        failed_records = {k: rec for k, rec in bank.records.items() if rec.status == "failed"}

        if failed_records and desired_total < len(datapoints):
            now_ts = time.time()
            priority = []
            rest = []
            for dp in datapoints:
                # index may be a string (e.g. "abc366_c") or an integer string ("42")
                dp_index = dp.index if dp.index is not None else 0
                key = MistakeBank.problem_key(dp.dataset, dp_index)
                (priority if key in failed_records else rest).append(dp)

            # High-value failures first (recent + low reward + repeated failures).
            priority.sort(
                key=lambda dp: bank.score_for_sampling(
                    failed_records[MistakeBank.problem_key(
                        dp.dataset,
                        dp.index if dp.index is not None else 0
                    )],
                    now_ts=now_ts,
                ),
                reverse=True,
            )
            if shuffle:
                epoch_random.shuffle(rest)

            # The resolved experiment config is authoritative. Direct
            # legacy DataManager callers may still populate this value
            # from UTU_MISTAKE_FOCUS_RATIO during construction.
            focus_ratio = float(getattr(self, "mistake_focus_ratio", 0.3))
            focus_n = int(desired_total * focus_ratio)

            sampled: list[DatasetSample] = []

            # Sample mistakes first (with replacement if needed).
            if focus_n > 0:
                if len(priority) >= focus_n:
                    sampled.extend(priority[:focus_n])
                else:
                    sampled.extend(priority)
                    while len(sampled) < focus_n and priority:
                        sampled.append(epoch_random.choice(priority))

            # Fill the rest from non-mistakes (without replacement).
            remaining_n = max(0, desired_total - len(sampled))
            if remaining_n > 0:
                sampled.extend(rest[:remaining_n])

            # If still short (rare), backfill from priority with replacement.
            while len(sampled) < desired_total and priority:
                sampled.append(epoch_random.choice(priority))

            datapoints = sampled[:desired_total]
            logger.info(
                f"Mistake-bank sampling enabled: focus_ratio={focus_ratio}, "
                f"selected={len(datapoints)}, priority_pool={len(priority)}, rest_pool={len(rest)}"
            )
        else:
            # Uniform sampling: shuffle first (to enable random sampling when truncating)
            if shuffle:
                epoch_random.shuffle(datapoints)
            datapoints = datapoints[:desired_total]

        selected_identities = [self._selected_datapoint_identity(item) for item in datapoints]
        marker = {
            "schema_version": PRACTICE_DATA_LAYOUT_SCHEMA_VERSION,
            "fingerprint": self._sha256(contract),
            "contract": contract,
            "selected_task_sha256": self._selected_task_multiset_fingerprint(
                selected_identities
            ),
            "selected_order_sha256": self._sha256(selected_identities),
            "sample_count": len(datapoints) * self.config.pass_k,
        }
        samples = []
        logger.info(f"Duplicate {self.config.pass_k} times for each sample.")
        # Create duplicates for each datapoint, keeping duplicates adjacent
        for selection_position, dp in enumerate(datapoints):
            for replica_index in range(self.config.pass_k):
                row_marker = {
                    **marker,
                    "selection_position": selection_position,
                    "replica_index": replica_index,
                }
                sample = EvaluationSample(
                    dataset=dp.dataset,
                    dataset_index=dp.index,
                    source=dp.source,
                    raw_question=dp.question,
                    level=dp.level,
                    correct_answer=dp.answer,
                    file_name=dp.file_name,
                    meta=self._meta_with_layout_marker(dp.meta, row_marker),
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
        layout_markers = [
            self._meta_as_dict(sample.meta).get(PRACTICE_DATA_LAYOUT_META_KEY)
            for sample in samples
        ]
        if layout_markers and all(isinstance(marker, dict) for marker in layout_markers):
            samples.sort(
                key=lambda sample: (
                    self._meta_as_dict(sample.meta)[PRACTICE_DATA_LAYOUT_META_KEY][
                        "selection_position"
                    ],
                    self._meta_as_dict(sample.meta)[PRACTICE_DATA_LAYOUT_META_KEY][
                        "replica_index"
                    ],
                )
            )
        elif any(isinstance(marker, dict) for marker in layout_markers):
            raise RuntimeError(
                "Practice epoch cache contains a mixture of ordered and legacy rows"
            )
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
