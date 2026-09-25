"""Structured records used by hierarchical experience learning.

The flat experience pool intentionally remains a ``dict[str, str]``.  The
hierarchical pool needs stronger guarantees: stable identities, parent links,
restart-safe aggregation state, and validated aggregation output.  Keeping
those concerns in this small module avoids coupling clustering to an LLM or a
particular persistence backend.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain.contracts import (
    AggregationStatus,
    CandidateAction,
    CandidateResolution,
    CandidateStatus,
    ExperienceLevel,
    ExperienceLifecycleStatus,
    ExperienceOutputLanguage,
    ExperienceValidationStatus,
    FailureMode,
    PairedValidationOutcome,
    TaskStage,
)
from .domain.identity import (
    normalise_content as _normalise_content,
    stable_experience_candidate_id,
    stable_experience_id,
    stable_l0_candidate_id,
)
from .domain.language import experience_output_language_instruction, validate_experience_output_language


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class L0ReviewDecision(BaseModel):
    """Strict action decision shared by L0, L1, and L2 candidates.

    The historical name remains public for compatibility.  ``level`` and the
    structured payload are optional for legacy L0 responses; upper-level
    reviewers validate both against the candidate before committing.
    """

    model_config = ConfigDict(extra="forbid")

    action: CandidateAction
    candidate_id: str = Field(min_length=1)
    level: ExperienceLevel | None = None
    target_id: str | None = None
    # Filled by the manager from the displayed target immediately after the
    # model response. It is never trusted as model-supplied evidence.
    target_version_fingerprint: str | None = None
    new_content: str | None = None
    new_structured_content: dict[str, Any] | None = None
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("new_content", mode="before")
    @classmethod
    def unwrap_versioned_content(cls, value: Any) -> Any:
        """Accept the narrow versioned wrapper emitted by some chat models."""

        if not isinstance(value, dict):
            return value
        unexpected = sorted(set(value) - {"content", "version"})
        content = value.get("content")
        if unexpected or not isinstance(content, str):
            raise ValueError(
                "new_content object must contain string content and only optional version metadata"
            )
        return content.strip()

    @field_validator("candidate_id", "target_id", "new_content", "reason", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def normalise_evidence_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("evidence_ids must be a JSON array")
        result = [str(item).strip() for item in value]
        if not all(result):
            raise ValueError("evidence_ids must not contain empty IDs")
        if len(result) != len(set(result)):
            raise ValueError("evidence_ids must not contain duplicates")
        return result

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action in {"UPDATE", "DELETE"} and not self.target_id:
            raise ValueError(f"{self.action} requires target_id")
        if self.action in {"ADD", "UPDATE"} and not self.new_content:
            raise ValueError(f"{self.action} requires non-empty new_content")
        if self.action == "ADD" and self.target_id is not None:
            raise ValueError("ADD must not specify target_id")
        if self.action in {"DELETE", "KEEP"} and self.new_content is not None:
            raise ValueError(f"{self.action} must not specify new_content")
        if self.action in {"DELETE", "KEEP"} and self.new_structured_content is not None:
            raise ValueError(f"{self.action} must not specify new_structured_content")
        if self.action == "KEEP" and self.target_id is not None:
            raise ValueError("KEEP must not specify target_id")
        return self


class L0CandidateEvidence(BaseModel):
    """Compact, auditable rollout evidence supplied to the L0 reviewer."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    task_id: str | None = None
    reward: float | int | bool | str | None = None
    outcome: str | None = None
    error_type: str | None = None
    infra_error_type: str | None = None
    trajectory_summary: str | None = None
    verifier_feedback: str | None = None

    @field_validator(
        "id",
        "task_id",
        "outcome",
        "error_type",
        "infra_error_type",
        "trajectory_summary",
        "verifier_feedback",
        mode="before",
    )
    @classmethod
    def strip_evidence_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class L0CandidateRecord(BaseModel):
    """Persisted candidate and review lifecycle for any hierarchy level.

    The legacy class name and default ``level=L0`` keep existing snapshots and
    callers valid.  L1/L2 candidates additionally pin their direct parent IDs,
    source-version fingerprints, and structured aggregation result.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    level: ExperienceLevel = "L0"
    content: str = Field(min_length=1)
    source_task_ids: list[str] = Field(default_factory=list)
    source_rollout_ids: list[str] = Field(default_factory=list)
    source_evidence: list[L0CandidateEvidence] = Field(default_factory=list)
    domain: str | None = None
    task_family: str | None = None
    failure_mode: FailureMode = FailureMode.UNKNOWN
    strategy_type: str | None = None
    tool_type: str | None = None
    task_stage: TaskStage = TaskStage.UNKNOWN
    parent_ids: list[str] = Field(default_factory=list)
    source_l0_ids: list[str] = Field(default_factory=list)
    source_l1_ids: list[str] = Field(default_factory=list)
    source_versions: dict[str, str] = Field(default_factory=dict)
    source_fingerprint: str | None = None
    generation_fingerprint: str | None = None
    cluster_id: str | None = None
    structured_content: dict[str, Any] | None = None
    step: int = Field(default=0, ge=0)
    run_id: str | None = None
    epoch: int | None = Field(default=None, ge=0)
    batch: int | None = Field(default=None, ge=0)
    batch_fingerprint: str | None = None
    status: CandidateStatus = "pending"
    attempt_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    review_decision: L0ReviewDecision | None = None
    resolution: CandidateResolution | None = None
    result_experience_id: str | None = None
    created_at: str = Field(default_factory=_utc_now)
    reviewed_at: str | None = None
    generator_version: str = "l0-summary-v1"

    @field_validator("content", mode="before")
    @classmethod
    def normalise_candidate_content(cls, value: Any) -> str:
        text = _normalise_content(str(value or ""))
        if not text:
            raise ValueError("candidate content must be non-empty")
        return text

    @field_validator(
        "source_task_ids",
        "source_rollout_ids",
        "parent_ids",
        "source_l0_ids",
        "source_l1_ids",
        mode="before",
    )
    @classmethod
    def normalise_source_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, int)):
            value = [value]
        return sorted({str(item).strip() for item in value if str(item).strip()})

    @field_validator("task_stage", mode="before")
    @classmethod
    def normalise_task_stage(cls, value: Any) -> TaskStage:
        return ExperienceRecord.normalise_task_stage(value)

    @field_validator("failure_mode", mode="before")
    @classmethod
    def normalise_failure_mode(cls, value: Any) -> FailureMode:
        return ExperienceRecord.normalise_failure_mode(value)

    @model_validator(mode="after")
    def validate_source_evidence(self):
        evidence_ids = [evidence.id for evidence in self.source_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("source_evidence must not contain duplicate rollout IDs")
        unknown_ids = sorted(set(evidence_ids) - set(self.source_rollout_ids))
        if unknown_ids:
            raise ValueError(f"source_evidence contains IDs absent from source_rollout_ids: {unknown_ids}")
        unknown_task_ids = sorted(
            {
                evidence.task_id
                for evidence in self.source_evidence
                if evidence.task_id is not None and evidence.task_id not in self.source_task_ids
            }
        )
        if unknown_task_ids:
            raise ValueError(
                f"source_evidence contains task IDs absent from source_task_ids: {unknown_task_ids}"
            )
        if self.level == "L0":
            if self.parent_ids or self.source_versions:
                raise ValueError("L0 candidates must not declare hierarchical parents")
        else:
            if not self.parent_ids:
                raise ValueError(f"{self.level} candidates require direct parent_ids")
            if set(self.source_versions) != set(self.parent_ids):
                raise ValueError("source_versions keys must exactly match parent_ids")
            if not self.generation_fingerprint:
                raise ValueError(f"{self.level} candidates require generation_fingerprint")
            if not self.source_fingerprint:
                raise ValueError(f"{self.level} candidates require source_fingerprint")
            if not isinstance(self.structured_content, dict):
                raise ValueError(f"{self.level} candidates require structured_content")
            if self.level == "L1" and set(self.source_l0_ids) != set(self.parent_ids):
                raise ValueError("L1 source_l0_ids must match its direct L0 parents")
            if self.level == "L2" and set(self.source_l1_ids) != set(self.parent_ids):
                raise ValueError("L2 source_l1_ids must match its direct L1 parents")
        return self

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# Generic names for new code; legacy imports continue to use the L0-prefixed
# aliases without changing persisted data or public APIs.
ExperienceReviewDecision = L0ReviewDecision
ExperienceCandidateRecord = L0CandidateRecord


class AggregatedExperienceContent(BaseModel):
    """Schema required from the LLM for an L1 or L2 aggregation."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["aggregate"] = "aggregate"
    title: str = Field(min_length=3)
    principle: str = Field(min_length=10)
    applicable_when: list[str] = Field(min_length=1)
    not_applicable_when: list[str] = Field(min_length=1)
    recommended_actions: list[str] = Field(min_length=1)
    evidence_summary: str = Field(min_length=10)
    confidence: float = Field(ge=0.0, le=1.0)

    def render(self) -> str:
        """Render the validated object for prompt injection."""

        applicable = "; ".join(self.applicable_when)
        exclusions = "; ".join(self.not_applicable_when)
        actions = "; ".join(self.recommended_actions)
        return (
            f"{self.title}: {self.principle} "
            f"Applicable when: {applicable}. "
            f"Do not apply when: {exclusions}. "
            f"Actions: {actions}. "
            f"Evidence: {self.evidence_summary}. "
            f"Confidence: {self.confidence:.2f}."
        )


class AggregationConflict(BaseModel):
    """Validated refusal returned when parents contain incompatible advice."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["conflict"]
    conflict_reasons: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reasons(self):
        if not all(reason.strip() for reason in self.conflict_reasons):
            raise ValueError("conflict reasons must be non-empty")
        return self


class PairedValidationResult(BaseModel):
    """One held-out, same-task baseline/treatment comparison for an L1."""

    model_config = ConfigDict(extra="forbid")

    trial_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_question_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset: str = Field(min_length=1)
    dataset_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_role: Literal["calibration", "heldout_validation"]
    repeat: int = Field(ge=0)
    model: str = Field(min_length=1)
    protocol_version: str = Field(min_length=1)
    generation_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experience_version_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    treatment_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_score: float
    treatment_score: float
    outcome: PairedValidationOutcome
    note: str | None = None
    recorded_at: str = Field(default_factory=_utc_now)

    @field_validator(
        "trial_id",
        "task_id",
        "task_question_sha256",
        "dataset",
        "dataset_manifest_sha256",
        "model",
        "protocol_version",
        "generation_config_sha256",
        "experience_version_fingerprint",
        "baseline_prompt_sha256",
        "treatment_prompt_sha256",
        "note",
        mode="before",
    )
    @classmethod
    def strip_validation_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator(
        "task_question_sha256",
        "dataset_manifest_sha256",
        "generation_config_sha256",
        "experience_version_fingerprint",
        "baseline_prompt_sha256",
        "treatment_prompt_sha256",
        mode="before",
    )
    @classmethod
    def normalise_sha256(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_outcome(self):
        if not math.isfinite(self.baseline_score) or not math.isfinite(self.treatment_score):
            raise ValueError("paired validation scores must be finite")
        expected: PairedValidationOutcome
        if self.treatment_score > self.baseline_score:
            expected = "help"
        elif self.treatment_score < self.baseline_score:
            expected = "harm"
        else:
            expected = "neutral"
        if self.outcome != expected:
            raise ValueError(
                "paired validation outcome must be derived from treatment_score versus baseline_score"
            )
        return self


class ExperienceRecord(BaseModel):
    """Versioned, backwards-compatible hierarchical experience record."""

    model_config = ConfigDict(extra="allow")

    id: str
    level: ExperienceLevel
    content: str
    source_task_ids: list[str] = Field(default_factory=list)
    source_rollout_ids: list[str] = Field(default_factory=list)
    domain: str | None = None
    task_family: str | None = None
    failure_mode: FailureMode = FailureMode.UNKNOWN
    strategy_type: str | None = None
    tool_type: str | None = None
    task_stage: TaskStage = TaskStage.UNKNOWN
    parent_ids: list[str] = Field(default_factory=list)
    source_l0_ids: list[str] = Field(default_factory=list)
    source_l1_ids: list[str] = Field(default_factory=list)
    cluster_id: str | None = None
    aggregated_into_cluster_id: str | None = None
    aggregated_into_experience_id: str | None = None
    aggregation_status: AggregationStatus = "pending"
    lifecycle_status: ExperienceLifecycleStatus = "active"
    validation_status: ExperienceValidationStatus = "validated"
    validation_results: dict[str, PairedValidationResult] = Field(default_factory=dict)
    validated_at: str | None = None
    revision_number: int = Field(default=1, ge=1)
    lineage_root_id: str | None = None
    supersedes_id: str | None = None
    superseded_by_id: str | None = None
    archived_at: str | None = None
    archive_reason: str | None = None
    review_candidate_ids: list[str] = Field(default_factory=list)
    parent_version_fingerprints: dict[str, str] = Field(default_factory=dict)
    source_version_fingerprint: str | None = None
    invalidated_by_ids: list[str] = Field(default_factory=list)
    needs_review_reason: str | None = None
    created_at: str = Field(default_factory=_utc_now)
    version: str = "3.0"
    structured_content: AggregatedExperienceContent | None = None

    @field_validator("task_stage", mode="before")
    @classmethod
    def normalise_task_stage(cls, value: Any) -> TaskStage:
        if isinstance(value, TaskStage):
            return value
        if value is None or str(value).strip() == "":
            return TaskStage.UNKNOWN
        aliases = {
            "plan": TaskStage.PLANNING,
            "solve": TaskStage.EXECUTION,
            "execute": TaskStage.EXECUTION,
            "verify": TaskStage.VERIFICATION,
            "submit": TaskStage.SUBMISSION,
        }
        text = str(value).strip().lower()
        try:
            return TaskStage(text)
        except ValueError:
            return aliases.get(text, TaskStage.UNKNOWN)

    @field_validator("failure_mode", mode="before")
    @classmethod
    def normalise_failure_mode(cls, value: Any) -> FailureMode:
        if isinstance(value, FailureMode):
            return value
        if value is None or str(value).strip() == "":
            return FailureMode.UNKNOWN
        aliases = {
            "success_pattern": FailureMode.NONE,
            "all_failure": FailureMode.UNKNOWN,
            "bad_output": FailureMode.VERIFIER_FAILURE,
        }
        text = str(value).strip().lower()
        try:
            return FailureMode(text)
        except ValueError:
            return aliases.get(text, FailureMode.UNKNOWN)

    @model_validator(mode="after")
    def validate_paired_results(self):
        mismatched_keys = sorted(
            trial_id for trial_id, result in self.validation_results.items() if trial_id != result.trial_id
        )
        if mismatched_keys:
            raise ValueError(f"validation_results keys must match result trial_id: {mismatched_keys}")
        return self

    @classmethod
    def from_legacy(
        cls,
        exp_id: str,
        content: str,
        level: ExperienceLevel,
        *,
        aggregation_status: AggregationStatus = "pending",
    ) -> ExperienceRecord:
        """Upgrade the old ``id -> content`` representation in memory."""

        return cls(
            id=str(exp_id),
            level=level,
            content=str(content),
            aggregation_status=aggregation_status,
            version="1.0-migrated",
        )

    def merge_evidence(self, other: ExperienceRecord) -> ExperienceRecord:
        """Merge source evidence without changing this record's stable ID."""

        merged = self.model_copy(deep=True)
        merged.source_task_ids = sorted(set(self.source_task_ids) | set(other.source_task_ids))
        merged.source_rollout_ids = sorted(set(self.source_rollout_ids) | set(other.source_rollout_ids))
        for field in (
            "domain",
            "task_family",
            "failure_mode",
            "strategy_type",
            "tool_type",
            "task_stage",
        ):
            current = getattr(merged, field)
            current_raw = getattr(current, "value", current)
            if current is None or str(current_raw).strip().lower() in {"", "unknown"}:
                setattr(merged, field, getattr(other, field))
        return merged

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "AggregatedExperienceContent",
    "AggregationConflict",
    "AggregationStatus",
    "CandidateAction",
    "CandidateResolution",
    "CandidateStatus",
    "ExperienceCandidateRecord",
    "ExperienceLifecycleStatus",
    "ExperienceValidationStatus",
    "ExperienceLevel",
    "ExperienceOutputLanguage",
    "ExperienceRecord",
    "ExperienceReviewDecision",
    "FailureMode",
    "L0CandidateEvidence",
    "L0CandidateRecord",
    "L0ReviewDecision",
    "PairedValidationOutcome",
    "PairedValidationResult",
    "TaskStage",
    "experience_output_language_instruction",
    "stable_experience_candidate_id",
    "stable_experience_id",
    "stable_l0_candidate_id",
    "validate_experience_output_language",
]
