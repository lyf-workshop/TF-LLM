import time
from datetime import datetime
from typing import Any

from sqlmodel import select

from ..db import ExperienceCacheModel
from .log import get_logger
from .sqlmodel_utils import SQLModelUtils

logger = get_logger(__name__)


class ExperienceCache:
    """Database-based cache for training experiences."""

    @staticmethod
    def _build_stmt(experiment_name: str, step: int, epoch: int | None, batch: int | None):
        """Build a SELECT statement that matches by (experiment_name, epoch, batch) when both
        are provided, falling back to (experiment_name, step) for legacy records."""
        if epoch is not None and batch is not None:
            return select(ExperienceCacheModel).where(
                ExperienceCacheModel.experiment_name == experiment_name,
                ExperienceCacheModel.epoch == epoch,
                ExperienceCacheModel.batch == batch,
            )
        return select(ExperienceCacheModel).where(
            ExperienceCacheModel.experiment_name == experiment_name,
            ExperienceCacheModel.step == step,
        )

    @staticmethod
    def save_experiences(
        experiment_name: str,
        step: int,
        experiences: dict[str, Any],
        epoch: int | None = None,
        batch: int | None = None,
    ) -> bool:
        """Save experiences to database keyed by (experiment_name, epoch, batch).

        Falls back to (experiment_name, step) when epoch/batch are not provided so
        that the old call-sites keep working.
        """
        try:
            with SQLModelUtils.create_session() as session:
                stmt = ExperienceCache._build_stmt(experiment_name, step, epoch, batch)
                existing_record = session.exec(stmt).first()

                if existing_record:
                    key = f"epoch={epoch} batch={batch}" if epoch is not None else f"step={step}"
                    logger.debug(f"Experience cache for {experiment_name} {key} already exists, updating.")
                    existing_record.experiences = experiences
                    existing_record.timestamp = time.time()
                    existing_record.datetime = datetime.now().isoformat()
                    existing_record.step = step
                    if epoch is not None:
                        existing_record.epoch = epoch
                    if batch is not None:
                        existing_record.batch = batch
                else:
                    cache_record = ExperienceCacheModel(
                        experiment_name=experiment_name,
                        step=step,
                        epoch=epoch,
                        batch=batch,
                        experiences=experiences,
                        timestamp=time.time(),
                        datetime=datetime.now().isoformat(),
                    )
                    session.add(cache_record)

                session.commit()
                key = f"epoch={epoch} batch={batch}" if epoch is not None else f"step={step}"
                logger.debug(f"Cached experiences for {experiment_name} {key} to database")
                return True

        except Exception as e:
            logger.error(f"Failed to save experiences to database: {e}")
            return False

    @staticmethod
    def load_experiences(
        experiment_name: str,
        step: int,
        epoch: int | None = None,
        batch: int | None = None,
    ) -> dict[str, Any] | None:
        """Load experiences from database.

        Looks up by (experiment_name, epoch, batch) when provided, otherwise falls
        back to (experiment_name, step) for backward compatibility.
        """
        try:
            with SQLModelUtils.create_session() as session:
                stmt = ExperienceCache._build_stmt(experiment_name, step, epoch, batch)
                record = session.exec(stmt).first()

                if record:
                    key = f"epoch={epoch} batch={batch}" if epoch is not None else f"step={step}"
                    logger.debug(f"Using cached experiences for {experiment_name} {key} from database")
                    return record.experiences
                else:
                    return None

        except Exception as e:
            logger.error(f"Failed to load experiences from database: {e}")
            return None

    @staticmethod
    def exists(
        experiment_name: str,
        step: int,
        epoch: int | None = None,
        batch: int | None = None,
    ) -> bool:
        """Check if experiences exist in cache."""
        try:
            with SQLModelUtils.create_session() as session:
                stmt = ExperienceCache._build_stmt(experiment_name, step, epoch, batch)
                record = session.exec(stmt).first()
                return record is not None

        except Exception as e:
            logger.error(f"Failed to check experience cache existence: {e}")
            return False

    @staticmethod
    def delete_experiment_cache(experiment_name: str) -> bool:
        """Delete all cached experiences for an experiment.

        Args:
            experiment_name: Name of the experiment

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            with SQLModelUtils.create_session() as session:
                stmt = select(ExperienceCacheModel).where(ExperienceCacheModel.experiment_name == experiment_name)
                records = session.exec(stmt).all()

                for record in records:
                    session.delete(record)

                session.commit()
                logger.info(f"Deleted {len(records)} experience cache records for {experiment_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete experiment cache: {e}")
            return False
