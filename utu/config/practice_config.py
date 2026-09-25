from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, model_validator

from .base_config import ConfigBaseModel
from .eval_config import RuntimeConfig


class HierarchicalLearningConfig(ConfigBaseModel):
    """Configuration for hierarchical experience learning (L0/L1/L2)."""

    enabled: bool = False
    """Enable hierarchical experience learning"""
    experience_output_language: Literal["same_as_input", "english"] = "same_as_input"
    """Language contract for generated and reviewed experience prose."""
    min_l0_per_l1: int = Field(
        default=5,
        ge=2,
    )
    """Minimum same-cluster L0 experiences needed to generate one L1."""
    min_l1_per_l2: int = Field(
        default=3,
        ge=2,
    )
    """Minimum same-cluster L1 experiences needed to generate one L2."""
    clustering_enabled: bool = True
    """Cluster before aggregation; false uses deterministic sequential grouping."""
    embedding_provider: Literal["sentence_transformer", "hashing"] = "sentence_transformer"
    """Formal runs use local semantic embeddings; hashing is a lexical test baseline only."""
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    """Lightweight English sentence encoder used for SkillsBench experiences."""
    embedding_model_revision: str = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
    """Pinned model revision; cache entries are bound to this exact revision."""
    embedding_dimensions: int = Field(default=384, ge=1)
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=32, ge=1)
    embedding_cache_path: str = "workspace/cache/experience_embeddings.sqlite3"
    embedding_local_files_only: bool = True
    """Never download model weights implicitly from a training/evaluation process."""
    l0_similarity_threshold: float = Field(default=0.60, ge=-1.0, le=1.0)
    """Provisional L0 threshold; replace only using the training-data calibration report."""
    l1_similarity_threshold: float = Field(default=0.55, ge=-1.0, le=1.0)
    """Provisional L1 threshold; replace only using the training-data calibration report."""
    l0_similarity_threshold_provisional: bool = True
    """Block clustered L0->L1 aggregation until the L0 threshold is accepted."""
    l1_similarity_threshold_provisional: bool = True
    """Block clustered L1->L2 aggregation until the L1 threshold is accepted."""
    allow_provisional_aggregation: bool = False
    strategy_conflict_check_enabled: bool = True
    strategy_conflict_lexical_overlap: float = Field(default=0.65, ge=0.0, le=1.0)
    max_cluster_size: int = Field(default=20, ge=2)
    """Maximum number of direct parents in one aggregation."""
    use_metadata_constraints: bool = True
    """Apply hard and soft metadata constraints before semantic merging."""
    hard_constraint_fields: list[str] = Field(default_factory=lambda: ["task_stage", "failure_mode"])
    """Known unequal values in these fields prohibit a merge."""
    soft_constraint_fields: list[str] = Field(
        default_factory=lambda: ["domain", "task_family", "tool_type", "strategy_type"]
    )
    """Known soft mismatches reduce the semantic similarity score."""
    random_seed: int = 42
    """Seed used by the deterministic embedding and cluster IDs."""
    aggregation_temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    """Deterministic L1/L2 aggregation; formal experiments require exactly zero."""
    aggregation_disable_thinking: bool = False
    """Disable provider-specific thinking mode for hierarchy generation and review."""
    aggregation_max_tokens: int | None = Field(default=None, ge=1)
    """Optional output-token ceiling for hierarchy generation and review calls."""
    upper_pool_update_mode: Literal["clustered", "stacked_pool"] = "clustered"
    """Build upper levels from semantic clusters or incrementally maintained stacked pools."""
    stacked_pool_source_batch_size: int = Field(default=1, ge=1)
    """Number of pending source records consumed by one stacked-pool update event."""
    min_l0_per_l1_candidate: int | None = Field(default=None, ge=1)
    """Optional lower proposal gate; defaults to min_l0_per_l1."""
    min_distinct_source_tasks_per_l1: int = Field(default=1, ge=1)
    """Minimum distinct source tasks supporting a production L1 experience."""
    min_distinct_source_tasks_per_l1_candidate: int | None = Field(default=None, ge=1)
    """Optional lower proposal gate; defaults to min_distinct_source_tasks_per_l1."""
    l1_validation_required: bool = False
    """Keep newly admitted L1 experiences provisional until paired validation promotes them."""
    min_distinct_source_tasks_per_l1_promotion: int = Field(default=3, ge=1)
    min_validation_trials_per_l1: int = Field(default=5, ge=1)
    min_distinct_validation_tasks_per_l1: int = Field(default=5, ge=1)
    min_l1_validation_net_help: int = Field(default=1, ge=0)
    max_l1_validation_harms: int = Field(default=1, ge=0)
    """Auditable paired-validation requirements for promoting a provisional L1."""
    strategy_aware_l0_clustering: bool = False
    """Require canonical-strategy compatibility when clustering L0 experiences."""
    l0_strategy_compatibility_threshold: float = Field(default=0.60, ge=-1.0, le=1.0)
    l0_strategy_fallback_threshold: float = Field(default=0.78, ge=-1.0, le=1.0)
    l0_strategy_ignore_failure_mode: bool = True
    """Ignore failure mode for L0 strategy clustering and L0 review compatibility."""
    l0_candidate_review_enabled: bool = True
    """Require sequential ADD/UPDATE/DELETE/KEEP review before L0 activation."""
    l1_candidate_review_enabled: bool = True
    """Review generated L1 candidates before activation; false explicitly selects legacy direct admission."""
    l2_candidate_review_enabled: bool = True
    """Review generated L2 candidates before activation; false explicitly selects legacy direct admission."""
    l0_review_temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    """Candidate maintenance decisions are deterministic in formal runs."""
    candidate_review_scope: Literal["retrieval", "full_pool"] = "retrieval"
    """Compare with a retrieved neighborhood or the full active pool subject to prompt character budgets."""
    l0_review_full_pool_limit: int = Field(default=50, ge=1)
    """In retrieval scope, automatically compare the full active pool when its size is at most this value."""
    l0_review_retrieval: Literal["semantic", "lexical"] = "semantic"
    """Large-pool candidate recall; the LLM still makes the final four-action decision."""
    l0_review_top_k: int = Field(default=12, ge=1)
    """Deterministic lexical prefilter size when the active pool is larger."""
    l0_review_evidence_per_experience: int = Field(default=4, ge=1)
    """Maximum source-candidate evidence records shown for each related active L0."""
    l0_review_rollout_evidence_per_candidate: int = Field(default=2, ge=1)
    """Maximum detailed rollout records shown from one candidate during review."""
    l0_review_source_ids_per_item: int = Field(default=32, ge=1)
    """Maximum task IDs and rollout IDs shown from one candidate or active L0."""
    l0_review_content_chars: int = Field(default=8000, ge=256)
    """Maximum content characters shown for one candidate or active L0."""
    l0_review_max_supporting_evidence_chars: int = Field(default=40000, ge=1000)
    """Global deterministic character budget for the complete related-pool JSON view."""
    l0_review_max_attempts: int = Field(default=3, ge=1)
    """Maximum automatic review attempts; failed candidates remain persisted."""
    max_l0_per_problem: int = Field(default=0, ge=0)
    """Optional active L0 cap per task; zero disables the legacy quota."""
    l0_injection_top_k: int = Field(default=0, ge=0)
    """Retrieve at most this many L0 experiences per rollout; zero injects all active L0."""
    max_l1_total: int = Field(default=50, ge=0)
    """Maximum active L1 experiences; zero means unlimited."""
    max_l2_total: int = Field(default=10, ge=0)
    """Maximum active L2 experiences; zero means unlimited."""
    export_include_l0: bool = Field(
        default=True,
    )
    """Whether the final exported Agent prompt includes L0; unrelated to training retrieval."""
    export_max_l0: int | None = Field(
        default=None,
        ge=0,
    )
    """Final Agent L0 export limit: None exports all, zero exports none, N exports the newest N."""
    l1_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    """Minimum confidence threshold for L1"""
    l2_confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    """Minimum confidence threshold for L2"""
    experience_save_path: str = "workspace/hierarchical_experiences/experiences.json"
    """Path to save hierarchical experiences JSON file"""
    clustering_audit_path: str | None = None
    """Optional JSONL audit path; defaults next to the experience file."""

    @model_validator(mode="after")
    def validate_cluster_sizes(self):
        if self.max_cluster_size < max(self.min_l0_per_l1, self.min_l1_per_l2):
            raise ValueError("max_cluster_size must be at least min_l0_per_l1 and min_l1_per_l2")
        candidate_size = self.min_l0_per_l1_candidate or self.min_l0_per_l1
        candidate_task_support = (
            self.min_distinct_source_tasks_per_l1_candidate
            or self.min_distinct_source_tasks_per_l1
        )
        if candidate_task_support > candidate_size:
            raise ValueError(
                "min_distinct_source_tasks_per_l1_candidate cannot exceed "
                "min_l0_per_l1_candidate (or its min_l0_per_l1 fallback)"
            )
        if candidate_size > self.max_cluster_size:
            raise ValueError(
                "min_l0_per_l1_candidate (or its fallback) cannot exceed max_cluster_size"
            )
        if self.min_distinct_source_tasks_per_l1 > self.max_cluster_size:
            raise ValueError(
                "min_distinct_source_tasks_per_l1 cannot exceed max_cluster_size"
            )
        if self.min_distinct_validation_tasks_per_l1 > self.min_validation_trials_per_l1:
            raise ValueError(
                "min_distinct_validation_tasks_per_l1 cannot exceed min_validation_trials_per_l1"
            )
        if self.min_l1_validation_net_help > self.min_validation_trials_per_l1:
            raise ValueError(
                "min_l1_validation_net_help cannot exceed min_validation_trials_per_l1"
            )
        if self.max_l1_validation_harms > self.min_validation_trials_per_l1:
            raise ValueError(
                "max_l1_validation_harms cannot exceed min_validation_trials_per_l1"
            )
        if self.l0_strategy_fallback_threshold < self.l0_strategy_compatibility_threshold:
            raise ValueError(
                "l0_strategy_fallback_threshold must be at least "
                "l0_strategy_compatibility_threshold"
            )
        if self.upper_pool_update_mode == "stacked_pool" and not (
            self.l1_candidate_review_enabled and self.l2_candidate_review_enabled
        ):
            raise ValueError(
                "upper_pool_update_mode='stacked_pool' requires both L1 and L2 "
                "candidate review to be enabled"
            )
        if self.embedding_provider == "sentence_transformer":
            if not self.embedding_model_name.strip() or not self.embedding_model_revision.strip():
                raise ValueError("semantic embedding model name and pinned revision are required")
            if not self.embedding_cache_path.strip():
                raise ValueError("semantic embedding cache path is required")
        if not self.experience_save_path.strip():
            raise ValueError("experience_save_path must not be empty")
        if self.clustering_audit_path is not None and not self.clustering_audit_path.strip():
            raise ValueError("clustering_audit_path must be null or a non-empty path")
        return self


class PracticeArguments(ConfigBaseModel):
    """Arguments for practice."""

    # rollout
    epochs: int = Field(default=3, ge=1)
    """Number of practice epochs"""
    batch_size: int = Field(default=64, ge=1)
    """Practice batch size"""
    grpo_n: int = Field(default=5, ge=1)
    """Number of rollouts in a group of GRPO"""
    rollout_concurrency: int = Field(default=4, ge=1)
    """Maximum number of concurrent practice rollouts."""
    rollout_max_retries: int = Field(default=2, ge=1)
    """Total rollout attempts per practice sample, including the first attempt."""
    rollout_temperature: float = Field(default=0.7, ge=0.0)
    """Temperature for the LLM during rollout"""
    rollout_data_truncate: int | None = Field(default=None, ge=1)
    """Truncate data to first N samples"""
    task_timeout: int = Field(default=3600, ge=1)
    """Timeout for each individual task in seconds"""
    shuffle_data: bool = True
    """Whether to shuffle the practice data each epoch"""
    data_seed: int = 42
    """Base seed for deterministic epoch sampling; epoch is added to this value."""
    mistake_focus_ratio: float = Field(default=0.3, ge=0.0, le=1.0)
    """Fraction of a truncated epoch reserved for mistake-bank samples."""
    restart_step: int | None = Field(default=None, ge=0)
    """Step number to restart from (None means use cache for all steps if available, 0 means restart from beginning)"""
    resume_from_hierarchy: bool = False
    """Skip the contiguous batch prefix durably committed in the hierarchy snapshot."""

    # experience update
    agent_objective: str = None
    """The objective of working agent"""
    learning_objective: str = None
    """Learning objective for experience update"""
    given_ground_truth: bool = True
    """Whether use ground truth answers"""
    num_experiences_per_query: int = Field(default=2, ge=1)
    """Number of experiences to generate per query during practice"""

    # hierarchical learning
    hierarchical_learning: HierarchicalLearningConfig = Field(default_factory=HierarchicalLearningConfig)
    """Hierarchical experience learning configuration"""

    # eval
    do_eval: bool = False
    """Whether to perform evaluation during practice"""
    eval_pass_k: int | None = Field(default=None, ge=1)
    """Optional pass-k for the in-run evaluation stage; null inherits legacy defaults."""
    eval_concurrency: int | None = Field(default=None, ge=1)
    """Optional evaluation rollout concurrency; null inherits the runtime default."""
    eval_judge_concurrency: int | None = Field(default=None, ge=1)
    """Optional evaluation judge concurrency; null inherits the runtime default."""
    eval_strategy: Literal["epoch", "steps"] = "epoch"
    """Evaluation strategy"""
    eval_steps: int = Field(default=1, ge=1)
    """Evaluation steps"""
    eval_data_truncate: int | None = Field(default=None, ge=1)
    """Truncate evaluation data to first N samples"""

    @model_validator(mode="after")
    def validate_resume_mode(self):
        if self.resume_from_hierarchy and not self.hierarchical_learning.enabled:
            raise ValueError("resume_from_hierarchy=true requires hierarchical_learning.enabled=true")
        if self.resume_from_hierarchy and self.restart_step is not None:
            raise ValueError("resume_from_hierarchy and restart_step are mutually exclusive")
        return self


class DataArguments(ConfigBaseModel):
    """Arguments for data processing."""

    practice_dataset_name: str = None
    """Name of the practice dataset"""
    require_practice_manifest: bool = False
    """Fail before component construction unless the practice snapshot manifest verifies."""
    practice_manifest_path: str | None = None
    """Repository-relative or absolute path to the signed practice dataset manifest."""
    practice_manifest_split: str | None = None
    """Exact manifest split whose task inventory must match the practice rows."""
    practice_manifest_expected_records: int | None = Field(default=None, ge=1)
    """Required row count for a strict practice snapshot (for example, DAPO-100)."""

    @model_validator(mode="after")
    def validate_practice_manifest_requirements(self):
        if not self.require_practice_manifest:
            return self
        missing = [
            name
            for name in (
                "practice_manifest_path",
                "practice_manifest_split",
                "practice_manifest_expected_records",
            )
            if getattr(self, name) in (None, "")
        ]
        if missing:
            raise ValueError(
                "require_practice_manifest=true requires: " + ", ".join(missing)
            )
        return self


# Keep the historical public name for callers that identify the practice
# entry point. Both practice and evaluation now use one runtime schema.
PracticeRuntimeConfig = RuntimeConfig


def _mapping(value: Any) -> dict[str, Any]:
    """Convert a Hydra mapping or Pydantic model to a plain dictionary."""

    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python", exclude_none=False)
    return {}


def _practice_runtime_payload(value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split an old evaluation-shaped block into runtime and rollout controls."""

    raw = _mapping(value)
    runtime_fields = {
        "db_url",
        "data",
        "agent",
        "judge_model",
        "judge_concurrency",
        "verify_filename",
        "verify_func_name",
        "korgym",
        "skillsbench",
    }
    runtime = {key: raw[key] for key in runtime_fields if key in raw}
    legacy = {
        key: raw[key]
        for key in (
            "exp_id",
            "pass_k",
            "concurrency",
        )
        if key in raw
    }
    return runtime, legacy


class TrainingFreeGRPOConfig(ConfigBaseModel):
    """Canonical configuration for Training-Free GRPO.

    ``runtime`` is the only source for the agent, judge, verifier, database,
    and benchmark adapters. Older practice YAML files used an ``evaluation``
    block (and sometimes a root ``korgym`` block); the pre-validator below
    migrates those shapes at load time and drops the duplicate fields.
    """

    exp_id: str = "default"
    """Experiment ID and durable DB/cache identity."""
    practice: PracticeArguments = Field(default_factory=PracticeArguments)
    """Practice sampling, evaluation, and hierarchy controls."""
    data: DataArguments = Field(default_factory=DataArguments)
    """Practice dataset and manifest controls."""
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    """Agent, judge, verifier, database, and benchmark runtime dependencies."""

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_runtime_shape(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data

        raw = dict(data)
        legacy_evaluation = raw.pop("evaluation", None)
        explicit_runtime = raw.get("runtime")
        source = explicit_runtime if explicit_runtime is not None else legacy_evaluation
        runtime_payload, legacy_controls = _practice_runtime_payload(source)
        if explicit_runtime is not None and legacy_evaluation is not None:
            # A derived legacy config may still contain an inherited
            # ``evaluation`` block. Canonical ``runtime`` values win.
            legacy_runtime, legacy_values = _practice_runtime_payload(legacy_evaluation)
            for key, value in legacy_runtime.items():
                runtime_payload.setdefault(key, value)
            legacy_controls.update(legacy_values)

        # A root KORGym block historically duplicated evaluation.korgym. Use it
        # only when the canonical runtime block does not already define one.
        if "korgym" in raw:
            root_korgym = raw.pop("korgym")
            if root_korgym is not None and "korgym" not in runtime_payload:
                runtime_payload["korgym"] = root_korgym

        runtime = RuntimeConfig(**runtime_payload)
        if "exp_id" not in raw and "exp_id" in legacy_controls:
            raw["exp_id"] = legacy_controls["exp_id"]
        practice_value = raw.get("practice")
        if isinstance(practice_value, PracticeArguments):
            # Assignment validation passes the already-parsed nested model
            # back through this migration hook. Keep it typed; replacing it
            # with a plain dict would make later attribute access fail.
            if legacy_controls:
                practice_updates: dict[str, Any] = {}
                if "pass_k" in legacy_controls:
                    practice_updates["grpo_n"] = legacy_controls["pass_k"]
                if "concurrency" in legacy_controls:
                    practice_updates["rollout_concurrency"] = legacy_controls["concurrency"]
                if practice_updates:
                    raw["practice"] = practice_value.model_copy(update=practice_updates)
        else:
            practice_payload = dict(practice_value or {})
            if "pass_k" in legacy_controls:
                practice_payload.setdefault("grpo_n", legacy_controls["pass_k"])
            if "concurrency" in legacy_controls:
                practice_payload.setdefault("rollout_concurrency", legacy_controls["concurrency"])
            if practice_payload:
                raw["practice"] = practice_payload
        raw["runtime"] = runtime
        return raw
