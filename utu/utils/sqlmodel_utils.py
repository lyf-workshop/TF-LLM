from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from .env import EnvUtils
from .log import get_logger

logger = get_logger(__name__)


class SQLModelUtils:
    """Process-wide SQLModel engine with backend-aware connection settings."""

    _engine: Engine | None = None
    _engine_url: URL | None = None
    _engine_lock = threading.RLock()
    _db_available: bool | None = None
    _last_check_time: float | None = None

    @staticmethod
    def _env_int(key: str, default: int) -> int:
        try:
            return int(EnvUtils.get_env(key, str(default)))
        except (TypeError, ValueError):
            logger.warning("Invalid %s; using %s", key, default)
            return default

    @staticmethod
    def _env_float(key: str, default: float) -> float:
        try:
            return float(EnvUtils.get_env(key, str(default)))
        except (TypeError, ValueError):
            logger.warning("Invalid %s; using %s", key, default)
            return default

    @staticmethod
    def _env_bool(key: str, default: bool) -> bool:
        value = EnvUtils.get_env(key, "true" if default else "false")
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _create_engine(cls, db_url: str) -> Engine:
        url = make_url(db_url)
        pool_timeout = max(0.0, cls._env_float("UTU_DB_POOL_TIMEOUT", 30.0))
        engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}

        if url.get_backend_name() == "sqlite":
            sqlite_timeout = cls._env_float("UTU_DB_SQLITE_TIMEOUT", 30.0)
            engine_kwargs["connect_args"] = {
                "check_same_thread": False,
                "timeout": sqlite_timeout,
            }
            is_memory = url.database in {None, "", ":memory:"}
            if is_memory:
                # All sessions must share one connection for an in-memory DB.
                engine_kwargs["poolclass"] = StaticPool
            else:
                engine_kwargs.update(
                    pool_size=max(1, cls._env_int("UTU_DB_POOL_SIZE", 5)),
                    max_overflow=max(0, cls._env_int("UTU_DB_MAX_OVERFLOW", 10)),
                    pool_timeout=pool_timeout,
                )
            engine = create_engine(url, **engine_kwargs)
            cls._configure_sqlite_connections(engine, is_memory=is_memory)
            return engine

        engine_kwargs.update(
            pool_size=max(1, cls._env_int("UTU_DB_POOL_SIZE", 20)),
            max_overflow=max(0, cls._env_int("UTU_DB_MAX_OVERFLOW", 20)),
            pool_timeout=pool_timeout,
            pool_recycle=max(-1, cls._env_int("UTU_DB_POOL_RECYCLE", 1800)),
        )
        return create_engine(url, **engine_kwargs)

    @classmethod
    def _configure_sqlite_connections(cls, engine: Engine, *, is_memory: bool) -> None:
        busy_timeout_ms = max(0, int(cls._env_float("UTU_DB_SQLITE_TIMEOUT", 30.0) * 1000))
        use_wal = cls._env_bool("UTU_DB_SQLITE_WAL", True) and not is_memory

        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
                if use_wal:
                    cursor.execute("PRAGMA synchronous=NORMAL")
            finally:
                cursor.close()

        if use_wal:

            @event.listens_for(engine, "first_connect")
            def enable_sqlite_wal(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                try:
                    # WAL is persistent, so changing it once avoids taking a
                    # journal-mode lock for every pooled connection.
                    cursor.execute("PRAGMA journal_mode=WAL")
                finally:
                    cursor.close()

    @classmethod
    def configure(cls, db_url: str | None = None, *, initialize_schema: bool = True) -> Engine:
        """Configure the shared engine, replacing it only when the URL changes."""

        resolved_url = db_url or EnvUtils.get_env("UTU_DB_URL", "sqlite:///test.db") or "sqlite:///test.db"
        requested_url = make_url(resolved_url)
        with cls._engine_lock:
            if cls._engine is not None and cls._engine_url == requested_url:
                return cls._engine
            if cls._engine is not None:
                cls._engine.dispose()
            cls._engine = cls._create_engine(resolved_url)
            cls._engine_url = requested_url
            cls._db_available = None
            cls._last_check_time = None
            if initialize_schema:
                try:
                    cls._init_db_schema(cls._engine)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Auto schema creation skipped due to error: %s", exc)
            return cls._engine

    @classmethod
    def get_engine(cls) -> Engine:
        if cls._engine is None:
            return cls.configure()
        return cls._engine

    @classmethod
    def dispose_engine(cls) -> None:
        """Dispose and forget the shared engine (primarily useful for tests)."""

        with cls._engine_lock:
            if cls._engine is not None:
                cls._engine.dispose()
            cls._engine = None
            cls._engine_url = None
            cls._db_available = None
            cls._last_check_time = None

    @staticmethod
    def create_session() -> Session:
        return Session(SQLModelUtils.get_engine())

    @classmethod
    def check_db_available(cls, force_check: bool = False, cache_ttl: int = 60) -> bool:
        """Check database availability while caching the result briefly."""

        if not force_check and cls._db_available is not None and cls._last_check_time is not None:
            if time.time() - cls._last_check_time < cache_ttl:
                logger.debug("Using cached DB availability status: %s", cls._db_available)
                return cls._db_available

        try:
            engine = cls.get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            cls._db_available = True
            cls._last_check_time = time.time()
            logger.debug("Database is available")
            return True
        except Exception as exc:  # noqa: BLE001
            cls._db_available = False
            cls._last_check_time = time.time()
            logger.error("Database connection failed: %s", exc)
            return False

    @staticmethod
    def _register_models() -> None:
        # Import every table module so SQLModel.metadata includes its indexes.
        from utu.db import (  # noqa: F401
            eval_datapoint,
            experience_cache_model,
            grpo_run_log_model,
            tool_cache_model,
            tracing_model,
            trajectory_model,
        )

    @classmethod
    def _init_db_schema(cls, engine: Engine) -> None:
        """Create missing tables and indexes for newly created tables."""

        cls._register_models()
        SQLModel.metadata.create_all(engine)
        logger.info("Database schema ensured (tables created if missing).")

    @classmethod
    def missing_indexes(cls, engine: Engine | None = None) -> list[tuple[str, str]]:
        """Return declared indexes absent from an existing database."""

        engine = engine or cls.get_engine()
        cls._register_models()
        inspector = inspect(engine)
        missing: list[tuple[str, str]] = []
        existing_tables = set(inspector.get_table_names())
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing = {item["name"] for item in inspector.get_indexes(table.name)}
            for index in table.indexes:
                if index.name and index.name not in existing:
                    missing.append((table.name, index.name))
        return sorted(missing)

    @classmethod
    def ensure_indexes(cls, engine: Engine | None = None) -> list[tuple[str, str]]:
        """Create missing declared indexes, including on pre-existing tables."""

        engine = engine or cls.get_engine()
        cls._register_models()
        missing = set(cls.missing_indexes(engine))
        created: list[tuple[str, str]] = []
        for table in SQLModel.metadata.sorted_tables:
            for index in sorted(table.indexes, key=lambda item: item.name or ""):
                if not index.name:
                    continue
                key = (table.name, index.name)
                if key not in missing:
                    continue
                logger.info("Creating database index %s on %s", index.name, table.name)
                index.create(bind=engine, checkfirst=True)
                created.append(key)
        return created
