"""
Logger for Training-Free GRPO runs.
Records comprehensive information about GRPO training runs to database.
"""
import time
import traceback
from datetime import datetime
from typing import Any

from sqlmodel import select

from ..db import GRPODatasetSnapshotModel, GRPORunModel, GRPOStepModel
from .log import get_logger
from .sqlmodel_utils import SQLModelUtils

logger = get_logger(__name__)


class GRPOLogger:
    """Comprehensive logger for Training-Free GRPO runs."""

    def __init__(self, exp_id: str, config: Any):
        """Initialize GRPO logger.

        Args:
            exp_id: Experiment ID
            config: TrainingFreeGRPOConfig instance
        """
        self.exp_id = exp_id
        self.config = config
        self.run_id = f"{exp_id}_{int(time.time())}"
        self.start_time = time.time()
        self.current_step_data = {}
        
        # Check if database is available
        if not SQLModelUtils.check_db_available():
            logger.warning("Database not available! GRPO logging will be disabled.")
            self.enabled = False
        else:
            self.enabled = True

    def log_run_start(
        self,
        agent_config: dict,
        model_config: dict,
        practice_dataset_name: str,
        practice_dataset_size: int | None = None,
        eval_dataset_name: str | None = None,
        eval_dataset_size: int | None = None,
    ) -> str:
        """Log the start of a GRPO run.

        Args:
            agent_config: Agent configuration dict
            model_config: Model configuration dict
            practice_dataset_name: Practice dataset name
            practice_dataset_size: Practice dataset size
            eval_dataset_name: Evaluation dataset name
            eval_dataset_size: Evaluation dataset size

        Returns:
            str: Run ID
        """
        if not self.enabled:
            return self.run_id

        try:
            with SQLModelUtils.create_session() as session:
                run_record = GRPORunModel(
                    exp_id=self.exp_id,
                    run_id=self.run_id,
                    status="running",
                    start_time=self.start_time,
                    start_datetime=datetime.fromtimestamp(self.start_time).isoformat(),
                    config=self.config.model_dump() if hasattr(self.config, "model_dump") else dict(self.config),
                    agent_config=agent_config,
                    llm_config=model_config,
                    practice_dataset_name=practice_dataset_name,
                    practice_dataset_size=practice_dataset_size,
                    eval_dataset_name=eval_dataset_name,
                    eval_dataset_size=eval_dataset_size,
                    total_epochs=self.config.practice.epochs,
                    batch_size=self.config.practice.batch_size,
                    grpo_n=self.config.practice.grpo_n,
                )
                session.add(run_record)
                session.commit()
                logger.info(f"✅ GRPO run logged: {self.run_id}")

        except Exception as e:
            logger.error(f"Failed to log GRPO run start: {e}")

        return self.run_id

    def log_run_end(self, status: str = "completed", error: Exception | None = None):
        """Log the end of a GRPO run.

        Args:
            status: Run status (completed, failed)
            error: Exception if failed
        """
        if not self.enabled:
            return

        try:
            end_time = time.time()
            with SQLModelUtils.create_session() as session:
                stmt = select(GRPORunModel).where(GRPORunModel.run_id == self.run_id)
                run_record = session.exec(stmt).first()

                if run_record:
                    run_record.status = status
                    run_record.end_time = end_time
                    run_record.end_datetime = datetime.fromtimestamp(end_time).isoformat()

                    if error:
                        run_record.error_message = str(error)
                        run_record.error_traceback = traceback.format_exc()

                    session.commit()
                    duration = end_time - self.start_time
                    logger.info(f"✅ GRPO run ended: {self.run_id} (status={status}, duration={duration:.2f}s)")

        except Exception as e:
            logger.error(f"Failed to log GRPO run end: {e}")

    def log_step_start(
        self,
        step: int,
        epoch: int,
        batch_idx: int,
        batch_data: list[dict],
        trace_id: str | None = None,
    ):
        """Log the start of a GRPO step.

        Args:
            step: Global step number
            epoch: Epoch number
            batch_idx: Batch index
            batch_data: Input data for this batch
            trace_id: OpenTelemetry trace ID
        """
        if not self.enabled:
            return

        self.current_step_data = {
            "step": step,
            "epoch": epoch,
            "batch_idx": batch_idx,
            "start_time": time.time(),
            "trace_id": trace_id,
            "batch_data": batch_data,
        }

    def log_step_end(
        self,
        rollout_results: Any | None = None,
        rollout_stats: dict | None = None,
        experiences: dict | None = None,
        eval_stats: dict | None = None,
        status: str = "completed",
        error: Exception | None = None,
    ):
        """Log the end of a GRPO step.

        Args:
            rollout_results: Rollout results
            rollout_stats: Rollout statistics
            experiences: Experiences generated
            eval_stats: Evaluation statistics
            status: Step status
            error: Exception if failed
        """
        if not self.enabled or not self.current_step_data:
            return

        try:
            end_time = time.time()
            start_time = self.current_step_data["start_time"]
            duration = end_time - start_time

            with SQLModelUtils.create_session() as session:
                step_record = GRPOStepModel(
                    run_id=self.run_id,
                    step=self.current_step_data["step"],
                    epoch=self.current_step_data["epoch"],
                    batch_idx=self.current_step_data["batch_idx"],
                    start_time=start_time,
                    end_time=end_time,
                    duration=duration,
                    trace_id=self.current_step_data.get("trace_id"),
                    batch_data=self.current_step_data["batch_data"],
                    rollout_results=rollout_results,
                    rollout_stats=rollout_stats,
                    experiences_generated=experiences,
                    num_experiences=len(experiences) if experiences else 0,
                    eval_performed=eval_stats is not None,
                    eval_stats=eval_stats,
                    status=status,
                    error_message=str(error) if error else None,
                )
                session.add(step_record)

                # Update run statistics
                stmt = select(GRPORunModel).where(GRPORunModel.run_id == self.run_id)
                run_record = session.exec(stmt).first()
                if run_record:
                    run_record.total_steps = (run_record.total_steps or 0) + 1
                    run_record.total_experiences = (run_record.total_experiences or 0) + (
                        len(experiences) if experiences else 0
                    )

                session.commit()
                logger.debug(f"✅ Step {self.current_step_data['step']} logged (duration={duration:.2f}s)")

        except Exception as e:
            logger.error(f"Failed to log GRPO step end: {e}")

        finally:
            self.current_step_data = {}

    def log_dataset_snapshot(self, dataset_name: str, dataset_type: str, samples: list[dict]):
        """Log a snapshot of the dataset used in this run.

        Args:
            dataset_name: Dataset name
            dataset_type: Dataset type (practice or eval)
            samples: Dataset samples
        """
        if not self.enabled:
            return

        try:
            with SQLModelUtils.create_session() as session:
                snapshot = GRPODatasetSnapshotModel(
                    run_id=self.run_id,
                    dataset_name=dataset_name,
                    dataset_type=dataset_type,
                    samples=samples,
                    sample_count=len(samples),
                    created_at=time.time(),
                    created_datetime=datetime.now().isoformat(),
                )
                session.add(snapshot)
                session.commit()
                logger.info(f"✅ Dataset snapshot logged: {dataset_name} ({dataset_type}, {len(samples)} samples)")

        except Exception as e:
            logger.error(f"Failed to log dataset snapshot: {e}")

    @staticmethod
    def get_run_by_id(run_id: str) -> GRPORunModel | None:
        """Get a run record by run ID.

        Args:
            run_id: Run ID

        Returns:
            GRPORunModel or None if not found
        """
        try:
            with SQLModelUtils.create_session() as session:
                stmt = select(GRPORunModel).where(GRPORunModel.run_id == run_id)
                return session.exec(stmt).first()
        except Exception as e:
            logger.error(f"Failed to get run: {e}")
            return None

    @staticmethod
    def get_runs_by_exp_id(exp_id: str) -> list[GRPORunModel]:
        """Get all runs for an experiment.

        Args:
            exp_id: Experiment ID

        Returns:
            List of GRPORunModel
        """
        try:
            with SQLModelUtils.create_session() as session:
                stmt = select(GRPORunModel).where(GRPORunModel.exp_id == exp_id).order_by(GRPORunModel.start_time)
                return list(session.exec(stmt).all())
        except Exception as e:
            logger.error(f"Failed to get runs: {e}")
            return []

    @staticmethod
    def get_steps_by_run_id(run_id: str) -> list[GRPOStepModel]:
        """Get all steps for a run.

        Args:
            run_id: Run ID

        Returns:
            List of GRPOStepModel
        """
        try:
            with SQLModelUtils.create_session() as session:
                stmt = select(GRPOStepModel).where(GRPOStepModel.run_id == run_id).order_by(GRPOStepModel.step)
                return list(session.exec(stmt).all())
        except Exception as e:
            logger.error(f"Failed to get steps: {e}")
            return []

    @staticmethod
    def get_dataset_snapshot(run_id: str, dataset_type: str) -> GRPODatasetSnapshotModel | None:
        """Get dataset snapshot for a run.

        Args:
            run_id: Run ID
            dataset_type: Dataset type (practice or eval)

        Returns:
            GRPODatasetSnapshotModel or None if not found
        """
        try:
            with SQLModelUtils.create_session() as session:
                stmt = select(GRPODatasetSnapshotModel).where(
                    GRPODatasetSnapshotModel.run_id == run_id, GRPODatasetSnapshotModel.dataset_type == dataset_type
                )
                return session.exec(stmt).first()
        except Exception as e:
            logger.error(f"Failed to get dataset snapshot: {e}")
            return None

