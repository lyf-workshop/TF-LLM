from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.experiments.validate_provisional_l1 import (
    load_held_out_tasks,
    load_named_l1,
    summarize,
)


def test_load_named_l1_accepts_active_provisional_record(tmp_path: Path):
    snapshot = tmp_path / "hierarchy.json"
    snapshot.write_text(
        json.dumps(
            {
                "l1_experiences": [
                    {
                        "id": "L1_candidate",
                        "level": "L1",
                        "content": "Use modular cycles under these conditions.",
                        "lifecycle_status": "active",
                        "validation_status": "provisional",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    experience = load_named_l1(snapshot, "L1_candidate")

    assert experience.id == "L1_candidate"
    assert experience.metadata["validation_status"] == "provisional"


def test_load_named_l1_rejects_inactive_record(tmp_path: Path):
    snapshot = tmp_path / "hierarchy.json"
    snapshot.write_text(
        json.dumps(
            {
                "l1_experiences": [
                    {
                        "id": "L1_candidate",
                        "level": "L1",
                        "content": "Use modular cycles under these conditions.",
                        "lifecycle_status": "inactive",
                        "validation_status": "provisional",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lifecycle_status=active"):
        load_named_l1(snapshot, "L1_candidate")


def test_held_out_loader_rejects_exact_source_question(tmp_path: Path, monkeypatch):
    database = tmp_path / "data.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE data (dataset TEXT, [index] INTEGER, question TEXT, answer TEXT, source TEXT)"
        )
        connection.executemany(
            "INSERT INTO data VALUES (?, ?, ?, ?, ?)",
            [
                ("train", 0, "Same   question", "1", "train"),
                ("heldout", 7, "same question", "1", "heldout"),
            ],
        )
    monkeypatch.setenv("UTU_DB_URL", f"sqlite:///{database}")

    with pytest.raises(ValueError, match="overlap"):
        load_held_out_tasks("heldout", [7], source_dataset="train")


def test_summary_reports_paired_help_harm_and_keeps_small_smoke_provisional():
    def row(index: int, condition: str, reward: float) -> dict:
        return {
            "experience_id": "L1_x",
            "model": "qwen",
            "dataset": "heldout",
            "dataset_index": index,
            "repeat": 0,
            "condition": condition,
            "reward": reward,
            "response": "answer",
            "error": None,
        }

    records = [
        row(1, "no_experience", 0.0),
        row(1, "provisional_l1", 1.0),
        row(2, "no_experience", 1.0),
        row(2, "provisional_l1", 0.0),
        row(3, "no_experience", 0.0),
        row(3, "provisional_l1", 0.0),
    ]

    result = summarize(
        records,
        experience_id="L1_x",
        model="qwen",
        dataset="heldout",
        indices={1, 2, 3},
        seed=42,
        min_validation_trials=10,
        min_distinct_validation_tasks=10,
        max_harms=0,
    )

    assert result["paired_n"] == 3
    assert result["help_count"] == 1
    assert result["harm_count"] == 1
    assert result["neutral_count"] == 1
    assert result["accuracy_delta"] == 0.0
    assert result["promotion_readiness"]["decision"] == "keep_provisional"
