import sqlite3

from sqlalchemy import inspect

from utu.utils import SQLModelUtils


def _sqlite_url(path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_sqlite_engine_uses_bounded_pool_and_pragmas(tmp_path, monkeypatch):
    db_path = tmp_path / "configured.db"
    monkeypatch.setenv("UTU_DB_POOL_SIZE", "2")
    monkeypatch.setenv("UTU_DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("UTU_DB_SQLITE_TIMEOUT", "7")
    monkeypatch.setenv("UTU_DB_SQLITE_WAL", "true")

    try:
        engine = SQLModelUtils.configure(_sqlite_url(db_path))
        assert engine.pool.size() == 2
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 7000
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
    finally:
        SQLModelUtils.dispose_engine()


def test_ensure_indexes_migrates_an_existing_table(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE evaluation_data ("
            "id INTEGER PRIMARY KEY, exp_id TEXT, stage TEXT, dataset_index INTEGER)"
        )
    monkeypatch.setenv("UTU_DB_SQLITE_WAL", "false")

    try:
        engine = SQLModelUtils.configure(_sqlite_url(db_path))
        target = ("evaluation_data", "ix_evaluation_data_exp_stage_dataset_index")
        assert target in SQLModelUtils.missing_indexes(engine)

        created = SQLModelUtils.ensure_indexes(engine)

        assert target in created
        index_names = {item["name"] for item in inspect(engine).get_indexes("evaluation_data")}
        assert target[1] in index_names
        assert target not in SQLModelUtils.missing_indexes(engine)
    finally:
        SQLModelUtils.dispose_engine()
