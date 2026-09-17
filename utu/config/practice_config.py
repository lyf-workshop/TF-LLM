from typing import Literal

from pydantic import AliasChoices, Field, model_validator

from .base_config import ConfigBaseModel
from .eval_config import EvalConfig, KORGymConfig


class HierarchicalLearningConfig(ConfigBaseModel):
    """Configuration for hierarchical experience learning (L0/L1/L2)."""

    enabled: bool = False
    """Enable hierarchical experience learning"""
    experience_output_language: Literal["same_as_input", "english"] = "same_as_input"
    """Language contract for generated and reviewed experience prose."""
    min_l0_per_l1: int = Field(
        default=5,
        ge=2,
        validation_alias=AliasChoices("min_l0_per_l1", "l1_aggregation_threshold"),
    )
    """Minimum same-cluster L0 experiences needed to generate one L1."""
    min_l1_per_l2: int = Field(
        default=3,
        ge=2,
        validation_alias=AliasChoices("min_l1_per_l2", "l2_aggregation_threshold"),
    )
    """Minimum same-cluster L1 experiences needed to generate one L2."""
    clustering_enabled: bool = True
    """Cluster before aggregation; false uses deterministic sequential grouping."""
    clustering_method: Literal["agglomerative"] = "agglomerative"
    """Unknown-k clustering method."""
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
    similarity_thresholds_provisional: bool | None = None
    """Deprecated compatibility switch; when set, it controls both layer gates."""
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
    l0_candidate_review_enabled: bool = True
    """Require sequential ADD/UPDATE/DELETE/KEEP review before L0 activation."""
    l1_candidate_review_enabled: bool = True
    """Review generated L1 candidates before activation; false explicitly selects legacy direct admission."""
    l2_candidate_review_enabled: bool = True
    """Review generated L2 candidates before activation; false explicitly selects legacy direct admission."""
    l0_review_temperature: float = Field(default=0.0, ge=0.0, le=0.0)
    """Candidate maintenance decisions are deterministic in formal runs."""
    l0_review_full_pool_limit: int = Field(default=50, ge=1)
    """Compare against the full active L0 pool up to this size."""
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
    max_l1_total: int = 50
    """Maximum total L1 experiences"""
    max_l2_total: int = 10
    """Maximum total L2 experiences"""
    include_l0_in_prompt: bool = True
    """Whether to include recent L0 in prompt"""
    max_l0_recent: int = 10
    """Maximum recent L0 to include in prompt"""
    l1_confidence_threshold: float = 0.7
    """Minimum confidence threshold for L1"""
    l2_confidence_threshold: float = 0.8
    """Minimum confidence threshold for L2"""
    experience_save_path: str = "workspace/hierarchical_experiences/experiences.json"
    """Path to save hierarchical experiences JSON file"""
    clustering_audit_path: str | None = None
    """Optional JSONL audit path; defaults next to the experience file."""

    @property
    def l1_aggregation_threshold(self) -> int:
        """Compatibility alias for old code and experiment configs."""

        return self.min_l0_per_l1

    @property
    def l2_aggregation_threshold(self) -> int:
        """Compatibility alias for old code and experiment configs."""

        return self.min_l1_per_l2

    @model_validator(mode="after")
    def validate_cluster_sizes(self):
        # The former global flag remains authoritative when explicitly present.
        # This also preserves old Hydra overrides after a base template starts
        # declaring the new per-layer flags. New configs should omit the legacy
        # field and change each layer only after reviewing its own calibration.
        if self.similarity_thresholds_provisional is not None:
            self.l0_similarity_threshold_provisional = self.similarity_thresholds_provisional
            self.l1_similarity_threshold_provisional = self.similarity_thresholds_provisional
        if self.max_cluster_size < max(self.min_l0_per_l1, self.min_l1_per_l2):
            raise ValueError("max_cluster_size must be at least min_l0_per_l1 and min_l1_per_l2")
        if self.embedding_provider == "sentence_transformer":
            if not self.embedding_model_name.strip() or not self.embedding_model_revision.strip():
                raise ValueError("semantic embedding model name and pinned revision are required")
            if not self.embedding_cache_path.strip():
                raise ValueError("semantic embedding cache path is required")
        return self


class PracticeArguments(ConfigBaseModel):
    """Arguments for practice."""

    # rollout
    epochs: int = 3
    """Number of practice epochs"""
    batch_size: int = 64
    """Practice batch size"""
    grpo_n: int = 5
    """Number of rollouts in a group of GRPO"""
    rollout_concurrency: int = 4
    """Concurrency level for rollouts"""
    rollout_temperature: float = 0.7
    """Temperature for the LLM during rollout"""
    rollout_data_truncate: int = None
    """Truncate data to first N samples"""
    task_timeout: int = 3600
    """Timeout for each individual task in seconds"""
    shuffle_data: bool = True
    """Whether to shuffle the practice data each epoch"""
    restart_step: int = None
    """Step number to restart from (None means use cache for all steps if available, 0 means restart from beginning)"""

    # experience update
    agent_objective: str = None
    """The objective of working agent"""
    learning_objective: str = None
    """Learning objective for experience update"""
    given_ground_truth: bool = True
    """Whether use ground truth answers"""
    num_experiences_per_query: int = 2
    """Number of experiences to generate per query during practice"""

    # hierarchical learning
    hierarchical_learning: HierarchicalLearningConfig = Field(default_factory=HierarchicalLearningConfig)
    """Hierarchical experience learning configuration"""

    # eval
    do_eval: bool = False
    """Whether to perform evaluation during practice"""
    eval_strategy: Literal["epoch", "steps"] = "epoch"
    """Evaluation strategy"""
    eval_steps: int = 1
    """Evaluation steps"""
    eval_data_truncate: int = None
    """Truncate evaluation data to first N samples"""


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


class TrainingFreeGRPOConfig(ConfigBaseModel):
    """Unified configuration for Training-Free GRPO."""

    exp_id: str = "default"
    """Experiment ID"""

    # Practice arguments
    practice: PracticeArguments = Field(default_factory=PracticeArguments)
    """Practice-related parameters"""
    # Data arguments
    data: DataArguments = Field(default_factory=DataArguments)
    """Data processing parameters"""
    # Evaluation arguments
    evaluation: EvalConfig = Field(default_factory=EvalConfig)
    """Evaluation parameters"""
    # KORGym arguments
    korgym: KORGymConfig = Field(default_factory=KORGymConfig)
    """KORGym game evaluation configuration"""
