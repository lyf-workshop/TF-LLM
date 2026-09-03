from typing import Any

from sqlalchemy import JSON, Index, Integer
from sqlmodel import Column, Field, Float, SQLModel, String


class ExperienceCacheModel(SQLModel, table=True):
    __tablename__ = "cache_experience"
    __table_args__ = (
        Index(
            "ix_cache_experience_name_epoch_batch",
            "experiment_name",
            "epoch",
            "batch",
        ),
        Index("ix_cache_experience_name_step", "experiment_name", "step"),
    )

    id: int | None = Field(default=None, primary_key=True)

    experiment_name: str = Field(sa_column=Column(String))
    step: int = Field(sa_column=Column(Integer))
    epoch: int | None = Field(default=None, sa_column=Column(Integer))
    batch: int | None = Field(default=None, sa_column=Column(Integer))

    experiences: Any | None = Field(default=None, sa_column=Column(JSON))

    timestamp: float = Field(sa_column=Column(Float))
    datetime: str = Field(sa_column=Column(String))
