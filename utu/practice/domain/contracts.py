"""Small, dependency-free contracts shared by experience modules."""

from enum import Enum
from typing import Literal

ExperienceLevel = Literal["L0", "L1", "L2"]
ExperienceOutputLanguage = Literal["same_as_input", "english"]
AggregationStatus = Literal["pending", "aggregated", "terminal"]
ExperienceLifecycleStatus = Literal["active", "inactive", "needs_review"]
ExperienceValidationStatus = Literal["provisional", "validated"]
PairedValidationOutcome = Literal["help", "harm", "neutral"]
CandidateStatus = Literal["pending", "review_failed", "stale", "committed"]
CandidateAction = Literal["ADD", "UPDATE", "DELETE", "KEEP"]
CandidateResolution = Literal["adopted", "not_adopted"]


class TaskStage(str, Enum):
    """Controlled task phase used by hierarchy metadata constraints."""

    PLANNING = "planning"
    EXECUTION = "execution"
    RECOVERY = "recovery"
    VERIFICATION = "verification"
    SUBMISSION = "submission"
    UNKNOWN = "unknown"


class FailureMode(str, Enum):
    """Failure evidence derived from rollout and verifier state."""

    NONE = "none"
    VERIFIER_FAILURE = "verifier_failure"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    TIMEOUT = "timeout"
    EXECUTION_ERROR = "execution_error"
    MIXED_OUTCOME = "mixed_outcome"
    UNKNOWN = "unknown"
