"""Create a deterministic, auditable random subset of DAPO-Math-17k.

The source database order is deliberately ignored. Records are normalized,
deduplicated, filtered against the evaluation set, sorted by stable SHA-256
fingerprints, and only then sampled with a local seeded RNG.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import os
import random
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from utu import utils as utu_utils
from utu.db import DatasetSample

DIR_ROOT = utu_utils.DIR_ROOT
SQLModelUtils = utu_utils.SQLModelUtils


SOURCE_DATASET = "DAPO-Math-17k"
TARGET_DATASET = "DAPO-Math-17k-Random-100-Seed42-No-AIME24-v2"
EXCLUSION_DATASET = "AIME24"
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_SEED = 42
NORMALIZER_VERSION = "math-question-v1"
MANIFEST_SCHEMA_VERSION = 2
PROVENANCE_KEY = "_tf_llm_dataset_snapshot"
UPSTREAM_METADATA_KEY = "_tf_llm_upstream"
ENRICHMENT_METADATA_KEY = "_tf_llm_metadata_enrichment"
ENRICHED_TARGET_DATASET = "DAPO-Math-17k-Random-100-Seed42-No-AIME24-v3"
ENRICHED_DATASET_VERSION = "dapo-random-100-seed42-no-aime24-v3"
ANNOTATION_SCHEMA_VERSION = 1
ENRICHED_MANIFEST_SCHEMA_VERSION = 3
CALIBRATION_SPLIT_NAME = "training_calibration_v1"
MATH_TASK_FAMILIES = (
    "algebra",
    "geometry",
    "number_theory",
    "combinatorics",
    "probability",
    "analysis",
    "mixed",
)
DEFAULT_MANIFEST_PATH = (
    DIR_ROOT / "configs" / "data" / "math" / "dapo_random_100_seed42_no_aime24_v2.json"
)
DEFAULT_ENRICHED_MANIFEST_PATH = (
    DIR_ROOT / "configs" / "data" / "math" / "dapo_random_100_seed42_no_aime24_v3.json"
)

_DAPO_PREFIX = re.compile(
    r"^\s*Solve the following math problem step by step\.\s*"
    r"The last line of your response should be of the form Answer:\s*\$Answer\s*"
    r"\(without quotes\) where \$Answer is the answer to the problem\.\s*",
    re.IGNORECASE,
)
_DAPO_SUFFIX = re.compile(
    r"\s*Remember to put your answer on its own line after [\"']Answer:[\"']\.\s*$",
    re.IGNORECASE,
)
# These literals intentionally mirror the historical DAPO importer.  Exact
# ``str.replace`` semantics matter here: the frozen v2 question was produced
# before normalized hashes were calculated, and the importer resolved repeated
# raw questions with dict assignment (last row wins).
_HISTORICAL_DAPO_PREFIX = (
    "Solve the following math problem step by step. The last line of your response should be of the "
    "form Answer: $Answer (without quotes) where $Answer is the answer to the problem.\n\n"
)
_HISTORICAL_DAPO_SUFFIX = (
    '\n\nRemember to put your answer on its own line after "Answer:".'
)
_PRESENTATION_TEX = re.compile(r"\\(?:(?:left|right|quad|qquad)\b|[,!;:])")
_TOKEN = re.compile(r"[a-z0-9]+|\\[a-z]+|[^\s]", re.IGNORECASE)


def canonical_sha256(value: Any) -> str:
    """Return a stable SHA-256 for JSON-compatible data."""

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_math_question(question: str | None, *, relaxed: bool = False) -> str:
    """Normalize presentation differences without removing math operators."""

    value = unicodedata.normalize("NFKC", question or "")
    value = value.replace("\ufeff", "").replace("\u200b", "").replace("\r\n", "\n").replace("\r", "\n")
    value = value.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2212": "-",
                "\u2013": "-",
                "\u2014": "-",
            }
        )
    )
    value = _DAPO_PREFIX.sub("", value)
    value = _DAPO_SUFFIX.sub("", value)
    value = value.casefold().strip()
    if relaxed:
        value = _PRESENTATION_TEX.sub("", value)
        for marker in ("$", r"\(", r"\)", r"\[", r"\]"):
            value = value.replace(marker, "")
        return re.sub(r"\s+", "", value)
    return re.sub(r"\s+", " ", value)


def _record_payload(sample: DatasetSample) -> dict[str, Any]:
    return {
        "index": sample.index,
        "source": sample.source,
        "source_index": sample.source_index,
        "question": sample.question,
        "answer": sample.answer,
        "topic": sample.topic,
        "level": sample.level,
        "file_name": sample.file_name,
        "meta": sample.meta,
    }


def _record_sha256(sample: DatasetSample) -> str:
    return canonical_sha256(_record_payload(sample))


def _question_sha256(sample: DatasetSample, *, relaxed: bool = False) -> str:
    return hashlib.sha256(normalize_math_question(sample.question, relaxed=relaxed).encode("utf-8")).hexdigest()


def _stable_records(samples: Iterable[DatasetSample]) -> list[DatasetSample]:
    """Sort independently of database insertion/query order."""

    return sorted(
        samples,
        key=lambda sample: (
            _question_sha256(sample, relaxed=True),
            canonical_sha256({"answer": sample.answer, "topic": sample.topic, "level": sample.level}),
            _record_sha256(sample),
        ),
    )


def _shingles(question: str | None, size: int = 5) -> set[tuple[str, ...]]:
    tokens = _TOKEN.findall(normalize_math_question(question))
    if not tokens:
        return set()
    if len(tokens) <= size:
        return {tuple(tokens)}
    return {tuple(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def _jaccard(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _source_index(sample: DatasetSample) -> int | None:
    # TARGET_DATASET points directly to SOURCE_DATASET, so the immediate
    # source's index is authoritative even if it has its own source_index.
    return sample.index


def _with_provenance(
    sample: DatasetSample,
    *,
    source_dataset: str,
    target_dataset: str,
    target_index: int,
    seed: int,
) -> Any:
    original_meta = copy.deepcopy(sample.meta)
    if isinstance(original_meta, dict):
        if PROVENANCE_KEY in original_meta:
            raise ValueError(f"Source record {sample.index!r} already uses reserved metadata key {PROVENANCE_KEY!r}")
        metadata = original_meta
    elif original_meta is None:
        metadata = {}
    else:
        metadata = {"source_meta": original_meta}
    metadata[PROVENANCE_KEY] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_dataset": source_dataset,
        "source_index": _source_index(sample),
        "source_record_sha256": _record_sha256(sample),
        "source_original_source": sample.source,
        "target_dataset": target_dataset,
        "target_index": target_index,
        "sampling_seed": seed,
        "normalizer_version": NORMALIZER_VERSION,
    }
    return metadata


def _snapshot_hash(samples: Sequence[DatasetSample]) -> str:
    ordered = sorted(samples, key=lambda sample: (sample.index is None, sample.index, _record_sha256(sample)))
    return canonical_sha256([_record_payload(sample) for sample in ordered])


def build_subset_plan(
    source_samples: Sequence[DatasetSample],
    exclusion_samples: Sequence[DatasetSample],
    *,
    source_dataset: str = SOURCE_DATASET,
    target_dataset: str = TARGET_DATASET,
    exclusion_dataset: str = EXCLUSION_DATASET,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    near_overlap_threshold: float = 0.90,
) -> tuple[list[DatasetSample], dict[str, Any]]:
    """Build target rows and their deterministic manifest without writing."""

    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    if not 0.0 <= near_overlap_threshold <= 1.0:
        raise ValueError("near_overlap_threshold must be between 0 and 1")
    if not source_samples:
        raise ValueError(f"Source dataset {source_dataset!r} is empty")
    if not exclusion_samples:
        raise ValueError(
            f"Exclusion dataset {exclusion_dataset!r} is empty; refusing to build a training snapshot "
            "without checking evaluation leakage"
        )

    stable_source = _stable_records(source_samples)
    deduplicated: dict[str, DatasetSample] = {}
    for sample in stable_source:
        key = _question_sha256(sample, relaxed=True)
        if not normalize_math_question(sample.question):
            raise ValueError(f"Source record {sample.index!r} has an empty question")
        deduplicated.setdefault(key, sample)

    exclusion_exact: dict[str, DatasetSample] = {}
    exclusion_relaxed: dict[str, DatasetSample] = {}
    exclusion_shingles: list[tuple[DatasetSample, set[tuple[str, ...]]]] = []
    for sample in _stable_records(exclusion_samples):
        exclusion_exact.setdefault(_question_sha256(sample), sample)
        exclusion_relaxed.setdefault(_question_sha256(sample, relaxed=True), sample)
        exclusion_shingles.append((sample, _shingles(sample.question)))

    eligible: list[DatasetSample] = []
    excluded: list[dict[str, Any]] = []
    for sample in deduplicated.values():
        strict_hash = _question_sha256(sample)
        relaxed_hash = _question_sha256(sample, relaxed=True)
        match = exclusion_exact.get(strict_hash)
        reason = "canonical_exact"
        score = 1.0
        if match is None:
            match = exclusion_relaxed.get(relaxed_hash)
            reason = "presentation_normalized_exact"
        if match is None:
            source_shingles = _shingles(sample.question)
            best_match: DatasetSample | None = None
            best_score = 0.0
            for eval_sample, eval_shingles in exclusion_shingles:
                candidate_score = _jaccard(source_shingles, eval_shingles)
                if candidate_score > best_score:
                    best_match = eval_sample
                    best_score = candidate_score
            if best_match is not None and best_score >= near_overlap_threshold:
                match = best_match
                reason = "token_5gram_jaccard"
                score = best_score
        if match is None:
            eligible.append(sample)
            continue
        excluded.append(
            {
                "source_index": _source_index(sample),
                "source_record_sha256": _record_sha256(sample),
                "evaluation_index": match.index,
                "reason": reason,
                "similarity": round(score, 8),
            }
        )

    eligible = _stable_records(eligible)
    if len(eligible) < sample_size:
        raise ValueError(
            f"Only {len(eligible)} eligible unique records remain in {source_dataset!r} after excluding "
            f"{len(excluded)} overlaps with {exclusion_dataset!r}; {sample_size} are required"
        )

    sampled = random.Random(seed).sample(eligible, sample_size)
    target_samples: list[DatasetSample] = []
    selected_manifest: list[dict[str, Any]] = []
    for target_index, sample in enumerate(sampled):
        if not (sample.source or "").strip():
            raise ValueError(
                f"Source record {sample.index!r} has no processor routing key; "
                "refusing to create a snapshot that cannot be executed"
            )
        target_sample = DatasetSample(
            dataset=target_dataset,
            index=target_index,
            # ``source`` is the runtime processor-routing key, not the
            # provenance dataset name. Preserve it from the source record;
            # the actual source dataset remains fully recorded below.
            source=sample.source,
            source_index=_source_index(sample),
            question=sample.question,
            answer=sample.answer,
            topic=sample.topic,
            level=sample.level,
            file_name=sample.file_name,
            meta=_with_provenance(
                sample,
                source_dataset=source_dataset,
                target_dataset=target_dataset,
                target_index=target_index,
                seed=seed,
            ),
        )
        target_samples.append(target_sample)
        selected_manifest.append(
            {
                "target_index": target_index,
                "source_index": _source_index(sample),
                "source_record_sha256": _record_sha256(sample),
                "question_sha256": _question_sha256(sample),
                "relaxed_question_sha256": _question_sha256(sample, relaxed=True),
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "target_dataset": target_dataset,
        "target_dataset_sha256": _snapshot_hash(target_samples),
        "sample_size": sample_size,
        "sampling": {
            "algorithm": "stable_sha256_sort_then_python_random_sample",
            "seed": seed,
        },
        "normalization": {
            "version": NORMALIZER_VERSION,
            "near_overlap_method": "token_5gram_jaccard",
            "near_overlap_threshold": near_overlap_threshold,
        },
        "source": {
            "dataset": source_dataset,
            "record_count": len(source_samples),
            "unique_question_count": len(deduplicated),
            "duplicate_question_count": len(source_samples) - len(deduplicated),
            "snapshot_sha256": canonical_sha256([_record_sha256(sample) for sample in stable_source]),
        },
        "evaluation_exclusion": {
            "dataset": exclusion_dataset,
            "record_count": len(exclusion_samples),
            "snapshot_sha256": canonical_sha256(
                [_record_sha256(sample) for sample in _stable_records(exclusion_samples)]
            ),
            "excluded_count": len(excluded),
            "excluded_records": excluded,
        },
        "eligible_population": {
            "record_count": len(eligible),
            "snapshot_sha256": canonical_sha256([_record_sha256(sample) for sample in eligible]),
        },
        "selected_records": selected_manifest,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return target_samples, manifest


def _validate_signed_manifest(manifest: Mapping[str, Any], *, label: str) -> None:
    expected = manifest.get("manifest_sha256")
    if not isinstance(expected, str) or not expected:
        raise ValueError(f"{label} is missing manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if canonical_sha256(unsigned) != expected:
        raise ValueError(f"{label} manifest_sha256 mismatch")


def _upstream_evidence(value: Any) -> dict[str, Any] | None:
    """Return an isolated upstream-evidence object from a row or mapping."""

    if isinstance(value, DatasetSample):
        value = value.meta
        if not isinstance(value, Mapping) or UPSTREAM_METADATA_KEY not in value:
            return None
    if not isinstance(value, Mapping):
        return None
    nested = value.get(UPSTREAM_METADATA_KEY)
    if nested is not None:
        value = nested
    if not isinstance(value, Mapping):
        return None
    return copy.deepcopy(dict(value))


def _validate_math_upstream_evidence(value: Any, *, question_sha256: str) -> dict[str, Any]:
    evidence = _upstream_evidence(value)
    if evidence is None:
        raise ValueError(f"missing upstream evidence for question {question_sha256}")
    data_source = evidence.get("data_source")
    ability = evidence.get("ability")
    if not isinstance(data_source, str) or data_source.strip().casefold() != "math_dapo":
        raise ValueError(f"question {question_sha256} has invalid upstream data_source")
    if not isinstance(ability, str) or ability.strip().casefold() != "math":
        raise ValueError(
            f"question {question_sha256} cannot derive domain=mathematics without upstream ability=MATH"
        )
    if "extra_info" not in evidence or not isinstance(evidence["extra_info"], Mapping):
        raise ValueError(f"question {question_sha256} is missing upstream extra_info")
    evidence["data_source"] = data_source.strip()
    evidence["ability"] = ability.strip()
    evidence["extra_info"] = copy.deepcopy(dict(evidence["extra_info"]))
    return evidence


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _historical_dapo_problem(prompt: Any, *, parquet_row_index: int) -> str:
    """Reproduce the exact question transformation used by the DAPO importer."""

    if not isinstance(prompt, list) or not prompt or not isinstance(prompt[0], Mapping):
        raise ValueError(f"upstream parquet row {parquet_row_index} has invalid prompt structure")
    content = prompt[0].get("content")
    if not isinstance(content, str):
        raise ValueError(f"upstream parquet row {parquet_row_index} has invalid prompt content")
    return content.replace(_HISTORICAL_DAPO_PREFIX, "").replace(_HISTORICAL_DAPO_SUFFIX, "")


def _select_historical_parquet_evidence(
    records: Iterable[Mapping[str, Any]],
    required: set[str],
    frozen_records_by_question_sha256: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Replay exact-key, last-write-wins DAPO import semantics.

    A normalized hash is used only to identify rows worth auditing.  It is not
    sufficient to select evidence: selection requires the exact transformed
    question stored in the frozen snapshot, and the selected last row's answer
    must still agree with that snapshot.
    """

    if frozen_records_by_question_sha256 is None:
        raise ValueError(
            "parquet evidence requires frozen question text and answer bindings; "
            "normalized hashes alone are ambiguous"
        )
    bindings = dict(frozen_records_by_question_sha256)
    if set(bindings) != required:
        raise ValueError("parquet frozen-record bindings must cover exactly the required hashes")

    expected: dict[str, tuple[str, str | None]] = {}
    for question_sha256 in sorted(required):
        binding = bindings[question_sha256]
        if not isinstance(binding, Mapping):
            raise ValueError(f"invalid frozen-record binding for question {question_sha256}")
        question = binding.get("question")
        if not isinstance(question, str) or not question:
            raise ValueError(f"frozen question text is missing for question {question_sha256}")
        if "answer" not in binding:
            raise ValueError(f"frozen answer is missing for question {question_sha256}")
        bound_sha256 = hashlib.sha256(normalize_math_question(question).encode("utf-8")).hexdigest()
        if bound_sha256 != question_sha256:
            raise ValueError(f"frozen question text does not match hash {question_sha256}")
        answer = binding["answer"]
        if answer is not None and not isinstance(answer, str):
            raise ValueError(f"frozen answer must be a string or null for question {question_sha256}")
        expected[question_sha256] = (question, answer)

    working_audit: dict[str, dict[str, Any]] = {
        question_sha256: {
            "normalized_match_count": 0,
            "exact_problem_match_count": 0,
            "non_exact_normalized_match_count": 0,
            "raw_problem_sha256s": set(),
            "normalized_evidence_sha256s": set(),
            "normalized_answer_sha256s": set(),
            "evidence_sha256s": set(),
            "answer_sha256s": set(),
        }
        for question_sha256 in required
    }
    last_exact_match: dict[str, tuple[int, dict[str, Any], Any]] = {}
    rows_scanned = 0
    for parquet_row_index, record in enumerate(records):
        rows_scanned += 1
        if not isinstance(record, Mapping):
            raise ValueError(f"upstream parquet row {parquet_row_index} is not a mapping")
        problem = _historical_dapo_problem(record.get("prompt"), parquet_row_index=parquet_row_index)
        question_sha256 = hashlib.sha256(
            normalize_math_question(problem).encode("utf-8")
        ).hexdigest()
        if question_sha256 not in required:
            continue
        question_audit = working_audit[question_sha256]
        question_audit["normalized_match_count"] += 1
        question_audit["raw_problem_sha256s"].add(
            hashlib.sha256(problem.encode("utf-8")).hexdigest()
        )
        reward_model = record.get("reward_model")
        if not isinstance(reward_model, Mapping) or "ground_truth" not in reward_model:
            raise ValueError(
                f"normalized upstream parquet match at row {parquet_row_index} is missing ground_truth"
            )
        raw_evidence = {
            "data_source": record.get("data_source"),
            "ability": record.get("ability"),
            "extra_info": record.get("extra_info"),
        }
        ground_truth = reward_model["ground_truth"]
        question_audit["normalized_evidence_sha256s"].add(canonical_sha256(raw_evidence))
        question_audit["normalized_answer_sha256s"].add(canonical_sha256(ground_truth))
        expected_question, _ = expected[question_sha256]
        if problem != expected_question:
            question_audit["non_exact_normalized_match_count"] += 1
            continue

        question_audit["exact_problem_match_count"] += 1
        question_audit["evidence_sha256s"].add(canonical_sha256(raw_evidence))
        question_audit["answer_sha256s"].add(canonical_sha256(ground_truth))
        # This assignment deliberately implements the importer's dict-based
        # last-write-wins behavior.  The full parquet must therefore be scanned.
        last_exact_match[question_sha256] = (
            parquet_row_index,
            raw_evidence,
            ground_truth,
        )

    result: dict[str, dict[str, Any]] = {}
    public_audit: dict[str, dict[str, Any]] = {}
    for question_sha256 in sorted(required):
        question_audit = working_audit[question_sha256]
        exact_count = question_audit["exact_problem_match_count"]
        normalized_count = question_audit["normalized_match_count"]
        if exact_count == 0:
            raise ValueError(
                f"no exact historical-importer match for question {question_sha256}; "
                f"found {normalized_count} normalized-hash match(es)"
            )
        selected_row_index, raw_evidence, ground_truth = last_exact_match[question_sha256]
        _, frozen_answer = expected[question_sha256]
        if ground_truth != frozen_answer:
            raise ValueError(
                f"last-write-wins answer mismatch for question {question_sha256} "
                f"at parquet row {selected_row_index}"
            )
        result[question_sha256] = _validate_math_upstream_evidence(
            raw_evidence,
            question_sha256=question_sha256,
        )
        public_audit[question_sha256] = {
            "normalized_match_count": normalized_count,
            "exact_problem_match_count": exact_count,
            "non_exact_normalized_match_count": question_audit[
                "non_exact_normalized_match_count"
            ],
            "raw_problem_variant_count": len(question_audit["raw_problem_sha256s"]),
            "normalized_evidence_variant_count": len(
                question_audit["normalized_evidence_sha256s"]
            ),
            "normalized_answer_variant_count": len(
                question_audit["normalized_answer_sha256s"]
            ),
            "evidence_variant_count": len(question_audit["evidence_sha256s"]),
            "answer_variant_count": len(question_audit["answer_sha256s"]),
            "selected_parquet_row_index": selected_row_index,
            "selected_evidence_sha256": canonical_sha256(result[question_sha256]),
        }

    audits = list(public_audit.values())
    return result, {
        "selection_policy": "historical_exact_problem_last_write_wins",
        "parquet_rows_scanned": rows_scanned,
        "required_question_count": len(required),
        "normalized_match_row_count": sum(item["normalized_match_count"] for item in audits),
        "exact_problem_match_row_count": sum(
            item["exact_problem_match_count"] for item in audits
        ),
        "duplicate_normalized_question_count": sum(
            item["normalized_match_count"] > 1 for item in audits
        ),
        "duplicate_exact_question_count": sum(
            item["exact_problem_match_count"] > 1 for item in audits
        ),
        "conflicting_evidence_question_count": sum(
            item["normalized_evidence_variant_count"] > 1 for item in audits
        ),
        "conflicting_exact_evidence_question_count": sum(
            item["evidence_variant_count"] > 1 for item in audits
        ),
        "conflicting_answer_question_count": sum(
            item["normalized_answer_variant_count"] > 1 for item in audits
        ),
        "conflicting_exact_answer_question_count": sum(
            item["answer_variant_count"] > 1 for item in audits
        ),
        "normalized_collision_question_count": sum(
            item["non_exact_normalized_match_count"] > 0 for item in audits
        ),
        "max_normalized_matches_per_question": max(
            item["normalized_match_count"] for item in audits
        ),
        "max_exact_matches_per_question": max(
            item["exact_problem_match_count"] for item in audits
        ),
        "questions": public_audit,
    }


def load_upstream_evidence(
    path: str | Path,
    required_question_sha256s: Iterable[str],
    *,
    frozen_records_by_question_sha256: Mapping[str, Mapping[str, Any]] | None = None,
    _parquet_records: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load explicit local DAPO evidence; this function never downloads data.

    JSON/JSONL records must contain ``question_sha256`` plus either a nested
    ``_tf_llm_upstream`` mapping or direct ``data_source``, ``ability`` and
    ``extra_info`` fields.  That format is a caller-asserted utility input and
    is deliberately *not* accepted by :func:`create_enriched_dapo_subset` for
    a formal dataset build.  A native DAPO parquet is fully scanned in source
    order so exact-question last-write-wins behavior matches the historical
    importer. ``_parquet_records`` is an offline-only deterministic test seam.
    """

    evidence_path = Path(path)
    if not evidence_path.is_file():
        raise FileNotFoundError(f"local upstream evidence file not found: {evidence_path}")
    required = {str(value) for value in required_question_sha256s}
    if not required or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in required):
        raise ValueError("required question hashes must be non-empty lowercase SHA-256 values")

    suffix = evidence_path.suffix.casefold()
    result: dict[str, dict[str, Any]] = {}
    if suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            raw_records: Any = [
                json.loads(line)
                for line in evidence_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            raw_records = payload.get("records") if isinstance(payload, Mapping) else payload
        if not isinstance(raw_records, list):
            raise ValueError("upstream JSON evidence must contain a records list")
        seen: set[str] = set()
        for record in raw_records:
            if not isinstance(record, Mapping):
                raise ValueError("upstream JSON evidence record must be a mapping")
            question_sha256 = record.get("question_sha256")
            if not isinstance(question_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", question_sha256
            ):
                raise ValueError("upstream JSON evidence has an invalid question_sha256")
            if question_sha256 in seen:
                raise ValueError(f"duplicate upstream evidence for question {question_sha256}")
            seen.add(question_sha256)
            if question_sha256 not in required:
                continue
            raw_evidence = record.get(UPSTREAM_METADATA_KEY, record)
            result[question_sha256] = _validate_math_upstream_evidence(
                raw_evidence,
                question_sha256=question_sha256,
            )
        evidence_format = suffix.removeprefix(".")
    elif suffix == ".parquet":
        if _parquet_records is None:
            try:
                import pyarrow.parquet as parquet
            except ImportError as error:  # pragma: no cover - optional dependency branch
                raise RuntimeError(
                    "Reading DAPO parquet evidence requires local pyarrow; no download was attempted"
                ) from error
            parquet_file = parquet.ParquetFile(evidence_path)
            required_columns = {
                "data_source",
                "prompt",
                "ability",
                "extra_info",
                "reward_model",
            }
            available_columns = set(parquet_file.schema_arrow.names)
            missing_columns = sorted(required_columns - available_columns)
            if missing_columns:
                raise ValueError(
                    f"upstream parquet is missing columns: {', '.join(missing_columns)}"
                )

            def parquet_records() -> Iterable[Mapping[str, Any]]:
                for batch in parquet_file.iter_batches(
                    batch_size=4096,
                    columns=sorted(required_columns),
                ):
                    yield from batch.to_pylist()

            records = parquet_records()
        else:
            records = _parquet_records
        result, parquet_audit = _select_historical_parquet_evidence(
            records,
            required,
            frozen_records_by_question_sha256,
        )
        evidence_format = "parquet"
    else:
        raise ValueError("upstream evidence path must end in .json, .jsonl, or .parquet")

    missing = sorted(required - result.keys())
    if missing:
        preview = ", ".join(missing[:5])
        raise ValueError(f"upstream evidence is missing {len(missing)} required question(s): {preview}")
    source = {
        "format": evidence_format,
        "file_name": evidence_path.name,
        "file_sha256": _file_sha256(evidence_path),
        "matched_question_count": len(result),
    }
    if suffix == ".parquet":
        source["source_audit"] = parquet_audit
    else:
        source["source_audit"] = {
            "selection_policy": "explicit_unique_question_sha256",
            "required_question_count": len(required),
            "duplicate_policy": "reject",
        }
    return result, source


def build_annotation_template(
    frozen_samples: Sequence[DatasetSample],
    frozen_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a reviewer-facing, hash-bound template from a frozen snapshot."""

    _validate_signed_manifest(frozen_manifest, label="frozen DAPO")
    parent_dataset = frozen_manifest.get("target_dataset")
    parent_snapshot_sha256 = frozen_manifest.get("target_dataset_sha256")
    if not isinstance(parent_dataset, str) or not parent_dataset:
        raise ValueError("frozen DAPO manifest is missing target_dataset")
    if _snapshot_hash(frozen_samples) != parent_snapshot_sha256:
        raise ValueError("frozen DAPO rows do not match target_dataset_sha256")
    samples_by_index = {sample.index: sample for sample in frozen_samples}
    if len(samples_by_index) != len(frozen_samples) or sorted(samples_by_index) != list(
        range(len(frozen_samples))
    ):
        raise ValueError("frozen DAPO target indices must be unique and contiguous from zero")
    selected_records = frozen_manifest.get("selected_records")
    if not isinstance(selected_records, list) or len(selected_records) != len(frozen_samples):
        raise ValueError("frozen DAPO selected_records do not cover the snapshot")
    selected_by_index = {
        selected.get("target_index"): selected
        for selected in selected_records
        if isinstance(selected, Mapping)
    }
    if len(selected_by_index) != len(selected_records) or sorted(selected_by_index) != list(
        range(len(frozen_samples))
    ):
        raise ValueError("frozen DAPO selected_records contain missing or duplicate target indices")

    records = []
    for target_index in range(len(frozen_samples)):
        sample = samples_by_index[target_index]
        selected = selected_by_index[target_index]
        question_sha256 = _question_sha256(sample)
        if selected.get("question_sha256") != question_sha256:
            raise ValueError(f"frozen question hash mismatch at target index {target_index}")
        if selected.get("source_index") != sample.source_index:
            raise ValueError(f"frozen source index mismatch at target index {target_index}")
        records.append(
            {
                "target_index": target_index,
                "source_index": sample.source_index,
                "question": sample.question,
                "question_sha256": question_sha256,
                "source_record_sha256": selected.get("source_record_sha256"),
                "task_family": None,
                "notes": None,
            }
        )
    return {
        "template": True,
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "annotation_method": "human_review",
        "primary_reviewer": None,
        "secondary_reviewer": None,
        "reviewed_at": None,
        "source_dataset": parent_dataset,
        "source_dataset_sha256": parent_snapshot_sha256,
        "source_manifest_sha256": frozen_manifest["manifest_sha256"],
        "expected_record_count": len(records),
        "task_family_enum": list(MATH_TASK_FAMILIES),
        "instructions": [
            "Copy this TEMPLATE to a separate versioned annotation file before editing it.",
            "Review every frozen problem manually; do not use an LLM or keyword-only classifier.",
            "Set task_family to exactly one task_family_enum value; use mixed only "
            "when no primary family is defensible.",
            "Do not edit target_index, source_index, question, question_sha256, or source_record_sha256.",
            "After two distinct reviewers finish, set template=false, fill both reviewer "
            "fields and reviewed_at with a timezone.",
            "The enrichment builder rejects incomplete coverage, null/unknown labels, "
            "duplicate indices, or hash mismatches.",
        ],
        "records": records,
    }


def build_enriched_subset_plan(
    frozen_samples: Sequence[DatasetSample],
    frozen_manifest: Mapping[str, Any],
    annotation_manifest: Mapping[str, Any],
    *,
    target_dataset: str = ENRICHED_TARGET_DATASET,
    dataset_version: str = ENRICHED_DATASET_VERSION,
    upstream_metadata_by_question_sha256: Mapping[str, Any] | None = None,
    upstream_evidence_source: Mapping[str, Any] | None = None,
) -> tuple[list[DatasetSample], dict[str, Any]]:
    """Enrich a frozen DAPO snapshot without resampling or writing it.

    The function is deliberately fail-closed.  ``domain`` is derived only from
    native DAPO ``ability=MATH`` evidence, while ``task_family`` is accepted
    only from a complete hash-bound human review manifest.  The existing
    snapshot and its provenance remain unchanged; callers may later persist the
    returned rows under a *new* dataset name using their normal transaction.
    """

    if not frozen_samples:
        raise ValueError("frozen DAPO snapshot is empty")
    if not isinstance(frozen_manifest, Mapping):
        raise ValueError("frozen DAPO manifest must be a mapping")
    if not isinstance(annotation_manifest, Mapping):
        raise ValueError("annotation manifest must be a mapping")
    _validate_signed_manifest(frozen_manifest, label="frozen DAPO")

    parent_dataset = frozen_manifest.get("target_dataset")
    parent_snapshot_sha256 = frozen_manifest.get("target_dataset_sha256")
    if not isinstance(parent_dataset, str) or not parent_dataset:
        raise ValueError("frozen DAPO manifest is missing target_dataset")
    if target_dataset == parent_dataset:
        raise ValueError("enriched target_dataset must differ from the frozen dataset")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("dataset_version must be non-empty")
    if not isinstance(parent_snapshot_sha256, str) or not parent_snapshot_sha256:
        raise ValueError("frozen DAPO manifest is missing target_dataset_sha256")
    if _snapshot_hash(frozen_samples) != parent_snapshot_sha256:
        raise ValueError("frozen DAPO rows do not match target_dataset_sha256")

    expected_indices = list(range(len(frozen_samples)))
    frozen_by_index: dict[int, DatasetSample] = {}
    for sample in frozen_samples:
        if sample.dataset != parent_dataset:
            raise ValueError("frozen DAPO row uses a different dataset namespace")
        if sample.index is None or sample.index in frozen_by_index:
            raise ValueError("frozen DAPO rows contain missing or duplicate target indices")
        frozen_by_index[sample.index] = sample
    if sorted(frozen_by_index) != expected_indices:
        raise ValueError("frozen DAPO target indices must be contiguous from zero")

    selected_records = frozen_manifest.get("selected_records")
    if not isinstance(selected_records, list) or len(selected_records) != len(frozen_samples):
        raise ValueError("frozen DAPO selected_records do not cover the snapshot")
    selected_by_index: dict[int, Mapping[str, Any]] = {}
    for selected in selected_records:
        if not isinstance(selected, Mapping):
            raise ValueError("frozen DAPO selected record must be a mapping")
        target_index = selected.get("target_index")
        if not isinstance(target_index, int) or target_index in selected_by_index:
            raise ValueError("frozen DAPO selected_records contain duplicate target indices")
        selected_by_index[target_index] = selected
    if sorted(selected_by_index) != expected_indices:
        raise ValueError("frozen DAPO selected_records contain missing target indices")

    if annotation_manifest.get("schema_version") != ANNOTATION_SCHEMA_VERSION:
        raise ValueError("unsupported annotation schema_version")
    if annotation_manifest.get("template") is not False:
        raise ValueError("annotation manifest must set template=false after review")
    if annotation_manifest.get("annotation_method") != "human_review":
        raise ValueError("task_family annotations must use annotation_method=human_review")
    primary_reviewer = annotation_manifest.get("primary_reviewer")
    secondary_reviewer = annotation_manifest.get("secondary_reviewer")
    if not isinstance(primary_reviewer, str) or not primary_reviewer.strip():
        raise ValueError("annotation primary_reviewer must be non-empty")
    if not isinstance(secondary_reviewer, str) or not secondary_reviewer.strip():
        raise ValueError("annotation secondary_reviewer must be non-empty")
    if primary_reviewer.strip() == secondary_reviewer.strip():
        raise ValueError("annotation primary_reviewer and secondary_reviewer must be distinct")
    reviewed_at = annotation_manifest.get("reviewed_at")
    if not isinstance(reviewed_at, str) or not reviewed_at.strip():
        raise ValueError("annotation reviewed_at must be a non-empty ISO-8601 timestamp")
    try:
        parsed_reviewed_at = datetime.datetime.fromisoformat(reviewed_at.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("annotation reviewed_at must be a valid ISO-8601 timestamp") from error
    if parsed_reviewed_at.tzinfo is None:
        raise ValueError("annotation reviewed_at must include a timezone")
    if annotation_manifest.get("source_dataset") != parent_dataset:
        raise ValueError("annotation source_dataset does not match the frozen snapshot")
    if annotation_manifest.get("source_dataset_sha256") != parent_snapshot_sha256:
        raise ValueError("annotation source_dataset_sha256 does not match the frozen snapshot")
    if annotation_manifest.get("source_manifest_sha256") != frozen_manifest["manifest_sha256"]:
        raise ValueError("annotation source_manifest_sha256 does not match the frozen manifest")
    if annotation_manifest.get("expected_record_count") != len(frozen_samples):
        raise ValueError("annotation expected_record_count does not match the frozen snapshot")
    if annotation_manifest.get("task_family_enum") != list(MATH_TASK_FAMILIES):
        raise ValueError("annotation task_family_enum does not match the supported taxonomy")

    annotation_records = annotation_manifest.get("records")
    if not isinstance(annotation_records, list):
        raise ValueError("annotation records must be a list")
    annotations_by_index: dict[int, Mapping[str, Any]] = {}
    for annotation in annotation_records:
        if not isinstance(annotation, Mapping):
            raise ValueError("annotation record must be a mapping")
        target_index = annotation.get("target_index")
        if not isinstance(target_index, int) or target_index in annotations_by_index:
            raise ValueError("annotation records contain a missing or duplicate target index")
        annotations_by_index[target_index] = annotation
    if sorted(annotations_by_index) != expected_indices:
        raise ValueError("annotation records must cover every frozen target index exactly once")

    evaluation_exclusion = frozen_manifest.get("evaluation_exclusion")
    if not isinstance(evaluation_exclusion, Mapping):
        raise ValueError("frozen DAPO manifest is missing evaluation_exclusion")
    for required in ("dataset", "record_count", "snapshot_sha256"):
        if evaluation_exclusion.get(required) in (None, ""):
            raise ValueError(f"frozen evaluation_exclusion is missing {required}")

    external_upstream = upstream_metadata_by_question_sha256 or {}
    annotation_sha256 = canonical_sha256(annotation_manifest)
    enriched_samples: list[DatasetSample] = []
    tasks: list[dict[str, Any]] = []
    for target_index in expected_indices:
        sample = frozen_by_index[target_index]
        selected = selected_by_index[target_index]
        annotation = annotations_by_index[target_index]
        question_sha256 = _question_sha256(sample)
        source_record_sha256 = selected.get("source_record_sha256")
        if selected.get("question_sha256") != question_sha256:
            raise ValueError(f"frozen question hash mismatch at target index {target_index}")
        if selected.get("source_index") != sample.source_index:
            raise ValueError(f"frozen source index mismatch at target index {target_index}")
        provenance = sample.meta.get(PROVENANCE_KEY) if isinstance(sample.meta, Mapping) else None
        if not isinstance(provenance, Mapping) or provenance.get("source_record_sha256") != source_record_sha256:
            raise ValueError(f"frozen source record hash mismatch at target index {target_index}")
        if annotation.get("question_sha256") != question_sha256:
            raise ValueError(f"annotation question hash mismatch at target index {target_index}")
        if annotation.get("source_record_sha256") != source_record_sha256:
            raise ValueError(f"annotation source record hash mismatch at target index {target_index}")
        if annotation.get("source_index") != sample.source_index:
            raise ValueError(f"annotation source index mismatch at target index {target_index}")
        if annotation.get("question") != sample.question:
            raise ValueError(f"annotation question text mismatch at target index {target_index}")
        task_family = annotation.get("task_family")
        if task_family is None or task_family == "":
            raise ValueError(f"annotation task_family is missing at target index {target_index}")
        if task_family not in MATH_TASK_FAMILIES:
            raise ValueError(f"unknown task_family {task_family!r} at target index {target_index}")

        row_upstream = _upstream_evidence(sample)
        external_evidence = external_upstream.get(question_sha256)
        if row_upstream is not None and external_evidence is not None:
            validated_row_upstream = _validate_math_upstream_evidence(
                row_upstream,
                question_sha256=question_sha256,
            )
            validated_external = _validate_math_upstream_evidence(
                external_evidence,
                question_sha256=question_sha256,
            )
            if canonical_sha256(validated_row_upstream) != canonical_sha256(validated_external):
                raise ValueError(
                    f"frozen row upstream evidence conflicts with the supplied source for "
                    f"question {question_sha256}"
                )
            row_upstream = validated_row_upstream
        elif row_upstream is None:
            row_upstream = external_evidence
        upstream = _validate_math_upstream_evidence(
            row_upstream,
            question_sha256=question_sha256,
        )
        metadata = copy.deepcopy(dict(sample.meta)) if isinstance(sample.meta, Mapping) else {}
        metadata[UPSTREAM_METADATA_KEY] = upstream
        metadata["domain"] = "mathematics"
        metadata["task_family"] = task_family
        metadata[ENRICHMENT_METADATA_KEY] = {
            "schema_version": ENRICHED_MANIFEST_SCHEMA_VERSION,
            "annotation_method": "human_review",
            "annotation_manifest_sha256": annotation_sha256,
            "primary_reviewer": primary_reviewer.strip(),
            "secondary_reviewer": secondary_reviewer.strip(),
            "reviewed_at": reviewed_at.strip(),
            "domain_source": f"{UPSTREAM_METADATA_KEY}.ability=MATH",
            "parent_dataset": parent_dataset,
            "parent_dataset_sha256": parent_snapshot_sha256,
            "target_dataset": target_dataset,
            "target_index": target_index,
            "question_sha256": question_sha256,
            "source_record_sha256": source_record_sha256,
            "upstream_evidence_sha256": canonical_sha256(upstream),
        }
        enriched = DatasetSample(
            dataset=target_dataset,
            index=sample.index,
            source=sample.source,
            source_index=sample.source_index,
            question=sample.question,
            answer=sample.answer,
            topic=sample.topic,
            level=sample.level,
            file_name=sample.file_name,
            meta=metadata,
        )
        enriched_samples.append(enriched)
        tasks.append(
            {
                "task_id": str(target_index),
                "namespaced_task_id": f"{target_dataset}:{target_index}",
                "target_index": target_index,
                "source_index": sample.source_index,
                "question_sha256": question_sha256,
                "source_record_sha256": source_record_sha256,
                "domain": "mathematics",
                "task_family": task_family,
            }
        )

    train_task_ids = [task["task_id"] for task in tasks]
    task_lists = {
        "train_task_ids": train_task_ids,
        # AIME is represented by its immutable exclusion snapshot below.  Its
        # task IDs are not present in the frozen v2 manifest and are not guessed.
        "eval_task_ids": [],
        "excluded_task_ids": [],
    }
    split = {
        **task_lists,
        "train_task_ids_sha256": canonical_sha256(train_task_ids),
        "eval_task_ids_sha256": canonical_sha256([]),
        "split_sha256": canonical_sha256(task_lists),
    }
    output: dict[str, Any] = {
        "schema_version": ENRICHED_MANIFEST_SCHEMA_VERSION,
        "target_dataset": target_dataset,
        "target_dataset_sha256": _snapshot_hash(enriched_samples),
        "dataset": {
            "name": target_dataset,
            "namespace": target_dataset,
            "version": dataset_version,
            "task_id_format": "zero-based target index; L0 evidence is namespaced as <dataset>:<index>",
            "inventory_task_count": len(tasks),
            "inventory_sha256": canonical_sha256(tasks),
            "parent_dataset": parent_dataset,
            "parent_dataset_sha256": parent_snapshot_sha256,
            "parent_manifest_sha256": frozen_manifest["manifest_sha256"],
            "annotation_manifest_sha256": annotation_sha256,
        },
        "tasks": tasks,
        "splits": {CALIBRATION_SPLIT_NAME: split},
        "evaluation_exclusion": copy.deepcopy(dict(evaluation_exclusion)),
        "enrichment": {
            "annotation_method": "human_review",
            "primary_reviewer": primary_reviewer.strip(),
            "secondary_reviewer": secondary_reviewer.strip(),
            "reviewed_at": reviewed_at.strip(),
            "task_family_enum": list(MATH_TASK_FAMILIES),
            "domain": "mathematics",
            "domain_source": f"{UPSTREAM_METADATA_KEY}.ability=MATH",
            "upstream_evidence_source": copy.deepcopy(
                dict(upstream_evidence_source)
                if upstream_evidence_source is not None
                else {
                    "format": "injected_mapping",
                    "mapping_sha256": canonical_sha256(external_upstream),
                }
            ),
        },
    }
    output["manifest_sha256"] = canonical_sha256(output)
    return enriched_samples, output


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_json_mapping(path: str | Path, *, label: str) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.is_file():
        raise FileNotFoundError(f"{label} file not found: {input_path}")
    value = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def export_annotation_template(
    *,
    frozen_dataset: str = TARGET_DATASET,
    frozen_manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    output_path: str | Path,
    session: Session | None = None,
) -> dict[str, Any]:
    """Export reviewable questions without altering the database."""

    frozen_manifest = _load_json_mapping(frozen_manifest_path, label="frozen DAPO manifest")
    if frozen_manifest.get("target_dataset") != frozen_dataset:
        raise ValueError("frozen dataset does not match frozen manifest")
    owns_session = session is None
    active_session = session or SQLModelUtils.create_session()
    try:
        frozen_samples = list(
            active_session.exec(
                select(DatasetSample)
                .where(DatasetSample.dataset == frozen_dataset)
                .order_by(DatasetSample.index)
            ).all()
        )
        template = build_annotation_template(frozen_samples, frozen_manifest)
        destination = Path(output_path)
        if destination.exists():
            existing = _load_json_mapping(destination, label="annotation template")
            if existing != template:
                raise FileExistsError(f"refusing to overwrite different annotation template: {destination}")
            return template
        _write_manifest(destination, template)
        return template
    finally:
        if owns_session:
            active_session.close()


def create_enriched_dapo_subset(
    *,
    frozen_dataset: str = TARGET_DATASET,
    target_dataset: str = ENRICHED_TARGET_DATASET,
    dataset_version: str = ENRICHED_DATASET_VERSION,
    frozen_manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    annotation_path: str | Path,
    upstream_evidence_path: str | Path,
    expected_upstream_evidence_sha256: str,
    manifest_path: str | Path = DEFAULT_ENRICHED_MANIFEST_PATH,
    session: Session | None = None,
) -> dict[str, Any]:
    """Create or verify a reviewed v3 snapshot from a hash-pinned native parquet.

    Database rows are inserted in one transaction and the manifest is written
    with an atomic file replacement.  A crash between those resources is safe
    to retry: exact existing rows are verified and the absent manifest is then
    repaired.  Existing partial or different rows/manifests are never replaced.
    """

    if target_dataset == frozen_dataset:
        raise ValueError("enriched target dataset must differ from frozen dataset")
    evidence_path = Path(upstream_evidence_path)
    if evidence_path.suffix.casefold() != ".parquet":
        raise ValueError(
            "formal DAPO enrichment requires the native local .parquet evidence file; "
            "JSON/JSONL evidence is not accepted"
        )
    if not isinstance(expected_upstream_evidence_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_upstream_evidence_sha256
    ):
        raise ValueError("expected_upstream_evidence_sha256 must be a lowercase SHA-256")
    actual_upstream_evidence_sha256 = _file_sha256(evidence_path)
    if actual_upstream_evidence_sha256 != expected_upstream_evidence_sha256:
        raise ValueError(
            "upstream evidence SHA-256 mismatch: the local parquet is not the expected snapshot"
        )
    frozen_manifest = _load_json_mapping(frozen_manifest_path, label="frozen DAPO manifest")
    annotation_manifest = _load_json_mapping(annotation_path, label="annotation manifest")
    if frozen_manifest.get("target_dataset") != frozen_dataset:
        raise ValueError("frozen dataset does not match frozen manifest")

    owns_session = session is None
    active_session = session or SQLModelUtils.create_session()
    try:
        frozen_samples = list(
            active_session.exec(
                select(DatasetSample)
                .where(DatasetSample.dataset == frozen_dataset)
                .order_by(DatasetSample.index)
            ).all()
        )
        selected_records = frozen_manifest.get("selected_records")
        if not isinstance(selected_records, list):
            raise ValueError("frozen DAPO manifest is missing selected_records")
        required_question_hashes = [
            record.get("question_sha256")
            for record in selected_records
            if isinstance(record, Mapping)
        ]
        frozen_bindings: dict[str, dict[str, Any]] = {}
        for sample in frozen_samples:
            question_sha256 = _question_sha256(sample)
            if question_sha256 in frozen_bindings:
                raise ValueError(
                    f"frozen DAPO rows contain duplicate normalized question hash {question_sha256}"
                )
            frozen_bindings[question_sha256] = {
                "question": sample.question,
                "answer": sample.answer,
            }
        upstream_mapping, upstream_source = load_upstream_evidence(
            evidence_path,
            required_question_hashes,
            frozen_records_by_question_sha256=frozen_bindings,
        )
        if (
            upstream_source.get("format") != "parquet"
            or upstream_source.get("file_sha256") != expected_upstream_evidence_sha256
        ):
            raise ValueError(
                "loaded upstream evidence does not match the verified native parquet snapshot"
            )
        planned, manifest = build_enriched_subset_plan(
            frozen_samples,
            frozen_manifest,
            annotation_manifest,
            target_dataset=target_dataset,
            dataset_version=dataset_version,
            upstream_metadata_by_question_sha256=upstream_mapping,
            upstream_evidence_source=upstream_source,
        )

        destination = Path(manifest_path)
        if destination.exists():
            existing_manifest = _load_json_mapping(destination, label="enriched DAPO manifest")
            if existing_manifest != manifest:
                raise FileExistsError(f"refusing to overwrite different enriched manifest: {destination}")

        existing_rows = list(
            active_session.exec(
                select(DatasetSample)
                .where(DatasetSample.dataset == target_dataset)
                .order_by(DatasetSample.index)
            ).all()
        )
        if existing_rows:
            expected_indices = list(range(len(planned)))
            actual_indices = [sample.index for sample in existing_rows]
            if actual_indices != expected_indices or _snapshot_hash(existing_rows) != manifest[
                "target_dataset_sha256"
            ]:
                raise ValueError(
                    f"existing enriched dataset {target_dataset!r} is partial or different; refusing to overwrite"
                )
            status = "verified_existing"
        else:
            active_session.add_all(planned)
            active_session.commit()
            status = "created"

        if not destination.exists():
            _write_manifest(destination, manifest)
        print(
            f"{status}: {target_dataset} ({len(planned)} rows, "
            f"sha256={manifest['target_dataset_sha256']})"
        )
        return manifest
    except Exception:
        active_session.rollback()
        raise
    finally:
        if owns_session:
            active_session.close()


def create_dapo_subset(
    *,
    source_dataset: str = SOURCE_DATASET,
    target_dataset: str = TARGET_DATASET,
    exclusion_dataset: str = EXCLUSION_DATASET,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    near_overlap_threshold: float = 0.90,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    session: Session | None = None,
) -> dict[str, Any]:
    """Create or verify the target dataset and write its manifest.

    Existing target rows are never overwritten. An exact target is treated as
    an idempotent retry; a partial or different target fails closed.
    """

    if len({source_dataset, target_dataset, exclusion_dataset}) != 3:
        raise ValueError("source, target, and exclusion dataset names must be distinct")

    owns_session = session is None
    active_session = session or SQLModelUtils.create_session()
    try:
        source_samples = list(
            active_session.exec(select(DatasetSample).where(DatasetSample.dataset == source_dataset)).all()
        )
        exclusion_samples = list(
            active_session.exec(select(DatasetSample).where(DatasetSample.dataset == exclusion_dataset)).all()
        )
        planned, manifest = build_subset_plan(
            source_samples,
            exclusion_samples,
            source_dataset=source_dataset,
            target_dataset=target_dataset,
            exclusion_dataset=exclusion_dataset,
            sample_size=sample_size,
            seed=seed,
            near_overlap_threshold=near_overlap_threshold,
        )
        existing = list(
            active_session.exec(select(DatasetSample).where(DatasetSample.dataset == target_dataset)).all()
        )
        if existing:
            expected_indices = list(range(sample_size))
            actual_indices = sorted(sample.index for sample in existing)
            if actual_indices != expected_indices or _snapshot_hash(existing) != manifest["target_dataset_sha256"]:
                raise ValueError(
                    f"Existing target dataset {target_dataset!r} is partial or differs from the requested snapshot; "
                    "refusing to overwrite it"
                )
            status = "verified_existing"
        else:
            active_session.add_all(planned)
            active_session.commit()
            status = "created"

        # The manifest is written after the DB commit. If this write fails, a
        # retry verifies the already-committed rows and repairs the manifest
        # without duplicating data.
        _write_manifest(Path(manifest_path), manifest)
        print(
            f"{status}: {target_dataset} ({sample_size} rows, seed={seed}, "
            f"sha256={manifest['target_dataset_sha256']})"
        )
        return manifest
    except Exception:
        active_session.rollback()
        raise
    finally:
        if owns_session:
            active_session.close()


def create_dapo_100(seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Backward-compatible callable using the audited snapshot defaults."""

    return create_dapo_subset(seed=seed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--enrich",
        action="store_true",
        help="Create a reviewed v3 snapshot from the frozen v2 rows and explicit local evidence.",
    )
    mode.add_argument(
        "--export-annotation-template",
        type=Path,
        metavar="PATH",
        help="Export target_index, source_index and question text for manual review; does not write the DB.",
    )
    parser.add_argument("--source-dataset", default=SOURCE_DATASET)
    parser.add_argument("--target-dataset", default=TARGET_DATASET)
    parser.add_argument("--exclude-dataset", default=EXCLUSION_DATASET)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--near-overlap-threshold", type=float, default=0.90)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--frozen-dataset", default=TARGET_DATASET)
    parser.add_argument("--frozen-manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--annotation-path", type=Path)
    parser.add_argument("--upstream-evidence-path", type=Path)
    parser.add_argument(
        "--upstream-evidence-sha256",
        help="Expected lowercase SHA-256 of the native local DAPO parquet (required with --enrich).",
    )
    parser.add_argument("--enriched-target-dataset", default=ENRICHED_TARGET_DATASET)
    parser.add_argument("--enriched-dataset-version", default=ENRICHED_DATASET_VERSION)
    parser.add_argument(
        "--enriched-manifest-path",
        type=Path,
        default=DEFAULT_ENRICHED_MANIFEST_PATH,
    )
    args = parser.parse_args()
    if args.export_annotation_template is not None:
        export_annotation_template(
            frozen_dataset=args.frozen_dataset,
            frozen_manifest_path=args.frozen_manifest_path,
            output_path=args.export_annotation_template,
        )
        return
    if args.enrich:
        if (
            args.annotation_path is None
            or args.upstream_evidence_path is None
            or args.upstream_evidence_sha256 is None
        ):
            parser.error(
                "--enrich requires --annotation-path, --upstream-evidence-path, "
                "and --upstream-evidence-sha256"
            )
        create_enriched_dapo_subset(
            frozen_dataset=args.frozen_dataset,
            target_dataset=args.enriched_target_dataset,
            dataset_version=args.enriched_dataset_version,
            frozen_manifest_path=args.frozen_manifest_path,
            annotation_path=args.annotation_path,
            upstream_evidence_path=args.upstream_evidence_path,
            expected_upstream_evidence_sha256=args.upstream_evidence_sha256,
            manifest_path=args.enriched_manifest_path,
        )
        return
    create_dapo_subset(
        source_dataset=args.source_dataset,
        target_dataset=args.target_dataset,
        exclusion_dataset=args.exclude_dataset,
        sample_size=args.sample_size,
        seed=args.seed,
        near_overlap_threshold=args.near_overlap_threshold,
        manifest_path=args.manifest_path,
    )


if __name__ == "__main__":
    main()
