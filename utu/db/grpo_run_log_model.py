"""
Database models for Training-Free GRPO run logging.
Records comprehensive information about GRPO training runs.
"""
from typing import Any

from sqlalchemy import JSON, Integer, Text
from sqlmodel import Column, Field, Float, SQLModel, String


class GRPORunModel(SQLModel, table=True):
    """Main table for GRPO run metadata and configuration."""
    
    __tablename__ = "grpo_run"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # Basic info
    exp_id: str = Field(sa_column=Column(String, index=True))
    """Experiment ID"""
    
    run_id: str = Field(sa_column=Column(String, unique=True, index=True))
    """Unique run ID (format: exp_id_timestamp)"""
    
    status: str = Field(default="running", sa_column=Column(String))
    """Run status: running, completed, failed"""
    
    # Time tracking
    start_time: float = Field(sa_column=Column(Float))
    """Start timestamp"""
    
    end_time: float | None = Field(default=None, sa_column=Column(Float))
    """End timestamp"""
    
    start_datetime: str = Field(sa_column=Column(String))
    """Start datetime in ISO format"""
    
    end_datetime: str | None = Field(default=None, sa_column=Column(String))
    """End datetime in ISO format"""
    
    # Configuration
    config: Any = Field(sa_column=Column(JSON))
    """Complete GRPO configuration (TrainingFreeGRPOConfig)"""
    
    agent_config: Any = Field(sa_column=Column(JSON))
    """Agent configuration used"""
    
    llm_config: Any = Field(sa_column=Column(JSON))
    """LLM model configuration used"""
    
    # Dataset info
    practice_dataset_name: str = Field(sa_column=Column(String))
    """Practice dataset name"""
    
    practice_dataset_size: int | None = Field(default=None, sa_column=Column(Integer))
    """Practice dataset size"""
    
    eval_dataset_name: str | None = Field(default=None, sa_column=Column(String))
    """Evaluation dataset name"""
    
    eval_dataset_size: int | None = Field(default=None, sa_column=Column(Integer))
    """Evaluation dataset size"""
    
    # Training parameters
    total_epochs: int = Field(sa_column=Column(Integer))
    """Total number of epochs"""
    
    batch_size: int = Field(sa_column=Column(Integer))
    """Batch size"""
    
    grpo_n: int = Field(sa_column=Column(Integer))
    """Number of rollouts per group"""
    
    # Summary statistics
    total_steps: int | None = Field(default=0, sa_column=Column(Integer))
    """Total steps completed"""
    
    total_experiences: int | None = Field(default=0, sa_column=Column(Integer))
    """Total experiences generated"""
    
    # Error info
    error_message: str | None = Field(default=None, sa_column=Column(Text))
    """Error message if failed"""
    
    error_traceback: str | None = Field(default=None, sa_column=Column(Text))
    """Error traceback if failed"""


class GRPOStepModel(SQLModel, table=True):
    """Detailed records for each GRPO step."""
    
    __tablename__ = "grpo_step"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # Reference to run
    run_id: str = Field(sa_column=Column(String, index=True))
    """Reference to GRPORunModel.run_id"""
    
    # Step info
    step: int = Field(sa_column=Column(Integer, index=True))
    """Global step number"""
    
    epoch: int = Field(sa_column=Column(Integer))
    """Epoch number"""
    
    batch_idx: int = Field(sa_column=Column(Integer))
    """Batch index within epoch"""
    
    # Time tracking
    start_time: float = Field(sa_column=Column(Float))
    """Step start timestamp"""
    
    end_time: float | None = Field(default=None, sa_column=Column(Float))
    """Step end timestamp"""
    
    duration: float | None = Field(default=None, sa_column=Column(Float))
    """Step duration in seconds"""
    
    # Tracing
    trace_id: str | None = Field(default=None, sa_column=Column(String))
    """OpenTelemetry trace ID"""
    
    # Rollout data
    batch_data: Any = Field(sa_column=Column(JSON))
    """Input data for this batch (question IDs and contents)"""
    
    rollout_results: Any | None = Field(default=None, sa_column=Column(JSON))
    """Rollout results (model outputs for each sample)"""
    
    rollout_stats: Any | None = Field(default=None, sa_column=Column(JSON))
    """Rollout statistics (accuracy, rewards, etc.)"""
    
    # Experience data
    experiences_generated: Any | None = Field(default=None, sa_column=Column(JSON))
    """Experiences generated in this step"""
    
    num_experiences: int | None = Field(default=0, sa_column=Column(Integer))
    """Number of experiences generated"""
    
    # Evaluation (if performed)
    eval_performed: bool = Field(default=False)
    """Whether evaluation was performed at this step"""
    
    eval_stats: Any | None = Field(default=None, sa_column=Column(JSON))
    """Evaluation statistics"""
    
    # Status
    status: str = Field(default="completed", sa_column=Column(String))
    """Step status: completed, failed, skipped"""
    
    error_message: str | None = Field(default=None, sa_column=Column(Text))
    """Error message if failed"""


class GRPODatasetSnapshotModel(SQLModel, table=True):
    """Snapshot of datasets used in a GRPO run."""
    
    __tablename__ = "grpo_dataset_snapshot"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # Reference to run
    run_id: str = Field(sa_column=Column(String, index=True))
    """Reference to GRPORunModel.run_id"""
    
    # Dataset info
    dataset_name: str = Field(sa_column=Column(String))
    """Dataset name"""
    
    dataset_type: str = Field(sa_column=Column(String))
    """Dataset type: practice or eval"""
    
    # Dataset content
    samples: Any = Field(sa_column=Column(JSON))
    """Complete dataset samples (questions and answers)"""
    
    sample_count: int = Field(sa_column=Column(Integer))
    """Number of samples"""
    
    # Metadata
    created_at: float = Field(sa_column=Column(Float))
    """Snapshot creation timestamp"""
    
    created_datetime: str = Field(sa_column=Column(String))
    """Snapshot creation datetime in ISO format"""

