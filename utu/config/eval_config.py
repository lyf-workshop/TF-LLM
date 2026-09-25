from typing import Literal

from pydantic import Field, model_validator

from ..utils import EnvUtils
from .agent_config import AgentConfig, ModelConfigs
from .base_config import ConfigBaseModel


class DataConfig(ConfigBaseModel):
    """Data config"""

    dataset: str = Field(min_length=1)  # WebWalkerQA | GAIA_validation | XBench | BrowseComp
    """Built-in dataset name or custom dataset path"""
    task_order: list[str] | None = None
    """Optional exact, namespaced task order supplied by a signed experiment protocol."""
    task_order_sha256: str | None = None
    """Canonical hash of task_order; validated before evaluation rows are created."""
    protocol_metadata: dict | None = None
    """Signed ablation metadata copied into every persisted evaluation trial."""


class LLMRerankConfig(ConfigBaseModel):
    """LLM-based experience reranking configuration."""

    model: str = Field(default="qwen3-32b", min_length=1)
    """LLM model to use for reranking"""
    temperature: float = Field(default=0.1, ge=0.0)
    """Temperature for LLM inference (lower = more deterministic)"""
    max_candidates: int = Field(default=20, gt=0)
    """Maximum number of experiences to evaluate with LLM"""
    final_top_k: int = Field(default=8, gt=0)
    """Final number of experiences to return after reranking"""
    include_reasoning: bool = True
    """Whether to include reasoning in LLM output"""
    scoring_criteria: list[str] = Field(default_factory=lambda: ["relevance", "generalization", "actionability"])
    """Criteria for scoring experiences"""
    timeout: int = Field(default=60, gt=0)
    """Timeout for LLM API call in seconds"""

    @model_validator(mode="after")
    def validate_limits(self) -> "LLMRerankConfig":
        if self.final_top_k > self.max_candidates:
            raise ValueError("final_top_k cannot exceed max_candidates")
        if not self.scoring_criteria or any(not item.strip() for item in self.scoring_criteria):
            raise ValueError("scoring_criteria must contain at least one non-empty criterion")
        return self


class RecallConfig(ConfigBaseModel):
    """Recall stage configuration for two-stage filtering."""

    method: Literal["static", "tfidf", "all"] = "static"
    """Recall method: fixed limits, lexical TF-IDF retrieval, or no filtering."""
    max_l2: int | None = Field(default=None, ge=0)
    """Maximum L2 experiences to recall. None = all"""
    max_l1: int | None = Field(default=None, ge=0)
    """Maximum L1 experiences to recall. None = all"""
    max_l0: int | None = Field(default=None, ge=0)
    """Maximum L0 experiences to recall. None = all"""

class ExperienceFilterConfig(ConfigBaseModel):
    """Experience filter configuration for controlling which experiences to inject into agent."""

    enabled: bool = False
    """Whether experience filtering is enabled. If False, all experiences are used."""

    # Experience source
    experience_source: str | None = None
    """Path to hierarchical experiences JSON file (e.g., 'workspace/hierarchical_experiences/wordle_practice_2.json').
    If None, experiences are parsed from agent instructions."""

    # Filtering strategy
    strategy: Literal["static", "retrieval", "llm_rerank"] = "static"
    """Filtering strategy: fixed counts, lexical TF-IDF retrieval, or LLM reranking."""

    # Retrieval-based filtering
    retrieval_top_k: int = Field(default=5, gt=0)
    """Number of experiences to retrieve per query when using 'retrieval' strategy"""
    retrieval_min_score: float = Field(default=0.0, ge=0.0)
    """Minimum relevance score threshold for retrieval"""

    # Two-stage filtering: recall + rerank
    recall: RecallConfig = Field(default_factory=RecallConfig)
    """Recall stage configuration (first stage)"""
    llm_rerank: LLMRerankConfig = Field(default_factory=LLMRerankConfig)
    """LLM reranking configuration (second stage)"""

class KORGymConfig(ConfigBaseModel):
    """KORGym game configuration"""

    enabled: bool = False
    """Whether KORGym evaluation is enabled"""
    game_name: str = Field(default="3-2048", min_length=1)
    """Name of the KORGym game"""
    game_host: str = Field(default="localhost", min_length=1)
    """Game server host"""
    game_port: int = Field(default=8775, ge=1, le=65535)
    """Game server port"""
    level: int = Field(default=3, ge=0)
    """Game-specific difficulty/size parameter; zero is valid for games that ignore it."""
    max_rounds: int = Field(default=50, gt=0)
    """Maximum rounds for multi-turn games"""
    timeout_per_game: float = Field(default=600.0, gt=0)
    """Wall-clock timeout for one complete game, in seconds."""


class SkillsBenchConfig(ConfigBaseModel):
    """SkillsBench harbor-based evaluation configuration."""

    enabled: bool = False
    """Whether SkillsBench harbor execution is enabled."""
    inject_curated_skills: bool = False
    """If True, inject the task's curated Skills text into the agent system prompt."""
    task_timeout_sec: int = Field(default=600, gt=0)
    """Wall-clock timeout per task in seconds."""
    max_agent_iterations: int = Field(default=30, gt=0)
    """Maximum bash-tool iterations the agent may perform per task."""
    env_build_timeout_multiplier: float = Field(default=3.0, gt=0)
    """Multiplier applied to harbor's default 200s Docker environment build timeout."""
    docker_cleanup_after_task: bool = True
    """Remove stopped containers and dangling images after every task to prevent
    the WSL ext4.vhdx from growing unboundedly."""
    docker_cleanup_builder_every_n: int = Field(default=10, ge=0)
    """Also prune the Docker build-cache every N tasks (0 = never).
    Build cache is the largest space consumer; pruning every 10 tasks is a
    good balance between disk savings and rebuild speed."""
    max_retries: int = Field(default=2, ge=0)
    """Number of extra attempts for a task when it fails due to an infrastructure
    error (Docker build failure, harbor crash, etc.). 0 disables retrying.
    A value of 2 means up to 3 total attempts. Retries are NOT triggered when the
    agent runs to completion and the verifier legitimately scores the task (even 0)."""
    retry_delay_sec: float = Field(default=5.0, ge=0)
    """Seconds to wait between retry attempts (gives Docker/daemon time to recover)."""
    retry_on_timeout: bool = False
    """If True, also retry when a task hits its wall-clock timeout. Disabled by
    default because timeouts usually mean the agent is genuinely stuck and would
    time out again, wasting a lot of wall-clock time."""
    llm_connect_timeout_sec: float = Field(default=10.0, gt=0)
    """Connection timeout for each model API request."""
    llm_read_timeout_sec: float = Field(default=120.0, gt=0)
    """Read timeout for each model API request."""
    llm_max_retries: int = Field(default=4, ge=0)
    """Extra attempts for transient model API errors within the same trial."""
    llm_retry_initial_delay_sec: float = Field(default=2.0, ge=0)
    """Initial exponential-backoff delay for transient model API errors."""
    llm_retry_max_delay_sec: float = Field(default=30.0, ge=0)
    """Maximum model API retry delay."""
    circuit_breaker_enabled: bool = True
    """Pause new trials after repeated transient model API failures."""
    circuit_breaker_failure_threshold: int = Field(default=3, gt=0)
    """Consecutive transient API failures that open the circuit."""
    circuit_breaker_cooldown_sec: float = Field(default=60.0, ge=0)
    """Fixed pause before a recovery probe; this value never grows exponentially."""
    healthcheck_enabled: bool = True
    """Probe the configured endpoint before measured SkillsBench trials."""
    healthcheck_attempts: int = Field(default=3, gt=0)
    """Number of successful startup probes required."""
    expected_num_tasks: int | None = Field(default=None, gt=0)
    """Expected benchmark task count. Paper-aligned SkillsBench uses 87."""
    require_complete_coverage: bool = True
    """Do not publish headline metrics until every expected trial is valid."""
    experience_condition: Literal[
        "unspecified",
        "no_experience",
        "sequential",
        "clustered",
        "task_local_skills",
    ] = "unspecified"
    """Declared treatment condition for leakage checks and ablation reports."""
    train_dataset_for_overlap_check: str | None = None
    """Dataset that produced learned experiences; absent for no-experience/task-local conditions."""
    require_disjoint_train_eval: bool = True
    """Abort before rollout when learned-experience train IDs overlap evaluation IDs."""
    task_split_manifest_path: str | None = None
    """Machine-readable versioned task inventory/split manifest."""
    task_split_name: str | None = None
    """Split key whose exact train/eval lists must match the database datasets."""
    declared_injected_token_count: int | None = Field(default=None, ge=0)
    """Static experience-only prompt token delta recorded for experiment auditing."""
    injected_tokenizer: str | None = None
    """Tokenizer used for declared_injected_token_count."""


class RuntimeConfig(ConfigBaseModel):
    """Shared runtime dependencies for practice and standalone evaluation."""

    db_url: str = EnvUtils.get_env("UTU_DB_URL", "sqlite:///test.db")
    """Database URL."""
    data: DataConfig | None = None
    """Optional evaluation dataset configuration."""
    agent: AgentConfig | None = None
    """Agent configuration used for rollouts."""
    judge_model: ModelConfigs = Field(default_factory=ModelConfigs)
    """Judge model configuration."""
    judge_concurrency: int = Field(default=1, gt=0)
    """Parallelism for judgement calls."""
    verify_filename: str | None = None
    """Optional verifier module under ``utu/practice/verify``."""
    verify_func_name: str | None = None
    """Optional verifier function name."""
    korgym: KORGymConfig = Field(default_factory=KORGymConfig)
    """KORGym runtime configuration."""
    skillsbench: SkillsBenchConfig = Field(default_factory=SkillsBenchConfig)
    """SkillsBench runtime configuration."""


class EvalConfig(RuntimeConfig):
    """Standalone evaluation configuration."""

    exp_id: str = "default"
    """Experiment ID"""

    # evaluation-specific rollout controls
    concurrency: int = Field(default=1, gt=0)
    """Rollout parallelism"""
    pass_k: int = Field(default=1, gt=0)
    """Rollout k for each sample"""
    log_trajectory_to_db: bool = True
    """Persist the agent trajectory separately from the evaluation row."""
    allow_legacy_cache_reuse: bool = False
    """Explicit opt-in for resuming pre-fingerprint evaluation rows."""

    # Experience filtering configuration
    experience_filter: ExperienceFilterConfig = Field(default_factory=ExperienceFilterConfig)
    """Experience filtering configuration for controlling injected experiences"""
