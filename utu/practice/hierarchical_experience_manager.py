"""Restart-safe L0/L1/L2 experience aggregation with deterministic clustering."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from jinja2 import Template
from pydantic import ValidationError

from ..config import AgentConfig
from ..utils import DIR_ROOT, FileUtils, SimplifiedAsyncOpenAI, get_logger
from .experience_clusterer import (
    ClusteringReport,
    EmbeddingProvider,
    ExperienceCluster,
    ExperienceClusterer,
    HashingEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    detect_strategy_conflicts,
)
from .experience_models import (
    AggregatedExperienceContent,
    AggregationConflict,
    ExperienceLevel,
    ExperienceRecord,
    stable_experience_id,
)

logger = get_logger(__name__)

SCHEMA_VERSION = 2
METADATA_FIELDS = (
    "domain",
    "task_family",
    "failure_mode",
    "strategy_type",
    "tool_type",
    "task_stage",
)


class AggregationError(RuntimeError):
    """An aggregation was not safe to commit."""


class HierarchicalExperienceManager:
    """Manage structured, traceable hierarchical experiences.

    The clustered path never sends generated L1/L2 through the generic
    ADD/UPDATE/DELETE pool merge. That merge can rewrite identity and lose the
    exact source mapping. Instead, one validated child is committed for one
    eligible cluster, together with its parent state changes, in a single atomic
    snapshot replacement.
    """

    def __init__(
        self,
        config: AgentConfig,
        hierarchical_config: Any,
        agent_objective: str,
        learning_objective: str,
        *,
        llm: Any | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.config = config
        self.h_config = hierarchical_config
        self.agent_objective = agent_objective
        self.learning_objective = learning_objective

        if llm is None:
            self.llm = SimplifiedAsyncOpenAI(**config.model.model_provider.model_dump())
            self.model_params = config.model.model_params.model_dump()
        else:
            self.llm = llm
            model = getattr(config, "model", None)
            params = getattr(model, "model_params", None)
            self.model_params = params.model_dump() if params is not None else {}

        prompt_path = DIR_ROOT / "configs" / "prompts" / "hierarchical_critique.yaml"
        self.prompts = FileUtils.load_prompts(str(prompt_path))

        configured_provider = self._cfg("embedding_provider", "sentence_transformer")
        if embedding_provider is None:
            if configured_provider == "hashing":
                embedding_provider = HashingEmbeddingProvider(seed=self._cfg("random_seed", 42))
            elif configured_provider == "sentence_transformer":
                embedding_provider = SentenceTransformerEmbeddingProvider(
                    model_name=self._cfg(
                        "embedding_model_name",
                        "sentence-transformers/all-MiniLM-L6-v2",
                    ),
                    model_revision=self._cfg("embedding_model_revision", ""),
                    expected_dimensions=int(self._cfg("embedding_dimensions", 384)),
                    cache_path=self._cfg(
                        "embedding_cache_path",
                        "workspace/cache/experience_embeddings.sqlite3",
                    ),
                    device=self._cfg("embedding_device", "cpu"),
                    batch_size=int(self._cfg("embedding_batch_size", 32)),
                    local_files_only=bool(self._cfg("embedding_local_files_only", True)),
                    random_seed=int(self._cfg("random_seed", 42)),
                )
            else:
                raise ValueError(
                    f"Unknown embedding_provider={configured_provider!r}; "
                    "expected 'sentence_transformer' or the lexical test baseline 'hashing'"
                )
        self.clusterer = ExperienceClusterer(
            embedding_provider,
            method=self._cfg("clustering_method", "agglomerative"),
            max_cluster_size=self._cfg("max_cluster_size", 20),
            use_metadata_constraints=self._cfg("use_metadata_constraints", True),
            hard_constraint_fields=self._cfg("hard_constraint_fields", ["task_stage", "failure_mode"]),
            soft_constraint_fields=self._cfg(
                "soft_constraint_fields",
                ["domain", "task_family", "tool_type", "strategy_type"],
            ),
            random_seed=self._cfg("random_seed", 42),
        )

        self._l0_records: dict[str, ExperienceRecord] = {}
        self._l1_records: dict[str, ExperienceRecord] = {}
        self._l2_records: dict[str, ExperienceRecord] = {}
        self._snapshot_provenance: dict[str, str] = {}
        self._load_experiences()

    def _cfg(self, name: str, default: Any) -> Any:
        return getattr(self.h_config, name, default)

    @property
    def _min_l0_per_l1(self) -> int:
        return int(
            self._cfg(
                "min_l0_per_l1",
                self._cfg("l1_aggregation_threshold", 5),
            )
        )

    @property
    def _min_l1_per_l2(self) -> int:
        return int(
            self._cfg(
                "min_l1_per_l2",
                self._cfg("l2_aggregation_threshold", 3),
            )
        )

    # ------------------------------------------------------------------
    # Persistence and migration
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_ids(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, int)):
            return [str(value)]
        return sorted({str(item) for item in value if item is not None and str(item)})

    def _load_level(
        self,
        raw: Any,
        level: ExperienceLevel,
        legacy_aggregated_ids: set[str],
    ) -> dict[str, ExperienceRecord]:
        records: dict[str, ExperienceRecord] = {}
        if isinstance(raw, dict):
            items = list(raw.items())
        elif isinstance(raw, list):
            items = []
            for index, item in enumerate(raw):
                if isinstance(item, dict):
                    items.append((str(item.get("id") or f"{level}_{index}"), item))
                else:
                    items.append((f"{level}_{index}", item))
        else:
            return records

        for exp_id, value in items:
            status = "aggregated" if str(exp_id) in legacy_aggregated_ids else "pending"
            if level == "L2":
                status = "terminal"
            if isinstance(value, dict):
                payload = dict(value)
                payload.setdefault("id", str(exp_id))
                payload.setdefault("level", level)
                payload.setdefault("aggregation_status", status)
                if not payload.get("parent_ids"):
                    if level == "L1":
                        payload["parent_ids"] = payload.get("source_l0_ids", [])
                    elif level == "L2":
                        payload["parent_ids"] = payload.get("source_l1_ids", [])
                try:
                    record = ExperienceRecord.model_validate(payload)
                except ValidationError as error:
                    logger.warning("Skipping invalid %s experience %s: %s", level, exp_id, error)
                    continue
            else:
                record = ExperienceRecord.from_legacy(str(exp_id), str(value), level, aggregation_status=status)
            records[record.id] = record
        return records

    def _load_experiences(self) -> None:
        save_path = Path(self.h_config.experience_save_path)
        if not save_path.exists():
            return
        try:
            with save_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            self._snapshot_provenance = {
                key: str(data[key])
                for key in ("source_snapshot_file_sha256", "source_l0_sha256")
                if data.get(key)
            }
            l0_done = set(self._normalise_ids(data.get("l0_aggregated_ids")))
            l1_done = set(self._normalise_ids(data.get("l1_aggregated_ids")))
            self._l0_records = self._load_level(data.get("l0_experiences", {}), "L0", l0_done)
            self._l1_records = self._load_level(data.get("l1_experiences", {}), "L1", l1_done)
            self._l2_records = self._load_level(data.get("l2_experiences", {}), "L2", set())

            # Legacy files never persisted L1 state. If such a file already
            # contains L2, conservatively mark its old L1 pool as processed so a
            # restart does not blindly regenerate the same L2 again.
            if int(data.get("schema_version", 1)) < SCHEMA_VERSION and self._l2_records:
                self._l1_records = {
                    exp_id: record.model_copy(update={"aggregation_status": "aggregated"})
                    for exp_id, record in self._l1_records.items()
                }
            logger.info(
                "Loaded hierarchical experiences: L0=%d L1=%d L2=%d",
                len(self._l0_records),
                len(self._l1_records),
                len(self._l2_records),
            )
        except Exception as error:  # noqa: BLE001
            logger.warning("Failed to load experiences from %s: %s", save_path, error)

    @staticmethod
    def _ordered_records(records: dict[str, ExperienceRecord]) -> list[dict[str, Any]]:
        ordered = sorted(records.values(), key=lambda record: (record.created_at, record.id))
        return [record.public_dict() for record in ordered]

    def _state_payload(
        self,
        l0_records: dict[str, ExperienceRecord],
        l1_records: dict[str, ExperienceRecord],
        l2_records: dict[str, ExperienceRecord],
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            **self._snapshot_provenance,
            "l0_experiences": self._ordered_records(l0_records),
            "l1_experiences": self._ordered_records(l1_records),
            "l2_experiences": self._ordered_records(l2_records),
            "l0_aggregated_ids": sorted(
                exp_id for exp_id, record in l0_records.items() if record.aggregation_status == "aggregated"
            ),
            "l1_aggregated_ids": sorted(
                exp_id for exp_id, record in l1_records.items() if record.aggregation_status == "aggregated"
            ),
            "stats": {
                "total_l0": len(l0_records),
                "total_l1": len(l1_records),
                "total_l2": len(l2_records),
                "pending_l0": sum(record.aggregation_status == "pending" for record in l0_records.values()),
                "pending_l1": sum(record.aggregation_status == "pending" for record in l1_records.values()),
                "l0_metadata_coverage": self._metadata_coverage(list(l0_records.values())),
            },
        }

    def _write_state(
        self,
        l0_records: dict[str, ExperienceRecord],
        l1_records: dict[str, ExperienceRecord],
        l2_records: dict[str, ExperienceRecord],
    ) -> None:
        save_path = Path(self.h_config.experience_save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = save_path.with_suffix(save_path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                self._state_payload(l0_records, l1_records, l2_records),
                file,
                indent=2,
                ensure_ascii=False,
            )
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, save_path)

    def save_experiences(self) -> None:
        self._write_state(self._l0_records, self._l1_records, self._l2_records)
        logger.info("Saved hierarchical experiences to %s", self.h_config.experience_save_path)

    # ------------------------------------------------------------------
    # L0 ingestion
    # ------------------------------------------------------------------

    def _candidate_to_record(self, candidate: str | dict[str, Any] | ExperienceRecord) -> ExperienceRecord | None:
        if isinstance(candidate, ExperienceRecord):
            return candidate
        if isinstance(candidate, str):
            payload: dict[str, Any] = {"content": candidate}
        elif isinstance(candidate, dict):
            payload = dict(candidate)
        else:
            return None
        content = str(payload.get("content") or "").strip()
        if not content:
            return None
        supplied_id = payload.get("id")
        payload["id"] = str(supplied_id or "L0_pending_normalisation")
        payload["level"] = "L0"
        payload.setdefault("aggregation_status", "pending")
        payload["source_task_ids"] = self._normalise_ids(payload.get("source_task_ids"))
        payload["source_rollout_ids"] = self._normalise_ids(payload.get("source_rollout_ids"))
        record = ExperienceRecord.model_validate(payload)
        if supplied_id:
            return record
        identity_context = []
        for field_name in METADATA_FIELDS:
            value = getattr(record, field_name, None)
            raw = getattr(value, "value", value)
            if raw is not None and str(raw).strip().lower() not in {"", "unknown"}:
                identity_context.append(f"{field_name}={raw}")
        return record.model_copy(
            update={"id": stable_experience_id("L0", content, identity_context=identity_context)}
        )

    @staticmethod
    def _metadata_coverage(records: Sequence[ExperienceRecord]) -> dict[str, dict[str, float | int]]:
        total = len(records)
        coverage: dict[str, dict[str, float | int]] = {}
        for field_name in METADATA_FIELDS:
            known = 0
            for record in records:
                value = getattr(record, field_name, None)
                raw = getattr(value, "value", value)
                if raw is not None and str(raw).strip().lower() not in {"", "unknown"}:
                    known += 1
            coverage[field_name] = {
                "known": known,
                "total": total,
                "ratio": known / total if total else 0.0,
            }
        return coverage

    def _task_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self._l0_records.values():
            for task_id in record.source_task_ids:
                counts[task_id] = counts.get(task_id, 0) + 1
        return counts

    async def process_step_experiences(
        self,
        l0_candidates: Sequence[str | dict[str, Any] | ExperienceRecord],
        step: int,
    ) -> None:
        candidates = [record for item in (l0_candidates or []) if (record := self._candidate_to_record(item))]
        if not candidates:
            logger.info("L0 step %s: no candidates", step)
            return

        updated = {exp_id: record.model_copy(deep=True) for exp_id, record in self._l0_records.items()}
        task_counts = self._task_counts()
        per_task_limit = int(self._cfg("max_l0_per_problem", 1))
        added = 0
        merged = 0
        skipped = 0
        for candidate in candidates:
            if candidate.id in updated:
                updated[candidate.id] = updated[candidate.id].merge_evidence(candidate)
                merged += 1
                continue
            if candidate.source_task_ids and per_task_limit > 0:
                if all(task_counts.get(task_id, 0) >= per_task_limit for task_id in candidate.source_task_ids):
                    skipped += 1
                    continue
            updated[candidate.id] = candidate
            added += 1
            for task_id in candidate.source_task_ids:
                task_counts[task_id] = task_counts.get(task_id, 0) + 1

        self._write_state(updated, self._l1_records, self._l2_records)
        self._l0_records = updated
        logger.info(
            "L0 step %s: candidates=%d added=%d evidence_merged=%d task_limit_skipped=%d total=%d",
            step,
            len(candidates),
            added,
            merged,
            skipped,
            len(self._l0_records),
        )
        logger.info(
            "L0 metadata coverage after step %s: %s",
            step,
            json.dumps(self._metadata_coverage(list(self._l0_records.values())), sort_keys=True),
        )

    # ------------------------------------------------------------------
    # Clustered aggregation
    # ------------------------------------------------------------------

    def _pending(self, level: ExperienceLevel) -> list[ExperienceRecord]:
        return [record for record in self._store(level).values() if record.aggregation_status == "pending"]

    def _store(self, level: ExperienceLevel) -> dict[str, ExperienceRecord]:
        if level == "L0":
            return self._l0_records
        if level == "L1":
            return self._l1_records
        return self._l2_records

    def _cluster_pending(
        self,
        pending: Sequence[ExperienceRecord],
        *,
        level: ExperienceLevel,
        minimum_size: int,
        similarity_threshold: float,
    ) -> ClusteringReport:
        if self._cfg("clustering_enabled", True):
            return self.clusterer.cluster(
                pending,
                level=level,
                similarity_threshold=similarity_threshold,
            )
        return self.clusterer.sequential_groups(
            pending,
            level=level,
            group_size=minimum_size,
        )

    @staticmethod
    def _consensus(records: Sequence[ExperienceRecord], field_name: str) -> str | None:
        values = {
            str(getattr(value, "value", value))
            for record in records
            if (value := getattr(record, field_name, None)) is not None
            and str(getattr(value, "value", value)).strip().lower() not in {"", "unknown"}
        }
        return next(iter(values)) if len(values) == 1 else None

    def _make_child(
        self,
        target_level: ExperienceLevel,
        parents: Sequence[ExperienceRecord],
        cluster: ExperienceCluster,
        result: AggregatedExperienceContent,
    ) -> ExperienceRecord:
        parent_ids = sorted(parent.id for parent in parents)
        content = result.render()
        source_l0_ids: list[str] = []
        source_l1_ids: list[str] = []
        if target_level == "L1":
            source_l0_ids = parent_ids
        else:
            source_l1_ids = parent_ids
            source_l0_ids = sorted(
                {source_id for parent in parents for source_id in (parent.source_l0_ids or parent.parent_ids)}
            )
        metadata = {field_name: self._consensus(parents, field_name) for field_name in METADATA_FIELDS}
        return ExperienceRecord(
            id=stable_experience_id(target_level, content, parent_ids),
            level=target_level,
            content=content,
            structured_content=result,
            source_task_ids=sorted({task_id for parent in parents for task_id in parent.source_task_ids}),
            source_rollout_ids=sorted({rollout_id for parent in parents for rollout_id in parent.source_rollout_ids}),
            parent_ids=parent_ids,
            source_l0_ids=source_l0_ids,
            source_l1_ids=source_l1_ids,
            cluster_id=cluster.cluster_id,
            aggregation_status="terminal" if target_level == "L2" else "pending",
            **metadata,
        )

    def _commit_child(
        self,
        source_level: ExperienceLevel,
        target_level: ExperienceLevel,
        child: ExperienceRecord,
        parent_ids: Sequence[str],
    ) -> None:
        l0 = {key: value.model_copy(deep=True) for key, value in self._l0_records.items()}
        l1 = {key: value.model_copy(deep=True) for key, value in self._l1_records.items()}
        l2 = {key: value.model_copy(deep=True) for key, value in self._l2_records.items()}
        stores = {"L0": l0, "L1": l1, "L2": l2}
        source_store = stores[source_level]
        target_store = stores[target_level]
        max_total = int(self._cfg("max_l1_total", 50) if target_level == "L1" else self._cfg("max_l2_total", 10))
        if child.id not in target_store and max_total > 0 and len(target_store) >= max_total:
            raise AggregationError(f"{target_level} capacity {max_total} reached")
        missing = [parent_id for parent_id in parent_ids if parent_id not in source_store]
        if missing:
            raise AggregationError(f"missing parent records: {missing}")

        target_store[child.id] = child
        for parent_id in parent_ids:
            parent = source_store[parent_id]
            updates = {
                "aggregation_status": "aggregated",
                "aggregated_into_cluster_id": child.cluster_id,
            }
            # L0 has no creation cluster of its own, so expose its first
            # assignment in the primary cluster_id field as well.
            if parent.cluster_id is None:
                updates["cluster_id"] = child.cluster_id
            source_store[parent_id] = parent.model_copy(update=updates)
        self._write_state(l0, l1, l2)
        self._l0_records, self._l1_records, self._l2_records = l0, l1, l2

    def _audit_path(self) -> Path:
        configured = self._cfg("clustering_audit_path", None)
        if configured:
            return Path(configured)
        save_path = Path(self.h_config.experience_save_path)
        return save_path.with_suffix(save_path.suffix + ".clusters.jsonl")

    def _append_audit(self, payload: dict[str, Any]) -> None:
        audit_path = self._audit_path()
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        except Exception as error:  # noqa: BLE001
            logger.error("Failed to write clustering audit %s: %s", audit_path, error)

    async def _aggregate_level(
        self,
        *,
        epoch: int,
        source_level: ExperienceLevel,
        target_level: ExperienceLevel,
        minimum_size: int,
        similarity_threshold: float,
        confidence_threshold: float,
    ) -> None:
        pending = self._pending(source_level)
        if not pending:
            logger.info("%s->%s epoch %s: no pending experiences", source_level, target_level, epoch)
            return
        if (
            self._cfg("clustering_enabled", True)
            and self._cfg("similarity_thresholds_provisional", False)
            and not self._cfg("allow_provisional_aggregation", False)
        ):
            logger.warning(
                "%s->%s aggregation skipped: similarity thresholds are provisional; "
                "collect training L0 and run calibration first",
                source_level,
                target_level,
            )
            self._append_audit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "epoch": epoch,
                    "source_level": source_level,
                    "target_level": target_level,
                    "status": "waiting_for_threshold_calibration",
                    "pending_experience_ids": sorted(record.id for record in pending),
                }
            )
            return
        report = self._cluster_pending(
            pending,
            level=source_level,
            minimum_size=minimum_size,
            similarity_threshold=similarity_threshold,
        )
        logger.info(
            "%s->%s epoch %s: input=%d clusters=%d metadata_splits=%d",
            source_level,
            target_level,
            epoch,
            report.input_count,
            len(report.clusters),
            len(report.metadata_constraint_splits),
        )
        attempts: list[dict[str, Any]] = []
        for cluster in report.clusters:
            logger.info(
                "Cluster %s ids=%s similarity=%.4f metadata_consistency=%.4f completeness=%.4f",
                cluster.cluster_id,
                cluster.experience_ids,
                cluster.intra_cluster_similarity,
                cluster.metadata_consistency,
                cluster.metadata_completeness,
            )
            if len(cluster.experience_ids) < minimum_size:
                attempts.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "experience_ids": cluster.experience_ids,
                        "status": "pending_below_minimum",
                        "minimum_size": minimum_size,
                    }
                )
                continue
            current_source = self._store(source_level)
            parents = [current_source[parent_id] for parent_id in cluster.experience_ids]
            conflicts = (
                detect_strategy_conflicts(
                    parents,
                    lexical_overlap_threshold=float(
                        self._cfg("strategy_conflict_lexical_overlap", 0.65)
                    ),
                )
                if self._cfg("strategy_conflict_check_enabled", True)
                else []
            )
            if conflicts:
                attempts.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "experience_ids": cluster.experience_ids,
                        "status": "pending_conflict",
                        "conflicts": conflicts,
                    }
                )
                logger.warning(
                    "Aggregation blocked for %s cluster %s due to strategy conflicts: %s",
                    source_level,
                    cluster.cluster_id,
                    conflicts,
                )
                continue
            try:
                if target_level == "L1":
                    result = await self._generate_l1_from_l0([parent.public_dict() for parent in parents])
                else:
                    result = await self._generate_l2_from_l1([parent.public_dict() for parent in parents])
                if result.confidence < confidence_threshold:
                    raise AggregationError(f"confidence {result.confidence:.3f} below {confidence_threshold:.3f}")
                child = self._make_child(target_level, parents, cluster, result)
                self._commit_child(
                    source_level,
                    target_level,
                    child,
                    cluster.experience_ids,
                )
                attempts.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "experience_ids": cluster.experience_ids,
                        "status": "success",
                        "child_id": child.id,
                        "parent_ids": child.parent_ids,
                    }
                )
                logger.info(
                    "Aggregated %s -> %s child=%s parents=%s",
                    source_level,
                    target_level,
                    child.id,
                    child.parent_ids,
                )
            except Exception as error:  # noqa: BLE001
                attempts.append(
                    {
                        "cluster_id": cluster.cluster_id,
                        "experience_ids": cluster.experience_ids,
                        "status": "failed",
                        "reason": str(error),
                    }
                )
                logger.error(
                    "Aggregation failed for %s cluster %s; parents remain pending: %s",
                    source_level,
                    cluster.cluster_id,
                    error,
                )

        remaining_pending = sorted(record.id for record in self._pending(source_level))
        self._append_audit(
            {
                "schema_version": SCHEMA_VERSION,
                "epoch": epoch,
                "source_level": source_level,
                "target_level": target_level,
                "clustering_enabled": self._cfg("clustering_enabled", True),
                "minimum_size": minimum_size,
                "report": report.as_dict(),
                "aggregation_attempts": attempts,
                "pending_experience_ids": remaining_pending,
            }
        )
        logger.info(
            "%s->%s epoch %s: successes=%d failures=%d pending=%d",
            source_level,
            target_level,
            epoch,
            sum(attempt["status"] == "success" for attempt in attempts),
            sum(attempt["status"] == "failed" for attempt in attempts),
            len(remaining_pending),
        )

    async def aggregate_epoch(self, epoch: int) -> None:
        await self._aggregate_level(
            epoch=epoch,
            source_level="L0",
            target_level="L1",
            minimum_size=self._min_l0_per_l1,
            similarity_threshold=float(self._cfg("l0_similarity_threshold", 0.60)),
            confidence_threshold=float(self._cfg("l1_confidence_threshold", 0.70)),
        )
        await self._aggregate_level(
            epoch=epoch,
            source_level="L1",
            target_level="L2",
            minimum_size=self._min_l1_per_l2,
            similarity_threshold=float(self._cfg("l1_similarity_threshold", 0.55)),
            confidence_threshold=float(self._cfg("l2_confidence_threshold", 0.80)),
        )
        logger.info(
            "Epoch %s hierarchy: L0=%d L1=%d L2=%d",
            epoch,
            len(self._l0_records),
            len(self._l1_records),
            len(self._l2_records),
        )

    async def _aggregate_l1(self, epoch: int) -> None:
        await self._aggregate_level(
            epoch=epoch,
            source_level="L0",
            target_level="L1",
            minimum_size=self._min_l0_per_l1,
            similarity_threshold=float(self._cfg("l0_similarity_threshold", 0.60)),
            confidence_threshold=float(self._cfg("l1_confidence_threshold", 0.70)),
        )

    async def _aggregate_l2(self, epoch: int) -> None:
        await self._aggregate_level(
            epoch=epoch,
            source_level="L1",
            target_level="L2",
            minimum_size=self._min_l1_per_l2,
            similarity_threshold=float(self._cfg("l1_similarity_threshold", 0.55)),
            confidence_threshold=float(self._cfg("l2_confidence_threshold", 0.80)),
        )

    # ------------------------------------------------------------------
    # LLM generation and validation
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_aggregation_response(response: str) -> AggregatedExperienceContent:
        text = (response or "").strip()
        if "```" in text:
            parts = text.split("```")
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        try:
            payload = json.loads(text.strip())
        except json.JSONDecodeError as error:
            raise AggregationError(f"invalid aggregation JSON: {error}") from error
        if not isinstance(payload, dict):
            raise AggregationError("aggregation output must be a JSON object")
        if payload.get("status") == "cannot_aggregate":
            raise AggregationError("model reported incompatible cluster: " + str(payload.get("reason", "unspecified")))
        if payload.get("decision") == "conflict":
            try:
                conflict = AggregationConflict.model_validate(payload)
            except ValidationError as error:
                raise AggregationError(f"aggregation conflict schema validation failed: {error}") from error
            raise AggregationError("model reported strategy conflict: " + "; ".join(conflict.conflict_reasons))
        try:
            return AggregatedExperienceContent.model_validate(payload)
        except ValidationError as error:
            raise AggregationError(f"aggregation schema validation failed: {error}") from error

    async def _query_aggregation(
        self,
        prompt_name: str,
        template_values: dict[str, Any],
    ) -> AggregatedExperienceContent:
        prompt = self.prompts[prompt_name]
        system_prompt = Template(prompt["system"]).render(
            agent_objective=self.agent_objective,
            learning_objective=self.learning_objective,
        )
        user_prompt = Template(prompt["user"]).render(**template_values)
        params = dict(self.model_params)
        params["temperature"] = float(self._cfg("aggregation_temperature", 0.0))
        response = await self.llm.query_one(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **params,
        )
        return self._parse_aggregation_response(response)

    async def _generate_l1_from_l0(self, l0_batch: list[dict[str, Any]]) -> AggregatedExperienceContent:
        return await self._query_aggregation(
            "L1_AGGREGATION_PROMPT",
            {"l0_experiences": l0_batch},
        )

    async def _generate_l2_from_l1(self, l1_batch: list[dict[str, Any]]) -> AggregatedExperienceContent:
        source_l0_ids = sorted({source_id for parent in l1_batch for source_id in parent.get("source_l0_ids", [])})
        l0_evidence = [
            self._l0_records[source_id].public_dict() for source_id in source_l0_ids if source_id in self._l0_records
        ]
        return await self._query_aggregation(
            "L2_AGGREGATION_PROMPT",
            {
                "l1_experiences": l1_batch,
                "l0_experiences": l0_evidence,
            },
        )

    # ------------------------------------------------------------------
    # Accessors and ancestry
    # ------------------------------------------------------------------

    @property
    def l0(self) -> dict[str, str]:
        return {exp_id: record.content for exp_id, record in self._l0_records.items()}

    @property
    def l1(self) -> dict[str, str]:
        return {exp_id: record.content for exp_id, record in self._l1_records.items()}

    @property
    def l2(self) -> dict[str, str]:
        return {exp_id: record.content for exp_id, record in self._l2_records.items()}

    def get_all_l0_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l0_records)

    def get_all_l1_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l1_records)

    def get_all_l2_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l2_records)

    def get_recent_l0_experiences(self, limit: int) -> list[dict[str, Any]]:
        items = self.get_all_l0_experiences()
        return items[-limit:] if limit > 0 else []

    def trace_ancestry(self, experience_id: str) -> dict[str, Any]:
        """Return the complete parent tree for an L0/L1/L2 experience."""

        all_records = {**self._l0_records, **self._l1_records, **self._l2_records}
        if experience_id not in all_records:
            raise KeyError(experience_id)
        record = all_records[experience_id]
        return {
            "experience": record.public_dict(),
            "parents": [self.trace_ancestry(parent_id) for parent_id in record.parent_ids],
        }

    @property
    def l0_experiences(self) -> list[dict[str, Any]]:
        return self.get_all_l0_experiences()

    @property
    def l1_experiences(self) -> list[dict[str, Any]]:
        return self.get_all_l1_experiences()

    @property
    def l2_experiences(self) -> list[dict[str, Any]]:
        return self.get_all_l2_experiences()
