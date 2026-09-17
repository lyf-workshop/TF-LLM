"""Restart-safe L0/L1/L2 experience aggregation with deterministic clustering."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from jinja2 import Template
from pydantic import ValidationError

from ..config import AgentConfig
from ..utils import DIR_ROOT, FileUtils, SimplifiedAsyncOpenAI, get_logger
from .experience_clusterer import (
    DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS,
    DEFAULT_HARD_CONSTRAINT_FIELDS,
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
    ExperienceCandidateRecord,
    ExperienceLevel,
    ExperienceRecord,
    ExperienceReviewDecision,
    L0CandidateRecord,
    experience_output_language_instruction,
    stable_experience_id,
    stable_l0_candidate_id,
    validate_experience_output_language,
)
from .experience_pool import review_experience_candidate, review_l0_candidate
from .hierarchy import aggregation, candidate_state, review_context, snapshot

logger = get_logger(__name__)

SCHEMA_VERSION = snapshot.SCHEMA_VERSION
STRICT_SNAPSHOT_VERSION = snapshot.STRICT_SNAPSHOT_VERSION
UPPER_CANDIDATE_GENERATOR_VERSION = "hierarchical-aggregate-candidate-v2"
METADATA_FIELDS = (
    "domain",
    "task_family",
    "failure_mode",
    "strategy_type",
    "tool_type",
    "task_stage",
)
AggregationTarget = Literal["L1", "L2"]


class AggregationError(RuntimeError):
    """An aggregation was not safe to commit."""


class CandidateDecisionError(RuntimeError):
    """A candidate review decision was invalid for the current pool."""


class StaleCandidateError(CandidateDecisionError):
    """A hierarchical candidate no longer matches its persisted source versions."""


class HierarchicalExperienceManager:
    """Manage structured, traceable hierarchical experiences.

    L0 summaries and, when configured, generated L1/L2 summaries first become
    persisted candidates.  A shared deterministic review queue validates one
    ADD/UPDATE/DELETE/KEEP decision at a time against the latest same-level
    active pool.  Pool, archive, dependency, and candidate state changes are
    committed by one atomic snapshot replacement.
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
        self.experience_output_language = self._cfg(
            "experience_output_language", "same_as_input"
        )
        self.experience_output_language_instruction = experience_output_language_instruction(
            self.experience_output_language
        )

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
            hard_constraint_fields=self._cfg(
                "hard_constraint_fields", list(DEFAULT_HARD_CONSTRAINT_FIELDS)
            ),
            soft_constraint_fields=self._cfg(
                "soft_constraint_fields",
                list(DEFAULT_CONFIGURED_SOFT_CONSTRAINT_FIELDS),
            ),
            random_seed=self._cfg("random_seed", 42),
        )

        self._l0_records: dict[str, ExperienceRecord] = {}
        self._l0_archive: dict[str, ExperienceRecord] = {}
        self._candidate_records: dict[str, ExperienceCandidateRecord] = {}
        self._l1_records: dict[str, ExperienceRecord] = {}
        self._l1_archive: dict[str, ExperienceRecord] = {}
        self._l2_records: dict[str, ExperienceRecord] = {}
        self._l2_archive: dict[str, ExperienceRecord] = {}
        self._snapshot_provenance: dict[str, str] = {}
        self._review_lock = asyncio.Lock()
        self._load_experiences()

    def _cfg(self, name: str, default: Any) -> Any:
        return getattr(self.h_config, name, default)

    def _similarity_threshold_is_provisional(self, source_level: ExperienceLevel) -> bool:
        """Return the calibration gate for the level being clustered.

        ``similarity_thresholds_provisional`` predates per-layer calibration.
        Keep it as a fallback for lightweight/legacy config objects which have
        not passed through ``HierarchicalLearningConfig`` validation.
        """

        field_by_level = {
            "L0": "l0_similarity_threshold_provisional",
            "L1": "l1_similarity_threshold_provisional",
        }
        field_name = field_by_level.get(source_level)
        if field_name is None:
            return False
        layer_value = self._cfg(field_name, None)
        if layer_value is not None:
            return bool(layer_value)
        return bool(self._cfg("similarity_thresholds_provisional", False))

    def _candidate_review_threshold_is_gated(
        self,
        candidate_level: ExperienceLevel,
    ) -> bool:
        """Prevent every upper-candidate review path from bypassing calibration."""

        source_level_by_candidate: dict[ExperienceLevel, ExperienceLevel] = {
            "L1": "L0",
            "L2": "L1",
        }
        source_level = source_level_by_candidate.get(candidate_level)
        return bool(
            source_level is not None
            and self._cfg("clustering_enabled", True)
            and self._similarity_threshold_is_provisional(source_level)
            and not self._cfg("allow_provisional_aggregation", False)
        )

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
        return snapshot.normalise_ids(value)

    def _load_level(
        self,
        raw: Any,
        level: ExperienceLevel,
        legacy_aggregated_ids: set[str],
        *,
        strict: bool = False,
    ) -> dict[str, ExperienceRecord]:
        return snapshot.load_level(
            raw,
            level,
            legacy_aggregated_ids,
            strict=strict,
            warning=logger.warning,
        )

    def _load_candidates(
        self,
        raw: Any,
        *,
        default_level: ExperienceLevel = "L0",
        strict_level: bool = False,
    ) -> dict[str, ExperienceCandidateRecord]:
        return snapshot.load_candidates(
            raw,
            default_level=default_level,
            strict_level=strict_level,
        )

    def _normalise_loaded_hierarchy(self, schema_version: int) -> None:
        """Repair v3 child pointers and quarantine invalid active descendants.

        Schema v1/v2 files predate reliable parent relations, so their
        historical aggregate markers are preserved.  From v3 onward, direct
        parent IDs are authoritative: an active child with a missing, inactive,
        or changed parent cannot remain injectable.
        """

        if schema_version < STRICT_SNAPSHOT_VERSION:
            return
        for level, records, lower in (
            ("L1", self._l1_records, self._l0_records),
            ("L2", self._l2_records, self._l1_records),
        ):
            for record_id, record in list(records.items()):
                if record.lifecycle_status != "active":
                    continue
                parent_ids = list(record.parent_ids)
                if not parent_ids:
                    # Old manually-authored upper experiences may have no
                    # traceable parents. Preserve them only for legacy input;
                    # schema v4 promises a fully traceable active hierarchy.
                    if schema_version >= SCHEMA_VERSION:
                        records[record_id] = record.model_copy(
                            update={
                                "lifecycle_status": "needs_review",
                                "needs_review_reason": (
                                    f"loaded {level} has no traceable direct parents"
                                ),
                            }
                        )
                    continue
                invalid_reasons: list[str] = []
                missing = sorted(parent_id for parent_id in parent_ids if parent_id not in lower)
                inactive = sorted(
                    parent_id
                    for parent_id in parent_ids
                    if parent_id in lower and lower[parent_id].lifecycle_status != "active"
                )
                if missing:
                    invalid_reasons.append(f"missing parents={missing}")
                if inactive:
                    invalid_reasons.append(f"inactive parents={inactive}")
                if not (missing or inactive):
                    current_versions = {
                        parent_id: self._record_version_fingerprint(lower[parent_id])
                        for parent_id in parent_ids
                    }
                    current_source_fingerprint = self._source_fingerprint(level, current_versions)
                    if schema_version < SCHEMA_VERSION:
                        # Schema v3 persisted parent IDs but not the version
                        # pins introduced with reviewed upper candidates.  Pin
                        # the exact current graph during migration; never
                        # invent parents or accept a conflicting existing pin.
                        if (
                            record.parent_version_fingerprints
                            and current_versions != record.parent_version_fingerprints
                        ):
                            invalid_reasons.append("parent version fingerprint changed")
                        if (
                            record.source_version_fingerprint
                            and record.source_version_fingerprint
                            != current_source_fingerprint
                        ):
                            invalid_reasons.append("source version fingerprint changed")
                        if not invalid_reasons:
                            record = record.model_copy(
                                update={
                                    "parent_version_fingerprints": current_versions,
                                    "source_version_fingerprint": current_source_fingerprint,
                                }
                            )
                            records[record_id] = record
                    else:
                        if set(record.parent_version_fingerprints) != set(parent_ids):
                            invalid_reasons.append(
                                "parent version fingerprint keys do not match parent_ids"
                            )
                        elif current_versions != record.parent_version_fingerprints:
                            invalid_reasons.append("parent version fingerprint changed")
                        if record.source_version_fingerprint != current_source_fingerprint:
                            invalid_reasons.append("source version fingerprint changed")
                if invalid_reasons:
                    records[record_id] = record.model_copy(
                        update={
                            "lifecycle_status": "needs_review",
                            "needs_review_reason": (
                                f"loaded {level} has invalid current sources: "
                                + "; ".join(invalid_reasons)
                            ),
                        }
                    )

        # This also backfills v3's missing aggregated_into_experience_id.  It
        # fails closed if one lower experience has multiple active consumers.
        self._reconcile_parent_statuses(
            "L0",
            list(self._l0_records),
            self._l0_records,
            self._l1_records,
            self._l2_records,
        )
        self._reconcile_parent_statuses(
            "L1",
            list(self._l1_records),
            self._l0_records,
            self._l1_records,
            self._l2_records,
        )

    def _migrate_loaded_candidate_results(self, schema_version: int) -> None:
        """Upgrade pre-v4 committed candidate state without inventing results.

        Older L0 review snapshots did not persist ``resolution`` consistently.
        An adopted result can be recovered only through a unique reverse link
        from an active or archived experience.  Ambiguous state fails closed so
        it cannot be rewritten as schema v4 and then suppress work forever.
        """

        if schema_version >= SCHEMA_VERSION:
            return
        stores = {"L0": self._l0_records, "L1": self._l1_records, "L2": self._l2_records}
        archives = {
            "L0": self._l0_archive,
            "L1": self._l1_archive,
            "L2": self._l2_archive,
        }
        for candidate_id, candidate in list(self._candidate_records.items()):
            if candidate.status != "committed":
                if candidate.resolution is not None or candidate.result_experience_id is not None:
                    raise ValueError(
                        f"cannot migrate uncommitted {candidate.level} candidate {candidate.id} "
                        "with a committed result"
                    )
                continue
            decision = candidate.review_decision
            if decision is None:
                raise ValueError(
                    f"cannot migrate committed {candidate.level} candidate {candidate.id} "
                    "without its review decision"
                )
            adopted = decision.action in {"ADD", "UPDATE"}
            result_id = candidate.result_experience_id
            if not adopted and result_id is not None:
                raise ValueError(
                    f"cannot migrate non-adopted {candidate.level} candidate {candidate.id} "
                    "with a result"
                )
            if adopted and result_id is None:
                reverse_matches = [
                    record
                    for record in (*stores[candidate.level].values(), *archives[candidate.level].values())
                    if candidate.id in record.review_candidate_ids
                ]
                if decision.action == "ADD":
                    reverse_matches = [
                        record for record in reverse_matches if record.supersedes_id is None
                    ]
                else:
                    reverse_matches = [
                        record
                        for record in reverse_matches
                        if record.supersedes_id == decision.target_id
                    ]
                if len(reverse_matches) != 1:
                    raise ValueError(
                        f"cannot safely migrate adopted {candidate.level} candidate {candidate.id}: "
                        f"expected one reverse-linked result, found {len(reverse_matches)}"
                    )
                result_id = reverse_matches[0].id
            self._candidate_records[candidate_id] = candidate.model_copy(
                update={
                    "resolution": "adopted" if adopted else "not_adopted",
                    "result_experience_id": result_id if adopted else None,
                }
            )

    def _validate_loaded_candidate_results(self, _schema_version: int) -> None:
        """Reject v4 review state that could otherwise suppress work forever."""

        stores = {"L0": self._l0_records, "L1": self._l1_records, "L2": self._l2_records}
        archives = {
            "L0": self._l0_archive,
            "L1": self._l1_archive,
            "L2": self._l2_archive,
        }
        for candidate in self._candidate_records.values():
            if candidate.status != "committed":
                if (
                    candidate.review_decision is not None
                    or candidate.resolution is not None
                    or candidate.result_experience_id is not None
                ):
                    raise ValueError(
                        f"uncommitted {candidate.level} candidate {candidate.id} has a committed result"
                    )
                continue
            decision = candidate.review_decision
            if decision is None:
                raise ValueError(f"committed {candidate.level} candidate {candidate.id} has no decision")
            if decision.candidate_id != candidate.id:
                raise ValueError(
                    f"committed {candidate.level} candidate {candidate.id} has a decision for "
                    f"{decision.candidate_id}"
                )
            if decision.level is not None and decision.level != candidate.level:
                raise ValueError(
                    f"committed {candidate.level} candidate {candidate.id} has decision "
                    f"level={decision.level}"
                )
            adopted = decision.action in {"ADD", "UPDATE"}
            expected_resolution = "adopted" if adopted else "not_adopted"
            if candidate.resolution != expected_resolution:
                raise ValueError(
                    f"committed {candidate.level} candidate {candidate.id} has inconsistent resolution"
                )
            if not adopted:
                if candidate.result_experience_id is not None:
                    raise ValueError(
                        f"non-adopted {candidate.level} candidate {candidate.id} has a result"
                    )
                continue
            result_id = candidate.result_experience_id
            result = stores[candidate.level].get(str(result_id)) or archives[candidate.level].get(
                str(result_id)
            )
            if result is None:
                raise ValueError(
                    f"adopted {candidate.level} candidate {candidate.id} references missing result {result_id}"
                )
            if candidate.id not in result.review_candidate_ids:
                raise ValueError(
                    f"result {result.id} does not reference adopted candidate {candidate.id}"
                )
            if decision.action == "ADD" and result.supersedes_id is not None:
                raise ValueError(
                    f"ADD candidate {candidate.id} result {result.id} is not a lineage root"
                )
            if decision.action == "UPDATE":
                target_id = str(decision.target_id)
                target = archives[candidate.level].get(target_id)
                if (
                    result.supersedes_id != target_id
                    or target is None
                    or target.superseded_by_id != result.id
                ):
                    raise ValueError(
                        f"UPDATE candidate {candidate.id} has inconsistent supersession lineage"
                    )
            if candidate.level != "L0" and not set(candidate.parent_ids).issubset(
                set(result.parent_ids)
            ):
                raise ValueError(
                    f"result {result.id} dropped candidate parents for {candidate.id}"
                )

    def _load_experiences(self) -> None:
        save_path = Path(self.h_config.experience_save_path)
        if not save_path.exists():
            return
        try:
            with save_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            schema_version = int(data.get("schema_version", 1))
            if schema_version > SCHEMA_VERSION:
                raise ValueError(
                    f"snapshot schema {schema_version} is newer than supported schema {SCHEMA_VERSION}"
                )
            strict_snapshot = schema_version >= STRICT_SNAPSHOT_VERSION
            snapshot_language = data.get("experience_output_language")
            has_experience_state = any(
                data.get(key)
                for key in (
                    "l0_candidates",
                    "l1_candidates",
                    "l2_candidates",
                    "l0_experiences",
                    "l1_experiences",
                    "l2_experiences",
                    "l0_archive",
                    "l1_archive",
                    "l2_archive",
                )
            )
            if snapshot_language is None:
                if self.experience_output_language != "same_as_input" and has_experience_state:
                    raise ValueError(
                        "existing snapshot has no experience_output_language contract; "
                        "use a new exp_id and experience_save_path for an English run"
                    )
            elif snapshot_language != self.experience_output_language:
                raise ValueError(
                    "snapshot experience_output_language does not match the current config: "
                    f"snapshot={snapshot_language!r}, "
                    f"current={self.experience_output_language!r}"
                )
            self._snapshot_provenance = {
                key: str(data[key])
                for key in ("source_snapshot_file_sha256", "source_l0_sha256")
                if data.get(key)
            }
            l0_done = set(self._normalise_ids(data.get("l0_aggregated_ids")))
            l1_done = set(self._normalise_ids(data.get("l1_aggregated_ids")))
            self._l0_records = self._load_level(
                data.get("l0_experiences", {}), "L0", l0_done, strict=strict_snapshot
            )
            self._l0_archive = self._load_level(
                data.get("l0_archive", {}), "L0", set(), strict=strict_snapshot
            )
            candidate_groups = (
                ("L0", data.get("l0_candidates", [])),
                ("L1", data.get("l1_candidates", [])),
                ("L2", data.get("l2_candidates", [])),
            )
            loaded_candidates: dict[str, ExperienceCandidateRecord] = {}
            for default_level, raw_candidates in candidate_groups:
                for candidate_id, candidate in self._load_candidates(
                    raw_candidates,
                    default_level=default_level,
                    strict_level=strict_snapshot,
                ).items():
                    previous = loaded_candidates.get(candidate_id)
                    if previous is not None and previous != candidate:
                        raise ValueError(f"conflicting duplicate candidate ID: {candidate_id}")
                    loaded_candidates[candidate_id] = candidate
            self._candidate_records = loaded_candidates
            self._l1_records = self._load_level(
                data.get("l1_experiences", {}), "L1", l1_done, strict=strict_snapshot
            )
            self._l1_archive = self._load_level(
                data.get("l1_archive", {}), "L1", set(), strict=strict_snapshot
            )
            self._l2_records = self._load_level(
                data.get("l2_experiences", {}), "L2", set(), strict=strict_snapshot
            )
            self._l2_archive = self._load_level(
                data.get("l2_archive", {}), "L2", set(), strict=strict_snapshot
            )

            if self.experience_output_language == "english":
                for record in (
                    *self._l0_records.values(),
                    *self._l1_records.values(),
                    *self._l2_records.values(),
                ):
                    if record.lifecycle_status == "active":
                        validate_experience_output_language(
                            record.content,
                            self.experience_output_language,
                            label=f"loaded active {record.level} experience {record.id}",
                        )
                for candidate in self._candidate_records.values():
                    if candidate.status in {"pending", "review_failed"}:
                        validate_experience_output_language(
                            candidate.content,
                            self.experience_output_language,
                            label=f"loaded retryable {candidate.level} candidate {candidate.id}",
                        )

            # Legacy files never persisted L1 state. If such a file already
            # contains L2, conservatively mark its old L1 pool as processed so a
            # restart does not blindly regenerate the same L2 again.
            if schema_version < 2 and self._l2_records:
                self._l1_records = {
                    exp_id: record.model_copy(update={"aggregation_status": "aggregated"})
                    for exp_id, record in self._l1_records.items()
                }
            self._migrate_loaded_candidate_results(schema_version)
            self._normalise_loaded_hierarchy(schema_version)
            self._validate_loaded_candidate_results(schema_version)
            logger.info(
                "Loaded hierarchical experiences: candidates=%d active_L0=%d archived_L0=%d "
                "active_L1=%d archived_L1=%d active_L2=%d archived_L2=%d",
                len(self._candidate_records),
                len(self._l0_records),
                len(self._l0_archive),
                len(self._l1_records),
                len(self._l1_archive),
                len(self._l2_records),
                len(self._l2_archive),
            )
        except Exception as error:  # noqa: BLE001
            # Existing state is authoritative.  Failing closed prevents a
            # malformed v3 snapshot from being overwritten with an empty pool.
            raise RuntimeError(f"Failed to load experiences from {save_path}: {error}") from error

    @staticmethod
    def _ordered_records(records: dict[str, ExperienceRecord]) -> list[dict[str, Any]]:
        return snapshot.ordered_records(records)

    @staticmethod
    def _ordered_candidates(records: dict[str, ExperienceCandidateRecord]) -> list[dict[str, Any]]:
        return snapshot.ordered_candidates(records)

    def _state_payload(
        self,
        l0_records: dict[str, ExperienceRecord],
        l1_records: dict[str, ExperienceRecord],
        l2_records: dict[str, ExperienceRecord],
        candidate_records: dict[str, ExperienceCandidateRecord] | None = None,
        l0_archive: dict[str, ExperienceRecord] | None = None,
        l1_archive: dict[str, ExperienceRecord] | None = None,
        l2_archive: dict[str, ExperienceRecord] | None = None,
    ) -> dict[str, Any]:
        return snapshot.state_payload(
            self,
            l0_records,
            l1_records,
            l2_records,
            candidate_records,
            l0_archive,
            l1_archive,
            l2_archive,
        )

    def _write_state(
        self,
        l0_records: dict[str, ExperienceRecord],
        l1_records: dict[str, ExperienceRecord],
        l2_records: dict[str, ExperienceRecord],
        candidate_records: dict[str, ExperienceCandidateRecord] | None = None,
        l0_archive: dict[str, ExperienceRecord] | None = None,
        l1_archive: dict[str, ExperienceRecord] | None = None,
        l2_archive: dict[str, ExperienceRecord] | None = None,
    ) -> None:
        snapshot.write_state(
            self,
            l0_records,
            l1_records,
            l2_records,
            candidate_records,
            l0_archive,
            l1_archive,
            l2_archive,
        )

    def save_experiences(self) -> None:
        self._write_state(
            self._l0_records,
            self._l1_records,
            self._l2_records,
            self._candidate_records,
            self._l0_archive,
            self._l1_archive,
            self._l2_archive,
        )
        logger.info("Saved hierarchical experiences to %s", self.h_config.experience_save_path)

    # ------------------------------------------------------------------
    # L0 ingestion
    # ------------------------------------------------------------------

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _known_metadata(value: Any) -> str | None:
        raw = getattr(value, "value", value)
        if raw is None or str(raw).strip().lower() in {"", "unknown"}:
            return None
        return str(raw).strip()

    def _identity_context(self, record: ExperienceRecord | L0CandidateRecord) -> list[str]:
        context: list[str] = []
        for field_name in METADATA_FIELDS:
            value = self._known_metadata(getattr(record, field_name, None))
            if value is not None:
                context.append(f"{field_name}={value}")
        return context

    @staticmethod
    def _record_version_fingerprint(record: ExperienceRecord) -> str:
        """Fingerprint semantic content and provenance, not mutable pool state."""

        payload = record.public_dict()
        stable_fields = (
            "id",
            "level",
            "content",
            "structured_content",
            "source_task_ids",
            "source_rollout_ids",
            "domain",
            "task_family",
            "failure_mode",
            "strategy_type",
            "tool_type",
            "task_stage",
            "parent_ids",
            "source_l0_ids",
            "source_l1_ids",
            "revision_number",
            "lineage_root_id",
            "supersedes_id",
            "review_candidate_ids",
        )
        canonical = {field_name: payload.get(field_name) for field_name in stable_fields}
        return hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _source_fingerprint(
        target_level: ExperienceLevel,
        source_versions: dict[str, str],
    ) -> str:
        payload = {
            "target_level": target_level,
            "source_versions": dict(sorted(source_versions.items())),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _generation_fingerprint(
        self,
        target_level: ExperienceLevel,
        source_fingerprint: str,
        cluster_id: str,
    ) -> str:
        prompt_name = "L1_AGGREGATION_PROMPT" if target_level == "L1" else "L2_AGGREGATION_PROMPT"
        review_prompt_name = self._review_prompt_name(target_level)
        model_config = getattr(self.config, "model", None)
        provider_config = getattr(model_config, "model_provider", None)
        safe_model_params = {
            key: value
            for key, value in sorted(self.model_params.items())
            if not any(
                marker in key.lower()
                for marker in ("key", "token", "secret", "password", "authorization")
            )
        }
        payload = {
            "target_level": target_level,
            "source_fingerprint": source_fingerprint,
            "cluster_id": cluster_id,
            "generator_version": UPPER_CANDIDATE_GENERATOR_VERSION,
            "schema_version": SCHEMA_VERSION,
            "aggregation_prompt": self.prompts.get(prompt_name),
            "review_prompt": self.prompts.get(review_prompt_name),
            "agent_objective": self.agent_objective,
            "learning_objective": self.learning_objective,
            "experience_output_language": self.experience_output_language,
            "model": getattr(provider_config, "model", None),
            "model_provider_type": getattr(provider_config, "type", None),
            "model_provider_base_url": getattr(provider_config, "base_url", None),
            "model_params": safe_model_params,
            "aggregation_temperature": float(self._cfg("aggregation_temperature", 0.0)),
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()

    def _upper_review_enabled(self, target_level: ExperienceLevel) -> bool:
        if target_level == "L1":
            return bool(self._cfg("l1_candidate_review_enabled", False))
        if target_level == "L2":
            return bool(self._cfg("l2_candidate_review_enabled", False))
        return bool(self._cfg("l0_candidate_review_enabled", False))

    @staticmethod
    def _review_prompt_name(level: ExperienceLevel) -> str:
        return f"{level}_CANDIDATE_REVIEW_PROMPT"

    def _legacy_candidate_to_record(
        self,
        candidate: str | dict[str, Any] | ExperienceRecord,
    ) -> ExperienceRecord | None:
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
        return record.model_copy(
            update={"id": stable_experience_id("L0", content, identity_context=self._identity_context(record))}
        )

    def _candidate_from_input(
        self,
        candidate: str | dict[str, Any] | ExperienceRecord | L0CandidateRecord,
        step: int,
        *,
        run_id: str | None = None,
        epoch: int | None = None,
        batch: int | None = None,
        batch_fingerprint: str | None = None,
    ) -> L0CandidateRecord | None:
        if isinstance(candidate, L0CandidateRecord):
            payload = candidate.public_dict()
        elif isinstance(candidate, ExperienceRecord):
            payload = candidate.public_dict()
        elif isinstance(candidate, str):
            payload = {"content": candidate}
        elif isinstance(candidate, dict):
            payload = dict(candidate)
        else:
            return None
        content = str(payload.get("content") or "").strip()
        if not content:
            return None
        source_task_ids = self._normalise_ids(payload.get("source_task_ids"))
        source_rollout_ids = self._normalise_ids(payload.get("source_rollout_ids"))
        generator_version = str(payload.get("generator_version") or "l0-summary-v1")
        candidate_payload = {
            "id": "C0_pending_normalisation",
            "content": content,
            "source_task_ids": source_task_ids,
            "source_rollout_ids": source_rollout_ids,
            "source_evidence": payload.get("source_evidence", []),
            "domain": payload.get("domain"),
            "task_family": payload.get("task_family"),
            "failure_mode": payload.get("failure_mode", "unknown"),
            "strategy_type": payload.get("strategy_type"),
            "tool_type": payload.get("tool_type"),
            "task_stage": payload.get("task_stage", "unknown"),
            "step": step,
            "run_id": run_id if run_id is not None else payload.get("run_id"),
            "epoch": epoch if epoch is not None else payload.get("epoch"),
            "batch": batch if batch is not None else payload.get("batch"),
            "batch_fingerprint": (
                batch_fingerprint
                if batch_fingerprint is not None
                else payload.get("batch_fingerprint")
            ),
            "generator_version": generator_version,
        }
        record = L0CandidateRecord.model_validate(candidate_payload)
        candidate_id = stable_l0_candidate_id(
            record.content,
            source_task_ids=record.source_task_ids,
            source_rollout_ids=record.source_rollout_ids,
            identity_context=self._identity_context(record),
            generator_version=record.generator_version,
        )
        return record.model_copy(update={"id": candidate_id})

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
            if record.lifecycle_status != "active":
                continue
            for task_id in record.source_task_ids:
                counts[task_id] = counts.get(task_id, 0) + 1
        return counts

    def _process_legacy_l0(
        self,
        l0_candidates: Sequence[str | dict[str, Any] | ExperienceRecord],
        step: int,
    ) -> dict[str, int]:
        """Compatibility ingestion used only when candidate review is disabled."""

        candidates = [
            record
            for item in (l0_candidates or [])
            if (record := self._legacy_candidate_to_record(item))
        ]
        if not candidates:
            logger.info("L0 step %s: no candidates", step)
            return {"candidates": 0, "added": 0, "merged": 0, "skipped": 0}

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
            "Legacy L0 step %s: candidates=%d added=%d evidence_merged=%d task_limit_skipped=%d total=%d",
            step,
            len(candidates),
            added,
            merged,
            skipped,
            len(self._l0_records),
        )
        return {"candidates": len(candidates), "added": added, "merged": merged, "skipped": skipped}

    @staticmethod
    def _review_sort_key(candidate: ExperienceCandidateRecord) -> tuple[Any, ...]:
        return (
            candidate.step,
            candidate.level,
            tuple(candidate.source_task_ids),
            tuple(candidate.source_rollout_ids),
            candidate.id,
        )

    @staticmethod
    def _candidate_identity_payload(candidate: ExperienceCandidateRecord) -> dict[str, Any]:
        """Compatibility wrapper for the stable candidate identity payload."""

        return candidate_state.identity_payload(candidate)

    @staticmethod
    def _lexical_tokens(text: str) -> set[str]:
        return review_context.lexical_tokens(text)

    def _related_active_l0(
        self,
        candidate: ExperienceCandidateRecord,
    ) -> tuple[list[ExperienceRecord], str]:
        return review_context.related_active(
            candidate,
            self._store(candidate.level),
            embedding_provider=self.clusterer.embedding_provider,
            full_pool_limit=int(self._cfg("l0_review_full_pool_limit", 50)),
            top_k=int(self._cfg("l0_review_top_k", 12)),
            retrieval_method=self._cfg("l0_review_retrieval", "semantic"),
        )

    def _candidate_l0_review_view(
        self,
        candidate: L0CandidateRecord,
    ) -> tuple[dict[str, Any], set[str]]:
        """Return a bounded candidate prompt view without mutating persisted evidence."""

        return review_context.candidate_l0_review_view(
            candidate,
            rollout_limit=int(self._cfg("l0_review_rollout_evidence_per_candidate", 2)),
            source_id_limit=int(self._cfg("l0_review_source_ids_per_item", 32)),
            content_limit=int(self._cfg("l0_review_content_chars", 8000)),
        )

    @staticmethod
    def _bounded_source_ids(
        values: Sequence[str],
        limit: int,
        preferred: Sequence[str] = (),
    ) -> list[str]:
        """Bound provenance IDs while retaining detailed evidence references first."""

        return review_context.bounded_source_ids(values, limit, preferred)

    def _supporting_candidate_views(
        self,
        record: ExperienceRecord,
    ) -> list[dict[str, Any]]:
        """Build individually bounded prior-candidate evidence views."""

        return review_context.supporting_candidate_views(
            record,
            self._candidate_records,
            evidence_limit=int(self._cfg("l0_review_evidence_per_experience", 4)),
            rollout_limit=int(self._cfg("l0_review_rollout_evidence_per_candidate", 2)),
            source_id_limit=int(self._cfg("l0_review_source_ids_per_item", 32)),
            content_limit=int(self._cfg("l0_review_content_chars", 8000)),
            sort_key=self._review_sort_key,
        )

    def _related_l0_review_views(
        self,
        records: Sequence[ExperienceRecord],
    ) -> tuple[list[dict[str, Any]], set[str], list[ExperienceRecord]]:
        """Build the complete related-pool JSON under one exact global budget."""

        return review_context.related_l0_review_views(
            records,
            self._candidate_records,
            max_chars=int(self._cfg("l0_review_max_supporting_evidence_chars", 40000)),
            source_id_limit=int(self._cfg("l0_review_source_ids_per_item", 32)),
            content_limit=int(self._cfg("l0_review_content_chars", 8000)),
            evidence_limit=int(self._cfg("l0_review_evidence_per_experience", 4)),
            rollout_limit=int(self._cfg("l0_review_rollout_evidence_per_candidate", 2)),
            sort_key=self._review_sort_key,
        )

    def _related_l0_review_view(self, record: ExperienceRecord) -> dict[str, Any]:
        """Compatibility helper for inspecting one bounded active-L0 view."""

        return self._related_l0_review_views([record])[0][0]

    @staticmethod
    def _lower_level(level: ExperienceLevel) -> ExperienceLevel:
        if level == "L1":
            return "L0"
        if level == "L2":
            return "L1"
        raise ValueError("L0 candidates do not have hierarchical parents")

    def _source_records_for_candidate(
        self,
        candidate: ExperienceCandidateRecord,
    ) -> list[ExperienceRecord]:
        if candidate.level == "L0":
            return []
        source_store = self._store(self._lower_level(candidate.level))
        return [source_store[parent_id] for parent_id in candidate.parent_ids if parent_id in source_store]

    def _validate_candidate_sources_current(
        self,
        candidate: ExperienceCandidateRecord,
    ) -> list[ExperienceRecord]:
        if candidate.level == "L0":
            return []
        source_store = self._store(self._lower_level(candidate.level))
        missing = [parent_id for parent_id in candidate.parent_ids if parent_id not in source_store]
        if missing:
            raise StaleCandidateError(f"candidate source records no longer exist: {missing}")
        parents = [source_store[parent_id] for parent_id in candidate.parent_ids]
        inactive = [parent.id for parent in parents if parent.lifecycle_status != "active"]
        if inactive:
            raise StaleCandidateError(f"candidate source records are no longer active: {inactive}")
        current_versions = {
            parent.id: self._record_version_fingerprint(parent) for parent in parents
        }
        if current_versions != candidate.source_versions:
            raise StaleCandidateError("candidate source version fingerprint changed")
        current_source_fingerprint = self._source_fingerprint(candidate.level, current_versions)
        if current_source_fingerprint != candidate.source_fingerprint:
            raise StaleCandidateError("candidate source-set fingerprint changed")
        if not candidate.cluster_id:
            raise StaleCandidateError("candidate is missing its generation cluster ID")
        expected_generation_fingerprint = self._generation_fingerprint(
            candidate.level,
            current_source_fingerprint,
            candidate.cluster_id,
        )
        if candidate.generation_fingerprint != expected_generation_fingerprint:
            raise StaleCandidateError(
                "candidate generation contract changed (prompt, model, language, or configuration)"
            )
        try:
            AggregatedExperienceContent.model_validate(candidate.structured_content)
        except ValidationError as error:
            raise CandidateDecisionError(f"invalid persisted upper candidate content: {error}") from error
        return parents

    def _candidate_review_view(
        self,
        candidate: ExperienceCandidateRecord,
    ) -> tuple[dict[str, Any], set[str]]:
        if candidate.level == "L0":
            return self._candidate_l0_review_view(candidate)
        return review_context.upper_candidate_review_view(
            candidate,
            self._source_records_for_candidate(candidate),
            self._l0_records,
            content_limit=int(self._cfg("l0_review_content_chars", 8000)),
            source_id_limit=int(self._cfg("l0_review_source_ids_per_item", 32)),
        )

    def _related_review_views(
        self,
        candidate: ExperienceCandidateRecord,
        records: Sequence[ExperienceRecord],
    ) -> tuple[list[dict[str, Any]], set[str], list[ExperienceRecord]]:
        if candidate.level == "L0":
            return self._related_l0_review_views(records)
        return review_context.upper_related_review_views(
            candidate,
            records,
            self._store(self._lower_level(candidate.level)),
            max_chars=int(self._cfg("l0_review_max_supporting_evidence_chars", 40000)),
        )

    def _validate_review_decision(
        self,
        candidate: ExperienceCandidateRecord,
        decision: ExperienceReviewDecision,
        related: Sequence[ExperienceRecord],
        allowed_evidence_ids: set[str],
        displayed_candidate_source_ids: set[str],
    ) -> ExperienceReviewDecision:
        if decision.candidate_id != candidate.id:
            raise CandidateDecisionError(
                f"candidate_id mismatch: expected {candidate.id}, got {decision.candidate_id}"
            )
        if decision.level is not None and decision.level != candidate.level:
            raise CandidateDecisionError(
                f"candidate level mismatch: expected {candidate.level}, got {decision.level}"
            )
        if candidate.level != "L0" and decision.level != candidate.level:
            raise CandidateDecisionError(f"{candidate.level} review must declare its level")
        unexpected_evidence = sorted(set(decision.evidence_ids) - allowed_evidence_ids)
        if unexpected_evidence:
            raise CandidateDecisionError(f"unknown evidence_ids: {unexpected_evidence}")
        if decision.action in {"ADD", "UPDATE", "DELETE"} and not decision.evidence_ids:
            raise CandidateDecisionError(f"{decision.action} requires at least one supplied evidence ID")
        candidate_evidence_ids = {
            candidate.id,
            *candidate.source_task_ids,
            *candidate.source_rollout_ids,
            *candidate.parent_ids,
            *candidate.source_l0_ids,
            *candidate.source_l1_ids,
        }
        if decision.action in {"ADD", "UPDATE", "DELETE"} and not (
            set(decision.evidence_ids) & candidate_evidence_ids
        ):
            raise CandidateDecisionError(
                f"{decision.action} must cite the current candidate or one of its source IDs"
            )
        if (
            decision.action in {"ADD", "UPDATE", "DELETE"}
            and displayed_candidate_source_ids
            and not (set(decision.evidence_ids) & displayed_candidate_source_ids)
        ):
            evidence_kind = "rollout" if candidate.level == "L0" else "direct-source"
            raise CandidateDecisionError(
                f"{decision.action} must cite at least one displayed {evidence_kind} evidence ID"
            )

        related_ids = {record.id for record in related}
        target_version_fingerprint: str | None = None
        if decision.action in {"UPDATE", "DELETE"}:
            if decision.target_id not in related_ids:
                raise CandidateDecisionError("target_id was not included in the review comparison set")
            displayed_target = next(
                record for record in related if record.id == decision.target_id
            )
            target = self._store(candidate.level).get(str(decision.target_id))
            if target is None or target.lifecycle_status != "active":
                raise CandidateDecisionError(
                    f"target_id is not a current active {candidate.level} experience"
                )
            if self._record_version_fingerprint(target) != self._record_version_fingerprint(
                displayed_target
            ):
                raise StaleCandidateError("review target version changed during decision")
            target_version_fingerprint = self._record_version_fingerprint(displayed_target)
            if candidate.level != "L0" and target.id not in set(decision.evidence_ids):
                raise CandidateDecisionError(
                    f"{decision.action} must cite the displayed target experience"
                )
            for field_name in ("failure_mode", "task_stage"):
                candidate_value = self._known_metadata(getattr(candidate, field_name))
                target_value = self._known_metadata(getattr(target, field_name))
                if candidate_value and target_value and candidate_value != target_value:
                    raise CandidateDecisionError(
                        f"hard metadata mismatch for {field_name}: {candidate_value} != {target_value}"
                    )
        if candidate.level == "L0":
            if decision.new_structured_content is not None:
                raise CandidateDecisionError("L0 review must not return new_structured_content")
            if decision.action in {"ADD", "UPDATE"}:
                try:
                    validate_experience_output_language(
                        str(decision.new_content),
                        self.experience_output_language,
                        label="reviewed L0 experience",
                    )
                except ValueError as error:
                    raise CandidateDecisionError(str(error)) from error
            return decision.model_copy(
                update={"target_version_fingerprint": target_version_fingerprint}
            )
        if decision.action in {"ADD", "UPDATE"}:
            try:
                structured = AggregatedExperienceContent.model_validate(
                    decision.new_structured_content
                )
            except ValidationError as error:
                raise CandidateDecisionError(
                    f"{candidate.level} ADD/UPDATE requires valid structured content: {error}"
                ) from error
            try:
                validate_experience_output_language(
                    structured.render(),
                    self.experience_output_language,
                    label=f"reviewed {candidate.level} experience",
                )
            except ValueError as error:
                raise CandidateDecisionError(str(error)) from error
            # The validated structure is authoritative; persist one canonical
            # rendering so free-form text cannot bypass the aggregation schema.
            return decision.model_copy(
                update={
                    "level": candidate.level,
                    "target_version_fingerprint": target_version_fingerprint,
                    "new_content": structured.render(),
                    "new_structured_content": structured.model_dump(mode="json"),
                }
            )
        return decision.model_copy(
            update={"target_version_fingerprint": target_version_fingerprint}
        )

    def _experience_from_candidate(
        self,
        candidate: L0CandidateRecord,
        content: str,
        *,
        base: ExperienceRecord | None = None,
    ) -> ExperienceRecord:
        metadata: dict[str, Any] = {}
        for field_name in METADATA_FIELDS:
            candidate_value = getattr(candidate, field_name)
            if base is None:
                metadata[field_name] = candidate_value
                continue
            base_value = getattr(base, field_name)
            candidate_known = self._known_metadata(candidate_value)
            base_known = self._known_metadata(base_value)
            if candidate_known is None:
                metadata[field_name] = base_value
            elif base_known is None or candidate_known == base_known:
                metadata[field_name] = candidate_value
            else:
                # A revised experience now has evidence from both records. A
                # conflicting soft label is no longer a valid single label.
                metadata[field_name] = None
        source_task_ids = sorted(
            set(candidate.source_task_ids) | set(base.source_task_ids if base else [])
        )
        source_rollout_ids = sorted(
            set(candidate.source_rollout_ids) | set(base.source_rollout_ids if base else [])
        )
        provisional = ExperienceRecord(
            id="L0_pending_normalisation",
            level="L0",
            content=content,
            source_task_ids=source_task_ids,
            source_rollout_ids=source_rollout_ids,
            review_candidate_ids=sorted(
                set(base.review_candidate_ids if base else []) | {candidate.id}
            ),
            aggregation_status="pending",
            lifecycle_status="active",
            **metadata,
        )
        experience_id = stable_experience_id(
            "L0",
            content,
            identity_context=self._identity_context(provisional),
        )
        if base is None:
            return provisional.model_copy(
                update={"id": experience_id, "lineage_root_id": experience_id}
            )
        return provisional.model_copy(
            update={
                "id": experience_id,
                "revision_number": base.revision_number + 1,
                "lineage_root_id": base.lineage_root_id or base.id,
                "supersedes_id": base.id,
            }
        )

    def _upper_experience_from_candidate(
        self,
        candidate: ExperienceCandidateRecord,
        decision: ExperienceReviewDecision,
        *,
        base: ExperienceRecord | None = None,
    ) -> ExperienceRecord:
        if candidate.level == "L0":
            raise CandidateDecisionError("upper experience builder received an L0 candidate")
        structured = AggregatedExperienceContent.model_validate(
            decision.new_structured_content
        )
        lower_level = self._lower_level(candidate.level)
        source_store = self._store(lower_level)
        requested_ids = set(candidate.parent_ids)
        if base is not None:
            requested_ids.update(base.parent_ids)
        parents = [
            source_store[parent_id]
            for parent_id in sorted(requested_ids)
            if parent_id in source_store and source_store[parent_id].lifecycle_status == "active"
        ]
        active_parent_ids = {parent.id for parent in parents}
        missing_or_inactive = sorted(requested_ids - active_parent_ids)
        if missing_or_inactive:
            source_kind = "candidate or target" if base is not None else "candidate"
            raise StaleCandidateError(
                f"{source_kind} parents are missing or inactive: {missing_or_inactive}"
            )
        parent_ids = sorted(parent.id for parent in parents)
        source_versions = {
            parent.id: self._record_version_fingerprint(parent) for parent in parents
        }
        source_fingerprint = self._source_fingerprint(candidate.level, source_versions)
        source_l0_ids: list[str]
        source_l1_ids: list[str]
        if candidate.level == "L1":
            source_l0_ids = parent_ids
            source_l1_ids = []
        else:
            source_l1_ids = parent_ids
            source_l0_ids = sorted(
                {
                    source_id
                    for parent in parents
                    for source_id in (parent.source_l0_ids or parent.parent_ids)
                    if source_id in self._l0_records
                    and self._l0_records[source_id].lifecycle_status == "active"
                }
            )
        content = structured.render()
        metadata = {
            field_name: self._consensus(parents, field_name) for field_name in METADATA_FIELDS
        }
        provisional = ExperienceRecord(
            id=f"{candidate.level}_pending_normalisation",
            level=candidate.level,
            content=content,
            structured_content=structured,
            source_task_ids=sorted(
                {task_id for parent in parents for task_id in parent.source_task_ids}
            ),
            source_rollout_ids=sorted(
                {rollout_id for parent in parents for rollout_id in parent.source_rollout_ids}
            ),
            parent_ids=parent_ids,
            source_l0_ids=source_l0_ids,
            source_l1_ids=source_l1_ids,
            parent_version_fingerprints=source_versions,
            source_version_fingerprint=source_fingerprint,
            cluster_id=candidate.cluster_id,
            aggregation_status="terminal" if candidate.level == "L2" else "pending",
            lifecycle_status="active",
            review_candidate_ids=sorted(
                set(base.review_candidate_ids if base else []) | {candidate.id}
            ),
            **metadata,
        )
        experience_id = stable_experience_id(
            candidate.level,
            content,
            parent_ids,
            identity_context=[f"source_version_fingerprint={source_fingerprint}"],
        )
        if base is None:
            return provisional.model_copy(
                update={"id": experience_id, "lineage_root_id": experience_id}
            )
        return provisional.model_copy(
            update={
                "id": experience_id,
                "revision_number": base.revision_number + 1,
                "lineage_root_id": base.lineage_root_id or base.id,
                "supersedes_id": base.id,
            }
        )

    @staticmethod
    def _invalidate_l1_descendants(
        target_id: str,
        candidate_id: str,
        l2: dict[str, ExperienceRecord],
    ) -> list[str]:
        affected = sorted(
            exp_id
            for exp_id, record in l2.items()
            if target_id in set(record.parent_ids) | set(record.source_l1_ids)
        )
        for exp_id in affected:
            record = l2[exp_id]
            l2[exp_id] = record.model_copy(
                update={
                    "lifecycle_status": "needs_review",
                    "needs_review_reason": f"source L1 {target_id} was revised or deactivated",
                    "invalidated_by_ids": sorted(
                        set(record.invalidated_by_ids) | {target_id, candidate_id}
                    ),
                }
            )
        return affected

    @staticmethod
    def _reconcile_parent_statuses(
        lower_level: ExperienceLevel,
        parent_ids: Sequence[str],
        l0: dict[str, ExperienceRecord],
        l1: dict[str, ExperienceRecord],
        l2: dict[str, ExperienceRecord],
    ) -> None:
        lower = l0 if lower_level == "L0" else l1
        upper = l1 if lower_level == "L0" else l2
        for parent_id in sorted(set(parent_ids)):
            parent = lower.get(parent_id)
            if parent is None or parent.lifecycle_status != "active":
                continue
            consumers = sorted(
                (
                    child
                    for child in upper.values()
                    if child.lifecycle_status == "active"
                    and parent_id
                    in set(child.parent_ids)
                    | set(child.source_l0_ids if lower_level == "L0" else child.source_l1_ids)
                ),
                key=lambda child: child.id,
            )
            if len(consumers) > 1:
                raise CandidateDecisionError(
                    f"{lower_level} parent {parent_id} has multiple active upper consumers: "
                    f"{[child.id for child in consumers]}"
                )
            if consumers:
                child = consumers[0]
                lower[parent_id] = parent.model_copy(
                    update={
                        "aggregation_status": "aggregated",
                        "aggregated_into_cluster_id": child.cluster_id,
                        "aggregated_into_experience_id": child.id,
                    }
                )
            else:
                lower[parent_id] = parent.model_copy(
                    update={
                        "aggregation_status": "pending",
                        "aggregated_into_cluster_id": None,
                        "aggregated_into_experience_id": None,
                    }
                )

    @staticmethod
    def _invalidate_descendants(
        target_id: str,
        candidate_id: str,
        l0: dict[str, ExperienceRecord],
        l1: dict[str, ExperienceRecord],
        l2: dict[str, ExperienceRecord],
    ) -> tuple[list[str], list[str]]:
        affected_l1 = sorted(
            exp_id
            for exp_id, record in l1.items()
            if target_id in set(record.parent_ids) | set(record.source_l0_ids)
        )
        invalidators = [target_id, candidate_id]
        for exp_id in affected_l1:
            record = l1[exp_id]
            l1[exp_id] = record.model_copy(
                update={
                    "lifecycle_status": "needs_review",
                    "needs_review_reason": f"source L0 {target_id} was revised or deactivated",
                    "invalidated_by_ids": sorted(set(record.invalidated_by_ids) | set(invalidators)),
                }
            )
            for sibling_id in set(record.parent_ids) | set(record.source_l0_ids):
                sibling = l0.get(sibling_id)
                if sibling is not None and sibling.lifecycle_status == "active":
                    l0[sibling_id] = sibling.model_copy(
                        update={
                            "aggregation_status": "pending",
                            "aggregated_into_cluster_id": None,
                            "aggregated_into_experience_id": None,
                        }
                    )

        affected_l2 = sorted(
            exp_id
            for exp_id, record in l2.items()
            if target_id in record.source_l0_ids
            or bool(set(record.parent_ids) & set(affected_l1))
            or bool(set(record.source_l1_ids) & set(affected_l1))
        )
        for exp_id in affected_l2:
            record = l2[exp_id]
            l2[exp_id] = record.model_copy(
                update={
                    "lifecycle_status": "needs_review",
                    "needs_review_reason": f"ancestor L0 {target_id} was revised or deactivated",
                    "invalidated_by_ids": sorted(set(record.invalidated_by_ids) | set(invalidators)),
                }
            )
            for sibling_id in set(record.parent_ids) | set(record.source_l1_ids):
                sibling = l1.get(sibling_id)
                if sibling is not None and sibling.lifecycle_status == "active":
                    l1[sibling_id] = sibling.model_copy(
                        update={
                            "aggregation_status": "pending",
                            "aggregated_into_cluster_id": None,
                            "aggregated_into_experience_id": None,
                        }
                    )
        return affected_l1, affected_l2

    def _enforce_l0_capacity(
        self,
        record: ExperienceRecord,
        *,
        replacing_id: str | None = None,
    ) -> None:
        limit = int(self._cfg("max_l0_per_problem", 0))
        if limit <= 0 or not record.source_task_ids:
            return
        counts = self._task_counts()
        replaced = self._l0_records.get(replacing_id) if replacing_id else None
        if replaced is not None:
            for task_id in replaced.source_task_ids:
                counts[task_id] = max(0, counts.get(task_id, 0) - 1)
        exceeded = sorted(
            task_id for task_id in record.source_task_ids if counts.get(task_id, 0) >= limit
        )
        if exceeded:
            raise CandidateDecisionError(
                f"action would exceed max_l0_per_problem={limit} for {exceeded}; "
                "candidate remains retryable"
            )

    def _commit_review_decision(
        self,
        candidate: ExperienceCandidateRecord,
        decision: ExperienceReviewDecision,
    ) -> None:
        if candidate.level != "L0":
            self._commit_upper_review_decision(candidate, decision)
            return
        candidates = {
            key: value.model_copy(deep=True) for key, value in self._candidate_records.items()
        }
        l0 = {key: value.model_copy(deep=True) for key, value in self._l0_records.items()}
        archive = {key: value.model_copy(deep=True) for key, value in self._l0_archive.items()}
        l1 = {key: value.model_copy(deep=True) for key, value in self._l1_records.items()}
        l1_archive = {key: value.model_copy(deep=True) for key, value in self._l1_archive.items()}
        l2 = {key: value.model_copy(deep=True) for key, value in self._l2_records.items()}
        l2_archive = {key: value.model_copy(deep=True) for key, value in self._l2_archive.items()}
        result_id: str | None = None

        if decision.action == "ADD":
            new_record = self._experience_from_candidate(candidate, str(decision.new_content))
            self._enforce_l0_capacity(new_record)
            if new_record.id in l0 or new_record.id in archive:
                raise CandidateDecisionError(
                    "ADD content already exists in the active pool or archive; return KEEP or UPDATE"
                )
            l0[new_record.id] = new_record
            result_id = new_record.id
        elif decision.action in {"UPDATE", "DELETE"}:
            target_id = str(decision.target_id)
            target = l0.get(target_id)
            if target is None or target.lifecycle_status != "active":
                raise CandidateDecisionError("review target is no longer active")
            if (
                not decision.target_version_fingerprint
                or self._record_version_fingerprint(target)
                != decision.target_version_fingerprint
            ):
                raise StaleCandidateError("review target version changed before commit")
            archived = target.model_copy(
                update={
                    "lifecycle_status": "inactive",
                    "archived_at": self._utc_now(),
                    "archive_reason": decision.reason,
                    "invalidated_by_ids": sorted(
                        set(target.invalidated_by_ids) | {candidate.id}
                    ),
                }
            )
            if decision.action == "UPDATE":
                replacement = self._experience_from_candidate(
                    candidate,
                    str(decision.new_content),
                    base=target,
                )
                self._enforce_l0_capacity(replacement, replacing_id=target_id)
                if replacement.id == target.id:
                    raise CandidateDecisionError("UPDATE must materially change normalized content")
                if replacement.id in l0 or replacement.id in archive:
                    raise CandidateDecisionError("UPDATE would collide with an existing experience version")
                archived = archived.model_copy(update={"superseded_by_id": replacement.id})
                l0[replacement.id] = replacement
                result_id = replacement.id
            del l0[target_id]
            archive[target_id] = archived
            affected_l1, affected_l2 = self._invalidate_descendants(
                target_id, candidate.id, l0, l1, l2
            )
            self._reconcile_parent_statuses(
                "L0",
                sorted(
                    {
                        parent_id
                        for l1_id in affected_l1
                        for parent_id in l1[l1_id].parent_ids
                    }
                ),
                l0,
                l1,
                l2,
            )
            self._reconcile_parent_statuses(
                "L1",
                sorted(
                    {
                        parent_id
                        for l2_id in affected_l2
                        for parent_id in l2[l2_id].parent_ids
                    }
                ),
                l0,
                l1,
                l2,
            )

        candidates[candidate.id] = candidate.model_copy(
            update={
                "status": "committed",
                "attempt_count": candidate.attempt_count + 1,
                "last_error": None,
                "review_decision": decision,
                "resolution": (
                    "adopted" if decision.action in {"ADD", "UPDATE"} else "not_adopted"
                ),
                "result_experience_id": result_id,
                "reviewed_at": self._utc_now(),
            }
        )
        self._write_state(
            l0,
            l1,
            l2,
            candidates,
            archive,
            l1_archive,
            l2_archive,
        )
        self._candidate_records = candidates
        self._l0_records = l0
        self._l0_archive = archive
        self._l1_records = l1
        self._l2_records = l2

    def _commit_upper_review_decision(
        self,
        candidate: ExperienceCandidateRecord,
        decision: ExperienceReviewDecision,
    ) -> None:
        self._validate_candidate_sources_current(candidate)
        candidates = {
            key: value.model_copy(deep=True) for key, value in self._candidate_records.items()
        }
        l0 = {key: value.model_copy(deep=True) for key, value in self._l0_records.items()}
        l1 = {key: value.model_copy(deep=True) for key, value in self._l1_records.items()}
        l2 = {key: value.model_copy(deep=True) for key, value in self._l2_records.items()}
        l0_archive = {key: value.model_copy(deep=True) for key, value in self._l0_archive.items()}
        l1_archive = {key: value.model_copy(deep=True) for key, value in self._l1_archive.items()}
        l2_archive = {key: value.model_copy(deep=True) for key, value in self._l2_archive.items()}
        stores = {"L0": l0, "L1": l1, "L2": l2}
        archives = {"L0": l0_archive, "L1": l1_archive, "L2": l2_archive}
        target_store = stores[candidate.level]
        target_archive = archives[candidate.level]
        lower_level = self._lower_level(candidate.level)
        lower_store = stores[lower_level]
        result_id: str | None = None
        affected_parent_ids: set[str] = set()
        affected_l2_ids: list[str] = []

        if decision.action in {"ADD", "UPDATE"}:
            permitted_consumer = str(decision.target_id) if decision.action == "UPDATE" else None
            consumed_elsewhere = [
                parent_id
                for parent_id in candidate.parent_ids
                if not (
                    lower_store[parent_id].aggregation_status == "pending"
                    and lower_store[parent_id].aggregated_into_experience_id is None
                )
                and not (
                    permitted_consumer is not None
                    and lower_store[parent_id].aggregation_status == "aggregated"
                    and lower_store[parent_id].aggregated_into_experience_id
                    == permitted_consumer
                )
            ]
            if consumed_elsewhere:
                raise CandidateDecisionError(
                    "candidate parents are not unconsumed or owned by the UPDATE target: "
                    f"{consumed_elsewhere}"
                )

        if decision.action == "ADD":
            new_record = self._upper_experience_from_candidate(candidate, decision)
            max_total = int(
                self._cfg("max_l1_total", 50)
                if candidate.level == "L1"
                else self._cfg("max_l2_total", 10)
            )
            active_total = sum(
                record.lifecycle_status == "active" for record in target_store.values()
            )
            if max_total > 0 and active_total >= max_total:
                raise CandidateDecisionError(f"{candidate.level} capacity {max_total} reached")
            if new_record.id in target_store or new_record.id in target_archive:
                raise CandidateDecisionError(
                    "ADD content/source version already exists; return KEEP or UPDATE"
                )
            target_store[new_record.id] = new_record
            affected_parent_ids.update(new_record.parent_ids)
            result_id = new_record.id
        elif decision.action in {"UPDATE", "DELETE"}:
            target_id = str(decision.target_id)
            target = target_store.get(target_id)
            if target is None or target.lifecycle_status != "active":
                raise CandidateDecisionError("review target is no longer active")
            if (
                not decision.target_version_fingerprint
                or self._record_version_fingerprint(target)
                != decision.target_version_fingerprint
            ):
                raise StaleCandidateError("review target version changed before commit")
            affected_parent_ids.update(target.parent_ids)
            archived = target.model_copy(
                update={
                    "lifecycle_status": "inactive",
                    "archived_at": self._utc_now(),
                    "archive_reason": decision.reason,
                    "invalidated_by_ids": sorted(
                        set(target.invalidated_by_ids) | {candidate.id}
                    ),
                }
            )
            if decision.action == "UPDATE":
                replacement = self._upper_experience_from_candidate(
                    candidate,
                    decision,
                    base=target,
                )
                if replacement.id == target.id:
                    raise CandidateDecisionError("UPDATE must materially change content or sources")
                if replacement.id in target_store or replacement.id in target_archive:
                    raise CandidateDecisionError("UPDATE would collide with an existing version")
                archived = archived.model_copy(update={"superseded_by_id": replacement.id})
                target_store[replacement.id] = replacement
                affected_parent_ids.update(replacement.parent_ids)
                result_id = replacement.id
            del target_store[target_id]
            target_archive[target_id] = archived
            if candidate.level == "L1":
                affected_l2_ids = self._invalidate_l1_descendants(
                    target_id,
                    candidate.id,
                    l2,
                )

        if decision.action in {"ADD", "UPDATE"}:
            self._reconcile_parent_statuses(
                lower_level,
                sorted(affected_parent_ids),
                l0,
                l1,
                l2,
            )
        elif decision.action == "DELETE":
            self._reconcile_parent_statuses(
                lower_level,
                sorted(affected_parent_ids),
                l0,
                l1,
                l2,
            )
        if affected_l2_ids:
            invalidated_l2_parent_ids = {
                parent_id
                for l2_id in affected_l2_ids
                for parent_id in l2[l2_id].parent_ids
            }
            self._reconcile_parent_statuses(
                "L1",
                sorted(invalidated_l2_parent_ids),
                l0,
                l1,
                l2,
            )

        candidates[candidate.id] = candidate.model_copy(
            update={
                "status": "committed",
                "attempt_count": candidate.attempt_count + 1,
                "last_error": None,
                "review_decision": decision,
                "resolution": (
                    "adopted" if decision.action in {"ADD", "UPDATE"} else "not_adopted"
                ),
                "result_experience_id": result_id,
                "reviewed_at": self._utc_now(),
            }
        )
        self._write_state(
            l0,
            l1,
            l2,
            candidates,
            l0_archive,
            l1_archive,
            l2_archive,
        )
        self._candidate_records = candidates
        self._l0_records, self._l1_records, self._l2_records = l0, l1, l2
        self._l0_archive, self._l1_archive, self._l2_archive = (
            l0_archive,
            l1_archive,
            l2_archive,
        )

    def _record_candidate_failure(
        self,
        candidate: ExperienceCandidateRecord,
        error: Exception,
        *,
        stale: bool = False,
    ) -> None:
        candidates = {
            key: value.model_copy(deep=True) for key, value in self._candidate_records.items()
        }
        current = candidates.get(candidate.id)
        if current is None or current.status == "committed":
            return
        candidates[candidate.id] = current.model_copy(
            update={
                "status": "stale" if stale else "review_failed",
                "attempt_count": current.attempt_count + 1,
                "last_error": str(error),
                "review_decision": None,
                "result_experience_id": None,
                "reviewed_at": None,
            }
        )
        try:
            self._write_state(
                self._l0_records,
                self._l1_records,
                self._l2_records,
                candidates,
                self._l0_archive,
                self._l1_archive,
                self._l2_archive,
            )
        except Exception as write_error:  # noqa: BLE001
            logger.error(
                "Could not persist review failure for candidate %s; prior pending state remains: %s",
                candidate.id,
                write_error,
            )
            return
        self._candidate_records = candidates

    async def review_pending_candidates(
        self,
        *,
        force_candidate_ids: Sequence[str] | None = None,
        candidate_level: ExperienceLevel | None = None,
    ) -> dict[str, int]:
        """Review retryable candidates one at a time in a stable order."""

        counts = {"committed": 0, "failed": 0, "stale": 0, "skipped": 0}
        forced = set(force_candidate_ids or [])
        async with self._review_lock:
            max_attempts = int(self._cfg("l0_review_max_attempts", 3))
            queue = sorted(
                (
                    candidate
                    for candidate in self._candidate_records.values()
                    if candidate.status in {"pending", "review_failed"}
                    and (candidate_level is None or candidate.level == candidate_level)
                    and (not forced or candidate.id in forced)
                ),
                key=self._review_sort_key,
            )
            for queued_candidate in queue:
                candidate = self._candidate_records.get(queued_candidate.id)
                if candidate is None or candidate.status == "committed":
                    counts["skipped"] += 1
                    continue
                if self._candidate_review_threshold_is_gated(candidate.level):
                    counts["skipped"] += 1
                    logger.warning(
                        "%s candidate %s review skipped: its source-level similarity "
                        "threshold is provisional",
                        candidate.level,
                        candidate.id,
                    )
                    continue
                if (
                    candidate.id not in forced
                    and max_attempts > 0
                    and candidate.attempt_count >= max_attempts
                ):
                    counts["skipped"] += 1
                    continue
                try:
                    self._validate_candidate_sources_current(candidate)
                    related, comparison_scope = self._related_active_l0(candidate)
                    candidate_view, displayed_candidate_source_ids = self._candidate_review_view(
                        candidate
                    )
                    (
                        related_views,
                        related_evidence_ids,
                        displayed_related,
                    ) = self._related_review_views(candidate, related)
                    if len(displayed_related) < len(related):
                        comparison_scope = (
                            f"{comparison_scope};prompt_budget_displayed="
                            f"{len(displayed_related)}_of_{len(related)}"
                        )
                    allowed_evidence_ids = {
                        candidate.id,
                        *candidate_view.get("source_task_ids", []),
                        *candidate_view.get("source_rollout_ids", []),
                        *candidate.parent_ids,
                        *candidate.source_l0_ids,
                        *candidate.source_l1_ids,
                        *related_evidence_ids,
                    }
                    review_kwargs = {
                        "candidate_view": candidate_view,
                        "allowed_evidence_ids": sorted(allowed_evidence_ids),
                        "comparison_scope": comparison_scope,
                        "model_params": self.model_params,
                        "temperature": float(self._cfg("l0_review_temperature", 0.0)),
                        "experience_output_language_instruction": (
                            self.experience_output_language_instruction
                        ),
                    }
                    if candidate.level == "L0":
                        decision = await review_l0_candidate(
                            self.llm,
                            self.prompts,
                            self.agent_objective,
                            self.learning_objective,
                            candidate,
                            related_views,
                            **review_kwargs,
                        )
                    else:
                        decision = await review_experience_candidate(
                            self.llm,
                            self.prompts,
                            self.agent_objective,
                            self.learning_objective,
                            candidate,
                            related_views,
                            prompt_name=self._review_prompt_name(candidate.level),
                            **review_kwargs,
                        )
                    decision = self._validate_review_decision(
                        candidate,
                        decision,
                        displayed_related,
                        allowed_evidence_ids,
                        displayed_candidate_source_ids,
                    )
                    self._commit_review_decision(candidate, decision)
                    counts["committed"] += 1
                    logger.info(
                        "Committed %s candidate review candidate=%s action=%s target=%s result=%s",
                        candidate.level,
                        candidate.id,
                        decision.action,
                        decision.target_id,
                        self._candidate_records[candidate.id].result_experience_id,
                    )
                except StaleCandidateError as error:
                    self._record_candidate_failure(candidate, error, stale=True)
                    counts["stale"] += 1
                    logger.warning("%s candidate %s is stale: %s", candidate.level, candidate.id, error)
                except Exception as error:  # noqa: BLE001
                    self._record_candidate_failure(candidate, error)
                    counts["failed"] += 1
                    logger.warning(
                        "%s candidate %s remains retryable: %s",
                        candidate.level,
                        candidate.id,
                        error,
                    )
        return counts

    async def retry_candidate(self, candidate_id: str) -> dict[str, int]:
        """Explicitly retry one failed/pending candidate, even after its auto limit."""

        candidate = self._candidate_records.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate.status in {"committed", "stale"}:
            return {"committed": 0, "failed": 0, "stale": 0, "skipped": 1}
        return await self.review_pending_candidates(
            force_candidate_ids=[candidate_id],
            candidate_level=candidate.level,
        )

    async def process_step_experiences(
        self,
        l0_candidates: Sequence[str | dict[str, Any] | ExperienceRecord | L0CandidateRecord],
        step: int,
        *,
        run_id: str | None = None,
        epoch: int | None = None,
        batch: int | None = None,
        batch_fingerprint: str | None = None,
    ) -> dict[str, int]:
        if not self._cfg("l0_candidate_review_enabled", False):
            return self._process_legacy_l0(l0_candidates, step)

        candidates = [
            record
            for item in (l0_candidates or [])
            if (
                record := self._candidate_from_input(
                    item,
                    step,
                    run_id=run_id,
                    epoch=epoch,
                    batch=batch,
                    batch_fingerprint=batch_fingerprint,
                )
            )
        ]
        staged = 0
        duplicate = 0
        if candidates:
            updated_candidates = {
                key: value.model_copy(deep=True)
                for key, value in self._candidate_records.items()
            }
            for candidate in sorted(candidates, key=self._review_sort_key):
                existing = updated_candidates.get(candidate.id)
                if existing is not None:
                    if not candidate_state.same_identity(existing, candidate):
                        raise CandidateDecisionError(
                            f"candidate ID collision with different immutable evidence: {candidate.id}"
                        )
                    duplicate += 1
                    continue
                updated_candidates[candidate.id] = candidate
                staged += 1
            if staged:
                self._write_state(
                    self._l0_records,
                    self._l1_records,
                    self._l2_records,
                    updated_candidates,
                    self._l0_archive,
                )
                self._candidate_records = updated_candidates

        review_counts = await self.review_pending_candidates(candidate_level="L0")
        logger.info(
            "L0 candidate step %s: received=%d staged=%d duplicate=%d committed=%d failed=%d skipped=%d active=%d",
            step,
            len(candidates),
            staged,
            duplicate,
            review_counts["committed"],
            review_counts["failed"],
            review_counts["skipped"],
            len(self._l0_records),
        )
        logger.info(
            "L0 metadata coverage after step %s: %s",
            step,
            json.dumps(self._metadata_coverage(list(self._l0_records.values())), sort_keys=True),
        )
        return {
            "received": len(candidates),
            "staged": staged,
            "duplicate": duplicate,
            **review_counts,
        }

    # ------------------------------------------------------------------
    # Clustered aggregation
    # ------------------------------------------------------------------

    def _pending(self, level: ExperienceLevel) -> list[ExperienceRecord]:
        return [
            record
            for record in self._store(level).values()
            if record.lifecycle_status == "active" and record.aggregation_status == "pending"
        ]

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
        return aggregation.cluster_pending(
            self.clusterer,
            pending,
            level=level,
            minimum_size=minimum_size,
            similarity_threshold=similarity_threshold,
            clustering_enabled=self._cfg("clustering_enabled", True),
        )

    @staticmethod
    def _consensus(records: Sequence[ExperienceRecord], field_name: str) -> str | None:
        return aggregation.consensus(records, field_name)

    def _make_child(
        self,
        target_level: ExperienceLevel,
        parents: Sequence[ExperienceRecord],
        cluster: ExperienceCluster,
        result: AggregatedExperienceContent,
    ) -> ExperienceRecord:
        return aggregation.make_child(
            target_level,
            parents,
            cluster,
            result,
            metadata_fields=METADATA_FIELDS,
            record_version_fingerprint=self._record_version_fingerprint,
            source_fingerprint=self._source_fingerprint,
        )

    def _make_upper_candidate(
        self,
        child: ExperienceRecord,
        cluster: ExperienceCluster,
        *,
        epoch: int,
    ) -> ExperienceCandidateRecord:
        return aggregation.make_upper_candidate(
            child,
            cluster,
            epoch=epoch,
            generator_version=UPPER_CANDIDATE_GENERATOR_VERSION,
            generation_fingerprint=self._generation_fingerprint,
            source_fingerprint=self._source_fingerprint,
            identity_context=self._identity_context,
        )

    def _candidate_for_generation(
        self,
        level: ExperienceLevel,
        generation_fingerprint: str,
    ) -> ExperienceCandidateRecord | None:
        try:
            return candidate_state.find_by_generation(
                self._candidate_records,
                level,
                generation_fingerprint,
                sort_key=self._review_sort_key,
            )
        except ValueError as error:
            raise AggregationError(str(error)) from error

    def _stage_upper_candidate(
        self,
        candidate: ExperienceCandidateRecord,
    ) -> tuple[ExperienceCandidateRecord, bool]:
        existing_by_generation = self._candidate_for_generation(
            candidate.level,
            str(candidate.generation_fingerprint),
        )
        if existing_by_generation is not None:
            if not candidate_state.same_identity(existing_by_generation, candidate):
                # The same deterministic aggregation input must never silently
                # acquire a second model output.
                raise AggregationError(
                    "generation fingerprint already exists with a different candidate payload"
                )
            return existing_by_generation, False
        existing = self._candidate_records.get(candidate.id)
        if existing is not None:
            if not candidate_state.same_identity(existing, candidate):
                raise AggregationError(f"conflicting duplicate candidate ID: {candidate.id}")
            return existing, False
        candidates = {
            key: value.model_copy(deep=True) for key, value in self._candidate_records.items()
        }
        candidates[candidate.id] = candidate
        self._write_state(
            self._l0_records,
            self._l1_records,
            self._l2_records,
            candidates,
            self._l0_archive,
            self._l1_archive,
            self._l2_archive,
        )
        self._candidate_records = candidates
        return candidate, True

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
        max_total = int(self._cfg("max_l1_total", 50) if target_level == "L1" else self._cfg("max_l2_total", 10))
        try:
            aggregation.commit_child(
                stores,
                source_level,
                target_level,
                child,
                parent_ids,
                max_total=max_total,
            )
        except RuntimeError as error:
            raise AggregationError(str(error)) from error
        self._write_state(
            l0,
            l1,
            l2,
            self._candidate_records,
            self._l0_archive,
            self._l1_archive,
            self._l2_archive,
        )
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

    @staticmethod
    def _aggregation_attempt_summary(attempts: Sequence[dict[str, Any]]) -> dict[str, int]:
        return aggregation.aggregation_attempt_summary(attempts)

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
        admission_mode = (
            "candidate_review" if self._upper_review_enabled(target_level) else "direct_legacy"
        )
        pending = self._pending(source_level)
        retryable_candidate_ids = (
            sorted(
                candidate.id
                for candidate in self._candidate_records.values()
                if candidate.level == target_level
                and candidate.status in {"pending", "review_failed"}
            )
            if admission_mode == "candidate_review"
            else []
        )
        if not pending and not retryable_candidate_ids:
            logger.info("%s->%s epoch %s: no pending experiences", source_level, target_level, epoch)
            return
        # A candidate persisted during an explicitly allowed dry run must not
        # bypass a restored calibration gate after restart. Gate the complete
        # level transition before any review can mutate the active pool.
        if (
            self._cfg("clustering_enabled", True)
            and self._similarity_threshold_is_provisional(source_level)
            and not self._cfg("allow_provisional_aggregation", False)
        ):
            threshold_field = f"{source_level.lower()}_similarity_threshold"
            logger.warning(
                "%s->%s aggregation skipped: %s is provisional; "
                "collect training %s and run calibration first",
                source_level,
                target_level,
                threshold_field,
                source_level,
            )
            self._append_audit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "epoch": epoch,
                    "source_level": source_level,
                    "target_level": target_level,
                    "admission_mode": admission_mode,
                    "status": "waiting_for_threshold_calibration",
                    "calibration_level": source_level,
                    "threshold_config_field": threshold_field,
                    "similarity_threshold": similarity_threshold,
                    "pending_candidate_ids": retryable_candidate_ids,
                    "pending_experience_ids": sorted(record.id for record in pending),
                }
            )
            return
        attempts: list[dict[str, Any]] = []
        preexisting_candidate_ids = set(retryable_candidate_ids)
        preexisting_review_counts: dict[str, int] | None = None
        if admission_mode == "candidate_review":
            preexisting_review_counts = await self.review_pending_candidates(
                candidate_level=target_level
            )
            for candidate_id in retryable_candidate_ids:
                reviewed = self._candidate_records.get(candidate_id)
                if reviewed is None:
                    continue
                attempts.append(
                    {
                        "status": "preexisting_candidate_review",
                        "candidate_id": reviewed.id,
                        "candidate_status": reviewed.status,
                        "candidate_resolution": reviewed.resolution,
                        "review_action": (
                            reviewed.review_decision.action
                            if reviewed.review_decision
                            else None
                        ),
                        "result_experience_id": reviewed.result_experience_id,
                        "experience_ids": reviewed.parent_ids,
                    }
                )
        # A recovered candidate may have committed and covered all previously
        # pending parents, so refresh after review before generating anything.
        pending = self._pending(source_level)
        if not pending:
            logger.info(
                "%s->%s epoch %s: no pending experiences after candidate recovery",
                source_level,
                target_level,
                epoch,
            )
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
            source_versions = {
                parent.id: self._record_version_fingerprint(parent) for parent in parents
            }
            source_fingerprint = self._source_fingerprint(target_level, source_versions)
            generation_fingerprint = self._generation_fingerprint(
                target_level,
                source_fingerprint,
                cluster.cluster_id,
            )
            if admission_mode == "candidate_review":
                existing_candidate = self._candidate_for_generation(
                    target_level,
                    generation_fingerprint,
                )
                if existing_candidate is not None:
                    if existing_candidate.id not in preexisting_candidate_ids:
                        attempts.append(
                            {
                                "cluster_id": cluster.cluster_id,
                                "experience_ids": cluster.experience_ids,
                                "status": "candidate_already_recorded",
                                "candidate_id": existing_candidate.id,
                                "candidate_status": existing_candidate.status,
                                "candidate_resolution": existing_candidate.resolution,
                            }
                        )
                    continue
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
                if admission_mode == "candidate_review":
                    candidate, staged = self._stage_upper_candidate(
                        self._make_upper_candidate(child, cluster, epoch=epoch)
                    )
                    attempts.append(
                        {
                            "cluster_id": cluster.cluster_id,
                            "experience_ids": cluster.experience_ids,
                            "status": "candidate_staged" if staged else "candidate_already_recorded",
                            "candidate_id": candidate.id,
                            "parent_ids": candidate.parent_ids,
                        }
                    )
                    logger.info(
                        "Staged %s candidate=%s parents=%s; parents remain pending until review",
                        target_level,
                        candidate.id,
                        candidate.parent_ids,
                    )
                else:
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

        post_generation_review_counts: dict[str, int] | None = None
        if admission_mode == "candidate_review":
            post_generation_review_counts = await self.review_pending_candidates(
                candidate_level=target_level
            )
            for attempt in attempts:
                candidate_id = attempt.get("candidate_id")
                if not candidate_id or candidate_id not in self._candidate_records:
                    continue
                reviewed = self._candidate_records[candidate_id]
                attempt["candidate_status"] = reviewed.status
                attempt["candidate_resolution"] = reviewed.resolution
                attempt["review_action"] = (
                    reviewed.review_decision.action if reviewed.review_decision else None
                )
                attempt["result_experience_id"] = reviewed.result_experience_id

        remaining_pending = sorted(record.id for record in self._pending(source_level))
        summary = self._aggregation_attempt_summary(attempts)
        self._append_audit(
            {
                "schema_version": SCHEMA_VERSION,
                "epoch": epoch,
                "source_level": source_level,
                "target_level": target_level,
                "clustering_enabled": self._cfg("clustering_enabled", True),
                "admission_mode": admission_mode,
                "minimum_size": minimum_size,
                "report": report.as_dict(),
                "aggregation_attempts": attempts,
                "preexisting_candidate_review": preexisting_review_counts,
                "post_generation_candidate_review": post_generation_review_counts,
                "aggregation_summary": summary,
                "pending_experience_ids": remaining_pending,
            }
        )
        logger.info(
            "%s->%s epoch %s: successes=%d direct=%d adopted=%d "
            "not_adopted=%d failures=%d generation_failed=%d review_failed=%d pending=%d",
            source_level,
            target_level,
            epoch,
            summary["direct_success"] + summary["adopted"],
            summary["direct_success"],
            summary["adopted"],
            summary["not_adopted"],
            summary["generation_failed"] + summary["review_failed"],
            summary["generation_failed"],
            summary["review_failed"],
            len(remaining_pending),
        )

    async def aggregate_epoch(self, epoch: int) -> None:
        await self.aggregate_levels(("L1", "L2"), epoch=epoch)
        logger.info(
            "Epoch %s hierarchy: L0=%d L1=%d L2=%d",
            epoch,
            len(self._l0_records),
            len(self._l1_records),
            len(self._l2_records),
        )

    async def aggregate_levels(
        self,
        targets: Sequence[AggregationTarget],
        *,
        epoch: int,
    ) -> None:
        """Aggregate only the requested upper levels, in hierarchy order.

        This is the public continuation API for an already persisted hierarchy.
        Selecting ``L2`` alone never creates L1 first; selecting both always
        processes and reviews L1 before inspecting the resulting active L1 pool.
        Threshold gates remain enforced by each underlying level operation.
        """

        requested = list(targets)
        invalid = sorted({str(target) for target in requested} - {"L1", "L2"})
        if invalid:
            raise ValueError(f"Unsupported aggregation target(s): {', '.join(invalid)}")
        if len(requested) != len(set(requested)):
            raise ValueError("Aggregation targets must not contain duplicates")
        if "L1" in requested:
            await self._aggregate_l1(epoch=epoch)
        if "L2" in requested:
            await self._aggregate_l2(epoch=epoch)

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
            experience_output_language_instruction=(
                self.experience_output_language_instruction
            ),
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
        result = self._parse_aggregation_response(response)
        try:
            validate_experience_output_language(
                result.render(),
                self.experience_output_language,
                label="generated hierarchical experience candidate",
            )
        except ValueError as error:
            raise AggregationError(str(error)) from error
        return result

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
        return {
            exp_id: record.content
            for exp_id, record in self._l0_records.items()
            if record.lifecycle_status == "active"
        }

    @property
    def l1(self) -> dict[str, str]:
        return {
            exp_id: record.content
            for exp_id, record in self._l1_records.items()
            if record.lifecycle_status == "active"
        }

    @property
    def l2(self) -> dict[str, str]:
        return {
            exp_id: record.content
            for exp_id, record in self._l2_records.items()
            if record.lifecycle_status == "active"
        }

    def get_all_l0_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l0_records)

    def get_all_l1_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l1_records)

    def get_all_l2_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l2_records)

    def get_recent_l0_experiences(self, limit: int) -> list[dict[str, Any]]:
        items = self.get_all_l0_experiences()
        return items[-limit:] if limit > 0 else []

    @staticmethod
    def _injectable(records: dict[str, ExperienceRecord]) -> list[dict[str, Any]]:
        active = {
            exp_id: record
            for exp_id, record in records.items()
            if record.lifecycle_status == "active"
        }
        return HierarchicalExperienceManager._ordered_records(active)

    def get_injectable_l0_experiences(self) -> list[dict[str, Any]]:
        return self._injectable(self._l0_records)

    def get_injectable_l1_experiences(self) -> list[dict[str, Any]]:
        return self._injectable(self._l1_records)

    def get_injectable_l2_experiences(self) -> list[dict[str, Any]]:
        return self._injectable(self._l2_records)

    def get_recent_injectable_l0_experiences(self, limit: int) -> list[dict[str, Any]]:
        items = self.get_injectable_l0_experiences()
        return items[-limit:] if limit > 0 else []

    def get_injectable_experience_pool(self) -> dict[str, str]:
        """Return the sole hierarchy-backed view used by subsequent rollouts."""

        records = (
            self.get_injectable_l2_experiences()
            + self.get_injectable_l1_experiences()
            + self.get_injectable_l0_experiences()
        )
        return {record["id"]: record["content"] for record in records}

    def get_l0_candidates(self) -> list[dict[str, Any]]:
        return self._ordered_candidates(
            {
                candidate_id: candidate
                for candidate_id, candidate in self._candidate_records.items()
                if candidate.level == "L0"
            }
        )

    def get_candidates(self, level: ExperienceLevel) -> list[dict[str, Any]]:
        """Return persisted candidates for one level, including terminal review states."""

        return self._ordered_candidates(
            {
                candidate_id: candidate
                for candidate_id, candidate in self._candidate_records.items()
                if candidate.level == level
            }
        )

    def get_l0_candidate_inputs_for_step(
        self,
        step: int,
        *,
        run_id: str | None = None,
        epoch: int | None = None,
        batch: int | None = None,
        batch_fingerprint: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the exact raw inputs needed to replay one persisted review step.

        The hierarchy snapshot is authoritative over the auxiliary database
        cache.  Exposing only immutable candidate input fields prevents a
        restart from accidentally replaying persisted review status as input.
        """

        input_fields = (
            "content",
            "source_task_ids",
            "source_rollout_ids",
            "source_evidence",
            "domain",
            "task_family",
            "failure_mode",
            "strategy_type",
            "tool_type",
            "task_stage",
            "generator_version",
            "run_id",
            "epoch",
            "batch",
            "batch_fingerprint",
        )
        complete_context = all(
            value is not None for value in (run_id, epoch, batch, batch_fingerprint)
        )

        def matches(candidate: ExperienceCandidateRecord) -> bool:
            context_matches = (
                (run_id is None or candidate.run_id == run_id)
                and (epoch is None or candidate.epoch == epoch)
                and (batch is None or candidate.batch == batch)
                and (
                    batch_fingerprint is None
                    or candidate.batch_fingerprint == batch_fingerprint
                )
            )
            # epoch/batch/fingerprint identify the real batch. ``step`` is a
            # derived loop index and may change when num_batches changes.
            return (
                candidate.level == "L0"
                and context_matches
                and (complete_context or candidate.step == step)
            )

        candidates = sorted(
            (candidate for candidate in self._candidate_records.values() if matches(candidate)),
            key=self._review_sort_key,
        )
        result: list[dict[str, Any]] = []
        for candidate in candidates:
            payload = candidate.public_dict()
            result.append({field_name: payload[field_name] for field_name in input_fields})
        return result

    def get_l0_candidate_fingerprints_for_batch(
        self,
        *,
        run_id: str,
        epoch: int,
        batch: int,
    ) -> set[str | None]:
        """Return every generation fingerprint already bound to a stable batch.

        ``step`` is intentionally excluded: it is derived from the number of
        batches and is not stable when batching parameters change on restart.
        """

        return {
            candidate.batch_fingerprint
            for candidate in self._candidate_records.values()
            if candidate.level == "L0"
            and candidate.run_id == run_id
            and candidate.epoch == epoch
            and candidate.batch == batch
        }

    def assert_restart_step_safe(self, restart_step: int) -> None:
        """Reject any rewind of a populated hierarchy.

        L1/L2 are created at epoch boundaries and records do not yet carry a
        stable checkpoint manifest. Candidate ``step`` is also derived from the
        current batch count. Therefore no non-empty snapshot can prove that an
        arbitrary numeric rewind excludes future state; fail closed instead of
        injecting it. Normal crash recovery uses ``restart_step=None``.
        """

        populated = bool(
            self._candidate_records
            or self._l0_records
            or self._l0_archive
            or self._l1_records
            or self._l1_archive
            or self._l2_records
            or self._l2_archive
        )
        if populated:
            raise RuntimeError(
                "Cannot safely rewind a populated hierarchical experience pool with restart_step="
                f"{restart_step}: the snapshot may contain state created after that checkpoint. "
                "Resume with cached steps (restart_step=null) or use a new "
                "exp_id and experience_save_path."
            )

    def get_archived_l0_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l0_archive)

    def get_archived_l1_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l1_archive)

    def get_archived_l2_experiences(self) -> list[dict[str, Any]]:
        return self._ordered_records(self._l2_archive)

    def trace_ancestry(self, experience_id: str) -> dict[str, Any]:
        """Return the complete parent tree for an L0/L1/L2 experience."""

        all_records = {
            **self._l0_archive,
            **self._l0_records,
            **self._l1_archive,
            **self._l1_records,
            **self._l2_archive,
            **self._l2_records,
        }
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
