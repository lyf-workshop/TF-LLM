from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf
from sqlmodel import select

os.environ["UTU_SKIP_AUTO_SETUP"] = "1"
os.environ.setdefault("UTU_LLM_TYPE", "chat.completions")
os.environ.setdefault("UTU_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_TYPE", "chat.completions")
os.environ.setdefault("JUDGE_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_BASE_URL", "http://127.0.0.1")
os.environ.setdefault("JUDGE_LLM_API_KEY", "offline-config-validation")

from scripts.data import (  # noqa: E402
    create_dapo_100 as dapo_script,
    process_training_free_GRPO_data as training_data_script,
)
from scripts.data.create_dapo_100 import (  # noqa: E402
    CALIBRATION_SPLIT_NAME,
    ENRICHMENT_METADATA_KEY,
    MATH_TASK_FAMILIES,
    PROVENANCE_KEY,
    TARGET_DATASET,
    UPSTREAM_METADATA_KEY,
    build_annotation_template,
    build_enriched_subset_plan,
    build_subset_plan,
    create_dapo_subset,
    create_enriched_dapo_subset,
    export_annotation_template,
    load_upstream_evidence,
    normalize_math_question,
)
from utu.config import ConfigLoader, TrainingFreeGRPOConfig  # noqa: E402
from utu.db import DatasetSample, EvaluationSample  # noqa: E402
from utu.skillsbench_data import load_task_split_manifest  # noqa: E402
from utu.utils import SQLModelUtils  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _source(index: int, question: str | None = None, *, dataset: str = "source") -> DatasetSample:
    return DatasetSample(
        dataset=dataset,
        index=index,
        source="original-import",
        question=question or f"Find the value of x_{index} when x_{index} + 1 = {index + 2}.",
        answer=str(index + 1),
        topic="algebra",
        level=2,
        file_name=f"problem-{index}.txt",
        meta={"original": index},
    )


def _evaluation(index: int, question: str, *, dataset: str = "eval") -> DatasetSample:
    return DatasetSample(dataset=dataset, index=index, question=question, answer="0")


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _annotation_manifest(
    frozen: list[DatasetSample], frozen_manifest: dict, labels: list[str]
) -> dict:
    records = []
    for sample, selected, label in zip(
        frozen, frozen_manifest["selected_records"], labels, strict=True
    ):
        records.append(
            {
                "target_index": selected["target_index"],
                "source_index": selected["source_index"],
                "question": sample.question,
                "question_sha256": selected["question_sha256"],
                "source_record_sha256": selected["source_record_sha256"],
                "task_family": label,
                "notes": None,
            }
        )
    return {
        "template": False,
        "schema_version": 1,
        "annotation_method": "human_review",
        "primary_reviewer": "reviewer-a",
        "secondary_reviewer": "reviewer-b",
        "reviewed_at": "2026-09-08T12:00:00Z",
        "source_dataset": frozen_manifest["target_dataset"],
        "source_dataset_sha256": frozen_manifest["target_dataset_sha256"],
        "source_manifest_sha256": frozen_manifest["manifest_sha256"],
        "expected_record_count": len(records),
        "task_family_enum": list(MATH_TASK_FAMILIES),
        "records": records,
    }


def _upstream_by_question(frozen_manifest: dict) -> dict[str, dict]:
    return {
        selected["question_sha256"]: {
            "data_source": "math_dapo",
            "ability": "MATH",
            "extra_info": {"index": f"upstream-{selected['source_index']}"},
        }
        for selected in frozen_manifest["selected_records"]
    }


def _upstream_evidence_payload(frozen_manifest: dict) -> dict:
    mapping = _upstream_by_question(frozen_manifest)
    return {
        "schema_version": 1,
        "records": [
            {"question_sha256": question_sha256, **evidence}
            for question_sha256, evidence in mapping.items()
        ],
    }


def _parquet_record(
    question: str,
    evidence_id: str,
    *,
    answer: str = "2",
) -> dict:
    return {
        "data_source": "math_dapo",
        "ability": "MATH",
        "prompt": [
            {
                "role": "user",
                "content": (
                    "Solve the following math problem step by step. The last line of your "
                    "response should be of the form Answer: $Answer (without quotes) where "
                    "$Answer is the answer to the problem.\n\n"
                    f"{question}"
                    '\n\nRemember to put your answer on its own line after "Answer:".'
                ),
            }
        ],
        "reward_model": {"ground_truth": answer},
        "extra_info": {"index": evidence_id},
    }


@pytest.mark.parametrize(
    "module_name",
    ("scripts.data.create_dapo_100", "scripts.data.process_training_free_GRPO_data"),
)
def test_data_script_imports_in_fresh_process(module_name: str):
    environment = os.environ.copy()
    environment["UTU_SKIP_AUTO_SETUP"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_normalizer_and_plan_are_deterministic_and_order_independent():
    wrapped = (
        "Solve the following math problem step by step. The last line of your response should be of the form "
        "Answer: $Answer (without quotes) where $Answer is the answer to the problem.\n\nFind  $x$  if x = 1."
    )
    assert normalize_math_question(wrapped) == "find $x$ if x = 1."

    source = [_source(index) for index in range(12)]
    evaluation = [_evaluation(0, "An unrelated geometry problem.")]
    first_rows, first_manifest = build_subset_plan(source, evaluation, sample_size=5, seed=42)
    second_rows, second_manifest = build_subset_plan(list(reversed(source)), evaluation, sample_size=5, seed=42)

    assert [row.source_index for row in first_rows] == [row.source_index for row in second_rows]
    assert first_manifest == second_manifest
    unsigned = {key: value for key, value in first_manifest.items() if key != "manifest_sha256"}
    encoded = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert first_manifest["manifest_sha256"] == hashlib.sha256(encoded).hexdigest()


def test_plan_excludes_evaluation_overlap_and_preserves_source_fields():
    overlap = _source(20, r"Compute \left( 2 + 3 \right).")
    source = [_source(index) for index in range(8)] + [overlap]
    evaluation = [_evaluation(24, "Compute $(2+3)$.")]

    rows, manifest = build_subset_plan(source, evaluation, sample_size=5, seed=7)

    assert overlap.index not in {row.source_index for row in rows}
    assert manifest["evaluation_exclusion"]["excluded_count"] == 1
    for row in rows:
        original = next(sample for sample in source if sample.index == row.source_index)
        assert row.source == original.source == "original-import"
        assert row.answer == original.answer
        assert row.topic == original.topic
        assert row.level == original.level
        assert row.file_name == original.file_name
        assert row.meta["original"] == original.meta["original"]
        provenance = row.meta[PROVENANCE_KEY]
        assert provenance["source_index"] == original.index
        assert provenance["sampling_seed"] == 7


def test_v2_plan_preserves_training_free_grpo_processor_route():
    source = [_source(index, dataset="DAPO-Math-17k") for index in range(6)]
    for sample in source:
        sample.source = "training_free_grpo"

    rows, manifest = build_subset_plan(
        source,
        [_evaluation(0, "An unrelated geometry problem.", dataset="AIME24")],
        sample_size=3,
    )

    assert manifest["schema_version"] == 2
    assert manifest["target_dataset"] == TARGET_DATASET
    assert {row.dataset for row in rows} == {TARGET_DATASET}
    assert {row.source for row in rows} == {"training_free_grpo"}


def test_plan_refuses_missing_leakage_set_or_insufficient_source():
    with pytest.raises(ValueError, match="Exclusion dataset"):
        build_subset_plan([_source(index) for index in range(5)], [], sample_size=2)
    with pytest.raises(ValueError, match="required"):
        build_subset_plan(
            [_source(index) for index in range(3)],
            [_evaluation(0, "Unrelated")],
            sample_size=4,
        )


def test_dapo_import_transform_and_db_mapping_preserve_native_metadata(monkeypatch):
    raw = {
        "data_source": "math_dapo",
        "ability": "MATH",
        "prompt": [
            {
                "role": "user",
                "content": (
                    "Solve the following math problem step by step. The last line of your response should be of the "
                    "form Answer: $Answer (without quotes) where $Answer is the answer to the problem.\n\n"
                    "What is 2 + 2?"
                    '\n\nRemember to put your answer on its own line after "Answer:".'
                ),
            }
        ],
        "reward_model": {"ground_truth": "4", "style": "rule"},
        "extra_info": {"index": "upstream-uuid"},
    }
    transformed = training_data_script._transform_dapo_record(raw)
    assert transformed["problem"] == "What is 2 + 2?"
    assert transformed["groundtruth"] == "4"
    assert transformed["meta"][training_data_script.UPSTREAM_METADATA_KEY] == {
        "data_source": "math_dapo",
        "ability": "MATH",
        "extra_info": {"index": "upstream-uuid"},
    }

    captured: list[DatasetSample] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def add_all(self, samples):
            captured.extend(samples)

        def commit(self):
            pass

    monkeypatch.setattr(training_data_script.SQLModelUtils, "create_session", FakeSession)
    training_data_script._save_dataset("dapo-fixture", [transformed], "db")
    assert len(captured) == 1
    assert captured[0].meta == transformed["meta"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("data_source", "", "data_source"),
        ("ability", None, "ability"),
        ("extra_info", None, "extra_info"),
    ],
)
def test_dapo_import_transform_rejects_missing_upstream_evidence(field, value, message):
    raw = {
        "data_source": "math_dapo",
        "ability": "MATH",
        "prompt": [{"role": "user", "content": "Question"}],
        "reward_model": {"ground_truth": "Answer"},
        "extra_info": {"index": "uuid"},
    }
    raw[field] = value
    with pytest.raises(ValueError, match=message):
        training_data_script._transform_dapo_record(raw)


def test_enriched_plan_preserves_frozen_tasks_and_emits_calibration_manifest(tmp_path: Path):
    source = [_source(index, dataset="DAPO-Math-17k") for index in range(8)]
    frozen, frozen_manifest = build_subset_plan(
        source,
        [_evaluation(0, "An unrelated evaluation problem.", dataset="AIME24")],
        sample_size=6,
        seed=5,
    )
    labels = ["algebra", "geometry", "number_theory", "combinatorics", "probability", "mixed"]
    annotation = _annotation_manifest(frozen, frozen_manifest, labels)
    upstream = _upstream_by_question(frozen_manifest)

    enriched, manifest = build_enriched_subset_plan(
        frozen,
        frozen_manifest,
        annotation,
        target_dataset="dapo-enriched-v3",
        dataset_version="fixture-v3",
        upstream_metadata_by_question_sha256=upstream,
    )

    assert [row.question for row in enriched] == [row.question for row in frozen]
    assert [row.answer for row in enriched] == [row.answer for row in frozen]
    assert [row.source_index for row in enriched] == [row.source_index for row in frozen]
    assert {row.dataset for row in enriched} == {"dapo-enriched-v3"}
    assert all("domain" not in row.meta for row in frozen)
    for index, row in enumerate(enriched):
        assert row.meta["domain"] == "mathematics"
        assert row.meta["task_family"] == labels[index]
        assert row.meta[UPSTREAM_METADATA_KEY]["ability"] == "MATH"
        assert row.meta[ENRICHMENT_METADATA_KEY]["domain_source"].endswith("ability=MATH")
        assert row.meta[PROVENANCE_KEY] == frozen[index].meta[PROVENANCE_KEY]

    assert manifest["dataset"]["namespace"] == "dapo-enriched-v3"
    assert manifest["dataset"]["version"] == "fixture-v3"
    assert manifest["dataset"]["parent_dataset_sha256"] == frozen_manifest["target_dataset_sha256"]
    assert manifest["evaluation_exclusion"] == frozen_manifest["evaluation_exclusion"]
    split = manifest["splits"][CALIBRATION_SPLIT_NAME]
    assert split["train_task_ids"] == [str(index) for index in range(6)]
    assert split["eval_task_ids"] == []
    assert [task["namespaced_task_id"] for task in manifest["tasks"]] == [
        f"dapo-enriched-v3:{index}" for index in range(6)
    ]

    manifest_path = tmp_path / "enriched-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert load_task_split_manifest(manifest_path) == manifest


def test_json_upstream_evidence_utility_matches_declared_hashes_and_rejects_duplicates(
    tmp_path: Path,
):
    question_hash = "a" * 64
    evidence_path = tmp_path / "upstream.json"
    payload = {
        "schema_version": 1,
        "records": [
            {
                "question_sha256": question_hash,
                "data_source": "math_dapo",
                "ability": "MATH",
                "extra_info": {"index": "native-id"},
            }
        ],
    }
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    mapping, source = load_upstream_evidence(evidence_path, [question_hash])
    assert mapping[question_hash]["extra_info"] == {"index": "native-id"}
    assert source["format"] == "json"
    assert source["file_name"] == evidence_path.name
    assert len(source["file_sha256"]) == 64

    payload["records"].append(deepcopy(payload["records"][0]))
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate upstream evidence"):
        load_upstream_evidence(evidence_path, [question_hash])


def test_parquet_evidence_replays_exact_question_last_write_wins_and_audits_conflicts(
    tmp_path: Path,
):
    question = "Compute 1 + 1."
    question_hash = hashlib.sha256(normalize_math_question(question).encode()).hexdigest()
    evidence_path = tmp_path / "upstream.parquet"
    evidence_path.write_bytes(b"offline-test-seam")
    records = [
        _parquet_record(f"  {question}  ", "normalized-collision"),
        _parquet_record(question, "older-exact-row"),
        _parquet_record("Unrelated problem.", "unrelated"),
        _parquet_record(question, "last-exact-row"),
    ]

    # Keep the replay transform tied to the actual importer contract.
    assert training_data_script._transform_dapo_record(records[-1])["problem"] == question
    mapping, source = load_upstream_evidence(
        evidence_path,
        [question_hash],
        frozen_records_by_question_sha256={
            question_hash: {"question": question, "answer": "2"}
        },
        _parquet_records=records,
    )

    assert mapping[question_hash]["extra_info"]["index"] == "last-exact-row"
    audit = source["source_audit"]
    assert audit["selection_policy"] == "historical_exact_problem_last_write_wins"
    assert audit["parquet_rows_scanned"] == 4
    assert audit["duplicate_normalized_question_count"] == 1
    assert audit["duplicate_exact_question_count"] == 1
    assert audit["conflicting_evidence_question_count"] == 1
    assert audit["conflicting_exact_evidence_question_count"] == 1
    assert audit["normalized_collision_question_count"] == 1
    assert audit["max_normalized_matches_per_question"] == 3
    assert audit["max_exact_matches_per_question"] == 2
    question_audit = audit["questions"][question_hash]
    assert question_audit["normalized_evidence_variant_count"] == 3
    assert question_audit["evidence_variant_count"] == 2
    assert question_audit["selected_parquet_row_index"] == 3


def test_parquet_evidence_fails_closed_without_exact_frozen_binding(tmp_path: Path):
    question = "Compute 1 + 1."
    question_hash = hashlib.sha256(normalize_math_question(question).encode()).hexdigest()
    evidence_path = tmp_path / "upstream.parquet"
    evidence_path.write_bytes(b"offline-test-seam")

    with pytest.raises(ValueError, match="normalized hashes alone are ambiguous"):
        load_upstream_evidence(
            evidence_path,
            [question_hash],
            _parquet_records=[_parquet_record(question, "row")],
        )
    with pytest.raises(ValueError, match="no exact historical-importer match"):
        load_upstream_evidence(
            evidence_path,
            [question_hash],
            frozen_records_by_question_sha256={
                question_hash: {"question": question, "answer": "2"}
            },
            _parquet_records=[_parquet_record(f" {question} ", "non-exact")],
        )


def test_parquet_evidence_rejects_last_write_answer_mismatch(tmp_path: Path):
    question = "Compute 1 + 1."
    question_hash = hashlib.sha256(normalize_math_question(question).encode()).hexdigest()
    evidence_path = tmp_path / "upstream.parquet"
    evidence_path.write_bytes(b"offline-test-seam")

    with pytest.raises(ValueError, match="last-write-wins answer mismatch"):
        load_upstream_evidence(
            evidence_path,
            [question_hash],
            frozen_records_by_question_sha256={
                question_hash: {"question": question, "answer": "2"}
            },
            _parquet_records=[
                _parquet_record(question, "older", answer="2"),
                _parquet_record(question, "last", answer="3"),
            ],
        )


def test_annotation_template_builder_exposes_questions_without_labels():
    source = [_source(index, dataset="DAPO-Math-17k") for index in range(6)]
    frozen, frozen_manifest = build_subset_plan(
        source,
        [_evaluation(0, "Unrelated evaluation question", dataset="AIME24")],
        sample_size=4,
    )
    template = build_annotation_template(frozen, frozen_manifest)
    assert template["template"] is True
    assert template["primary_reviewer"] is None
    assert [record["question"] for record in template["records"]] == [
        sample.question for sample in frozen
    ]
    assert [record["source_index"] for record in template["records"]] == [
        sample.source_index for sample in frozen
    ]
    assert all(record["task_family"] is None for record in template["records"])


def test_create_enriched_subset_is_idempotent_and_rejects_partial_rows(
    tmp_path: Path,
    monkeypatch,
):
    database_path = tmp_path / "enriched.db"
    frozen_manifest_path = tmp_path / "frozen.json"
    annotation_path = tmp_path / "annotations.json"
    evidence_path = tmp_path / "upstream.parquet"
    enriched_manifest_path = tmp_path / "enriched.json"
    SQLModelUtils.configure(_sqlite_url(database_path))
    try:
        source = [_source(index, dataset="DAPO-Math-17k") for index in range(8)]
        frozen, frozen_manifest = build_subset_plan(
            source,
            [_evaluation(0, "Unrelated evaluation question", dataset="AIME24")],
            sample_size=4,
        )
        frozen_manifest_path.write_text(json.dumps(frozen_manifest), encoding="utf-8")
        annotation = _annotation_manifest(
            frozen,
            frozen_manifest,
            ["algebra", "geometry", "number_theory", "combinatorics"],
        )
        annotation_path.write_text(json.dumps(annotation), encoding="utf-8")
        evidence_path.write_bytes(b"deterministic-native-parquet-test-fixture")
        evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        upstream_mapping = _upstream_by_question(frozen_manifest)

        def load_verified_test_parquet(path, required_hashes, **kwargs):
            assert Path(path) == evidence_path
            assert set(required_hashes) == set(upstream_mapping)
            assert kwargs["frozen_records_by_question_sha256"]
            return upstream_mapping, {
                "format": "parquet",
                "file_name": evidence_path.name,
                "file_sha256": evidence_sha256,
                "matched_question_count": len(upstream_mapping),
                "source_audit": {"selection_policy": "offline-test-fixture"},
            }

        monkeypatch.setattr(dapo_script, "load_upstream_evidence", load_verified_test_parquet)
        partial, _ = build_enriched_subset_plan(
            frozen,
            frozen_manifest,
            annotation,
            target_dataset="fixture-partial-v3",
            dataset_version="fixture-v3",
            upstream_metadata_by_question_sha256=_upstream_by_question(frozen_manifest),
        )
        with SQLModelUtils.create_session() as session:
            session.add_all(frozen)
            session.commit()

        first = create_enriched_dapo_subset(
            frozen_dataset=TARGET_DATASET,
            target_dataset="fixture-enriched-v3",
            dataset_version="fixture-v3",
            frozen_manifest_path=frozen_manifest_path,
            annotation_path=annotation_path,
            upstream_evidence_path=evidence_path,
            expected_upstream_evidence_sha256=evidence_sha256,
            manifest_path=enriched_manifest_path,
        )
        second = create_enriched_dapo_subset(
            frozen_dataset=TARGET_DATASET,
            target_dataset="fixture-enriched-v3",
            dataset_version="fixture-v3",
            frozen_manifest_path=frozen_manifest_path,
            annotation_path=annotation_path,
            upstream_evidence_path=evidence_path,
            expected_upstream_evidence_sha256=evidence_sha256,
            manifest_path=enriched_manifest_path,
        )
        assert first == second == json.loads(enriched_manifest_path.read_text(encoding="utf-8"))
        with SQLModelUtils.create_session() as session:
            rows = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == "fixture-enriched-v3")
            ).all()
            assert len(rows) == 4
            assert all(row.meta["domain"] == "mathematics" for row in rows)

        with SQLModelUtils.create_session() as session:
            session.add(partial[0])
            session.commit()
        with pytest.raises(ValueError, match="partial or different"):
            create_enriched_dapo_subset(
                frozen_dataset=TARGET_DATASET,
                target_dataset="fixture-partial-v3",
                dataset_version="fixture-v3",
                frozen_manifest_path=frozen_manifest_path,
                annotation_path=annotation_path,
                upstream_evidence_path=evidence_path,
                expected_upstream_evidence_sha256=evidence_sha256,
                manifest_path=tmp_path / "partial-manifest.json",
            )
    finally:
        SQLModelUtils.dispose_engine()


def test_formal_enrichment_rejects_json_and_missing_or_wrong_parquet_sha(tmp_path: Path):
    json_path = tmp_path / "upstream.json"
    json_path.write_text(json.dumps({"records": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="native local .parquet"):
        create_enriched_dapo_subset(
            annotation_path=tmp_path / "unused-annotations.json",
            upstream_evidence_path=json_path,
            expected_upstream_evidence_sha256="0" * 64,
        )

    parquet_path = tmp_path / "upstream.parquet"
    parquet_path.write_bytes(b"local-parquet-snapshot")
    with pytest.raises(ValueError, match="must be a lowercase SHA-256"):
        create_enriched_dapo_subset(
            annotation_path=tmp_path / "unused-annotations.json",
            upstream_evidence_path=parquet_path,
            expected_upstream_evidence_sha256=None,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        create_enriched_dapo_subset(
            annotation_path=tmp_path / "unused-annotations.json",
            upstream_evidence_path=parquet_path,
            expected_upstream_evidence_sha256="0" * 64,
        )


def test_enrich_cli_requires_and_forwards_upstream_evidence_sha256(
    tmp_path: Path,
    monkeypatch,
):
    common_args = [
        "create_dapo_100.py",
        "--enrich",
        "--annotation-path",
        str(tmp_path / "annotations.json"),
        "--upstream-evidence-path",
        str(tmp_path / "upstream.parquet"),
    ]
    monkeypatch.setattr(sys, "argv", common_args)
    with pytest.raises(SystemExit):
        dapo_script.main()

    expected_sha256 = "a" * 64
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(dapo_script, "create_enriched_dapo_subset", fake_create)
    monkeypatch.setattr(
        sys,
        "argv",
        [*common_args, "--upstream-evidence-sha256", expected_sha256],
    )
    dapo_script.main()

    assert captured["upstream_evidence_path"] == tmp_path / "upstream.parquet"
    assert captured["expected_upstream_evidence_sha256"] == expected_sha256


def test_export_annotation_template_is_read_only_and_idempotent(tmp_path: Path):
    database_path = tmp_path / "template.db"
    frozen_manifest_path = tmp_path / "frozen.json"
    output_path = tmp_path / "review.json"
    SQLModelUtils.configure(_sqlite_url(database_path))
    try:
        source = [_source(index, dataset="DAPO-Math-17k") for index in range(6)]
        frozen, frozen_manifest = build_subset_plan(
            source,
            [_evaluation(0, "Unrelated evaluation question", dataset="AIME24")],
            sample_size=3,
        )
        expected_questions = [sample.question for sample in frozen]
        frozen_manifest_path.write_text(json.dumps(frozen_manifest), encoding="utf-8")
        with SQLModelUtils.create_session() as session:
            session.add_all(frozen)
            session.commit()
        first = export_annotation_template(
            frozen_manifest_path=frozen_manifest_path,
            output_path=output_path,
        )
        second = export_annotation_template(
            frozen_manifest_path=frozen_manifest_path,
            output_path=output_path,
        )
        assert first == second
        assert [record["question"] for record in first["records"]] == expected_questions
        with SQLModelUtils.create_session() as session:
            datasets = session.exec(select(DatasetSample.dataset)).all()
        assert datasets == [TARGET_DATASET] * 3
    finally:
        SQLModelUtils.dispose_engine()


def test_checked_in_annotation_template_is_complete_hash_binding_with_no_labels():
    frozen_manifest = json.loads(
        (ROOT / "configs/data/math/dapo_random_100_seed42_no_aime24_v2.json").read_text(
            encoding="utf-8"
        )
    )
    template = json.loads(
        (
            ROOT
            / "configs/data/math/dapo_random_100_seed42_no_aime24_annotations_TEMPLATE.json"
        ).read_text(encoding="utf-8")
    )
    assert template["template"] is True
    assert template["annotation_method"] == "human_review"
    assert template["primary_reviewer"] is None
    assert template["secondary_reviewer"] is None
    assert template["reviewed_at"] is None
    assert template["source_dataset"] == frozen_manifest["target_dataset"]
    assert template["source_dataset_sha256"] == frozen_manifest["target_dataset_sha256"]
    assert template["source_manifest_sha256"] == frozen_manifest["manifest_sha256"]
    assert template["task_family_enum"] == list(MATH_TASK_FAMILIES)
    assert len(template["records"]) == template["expected_record_count"] == 100
    assert [record["target_index"] for record in template["records"]] == list(range(100))
    assert all(record["task_family"] is None for record in template["records"])
    assert all(isinstance(record["question"], str) and record["question"] for record in template["records"])
    assert [
        (
            record["target_index"],
            record["source_index"],
            record["question_sha256"],
            record["source_record_sha256"],
        )
        for record in template["records"]
    ] == [
        (
            record["target_index"],
            record["source_index"],
            record["question_sha256"],
            record["source_record_sha256"],
        )
        for record in frozen_manifest["selected_records"]
    ]


@pytest.mark.parametrize(
    "failure",
    (
        "missing_record",
        "duplicate_record",
        "question_hash",
        "source_hash",
        "unknown_family",
        "missing_family",
        "non_human_method",
        "template_mode",
        "missing_primary_reviewer",
        "missing_secondary_reviewer",
        "same_reviewer",
        "missing_reviewed_at",
        "reviewed_at_without_timezone",
    ),
)
def test_enriched_plan_rejects_untrusted_or_incomplete_annotations(failure: str):
    source = [_source(index, dataset="DAPO-Math-17k") for index in range(6)]
    frozen, frozen_manifest = build_subset_plan(
        source,
        [_evaluation(0, "Unrelated evaluation question", dataset="AIME24")],
        sample_size=4,
    )
    annotation = _annotation_manifest(
        frozen,
        frozen_manifest,
        ["algebra", "geometry", "number_theory", "combinatorics"],
    )
    if failure == "missing_record":
        annotation["records"].pop()
    elif failure == "duplicate_record":
        annotation["records"].append(deepcopy(annotation["records"][0]))
    elif failure == "question_hash":
        annotation["records"][0]["question_sha256"] = "0" * 64
    elif failure == "source_hash":
        annotation["records"][0]["source_record_sha256"] = "0" * 64
    elif failure == "unknown_family":
        annotation["records"][0]["task_family"] = "calculus_guess"
    elif failure == "missing_family":
        annotation["records"][0]["task_family"] = None
    elif failure == "non_human_method":
        annotation["annotation_method"] = "llm_generated"
    elif failure == "template_mode":
        annotation["template"] = True
    elif failure == "missing_primary_reviewer":
        annotation["primary_reviewer"] = None
    elif failure == "missing_secondary_reviewer":
        annotation["secondary_reviewer"] = ""
    elif failure == "same_reviewer":
        annotation["secondary_reviewer"] = annotation["primary_reviewer"]
    elif failure == "missing_reviewed_at":
        annotation["reviewed_at"] = None
    elif failure == "reviewed_at_without_timezone":
        annotation["reviewed_at"] = "2026-09-08T12:00:00"

    with pytest.raises(ValueError):
        build_enriched_subset_plan(
            frozen,
            frozen_manifest,
            annotation,
            upstream_metadata_by_question_sha256=_upstream_by_question(frozen_manifest),
        )


@pytest.mark.parametrize("ability", (None, "", "GENERAL"))
def test_enriched_plan_requires_math_domain_evidence_from_upstream_ability(ability):
    source = [_source(index, dataset="DAPO-Math-17k") for index in range(4)]
    frozen, frozen_manifest = build_subset_plan(
        source,
        [_evaluation(0, "Unrelated evaluation question", dataset="AIME24")],
        sample_size=2,
    )
    annotation = _annotation_manifest(frozen, frozen_manifest, ["algebra", "geometry"])
    upstream = _upstream_by_question(frozen_manifest)
    upstream[frozen_manifest["selected_records"][0]["question_sha256"]]["ability"] = ability

    with pytest.raises(ValueError, match="ability=MATH"):
        build_enriched_subset_plan(
            frozen,
            frozen_manifest,
            annotation,
            upstream_metadata_by_question_sha256=upstream,
        )


def test_database_creation_is_idempotent_and_rejects_partial_target(tmp_path: Path):
    database_path = tmp_path / "datasets.db"
    manifest_path = tmp_path / "manifest.json"
    SQLModelUtils.configure(_sqlite_url(database_path))
    try:
        with SQLModelUtils.create_session() as session:
            session.add_all([_source(index, dataset="source-dataset") for index in range(10)])
            session.add(_evaluation(0, "No overlap here", dataset="eval-dataset"))
            session.commit()

        first = create_dapo_subset(
            source_dataset="source-dataset",
            target_dataset="target-dataset",
            exclusion_dataset="eval-dataset",
            sample_size=5,
            seed=9,
            manifest_path=manifest_path,
        )
        second = create_dapo_subset(
            source_dataset="source-dataset",
            target_dataset="target-dataset",
            exclusion_dataset="eval-dataset",
            sample_size=5,
            seed=9,
            manifest_path=manifest_path,
        )
        assert first == second == json.loads(manifest_path.read_text(encoding="utf-8"))
        with SQLModelUtils.create_session() as session:
            rows = session.exec(select(DatasetSample).where(DatasetSample.dataset == "target-dataset")).all()
            assert len(rows) == 5
            rows[0].answer = "corrupted"
            session.add(rows[0])
            session.commit()

        with pytest.raises(ValueError, match="refusing to overwrite"):
            create_dapo_subset(
                source_dataset="source-dataset",
                target_dataset="target-dataset",
                exclusion_dataset="eval-dataset",
                sample_size=5,
                seed=9,
                manifest_path=manifest_path,
            )
    finally:
        SQLModelUtils.dispose_engine()


def test_math_dapo_100_config_resolves_requested_model_and_dataset():
    config_dir = ROOT / "configs"
    with initialize_config_dir(version_base="1.3", config_dir=str(config_dir)):
        raw = OmegaConf.to_container(
            compose(config_name="practice/math/math_dapo_100_aime24"),
            resolve=True,
        )
    assert isinstance(raw, dict)
    config = TrainingFreeGRPOConfig.model_validate(raw, extra="forbid")
    runtime_config = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_aime24")

    assert config.data.practice_dataset_name == "DAPO-Math-17k-Random-100-Seed42-No-AIME24-v3"
    assert runtime_config.data.practice_dataset_name == config.data.practice_dataset_name
    assert config.evaluation.exp_id == config.exp_id
    assert runtime_config.evaluation.exp_id == runtime_config.exp_id
    assert config.evaluation.data.dataset == "AIME24"
    assert config.evaluation.agent.model.model_provider.model == "deepseek-v4-flash"
    assert runtime_config.evaluation.agent.model.model_provider.model == "deepseek-v4-flash"
    assert config.evaluation.judge_model.model_provider.model == "deepseek-v4-flash"
    assert config.practice.epochs == 1
    assert config.practice.batch_size == config.practice.rollout_data_truncate == 100
    assert config.practice.shuffle_data is False
    assert config.practice.hierarchical_learning.aggregation_temperature == 0.0
    assert config.practice.hierarchical_learning.experience_output_language == "english"


def test_math_dapo_100_smoke_config_is_isolated_from_measured_run():
    measured = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_aime24")
    smoke = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_aime24_smoke")

    assert smoke.exp_id.endswith("_smoke_v2")
    assert smoke.evaluation.exp_id == smoke.exp_id
    assert smoke.exp_id != measured.exp_id
    assert smoke.evaluation.exp_id != measured.evaluation.exp_id
    assert smoke.data.practice_dataset_name == "DAPO-Math-17k-Random-100-Seed42-No-AIME24-v2"
    assert smoke.data.practice_dataset_name != measured.data.practice_dataset_name
    assert smoke.evaluation.data.dataset == measured.evaluation.data.dataset == "AIME24"
    assert (
        smoke.evaluation.agent.model.model_provider.model
        == measured.evaluation.agent.model.model_provider.model
        == "deepseek-v4-flash"
    )
    assert smoke.practice.epochs == 1
    assert smoke.practice.batch_size == 1
    assert smoke.practice.grpo_n == 1
    assert smoke.practice.rollout_concurrency == 1
    assert smoke.practice.rollout_data_truncate == 1
    assert smoke.practice.do_eval is False

    measured_hierarchy = measured.practice.hierarchical_learning
    smoke_hierarchy = smoke.practice.hierarchical_learning
    assert smoke_hierarchy.embedding_cache_path != measured_hierarchy.embedding_cache_path
    assert smoke_hierarchy.experience_save_path != measured_hierarchy.experience_save_path
    assert smoke_hierarchy.clustering_audit_path != measured_hierarchy.clustering_audit_path
    assert smoke_hierarchy.experience_output_language == "same_as_input"
    assert measured_hierarchy.experience_output_language == "english"
    assert smoke_hierarchy.l0_similarity_threshold_provisional is True
    assert smoke_hierarchy.l1_similarity_threshold_provisional is True
    assert smoke_hierarchy.similarity_thresholds_provisional is None
    assert smoke_hierarchy.allow_provisional_aggregation is False


def test_math_dapo_v2_routes_through_training_processor_and_math_verifier(monkeypatch):
    monkeypatch.setattr(SQLModelUtils, "check_db_available", lambda *args, **kwargs: False)

    import utu.eval.processer.base_llm_processor as base_llm_processor
    from utu.eval.processer import TrainingFreeGRPOProcesser
    from utu.practice.rollout_manager import RolloutManager

    class NoNetworkClient:
        def __init__(self, **kwargs):
            pass

        async def query_one(self, **kwargs):
            raise AssertionError("external LLM calls are forbidden in this test")

    monkeypatch.setattr(base_llm_processor, "SimplifiedAsyncOpenAI", NoNetworkClient)
    config = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_aime24_smoke")
    assert config.evaluation.verify_filename == "math.py"
    assert config.evaluation.verify_func_name == "verify_func"

    manager = RolloutManager.__new__(RolloutManager)
    manager.config = config.evaluation
    manager._source_to_processer = {}
    saved: list[EvaluationSample] = []
    manager.dataset = type("DatasetSink", (), {"save": lambda self, sample: saved.append(sample)})()

    sample = EvaluationSample(
        dataset=config.data.practice_dataset_name,
        dataset_index=0,
        source="training_free_grpo",
        raw_question="What is 1 + 1?",
        correct_answer="2",
        exp_id=f"{config.evaluation.exp_id}_epoch_0",
    )
    processor = manager._get_processer(sample.source)
    assert isinstance(processor, TrainingFreeGRPOProcesser)
    assert processor.verify_func is not None
    assert Path(processor.verify_func.__code__.co_filename).resolve() == (
        ROOT / "utu" / "practice" / "verify" / "math.py"
    ).resolve()

    recorder = SimpleNamespace(experiences={"l0-test": "Check arithmetic before submitting."})
    processed = manager.preprocess_one(sample, recorder)

    assert processed is sample
    assert "Check arithmetic before submitting." in processed.augmented_question
    assert processed.stage == "init"
    assert saved == [sample]

    processed.response = r"\boxed{2}"
    assert processor.verify_func(processed)["reward"] == 1.0


def test_explicit_math_verifier_load_failure_does_not_fall_back_to_llm_judge():
    from utu.eval.processer import TrainingFreeGRPOProcesser

    config = ConfigLoader.load_training_free_grpo_config("math/math_dapo_100_aime24_smoke")
    broken = config.evaluation.model_copy(update={"verify_filename": "missing_math_verifier.py"})

    with pytest.raises(RuntimeError, match="refusing to fall back to LLM judging"):
        TrainingFreeGRPOProcesser(broken)
