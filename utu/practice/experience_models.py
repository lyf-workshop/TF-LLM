"""Structured records used by hierarchical experience learning.

The flat experience pool intentionally remains a ``dict[str, str]``.  The
hierarchical pool needs stronger guarantees: stable identities, parent links,
restart-safe aggregation state, and validated aggregation output.  Keeping
those concerns in this small module avoids coupling clustering to an LLM or a
particular persistence backend.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ExperienceLevel = Literal["L0", "L1", "L2"]
AggregationStatus = Literal["pending", "aggregated", "terminal"]


class TaskStage(str, Enum):
    """Controlled task phase used by the clustering hard constraint."""

    PLANNING = "planning"
    EXECUTION = "execution"
    RECOVERY = "recovery"
    VERIFICATION = "verification"
    SUBMISSION = "submission"
    UNKNOWN = "unknown"


class FailureMode(str, Enum):
    """Failure evidence that can be derived from rollout/verifier state.

    These values deliberately avoid free-form, LLM-inferred diagnoses.  A
    missing or unrecognised signal is ``unknown`` and therefore does not act as
    a hard clustering constraint.
    """

    NONE = "none"
    VERIFIER_FAILURE = "verifier_failure"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    TIMEOUT = "timeout"
    EXECUTION_ERROR = "execution_error"
    MIXED_OUTCOME = "mixed_outcome"
    UNKNOWN = "unknown"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalise_content(content: str) -> str:
    return re.sub(r"\s+", " ", content or "").strip()


def stable_experience_id(
    level: ExperienceLevel,
    content: str,
    parent_ids: list[str] | tuple[str, ...] | None = None,
    *,
    identity_context: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Return a deterministic ID that is independent of insertion order.

    L0 is content-addressed with optional classification context, so identical
    observations with compatible metadata merge their source evidence while
    known conflicting classifications remain separate. L1/L2 also include the
    sorted parent set: equal prose from different evidence remains auditable.
    """

    payload = {
        "level": level,
        "content": _normalise_content(content),
        "parents": sorted(parent_ids or []),
        "identity_context": sorted(identity_context or []),
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return f"{level}_{digest}"


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
    aggregation_status: AggregationStatus = "pending"
    created_at: str = Field(default_factory=_utc_now)
    version: str = "2.0"
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
