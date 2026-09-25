#!/usr/bin/env python3
"""Paired held-out validation for one provisional L1 experience.

This command deliberately evaluates an explicitly named L1 instead of running a
retriever.  It therefore separates the quality of an aggregated lesson from the
quality of retrieval.  The selected evaluation questions are checked against the
complete source dataset for exact duplicates before any API call is made.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import os
import random
import re
import sqlite3
import statistics
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(raise_error_if_not_found=False), override=True)
os.environ.setdefault("UTU_SKIP_AUTO_SETUP", "1")

from openai import AsyncOpenAI  # noqa: E402

from scripts.experiments.run_retrieval_ab import (  # noqa: E402
    BASE_SYSTEM_PROMPT,
    EXPERIENCE_HEADER,
    Experience,
    Selection,
    Task,
    append_record,
    combine_usage,
    exact_mcnemar_p,
    make_user_prompt,
    paired_bootstrap_ci,
    read_existing,
    render_experiences,
    verify_math,
)

CONDITIONS = ("no_experience", "provisional_l1")
PROTOCOL_VERSION = "provisional-l1-paired-v1"
_EXPERIENCE_FINGERPRINT_FIELDS = (
    "id",
    "level",
    "content",
    "structured_content",
    "source_task_ids",
    "source_rollout_ids",
    "domain",
    "task_family",
    "failure_mode",
    "strategy_type",
    "tool_type",
    "task_stage",
    "parent_ids",
    "source_l0_ids",
    "source_l1_ids",
    "revision_number",
    "lineage_root_id",
    "supersedes_id",
    "review_candidate_ids",
)


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        result = []
        for key, value_item in value.items():
            if isinstance(value_item, dict):
                item = dict(value_item)
                item.setdefault("id", str(key))
                result.append(item)
        return result
    return []


def load_named_l1(snapshot: Path, experience_id: str) -> Experience:
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    matches = [item for item in _items(payload.get("l1_experiences")) if str(item.get("id")) == experience_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one L1 experience with id={experience_id}, found {len(matches)}")
    item = matches[0]
    content = str(item.get("content", "")).strip()
    if not content:
        raise ValueError(f"L1 experience has empty content: {experience_id}")
    if item.get("lifecycle_status") != "active":
        raise ValueError(f"L1 experience must have lifecycle_status=active: {experience_id}")
    if item.get("validation_status") != "provisional":
        raise ValueError(
            f"L1 experience must have validation_status=provisional: {experience_id}"
        )
    return Experience(id=experience_id, level="L1", content=content, metadata=item)


def experience_version_fingerprint(experience: Experience) -> str:
    """Mirror the manager's semantic/provenance version fingerprint."""

    canonical = {
        field_name: experience.metadata.get(field_name)
        for field_name in _EXPERIENCE_FINGERPRINT_FIELDS
    }
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _sqlite_path(db_url: str) -> Path:
    for prefix in ("sqlite:///", "sqlite+pysqlite:///"):
        if db_url.startswith(prefix):
            return Path(db_url[len(prefix) :])
    raise ValueError("provisional L1 validation currently supports a SQLite UTU_DB_URL only")


def _normalise_question(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _relaxed_question(text: str) -> str:
    return "".join(character for character in _normalise_question(text) if character.isalnum())


def _character_ngrams(text: str, width: int = 5) -> set[str]:
    compact = _relaxed_question(text)
    if len(compact) < width:
        return {compact} if compact else set()
    return {compact[index : index + width] for index in range(len(compact) - width + 1)}


def _near_duplicate(left: str, right: str, threshold: float = 0.90) -> bool:
    left_ngrams = _character_ngrams(left)
    right_ngrams = _character_ngrams(right)
    union = left_ngrams | right_ngrams
    return bool(union) and len(left_ngrams & right_ngrams) / len(union) >= threshold


def load_held_out_tasks(
    dataset: str,
    indices: Sequence[int],
    *,
    source_dataset: str,
    disjoint_datasets: Sequence[str] = ("AIME24",),
) -> tuple[list[Task], dict[str, Any]]:
    if not indices:
        raise ValueError("at least one held-out index is required")
    if len(indices) != len(set(indices)):
        raise ValueError("held-out indices must be unique")
    db_path = _sqlite_path(os.getenv("UTU_DB_URL", "sqlite:///test.db"))
    placeholders = ",".join("?" for _ in indices)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            f'SELECT "index", question, answer, source FROM data '
            f'WHERE dataset = ? AND "index" IN ({placeholders}) ORDER BY "index"',  # noqa: S608
            (dataset, *indices),
        ).fetchall()
        exclusion_datasets = list(dict.fromkeys((source_dataset, *disjoint_datasets)))
        exclusion_rows: list[tuple[str, str]] = []
        for exclusion_dataset in exclusion_datasets:
            exclusion_rows.extend(
                (exclusion_dataset, str(row[0]))
                for row in connection.execute(
                    "SELECT question FROM data WHERE dataset = ?",
                    (exclusion_dataset,),
                ).fetchall()
            )
    found = {int(row[0]) for row in rows}
    missing = sorted(set(indices) - found)
    if missing:
        raise ValueError(f"held-out dataset is missing indices: {missing}")
    exclusion_hashes = {
        hashlib.sha256(_normalise_question(question).encode()).hexdigest()
        for _exclusion_dataset, question in exclusion_rows
    }
    exclusion_relaxed = {_relaxed_question(question) for _dataset, question in exclusion_rows}
    exact_overlaps = []
    near_overlaps = []
    tasks = []
    for index, question, answer, source in rows:
        question = str(question)
        if "\ufffd" in question:
            raise ValueError(f"held-out question contains a Unicode replacement character: {index}")
        fingerprint = hashlib.sha256(_normalise_question(question).encode()).hexdigest()
        if fingerprint in exclusion_hashes or _relaxed_question(question) in exclusion_relaxed:
            exact_overlaps.append(int(index))
        elif any(_near_duplicate(question, excluded) for _dataset, excluded in exclusion_rows):
            near_overlaps.append(int(index))
        tasks.append(Task(int(index), question, str(answer), str(source)))
    if exact_overlaps:
        raise ValueError(
            f"held-out questions overlap an excluded dataset by normalized text: {exact_overlaps}"
        )
    if near_overlaps:
        raise ValueError(f"held-out questions are near-duplicates of an excluded dataset: {near_overlaps}")
    manifest_rows = [
        {
            "dataset_index": task.dataset_index,
            "question_sha256": hashlib.sha256(_normalise_question(task.question).encode()).hexdigest(),
            "answer_sha256": hashlib.sha256(task.answer.encode()).hexdigest(),
        }
        for task in tasks
    ]
    manifest_sha256 = hashlib.sha256(
        json.dumps(manifest_rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return tasks, {
        "dataset": dataset,
        "source_dataset": source_dataset,
        "disjoint_datasets": list(disjoint_datasets),
        "indices": [task.dataset_index for task in tasks],
        "exact_overlap_count": 0,
        "near_overlap_count": 0,
        "excluded_question_count": len(exclusion_rows),
        "manifest_sha256": manifest_sha256,
        "role": "heldout_validation",
    }


def summarize(
    records: Sequence[dict[str, Any]],
    *,
    experience_id: str,
    model: str,
    dataset: str,
    indices: set[int],
    seed: int,
    min_validation_trials: int,
    min_distinct_validation_tasks: int,
    max_harms: int,
    policy_hash: str | None = None,
) -> dict[str, Any]:
    _latest, pairs = _complete_pairs(
        records,
        experience_id=experience_id,
        model=model,
        dataset=dataset,
        indices=indices,
        policy_hash=policy_hash,
    )

    differences = [pair["provisional_l1"]["reward"] - pair["no_experience"]["reward"] for pair in pairs]
    helps = sum(pair["provisional_l1"]["reward"] > pair["no_experience"]["reward"] for pair in pairs)
    harms = sum(pair["provisional_l1"]["reward"] < pair["no_experience"]["reward"] for pair in pairs)
    neutral = len(pairs) - helps - harms

    def accuracy(condition: str) -> float | None:
        return statistics.mean(float(pair[condition]["reward"]) for pair in pairs) if pairs else None

    readiness = {
        "decision": "keep_provisional",
        "reason": "insufficient_or_nonpositive_paired_evidence",
        "minimum_trials": min_validation_trials,
        "minimum_distinct_tasks": min_distinct_validation_tasks,
        "maximum_harms": max_harms,
    }
    distinct_task_n = len({int(pair["no_experience"]["dataset_index"]) for pair in pairs})
    if (
        len(pairs) >= min_validation_trials
        and distinct_task_n >= min_distinct_validation_tasks
        and helps > harms
        and harms <= max_harms
    ):
        readiness = {
            "decision": "eligible_for_promotion_review",
            "reason": "paired_evidence_gate_satisfied",
            "minimum_trials": min_validation_trials,
            "minimum_distinct_tasks": min_distinct_validation_tasks,
            "maximum_harms": max_harms,
        }
    return {
        "completed_records": len(pairs) * len(CONDITIONS),
        "failed_records": max(0, len(_latest) - len(pairs) * len(CONDITIONS)),
        "paired_n": len(pairs),
        "distinct_task_n": distinct_task_n,
        "accuracy": {condition: accuracy(condition) for condition in CONDITIONS},
        "accuracy_delta": statistics.mean(differences) if differences else None,
        "help_count": helps,
        "harm_count": harms,
        "neutral_count": neutral,
        "bootstrap_95_ci": paired_bootstrap_ci(differences, seed) if differences else None,
        "mcnemar_exact_p": exact_mcnemar_p(harms, helps),
        "promotion_readiness": readiness,
    }


def _complete_pairs(
    records: Sequence[dict[str, Any]],
    *,
    experience_id: str,
    model: str,
    dataset: str,
    indices: set[int],
    policy_hash: str | None,
) -> tuple[dict[tuple[int, int, str], dict[str, Any]], list[dict[str, dict[str, Any]]]]:
    """Select the latest usable records and return complete paired trials."""

    latest: dict[tuple[int, int, str], dict[str, Any]] = {}
    for record in records:
        if (
            record.get("experience_id") != experience_id
            or record.get("model") != model
            or record.get("dataset") != dataset
            or int(record.get("dataset_index", -1)) not in indices
            or (policy_hash is not None and record.get("policy_hash") != policy_hash)
        ):
            continue
        key = (int(record["dataset_index"]), int(record["repeat"]), str(record["condition"]))
        usable = record.get("error") is None and bool(str(record.get("response", "")).strip())
        previous = latest.get(key)
        previous_usable = previous is not None and previous.get("error") is None
        if previous is None or usable or not previous_usable:
            latest[key] = record

    usable_rows = [
        record
        for record in latest.values()
        if record.get("error") is None and bool(str(record.get("response", "")).strip())
    ]
    pairs: list[dict[str, dict[str, Any]]] = []
    pair_keys = sorted({(int(row["dataset_index"]), int(row["repeat"])) for row in usable_rows})
    for pair_key in pair_keys:
        pair = {
            row["condition"]: row
            for row in usable_rows
            if (int(row["dataset_index"]), int(row["repeat"])) == pair_key
        }
        if all(condition in pair for condition in CONDITIONS):
            pairs.append(pair)
    return latest, pairs


def record_pairs_to_snapshot(
    args: argparse.Namespace,
    records: Sequence[dict[str, Any]],
    *,
    policy: dict[str, Any],
    policy_hash: str,
) -> dict[str, Any]:
    """Persist complete smoke/validation pairs through the manager state machine."""

    from utu.config import ConfigLoader
    from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager

    if not args.config_name:
        raise ValueError("--config-name is required with --record-to-snapshot")
    config = ConfigLoader.load_training_free_grpo_config(args.config_name)
    hierarchical_config = config.practice.hierarchical_learning.model_copy(deep=True)
    hierarchical_config.experience_save_path = str(args.snapshot.resolve())
    hierarchical_config.clustering_audit_path = str(
        args.snapshot.resolve().with_suffix(args.snapshot.suffix + ".clusters.jsonl")
    )
    manager = HierarchicalExperienceManager(
        config=config.runtime.agent,
        hierarchical_config=hierarchical_config,
        agent_objective=config.practice.agent_objective,
        learning_objective=config.practice.learning_objective,
    )
    _latest, pairs = _complete_pairs(
        records,
        experience_id=args.experience_id,
        model=policy["model"],
        dataset=args.dataset,
        indices=set(args.indices),
        policy_hash=policy_hash,
    )
    recorded = 0
    for pair in pairs:
        baseline = pair["no_experience"]
        treatment = pair["provisional_l1"]
        question_hash = str(baseline["question_sha256"])
        if question_hash != treatment.get("question_sha256"):
            raise ValueError("paired records disagree on the held-out question hash")
        trial_payload = {
            "experience_id": args.experience_id,
            "policy_hash": policy_hash,
            "question_sha256": question_hash,
            "repeat": int(baseline["repeat"]),
        }
        trial_id = hashlib.sha256(
            json.dumps(trial_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manager.record_l1_paired_validation(
            args.experience_id,
            f"{args.dataset}:{int(baseline['dataset_index'])}",
            trial_id=trial_id,
            task_question_sha256=question_hash,
            dataset=args.dataset,
            dataset_manifest_sha256=policy["validation_manifest_sha256"],
            dataset_role="heldout_validation",
            repeat=int(baseline["repeat"]),
            model=policy["model"],
            protocol_version=policy["protocol_version"],
            generation_config_sha256=policy_hash,
            experience_version_fingerprint=policy["experience_version_fingerprint"],
            baseline_prompt_sha256=baseline["prompt_sha256"],
            treatment_prompt_sha256=treatment["prompt_sha256"],
            baseline_score=float(baseline["reward"]),
            treatment_score=float(treatment["reward"]),
            note="Recorded by validate_provisional_l1.py",
        )
        recorded += 1
    return {
        "recorded_pair_count": recorded,
        "promotion_readiness": manager.get_l1_promotion_readiness(args.experience_id),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    experience = load_named_l1(args.snapshot, args.experience_id)
    tasks, leakage = load_held_out_tasks(
        args.dataset,
        args.indices,
        source_dataset=args.source_dataset,
        disjoint_datasets=args.disjoint_dataset,
    )
    api_key = os.getenv("UTU_LLM_API_KEY")
    base_url = os.getenv("UTU_LLM_BASE_URL")
    model = args.model or os.getenv("UTU_LLM_MODEL")
    if not api_key or not base_url or not model:
        raise ValueError("UTU_LLM_API_KEY, UTU_LLM_BASE_URL, and model must be configured")

    selection = Selection(experience=experience, score=1.0)
    block, injected_tokens = render_experiences([selection], args.token_budget, header=EXPERIENCE_HEADER)
    verifier_sha256 = hashlib.sha256(inspect.getsource(verify_math).encode()).hexdigest()
    policy = {
        "version": 2,
        "protocol_version": PROTOCOL_VERSION,
        "experience_id": experience.id,
        "experience_content_sha256": hashlib.sha256(experience.content.encode()).hexdigest(),
        "experience_version_fingerprint": experience_version_fingerprint(experience),
        "rendered_experience_sha256": hashlib.sha256(block.encode()).hexdigest(),
        "system_prompt_sha256": hashlib.sha256(BASE_SYSTEM_PROMPT.encode()).hexdigest(),
        "verifier_sha256": verifier_sha256,
        "dataset": args.dataset,
        "indices": sorted(args.indices),
        "validation_manifest_sha256": leakage["manifest_sha256"],
        "source_dataset": args.source_dataset,
        "model": model,
        "token_budget": args.token_budget,
        "temperature": 0.0,
        "max_output_tokens": args.max_output_tokens,
        "disable_thinking": args.disable_thinking,
    }
    policy_hash = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
    existing = read_existing(args.output)
    completed = {
        (int(record["dataset_index"]), int(record["repeat"]), str(record["condition"]))
        for record in existing
        if record.get("policy_hash") == policy_hash
        and record.get("error") is None
        and bool(str(record.get("response", "")).strip())
    }
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)
    semaphore = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()
    jobs = []
    rng = random.Random(args.seed)
    for repeat in range(args.repeats):
        for task in tasks:
            order = list(CONDITIONS)
            rng.shuffle(order)
            jobs.extend((task, repeat, condition) for condition in order)

    async def execute(task: Task, repeat: int, condition: str) -> dict[str, Any] | None:
        key = (task.dataset_index, repeat, condition)
        if key in completed:
            return None
        prompt = make_user_prompt(task, block if condition == "provisional_l1" else "")
        started = time.perf_counter()
        response = ""
        error = None
        finish_reason = None
        usage = None
        reasoning_chars = 0
        for attempt in range(1, args.max_attempts + 1):
            try:
                request: dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": BASE_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.0,
                    "max_tokens": args.max_output_tokens,
                }
                if args.disable_thinking:
                    request["extra_body"] = {"enable_thinking": False}
                async with semaphore:
                    completion = await client.chat.completions.create(**request)
                choice = completion.choices[0]
                response = choice.message.content or ""
                finish_reason = choice.finish_reason
                reasoning = getattr(choice.message, "reasoning_content", None)
                if reasoning is None and getattr(choice.message, "model_extra", None):
                    reasoning = choice.message.model_extra.get("reasoning_content")
                reasoning_chars = len(reasoning or "")
                usage = completion.usage.model_dump() if completion.usage is not None else None
                if finish_reason == "length":
                    error = "IncompleteModelResponse: finish_reason=length"
                elif not response.strip():
                    error = f"EmptyModelResponse: finish_reason={finish_reason}"
                else:
                    error = None
                break
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                if attempt < args.max_attempts:
                    await asyncio.sleep(min(2**attempt, 8))
        reward = verify_math(task.answer, response) if error is None else 0.0
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "policy_hash": policy_hash,
            "experience_id": experience.id,
            "dataset": args.dataset,
            "dataset_index": task.dataset_index,
            "question_sha256": hashlib.sha256(_normalise_question(task.question).encode()).hexdigest(),
            "validation_manifest_sha256": leakage["manifest_sha256"],
            "dataset_role": "heldout_validation",
            "repeat": repeat,
            "condition": condition,
            "model": model,
            "answer": task.answer,
            "reward": reward,
            "response": response,
            "error": error,
            "finish_reason": finish_reason,
            "usage": combine_usage(usage),
            "reasoning_chars": reasoning_chars,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "selected_ids": [experience.id] if condition == "provisional_l1" else [],
            "injected_tokens": injected_tokens if condition == "provisional_l1" else 0,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        }
        async with write_lock:
            append_record(args.output, record)
        print(
            f"task={task.dataset_index} repeat={repeat} condition={condition:<15} "
            f"reward={reward:.0f} error={error is not None}",
            flush=True,
        )
        return record

    try:
        new_records = await asyncio.gather(*(execute(*job) for job in jobs))
    finally:
        await client.close()
    records = existing + [record for record in new_records if record is not None]
    result = {
        "run_config": policy,
        "policy_hash": policy_hash,
        "leakage_guard": leakage,
        "experience": {
            "id": experience.id,
            "lifecycle_status": experience.metadata.get("lifecycle_status"),
            "validation_status": experience.metadata.get("validation_status"),
            "source_task_ids": experience.metadata.get("source_task_ids", []),
            "parent_ids": experience.metadata.get("parent_ids", []),
        },
        "results": summarize(
            records,
            experience_id=experience.id,
            model=model,
            dataset=args.dataset,
            indices={task.dataset_index for task in tasks},
            seed=args.seed,
            min_validation_trials=args.min_validation_trials,
            min_distinct_validation_tasks=args.min_distinct_validation_tasks,
            max_harms=args.max_harms,
            policy_hash=policy_hash,
        ),
    }
    if args.record_to_snapshot:
        result["snapshot_recording"] = record_pairs_to_snapshot(
            args,
            records,
            policy=policy,
            policy_hash=policy_hash,
        )
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--config-name")
    parser.add_argument("--experience-id", required=True)
    parser.add_argument("--dataset", default="DAPO-Math-17k")
    parser.add_argument("--source-dataset", required=True)
    parser.add_argument("--disjoint-dataset", action="append", default=["AIME24"])
    parser.add_argument("--indices", type=int, nargs="+", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--token-budget", type=int, default=800)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--min-validation-trials", type=int, default=20)
    parser.add_argument("--min-distinct-validation-tasks", type=int, default=20)
    parser.add_argument("--max-harms", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--record-to-snapshot", action="store_true")
    args = parser.parse_args(argv)
    if args.repeats < 1 or args.concurrency < 1 or args.max_attempts < 1:
        parser.error("repeats, concurrency, and max-attempts must be positive")
    if args.token_budget < 64 or args.max_output_tokens < 1:
        parser.error("token budgets must be positive")
    if (
        args.min_validation_trials < 1
        or args.min_distinct_validation_tasks < 1
        or args.max_harms < 0
    ):
        parser.error("validation thresholds are invalid")
    if args.record_to_snapshot and not args.config_name:
        parser.error("--config-name is required with --record-to-snapshot")
    return args


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
