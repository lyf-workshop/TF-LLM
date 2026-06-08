from typing import Literal

from pydantic import Field

from ..utils import EnvUtils
from .agent_config import AgentConfig, ModelConfigs
from .base_config import ConfigBaseModel


class DataConfig(ConfigBaseModel):
    """Data config"""

    dataset: str  # WebWalkerQA | GAIA_validation | XBench | BrowseComp
    """Built-in dataset name or custom dataset path"""
    type: Literal["single", "mixed"] = "single"
    """Whether the dataset contains only single benchmark data or multiple benchmarks"""
    question_field: str = "question"
    """Question field name in the dataset"""
    gt_field: str = "answer"
    """Ground truth field name in the dataset"""


class LLMRerankConfig(ConfigBaseModel):
    """LLM-based experience reranking configuration."""
    
    enabled: bool = False
    """Whether LLM reranking is enabled"""
    model: str = "qwen3-32b"
    """LLM model to use for reranking"""
    temperature: float = 0.1
    """Temperature for LLM inference (lower = more deterministic)"""
    max_candidates: int = 20
    """Maximum number of experiences to evaluate with LLM"""
    final_top_k: int = 8
    """Final number of experiences to return after reranking"""
    include_reasoning: bool = True
    """Whether to include reasoning in LLM output"""
    scoring_criteria: list[str] = Field(default_factory=lambda: ["relevance", "generalization", "actionability"])
    """Criteria for scoring experiences"""
    timeout: int = 60
    """Timeout for LLM API call in seconds"""


class RecallConfig(ConfigBaseModel):
    """Recall stage configuration for two-stage filtering."""
    
    method: Literal["static", "bm25", "all"] = "static"
    """Recall method: 'static' = fixed limits, 'bm25' = BM25 retrieval, 'all' = no filtering"""
    max_l2: int | None = None
    """Maximum L2 experiences to recall. None = all"""
    max_l1: int | None = None
    """Maximum L1 experiences to recall. None = all"""
    max_l0: int | None = 50
    """Maximum L0 experiences to recall. None = all"""


class ExperienceFilterConfig(ConfigBaseModel):
    """Experience filter configuration for controlling which experiences to inject into agent."""
    
    enabled: bool = False
    """Whether experience filtering is enabled. If False, all experiences are used."""
    
    # Experience source
    experience_source: str | None = None
    """Path to hierarchical experiences JSON file (e.g., 'workspace/hierarchical_experiences/wordle_practice_2.json'). 
    If None, experiences are parsed from agent instructions."""
    
    # Legacy single-stage filtering
    strategy: Literal["static", "retrieval", "llm_rerank"] = "static"
    """Filtering strategy: 'static' = fixed counts per level, 'retrieval' = BM25-based, 'llm_rerank' = LLM-based"""
    max_l2: int | None = None
    """Maximum number of L2 (meta-strategy) experiences to include. None = include all"""
    max_l1: int | None = None
    """Maximum number of L1 (pattern-level) experiences to include. None = include all"""
    max_l0: int | None = None
    """Maximum number of L0 (case-level) experiences to include. None = include all"""
    
    # Retrieval-based filtering
    retrieval_top_k: int = 5
    """Number of experiences to retrieve per query when using 'retrieval' strategy"""
    retrieval_min_score: float = 0.0
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
    game_name: str = "3-2048"
    """Name of the KORGym game"""
    game_host: str = "localhost"
    """Game server host"""
    game_port: int = 8775
    """Game server port"""
    level: int = 3
    """Game difficulty level (1-5)"""
    num_seeds: int = 20
    """Number of game instances to evaluate"""
    max_rounds: int = 50
    """Maximum rounds for multi-turn games"""


class SkillsBenchConfig(ConfigBaseModel):
    """SkillsBench harbor-based evaluation configuration."""

    enabled: bool = False
    """Whether SkillsBench harbor execution is enabled."""
    inject_curated_skills: bool = False
    """If True, inject the task's curated Skills text into the agent system prompt."""
    task_timeout_sec: int = 600
    """Wall-clock timeout per task in seconds."""
    max_agent_iterations: int = 30
    """Maximum bash-tool iterations the agent may perform per task."""
    env_build_timeout_multiplier: float = 3.0
    """Multiplier applied to harbor's default 200s Docker environment build timeout."""
    docker_cleanup_after_task: bool = True
    """Remove stopped containers and dangling images after every task to prevent
    the WSL ext4.vhdx from growing unboundedly."""
    docker_cleanup_builder_every_n: int = 10
    """Also prune the Docker build-cache every N tasks (0 = never).
    Build cache is the largest space consumer; pruning every 10 tasks is a
    good balance between disk savings and rebuild speed."""
    max_retries: int = 2
    """Number of extra attempts for a task when it fails due to an infrastructure
    error (Docker build failure, harbor crash, etc.). 0 disables retrying.
    A value of 2 means up to 3 total attempts. Retries are NOT triggered when the
    agent runs to completion and the verifier legitimately scores the task (even 0)."""
    retry_delay_sec: float = 5.0
    """Seconds to wait between retry attempts (gives Docker/daemon time to recover)."""
    retry_on_timeout: bool = False
    """If True, also retry when a task hits its wall-clock timeout. Disabled by
    default because timeouts usually mean the agent is genuinely stuck and would
    time out again, wasting a lot of wall-clock time."""


class EvalConfig(ConfigBaseModel):
    """Evaluation config"""

    exp_id: str = "default"
    """Experiment ID"""

    # data
    db_url: str = EnvUtils.get_env("UTU_DB_URL", "sqlite:///test.db")
    """Database URL"""
    data: DataConfig = None
    """Data config"""

    # rollout
    agent: AgentConfig | None = None
    """Agent config for rollout"""
    concurrency: int = 1
    """Rollout parallelism"""
    pass_k: int = 1
    """Rollout k for each sample"""

    # judgement
    judge_model: ModelConfigs = Field(default_factory=ModelConfigs)
    """Judge model config"""
    judge_concurrency: int = 1
    """Judgement parallelism"""
    eval_method: str = None
    """Evaluation method"""
    # optional verify function for custom judgement (used by `train` processors etc.)
    verify_filename: str | None = None
    """Optional: Python filename under `utu/train/verify/` that contains a verify function."""
    verify_func_name: str | None = None
    """Optional: The function name inside the verify file to call for judgement."""
    
    # KORGym specific configuration
    korgym: KORGymConfig = Field(default_factory=KORGymConfig)
    """KORGym game evaluation configuration"""

    # SkillsBench specific configuration
    skillsbench: "SkillsBenchConfig" = Field(default_factory=lambda: SkillsBenchConfig())
    """SkillsBench harbor-based evaluation configuration"""

    # Experience filtering configuration
    experience_filter: ExperienceFilterConfig = Field(default_factory=ExperienceFilterConfig)
    """Experience filtering configuration for controlling injected experiences"""