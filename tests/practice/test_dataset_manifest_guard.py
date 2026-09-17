from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from sqlmodel import Session

from utu.config import ConfigLoader
from utu.config.eval_config import DataConfig, EvalConfig
from utu.config.practice_config import DataArguments, TrainingFreeGRPOConfig
from utu.db import DatasetSample
from utu.practice.dataset_manifest_guard import (
    canonical_row_sha256,
    canonical_sha256,
    exclusion_snapshot_sha256,
    question_sha256,
    snapshot_sha256,
    validate_hierarchy_snapshot_sources,
    validate_practice_dataset_manifest,
)
from utu.practice.training_free_grpo import TrainingFreeGRPO
from utu.utils import SQLModelUtils

PRACTICE_DATASET = "fixture-dapo-v3"
EVALUATION_DATASET = "fixture-aime24"
SPLIT_NAME = "training_calibration_v1"


@pytest.fixture(autouse=True)
def _dispose_shared_engine():
    SQLModelUtils.dispose_engine()
    yield
    SQLModelUtils.dispose_engine()


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _sign_manifest(manifest: dict) -> dict:
    output = copy.deepcopy(manifest)
    output.pop("manifest_sha256", None)
    output["manifest_sha256"] = canonical_sha256(output)
    return output


def _build_fixture(
    tmp_path: Path,
    *,
    overlapping_question: bool = False,
) -> tuple[str, Path, list[DatasetSample], list[DatasetSample], dict]:
    practice_rows: list[DatasetSample] = []
    tasks: list[dict] = []
    for index in range(100):
        question = f"Prove fixture training identity {index} + {index} = {2 * index}."
        source_record_hash = canonical_sha256({"source_index": index + 1000, "question": question})
        metadata = {
            "domain": "mathematics",
            "task_family": "algebra" if index % 2 == 0 else "number_theory",
            "_tf_llm_dataset_snapshot": {
                "schema_version": 2,
                "source_dataset": "fixture-source",
                "source_index": index + 1000,
                "target_dataset": "fixture-dapo-v2",
                "target_index": index,
            },
            "_tf_llm_metadata_enrichment": {
                "schema_version": 3,
                "target_dataset": PRACTICE_DATASET,
                "target_index": index,
                "question_sha256": question_sha256(question),
                "source_record_sha256": source_record_hash,
            },
        }
        row = DatasetSample(
            dataset=PRACTICE_DATASET,
            index=index,
            source="fixture-source",
            source_index=index + 1000,
            question=question,
            answer=str(2 * index),
            topic="",
            level=0,
            file_name="",
            meta=metadata,
        )
        practice_rows.append(row)
        tasks.append(
            {
                "task_id": str(index),
                "namespaced_task_id": f"{PRACTICE_DATASET}:{index}",
                "target_index": index,
                "source_index": index + 1000,
                "question_sha256": question_sha256(question),
                "source_record_sha256": source_record_hash,
                "domain": metadata["domain"],
                "task_family": metadata["task_family"],
            }
        )

    evaluation_rows = [
        DatasetSample(
            dataset=EVALUATION_DATASET,
            # Deliberately reuse local numeric indices. This is not leakage:
            # task identity is namespaced and content is checked separately.
            index=index,
            source="fixture-aime",
            source_index=index,
            question=(
                practice_rows[0].question
                if overlapping_question and index == 0
                else f"Evaluate unrelated contest expression {index}^3 + 17."
            ),
            answer=str(index**3 + 17),
            topic="",
            level=0,
            file_name="",
            meta={"competition": "AIME24"},
        )
        for index in range(3)
    ]

    train_ids = [str(index) for index in range(100)]
    split_lists = {
        "train_task_ids": train_ids,
        "eval_task_ids": [],
        "excluded_task_ids": [],
    }
    split = {
        **split_lists,
        "train_task_ids_sha256": canonical_sha256(train_ids),
        "eval_task_ids_sha256": canonical_sha256([]),
        "split_sha256": canonical_sha256(split_lists),
    }
    manifest = _sign_manifest(
        {
            "schema_version": 3,
            "target_dataset": PRACTICE_DATASET,
            "target_dataset_sha256": snapshot_sha256(practice_rows),
            "dataset": {
                "name": PRACTICE_DATASET,
                "namespace": PRACTICE_DATASET,
                "version": "fixture-v3",
                "inventory_task_count": 100,
                "inventory_sha256": canonical_sha256(tasks),
            },
            "tasks": tasks,
            "splits": {SPLIT_NAME: split},
            "evaluation_exclusion": {
                "dataset": EVALUATION_DATASET,
                "record_count": len(evaluation_rows),
                "snapshot_sha256": exclusion_snapshot_sha256(evaluation_rows),
            },
        }
    )

    database_path = tmp_path / "manifest-guard.sqlite3"
    db_url = _sqlite_url(database_path)
    engine = SQLModelUtils.configure(db_url)
    with Session(engine) as session:
        session.add_all([*practice_rows, *evaluation_rows])
        session.commit()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return db_url, manifest_path, practice_rows, evaluation_rows, manifest


def _validate(db_url: str, manifest_path: Path) -> dict:
    return validate_practice_dataset_manifest(
        practice_dataset=PRACTICE_DATASET,
        manifest_path=manifest_path,
        split_name=SPLIT_NAME,
        expected_record_count=100,
        evaluation_dataset=EVALUATION_DATASET,
        db_url=db_url,
    )


def test_manifest_guard_accepts_exact_snapshot_and_namespaces_numeric_indices(tmp_path: Path):
    db_url, manifest_path, _, _, manifest = _build_fixture(tmp_path)

    evidence = _validate(db_url, manifest_path)

    assert evidence["manifest_sha256"] == manifest["manifest_sha256"]
    assert evidence["practice_record_count"] == 100
    assert evidence["evaluation_record_count"] == 3
    assert evidence["content_overlap_count"] == 0
    assert evidence["practice_namespace"] == PRACTICE_DATASET


def test_snapshot_contract_matches_dapo_builder():
    from scripts.data.create_dapo_100 import (
        _record_sha256,
        _snapshot_hash,
        _stable_records,
        canonical_sha256 as builder_canonical_sha256,
    )

    rows = [
        DatasetSample(
            dataset="not-covered-by-payload",
            index=index,
            source="source",
            source_index=20 - index,
            question=f"Question {index}",
            answer=str(index),
            topic="algebra",
            level=index,
            file_name="fixture.json",
            meta={"nested": {"index": index}},
        )
        for index in (2, 0, 1)
    ]

    assert [canonical_row_sha256(row) for row in rows] == [_record_sha256(row) for row in rows]
    assert snapshot_sha256(rows) == _snapshot_hash(rows)
    expected_exclusion_hash = builder_canonical_sha256([_record_sha256(row) for row in _stable_records(rows)])
    assert exclusion_snapshot_sha256(rows) == expected_exclusion_hash


def test_data_arguments_keep_legacy_configs_compatible_but_strict_mode_is_explicit():
    legacy = DataArguments(practice_dataset_name="legacy")
    assert legacy.require_practice_manifest is False

    with pytest.raises(ValueError, match="practice_manifest_path"):
        DataArguments(practice_dataset_name="strict", require_practice_manifest=True)


def test_formal_math_config_enables_strict_manifest_and_smoke_remains_compatible():
    measured = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_aime24")
    smoke = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_aime24_smoke")

    assert measured.data.require_practice_manifest is True
    assert measured.data.practice_manifest_path == ("configs/data/math/dapo_random_100_seed42_no_aime24_v3.json")
    assert measured.data.practice_manifest_split == SPLIT_NAME
    assert measured.data.practice_manifest_expected_records == 100
    assert smoke.data.require_practice_manifest is False


def test_manifest_guard_rejects_bad_signature(tmp_path: Path):
    db_url, manifest_path, _, _, manifest = _build_fixture(tmp_path)
    manifest["target_dataset"] = "tampered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="signature mismatch"):
        _validate(db_url, manifest_path)


def test_manifest_guard_rejects_resigned_wrong_target_dataset(tmp_path: Path):
    db_url, manifest_path, _, _, manifest = _build_fixture(tmp_path)
    manifest["target_dataset"] = "a-different-dataset"
    manifest_path.write_text(json.dumps(_sign_manifest(manifest)), encoding="utf-8")

    with pytest.raises(ValueError, match="target_dataset does not match"):
        _validate(db_url, manifest_path)


def test_manifest_guard_rejects_resigned_split_that_differs_from_inventory(tmp_path: Path):
    db_url, manifest_path, _, _, manifest = _build_fixture(tmp_path)
    split = manifest["splits"][SPLIT_NAME]
    split["train_task_ids"] = list(reversed(split["train_task_ids"]))
    split["train_task_ids_sha256"] = canonical_sha256(split["train_task_ids"])
    split["split_sha256"] = canonical_sha256(
        {
            "train_task_ids": split["train_task_ids"],
            "eval_task_ids": split["eval_task_ids"],
            "excluded_task_ids": split["excluded_task_ids"],
        }
    )
    manifest_path.write_text(json.dumps(_sign_manifest(manifest)), encoding="utf-8")

    with pytest.raises(ValueError, match="split does not exactly match"):
        _validate(db_url, manifest_path)


def test_manifest_guard_rejects_incomplete_practice_rows(tmp_path: Path):
    db_url, manifest_path, _, _, _ = _build_fixture(tmp_path)
    with SQLModelUtils.create_session() as session:
        row = session.get(DatasetSample, 100)
        assert row is not None
        session.delete(row)
        session.commit()

    with pytest.raises(ValueError, match="has 99 rows; expected exactly 100"):
        _validate(db_url, manifest_path)


def test_manifest_guard_rejects_actual_practice_snapshot_mutation(tmp_path: Path):
    db_url, manifest_path, _, _, _ = _build_fixture(tmp_path)
    with SQLModelUtils.create_session() as session:
        row = session.get(DatasetSample, 1)
        assert row is not None
        row.answer = "mutated"
        session.add(row)
        session.commit()

    with pytest.raises(ValueError, match="target_dataset_sha256"):
        _validate(db_url, manifest_path)


def test_manifest_guard_rejects_semantically_resigned_inventory_mismatch(tmp_path: Path):
    db_url, manifest_path, _, _, manifest = _build_fixture(tmp_path)
    manifest["tasks"][0]["domain"] = "physics"
    manifest["dataset"]["inventory_sha256"] = canonical_sha256(manifest["tasks"])
    manifest = _sign_manifest(manifest)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata does not match"):
        _validate(db_url, manifest_path)


def test_manifest_guard_rejects_non_contiguous_or_duplicate_indices(tmp_path: Path):
    db_url, manifest_path, _, _, _ = _build_fixture(tmp_path)
    with SQLModelUtils.create_session() as session:
        row = session.get(DatasetSample, 100)
        assert row is not None
        row.index = 98
        session.add(row)
        session.commit()

    with pytest.raises(ValueError, match="duplicate indices"):
        _validate(db_url, manifest_path)


def test_manifest_guard_rejects_changed_aime_snapshot(tmp_path: Path):
    db_url, manifest_path, _, _, _ = _build_fixture(tmp_path)
    with SQLModelUtils.create_session() as session:
        # IDs 101..103 are evaluation rows after the 100 practice rows.
        row = session.get(DatasetSample, 101)
        assert row is not None
        row.question = "Changed after the exclusion snapshot was signed"
        session.add(row)
        session.commit()

    with pytest.raises(ValueError, match="exclusion snapshot_sha256"):
        _validate(db_url, manifest_path)


def test_manifest_guard_uses_content_hashes_for_cross_dataset_leakage(tmp_path: Path):
    db_url, manifest_path, _, _, _ = _build_fixture(tmp_path, overlapping_question=True)

    with pytest.raises(ValueError, match="content leakage"):
        _validate(db_url, manifest_path)


def test_hierarchy_source_guard_checks_active_archive_and_candidate_records(tmp_path: Path):
    _, manifest_path, _, _, manifest = _build_fixture(tmp_path)
    source_id = manifest["tasks"][0]["namespaced_task_id"]
    payload = {
        f"{level}_{suffix}": [
            {
                "id": f"{level}_{suffix}",
                "source_task_ids": [source_id],
            }
        ]
        for level in ("l0", "l1", "l2")
        for suffix in ("experiences", "archive", "candidates")
    }

    evidence = validate_hierarchy_snapshot_sources(
        payload,
        manifest_path=manifest_path,
        practice_dataset=PRACTICE_DATASET,
    )

    assert evidence["practice_namespace"] == PRACTICE_DATASET
    assert evidence["inventory_task_count"] == 100
    assert evidence["referenced_source_task_count"] == 1
    assert set(evidence["collection_counts"].values()) == {1}


@pytest.mark.parametrize("source_task_ids", [None, [], ["0"], ["foreign-dataset:0"]])
def test_hierarchy_source_guard_fails_closed_for_missing_or_foreign_sources(
    tmp_path: Path,
    source_task_ids,
):
    _, manifest_path, _, _, _ = _build_fixture(tmp_path)
    record = {"id": "L0_fixture"}
    if source_task_ids is not None:
        record["source_task_ids"] = source_task_ids
    payload = {"l0_experiences": [record]}

    with pytest.raises(ValueError, match="source_task_ids|outside manifest namespace"):
        validate_hierarchy_snapshot_sources(
            payload,
            manifest_path=manifest_path,
            practice_dataset=PRACTICE_DATASET,
        )


@pytest.mark.asyncio
async def test_training_build_checks_manifest_before_any_component_construction(tmp_path: Path, monkeypatch):
    constructed: list[str] = []

    def forbidden_data_manager(*_args, **_kwargs):
        constructed.append("data_manager")
        raise AssertionError("component construction must not occur")

    monkeypatch.setattr(
        "utu.practice.training_free_grpo.TrainingFreeGRPODataManager",
        forbidden_data_manager,
    )
    config = TrainingFreeGRPOConfig(
        exp_id="guard-before-models",
        data=DataArguments(
            practice_dataset_name=PRACTICE_DATASET,
            require_practice_manifest=True,
            practice_manifest_path=str(tmp_path / "missing.json"),
            practice_manifest_split=SPLIT_NAME,
            practice_manifest_expected_records=100,
        ),
        evaluation=EvalConfig(
            db_url=_sqlite_url(tmp_path / "unused.sqlite3"),
            data=DataConfig(dataset=EVALUATION_DATASET),
        ),
    )

    with pytest.raises(ValueError, match="manifest does not exist"):
        await TrainingFreeGRPO(config).build()

    assert constructed == []
