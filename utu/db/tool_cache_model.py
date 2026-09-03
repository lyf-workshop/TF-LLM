from typing import Any

from sqlalchemy import JSON, Index
from sqlmodel import Column, Field, Float, SQLModel, String


class ToolCacheModel(SQLModel, table=True):
    __tablename__ = "cache_tool"
    __table_args__ = (Index("ix_cache_tool_function_key", "function", "cache_key"),)

    id: int | None = Field(default=None, primary_key=True)

    function: str = Field(sa_column=Column(String))
    args: str | None = Field(default=None, sa_column=Column(String))
    kwargs: str | None = Field(default=None, sa_column=Column(String))
    result: Any | None = Field(default=None, sa_column=Column(JSON))

    cache_key: str = Field(sa_column=Column(String))
    timestamp: int = Field(sa_column=Column(Float))
    datetime: str = Field(sa_column=Column(String))
    execution_time: float = Field(sa_column=Column(Float))
