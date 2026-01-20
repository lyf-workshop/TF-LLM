from typing import Literal

from pydantic import Field

from .base_config import ConfigBaseModel
from .eval_config import EvalConfig, KORGymConfig


class HierarchicalLearningConfig(ConfigBaseModel):
    """Configuration for hierarchical experience learning (L0/L1/L2)."""
    
    enabled: bool = False
    """Enable hierarchical experience learning"""
    l1_aggregation_threshold: int = 5
    """Number of L0 experiences needed to generate one L1"""
    l2_aggregation_threshold: int = 3
    """Number of L1 experiences needed to generate one L2"""
    max_l0_per_problem: int = 1
    """Maximum L0 experiences to keep per problem"""
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
