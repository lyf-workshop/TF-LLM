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
