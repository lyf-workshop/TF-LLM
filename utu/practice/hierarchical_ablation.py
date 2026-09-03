"""Offline metrics and seed preparation for hierarchy A/B experiments."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import statistics
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .experience_models import ExperienceRecord

CONDITIONS = ("no_experience", "sequential", "clustered")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_l0_fingerprint(source: str | Path) -> dict[str, Any]:
    """Fingerprint the exact normalized L0 snapshot used by both treatments."""

    records = []
    for raw in load_hierarchy(source)["L0"]:
        record = ExperienceRecord.model_validate(raw).model_copy(
            update={
                "aggregation_status": "pending",
                "cluster_id": None,
                "aggregated_into_cluster_id": None,
                "parent_ids": [],
                "source_l0_ids": [],
                "source_l1_ids": [],
            }
        )
        records.append(record.public_dict())
    if not records:
        raise ValueError(f"No L0 experiences found in {source}")
    return {
        "source_snapshot_file_sha256": file_sha256(source),
        "source_l0_sha256": _canonical_sha256(records),
        "l0_count": len(records),
    }


def _level_records(raw: Any, level: str) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        items = []
        for exp_id, value in raw.items():
            item = dict(value) if isinstance(value, dict) else {"content": str(value)}
            item.setdefault("id", str(exp_id))
            item.setdefault("level", level)
            items.append(item)
        return items
    if isinstance(raw, list):
        return [
            (
                {**item, "id": str(item.get("id") or f"{level}_{index}"), "level": level}
                if isinstance(item, dict)
                else {"id": f"{level}_{index}", "level": level, "content": str(item)}
            )
            for index, item in enumerate(raw)
        ]
    return []


def load_hierarchy(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)
    return {level: _level_records(data.get(f"{level.lower()}_experiences", []), level) for level in ("L0", "L1", "L2")}


def prepare_ablation_seed(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Copy the exact L0 evidence into a fresh, pending hierarchy snapshot."""

    source_hierarchy = load_hierarchy(source)
    l0_records = []
    for raw in source_hierarchy["L0"]:
        record = ExperienceRecord.model_validate(raw).model_copy(
            update={
                "aggregation_status": "pending",
                "cluster_id": None,
                "aggregated_into_cluster_id": None,
                "parent_ids": [],
                "source_l0_ids": [],
                "source_l1_ids": [],
            }
        )
        l0_records.append(record.public_dict())
    fingerprint = source_l0_fingerprint(source)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite ablation artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "source_snapshot_file_sha256": fingerprint["source_snapshot_file_sha256"],
        "source_l0_sha256": fingerprint["source_l0_sha256"],
        "l0_experiences": l0_records,
        "l1_experiences": [],
        "l2_experiences": [],
        "l0_aggregated_ids": [],
        "l1_aggregated_ids": [],
        "stats": {"total_l0": len(l0_records), "total_l1": 0, "total_l2": 0},
    }
    with destination.open("x", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return {
        "source_snapshot_file_sha256": payload["source_snapshot_file_sha256"],
        "source_l0_sha256": payload["source_l0_sha256"],
        "l0_count": len(l0_records),
        "destination": str(destination),
    }


def load_audit(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).exists():
        return []
    entries = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def _normalise_content(content: str) -> str:
    return re.sub(r"\s+", " ", (content or "").strip().lower())


def _token_count(text: str) -> tuple[int, str]:
    try:
        import tiktoken  # type: ignore[import-not-found]

        return len(tiktoken.get_encoding("cl100k_base").encode(text)), "cl100k_base"
    except ImportError:
        # Deterministic fallback: words, numbers, punctuation, and each CJK
        # character are counted separately.  The report labels it as estimated.
        tokens = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]|[^\s\w]", text)
        return len(tokens), "regex_estimate"


def _cluster_metrics(
    audit_entries: Iterable[dict[str, Any]],
    records_by_id: dict[str, dict[str, Any]],
    hard_fields: tuple[str, ...] = ("task_stage", "failure_mode"),
) -> dict[str, Any]:
    unique_clusters: dict[str, dict[str, Any]] = {}
    for entry in audit_entries:
        for cluster in entry.get("report", {}).get("clusters", []):
            unique_clusters[cluster["cluster_id"]] = cluster
    clusters = list(unique_clusters.values())
    weights = [max(1, len(cluster.get("experience_ids", []))) for cluster in clusters]
    total_weight = sum(weights)
    mean_similarity = (
        sum(
            cluster.get("intra_cluster_similarity", 0.0) * weight
            for cluster, weight in zip(clusters, weights, strict=False)
        )
        / total_weight
        if total_weight
        else None
    )
    metadata_consistency = (
        sum(
            cluster.get("metadata_consistency", 0.0) * weight
            for cluster, weight in zip(clusters, weights, strict=False)
        )
        / total_weight
        if total_weight
        else None
    )
    conflict_pairs = 0
    total_pairs = 0
    for cluster in clusters:
        ids = cluster.get("experience_ids", [])
        for index, left_id in enumerate(ids):
            for right_id in ids[index + 1 :]:
                total_pairs += 1
                left = records_by_id.get(left_id, {})
                right = records_by_id.get(right_id, {})
                if any(
                    str(left.get(field) or "").lower() not in ("", "unknown", "null")
                    and str(right.get(field) or "").lower() not in ("", "unknown", "null")
                    and left.get(field) != right.get(field)
                    for field in hard_fields
                ):
                    conflict_pairs += 1
    return {
        "cluster_count": len(clusters),
        "cluster_size_distribution": sorted([len(cluster.get("experience_ids", [])) for cluster in clusters]),
        "mean_intra_cluster_similarity": mean_similarity,
        "mean_metadata_consistency": metadata_consistency,
        "conflict_experience_pair_ratio": conflict_pairs / total_pairs if total_pairs else 0.0,
    }


def hierarchy_metrics(
    hierarchy_path: str | Path,
    audit_path: str | Path | None = None,
    *,
    max_l0_recent: int = 40,
) -> dict[str, Any]:
    hierarchy = load_hierarchy(hierarchy_path)
    all_records = [record for level in ("L0", "L1", "L2") for record in hierarchy[level]]
    records_by_id = {record["id"]: record for record in all_records}
    pending = [
        record
        for level in ("L0", "L1")
        for record in hierarchy[level]
        if record.get("aggregation_status", "pending") == "pending"
    ]
    aggregatable_count = len(hierarchy["L0"]) + len(hierarchy["L1"])
    duplicates = 0
    duplicate_denominator = 0
    for level in ("L0", "L1", "L2"):
        contents = [_normalise_content(record.get("content", "")) for record in hierarchy[level]]
        contents = [content for content in contents if content]
        duplicates += len(contents) - len(set(contents))
        duplicate_denominator += len(contents)
    prompt_records = hierarchy["L2"] + hierarchy["L1"] + hierarchy["L0"][-max_l0_recent:]
    token_count, tokenizer = _token_count("\n".join(record.get("content", "") for record in prompt_records))
    return {
        "counts": {level: len(hierarchy[level]) for level in ("L0", "L1", "L2")},
        **_cluster_metrics(load_audit(audit_path), records_by_id),
        "unable_to_aggregate_ratio": len(pending) / aggregatable_count if aggregatable_count else 0.0,
        "duplicate_experience_ratio": duplicates / duplicate_denominator if duplicate_denominator else 0.0,
        "final_prompt_token_count": token_count,
        "tokenizer": tokenizer,
    }


def _load_evaluation(path: str | Path | None) -> dict[str, float]:
    if path is None:
        return {}
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as file:
            raw: Any = [json.loads(line) for line in file if line.strip()]
    else:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    if isinstance(raw, dict):
        raw = raw.get("results", raw.get("samples", list(raw.values())))
    outcomes: dict[str, float] = {}
    for index, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        task_id = item.get("task_id") or item.get("source_task_id") or item.get("id")
        if task_id is None and item.get("dataset_index") is not None:
            task_id = f"{item.get('dataset', 'dataset')}:{item['dataset_index']}"
        task_id = str(task_id if task_id is not None else index)
        if item.get("reward") is not None:
            outcome = float(item["reward"])
        elif item.get("correct") is not None:
            outcome = 1.0 if bool(item["correct"]) else 0.0
        elif item.get("success") is not None:
            outcome = 1.0 if bool(item["success"]) else 0.0
        else:
            continue
        outcomes[task_id] = max(outcomes.get(task_id, float("-inf")), outcome)
    return outcomes


def _load_evaluation_from_db(exp_id: str | None) -> dict[str, float]:
    if not exp_id:
        return {}
    from sqlmodel import select

    from ..db.eval_datapoint import EvaluationSample
    from ..utils.sqlmodel_utils import SQLModelUtils

    with SQLModelUtils.create_session() as session:
        samples = session.exec(
            select(EvaluationSample).where(
                EvaluationSample.exp_id == exp_id,
                EvaluationSample.stage == "judged",
            )
        ).all()
    outcomes: dict[str, float] = {}
    for sample in samples:
        if sample.dataset_index is not None:
            task_id = f"{sample.dataset}:{sample.dataset_index}"
        else:
            task_id = str(sample.trace_id or sample.id)
        if sample.reward is not None:
            outcome = float(sample.reward)
        elif sample.correct is not None:
            outcome = 1.0 if sample.correct else 0.0
        else:
            continue
        # pass-k evaluations may have multiple trials per task; task success is
        # the best observed reward, matching pass@k semantics.
        outcomes[task_id] = max(outcomes.get(task_id, float("-inf")), outcome)
    return outcomes


def _load_result_rows(path: str | Path | None, exp_id: str | None) -> list[dict[str, Any]]:
    if path is not None:
        result_path = Path(path)
        if result_path.suffix.lower() == ".jsonl":
            with result_path.open("r", encoding="utf-8") as file:
                raw: Any = [json.loads(line) for line in file if line.strip()]
        else:
            with result_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        if isinstance(raw, dict):
            raw = raw.get("results", raw.get("samples", list(raw.values())))
        return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    if not exp_id:
        return []

    from sqlmodel import select

    from ..db.eval_datapoint import EvaluationSample
    from ..utils.sqlmodel_utils import SQLModelUtils

    with SQLModelUtils.create_session() as session:
        samples = session.exec(
            select(EvaluationSample)
            .where(EvaluationSample.exp_id == exp_id, EvaluationSample.stage == "judged")
            .order_by(EvaluationSample.id)
        ).all()
    return [sample.model_dump(mode="json") for sample in samples]


def _row_task_id(row: dict[str, Any]) -> str:
    meta = row.get("meta")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
    value = (
        row.get("task_id")
        or row.get("source_task_id")
        or meta.get("task_id")
        or row.get("dataset_index")
        or row.get("id")
    )
    if value is None:
        raise ValueError("Evaluation row has no task identifier")
    return str(value)


def _row_reward(row: dict[str, Any]) -> float | None:
    if row.get("reward") is not None:
        return float(row["reward"])
    if row.get("correct") is not None:
        return 1.0 if bool(row["correct"]) else 0.0
    if row.get("success") is not None:
        return 1.0 if bool(row["success"]) else 0.0
    return None


def _row_injected_tokens(row: dict[str, Any]) -> float | None:
    meta = row.get("meta")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    candidates = [row]
    if isinstance(meta, dict):
        candidates.append(meta)
    for container in candidates:
        for key in ("injected_token_count", "prompt_injected_tokens", "experience_tokens"):
            if container.get(key) is not None:
                return float(container[key])
    return None


def _collapse_results(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Collapse pass-k trials while preserving the first task occurrence order."""

    order: list[str] = []
    collapsed: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = _row_task_id(row)
        reward = _row_reward(row)
        if reward is None:
            continue
        if task_id not in collapsed:
            order.append(task_id)
            collapsed[task_id] = {"reward": reward, "injected_tokens": []}
        else:
            collapsed[task_id]["reward"] = max(collapsed[task_id]["reward"], reward)
        tokens = _row_injected_tokens(row)
        if tokens is not None:
            collapsed[task_id]["injected_tokens"].append(tokens)
    return order, collapsed


def _runtime_signature(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "model_config_sha256",
        "requested_model",
        "temperature",
        "expected_trials_per_task",
        "task_split_name",
        "train_dataset_for_overlap_check",
        "injected_tokenizer",
    )
    collected: dict[str, set[Any]] = {field: set() for field in fields}
    conditions: set[str] = set()
    for row in rows:
        meta = row.get("meta")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, dict):
            continue
        for field in fields:
            if meta.get(field) is not None:
                collected[field].add(meta[field])
        if meta.get("experience_condition"):
            conditions.add(str(meta["experience_condition"]))
    inconsistent = {field: sorted(values, key=str) for field, values in collected.items() if len(values) > 1}
    if inconsistent:
        raise ValueError(f"Evaluation rows contain inconsistent runtime metadata: {inconsistent}")
    return {
        field: next(iter(values)) if values else None for field, values in collected.items()
    } | {"experience_conditions": sorted(conditions)}


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _paired_bootstrap(
    baseline: list[int],
    treatment: list[int],
    *,
    seed: int = 42,
    samples: int = 10_000,
) -> dict[str, float | int]:
    if len(baseline) != len(treatment) or not baseline:
        raise ValueError("Paired bootstrap requires equal, non-empty outcome vectors")
    rng = random.Random(seed)
    count = len(baseline)
    deltas = []
    for _ in range(samples):
        indices = [rng.randrange(count) for _ in range(count)]
        deltas.append(statistics.fmean(treatment[index] - baseline[index] for index in indices))
    return {
        "point_estimate": statistics.fmean(t - b for b, t in zip(baseline, treatment, strict=True)),
        "ci95_low": _percentile(deltas, 0.025),
        "ci95_high": _percentile(deltas, 0.975),
        "bootstrap_samples": samples,
        "random_seed": seed,
    }


def _mcnemar_exact(baseline_only: int, treatment_only: int) -> dict[str, float | int]:
    discordant = baseline_only + treatment_only
    if discordant == 0:
        p_value = 1.0
    else:
        lower = min(baseline_only, treatment_only)
        tail = sum(math.comb(discordant, index) for index in range(lower + 1)) / (2**discordant)
        p_value = min(1.0, 2.0 * tail)
    return {
        "baseline_only": baseline_only,
        "treatment_only": treatment_only,
        "discordant_pairs": discordant,
        "two_sided_exact_p_value": p_value,
    }


def _group_breakdown(
    task_ids: list[str],
    outcomes: dict[str, int],
    task_metadata: dict[str, dict[str, Any]],
    field: str,
) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[int]] = {}
    for task_id in task_ids:
        value = str(task_metadata[task_id].get(field) or "unknown")
        groups.setdefault(value, []).append(outcomes[task_id])
    return {
        value: {
            "tasks": len(values),
            "passes": sum(values),
            "pass_rate": sum(values) / len(values),
        }
        for value, values in sorted(groups.items())
    }


def build_three_group_report(
    *,
    evaluation_paths: dict[str, str | Path | None],
    evaluation_exp_ids: dict[str, str | None] | None,
    sequential_hierarchy: str | Path,
    clustered_hierarchy: str | Path,
    split_manifest_path: str | Path,
    split_name: str,
    sequential_audit: str | Path | None = None,
    clustered_audit: str | Path | None = None,
    max_l0_recent: int = 40,
    strict_success_threshold: float = 1.0,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Build one strict paired report for no/sequence/cluster conditions."""

    from ..skillsbench_data import canonical_sha256, load_task_split_manifest

    evaluation_exp_ids = evaluation_exp_ids or {}
    if set(evaluation_paths) != set(CONDITIONS):
        raise ValueError(f"evaluation_paths must contain exactly {CONDITIONS}")
    manifest = load_task_split_manifest(split_manifest_path)
    split = manifest["splits"][split_name]
    expected_order = list(split["eval_task_ids"])
    expected_set = set(expected_order)
    task_metadata = {item["task_id"]: item for item in manifest["tasks"]}

    collapsed: dict[str, dict[str, dict[str, Any]]] = {}
    observed_orders: dict[str, list[str]] = {}
    runtime_signatures: dict[str, dict[str, Any]] = {}
    for condition in CONDITIONS:
        rows = _load_result_rows(evaluation_paths[condition], evaluation_exp_ids.get(condition))
        runtime_signatures[condition] = _runtime_signature(rows)
        declared = runtime_signatures[condition]["experience_conditions"]
        if declared and declared != [condition]:
            raise ValueError(f"{condition} result declares the wrong treatment metadata: {declared}")
        order, values = _collapse_results(rows)
        if set(order) != expected_set:
            missing = sorted(expected_set - set(order))
            unexpected = sorted(set(order) - expected_set)
            raise ValueError(
                f"{condition} evaluation task list differs from manifest {split_name}: "
                f"missing={missing}, unexpected={unexpected}"
            )
        if order != expected_order:
            raise ValueError(
                f"{condition} evaluation order differs from the manifest; paired runs must use one order"
            )
        observed_orders[condition] = order
        collapsed[condition] = values

    comparable_fields = (
        "model_config_sha256",
        "requested_model",
        "temperature",
        "expected_trials_per_task",
        "task_split_name",
        "train_dataset_for_overlap_check",
        "injected_tokenizer",
    )
    verified_fields = []
    missing_fields = []
    for field in comparable_fields:
        values = [runtime_signatures[condition][field] for condition in CONDITIONS]
        if any(value is None for value in values):
            missing_fields.append(field)
        elif len(set(values)) != 1:
            raise ValueError(f"Three conditions used different {field}: {values}")
        else:
            verified_fields.append(field)

    hierarchy = {
        "sequential": hierarchy_metrics(
            sequential_hierarchy, sequential_audit, max_l0_recent=max_l0_recent
        ),
        "clustered": hierarchy_metrics(
            clustered_hierarchy, clustered_audit, max_l0_recent=max_l0_recent
        ),
    }
    sequential_seed = json.loads(Path(sequential_hierarchy).read_text(encoding="utf-8"))
    clustered_seed = json.loads(Path(clustered_hierarchy).read_text(encoding="utf-8"))
    sequential_source_hash = sequential_seed.get("source_l0_sha256")
    clustered_source_hash = clustered_seed.get("source_l0_sha256")
    if not sequential_source_hash or sequential_source_hash != clustered_source_hash:
        raise ValueError("Sequential and clustered conditions do not share the same original L0 snapshot hash")

    strict: dict[str, dict[str, int]] = {}
    group_metrics: dict[str, dict[str, Any]] = {}
    for condition in CONDITIONS:
        strict[condition] = {
            task_id: int(collapsed[condition][task_id]["reward"] >= strict_success_threshold)
            for task_id in expected_order
        }
        token_values = [
            statistics.fmean(collapsed[condition][task_id]["injected_tokens"])
            for task_id in expected_order
            if collapsed[condition][task_id]["injected_tokens"]
        ]
        if condition == "no_experience":
            mean_tokens: float | None = statistics.fmean(token_values) if token_values else 0.0
            token_source = "evaluation_metadata" if token_values else "declared_no_experience"
        elif token_values:
            mean_tokens = statistics.fmean(token_values)
            token_source = "evaluation_metadata"
        else:
            mean_tokens = float(hierarchy[condition]["final_prompt_token_count"])
            token_source = "static_hierarchy_prompt_estimate"
        values = list(strict[condition].values())
        group_metrics[condition] = {
            "task_count": len(values),
            "passes": sum(values),
            "pass_rate": sum(values) / len(values),
            "average_injected_tokens": mean_tokens,
            "injected_token_source": token_source,
            "pending_ratio": 0.0 if condition == "no_experience" else hierarchy[condition]["unable_to_aggregate_ratio"],
            "cluster_count": 0 if condition == "no_experience" else hierarchy[condition]["cluster_count"],
            "cluster_size_distribution": (
                [] if condition == "no_experience" else hierarchy[condition]["cluster_size_distribution"]
            ),
            "by_domain": _group_breakdown(expected_order, strict[condition], task_metadata, "domain"),
            "by_task_family": _group_breakdown(expected_order, strict[condition], task_metadata, "task_family"),
        }

    pairwise = {}
    for treatment in ("sequential", "clustered"):
        baseline_vector = [strict["no_experience"][task_id] for task_id in expected_order]
        treatment_vector = [strict[treatment][task_id] for task_id in expected_order]
        both_pass = sum(b == 1 and t == 1 for b, t in zip(baseline_vector, treatment_vector, strict=True))
        both_fail = sum(b == 0 and t == 0 for b, t in zip(baseline_vector, treatment_vector, strict=True))
        experience_win = sum(b == 0 and t == 1 for b, t in zip(baseline_vector, treatment_vector, strict=True))
        baseline_win = sum(b == 1 and t == 0 for b, t in zip(baseline_vector, treatment_vector, strict=True))
        pairwise[treatment] = {
            "experience_win": experience_win,
            "baseline_win": baseline_win,
            "both_pass": both_pass,
            "both_fail": both_fail,
            "paired_bootstrap_pass_rate_delta": _paired_bootstrap(
                baseline_vector, treatment_vector, seed=random_seed
            ),
            "mcnemar_strict_success": _mcnemar_exact(baseline_win, experience_win),
        }

    per_task = []
    for task_id in expected_order:
        item = {
            "task_id": task_id,
            "domain": task_metadata[task_id]["domain"],
            "task_family": task_metadata[task_id]["task_family"],
        }
        for condition in CONDITIONS:
            item[condition] = {
                "reward": collapsed[condition][task_id]["reward"],
                "strict_success": bool(strict[condition][task_id]),
            }
        per_task.append(item)

    rates = {condition: group_metrics[condition]["pass_rate"] for condition in CONDITIONS}
    best_rate = max(rates.values())
    best = sorted(condition for condition, rate in rates.items() if rate == best_rate)
    conclusion = "tie" if len(best) > 1 else f"highest_observed_pass_rate:{best[0]}"
    return {
        "schema_version": "three-condition-v1",
        "conditions": list(CONDITIONS),
        "integrity": {
            "dataset": manifest["dataset"],
            "split_name": split_name,
            "split_sha256": split["split_sha256"],
            "task_order_sha256": canonical_sha256(expected_order),
            "identical_task_order": len({tuple(order) for order in observed_orders.values()}) == 1,
            "runtime_parameter_verification": {
                "status": "verified" if not missing_fields else "partially_unverified",
                "verified_equal_fields": verified_fields,
                "missing_fields": missing_fields,
                "signatures": runtime_signatures,
            },
            "source_l0_sha256": sequential_source_hash,
            "aggregation_temperature": 0.0,
            "strict_success_threshold": strict_success_threshold,
        },
        "groups": group_metrics,
        "hierarchy": hierarchy,
        "pairwise_vs_no_experience": pairwise,
        "per_task": per_task,
        "conclusion": conclusion,
    }


def evaluation_comparison(
    baseline_path: str | Path | None,
    clustered_path: str | Path | None,
    *,
    baseline_exp_id: str | None = None,
    clustered_exp_id: str | None = None,
) -> dict[str, Any]:
    baseline = _load_evaluation(baseline_path) or _load_evaluation_from_db(baseline_exp_id)
    clustered = _load_evaluation(clustered_path) or _load_evaluation_from_db(clustered_exp_id)
    common = sorted(set(baseline) & set(clustered))
    if not common:
        return {
            "baseline_success_rate": None,
            "clustered_success_rate": None,
            "compared_tasks": 0,
            "improved_tasks": 0,
            "degraded_tasks": 0,
            "unchanged_tasks": 0,
        }
    deltas = [clustered[task_id] - baseline[task_id] for task_id in common]
    return {
        "baseline_success_rate": sum(baseline[task_id] for task_id in common) / len(common),
        "clustered_success_rate": sum(clustered[task_id] for task_id in common) / len(common),
        "compared_tasks": len(common),
        "improved_tasks": sum(delta > 1e-9 for delta in deltas),
        "degraded_tasks": sum(delta < -1e-9 for delta in deltas),
        "unchanged_tasks": sum(abs(delta) <= 1e-9 for delta in deltas),
    }


def build_ablation_report(
    baseline_hierarchy: str | Path,
    clustered_hierarchy: str | Path,
    *,
    baseline_audit: str | Path | None = None,
    clustered_audit: str | Path | None = None,
    baseline_eval: str | Path | None = None,
    clustered_eval: str | Path | None = None,
    baseline_exp_id: str | None = None,
    clustered_exp_id: str | None = None,
    max_l0_recent: int = 40,
) -> dict[str, Any]:
    downstream = evaluation_comparison(
        baseline_eval,
        clustered_eval,
        baseline_exp_id=baseline_exp_id,
        clustered_exp_id=clustered_exp_id,
    )
    baseline_rate = downstream["baseline_success_rate"]
    clustered_rate = downstream["clustered_success_rate"]
    if baseline_rate is None or clustered_rate is None:
        conclusion = "downstream_evaluation_not_provided"
    elif clustered_rate > baseline_rate:
        conclusion = "positive"
    elif clustered_rate < baseline_rate:
        conclusion = "negative"
    else:
        conclusion = "no_improvement"
    return {
        "baseline_sequential": hierarchy_metrics(baseline_hierarchy, baseline_audit, max_l0_recent=max_l0_recent),
        "cluster_first": hierarchy_metrics(clustered_hierarchy, clustered_audit, max_l0_recent=max_l0_recent),
        "downstream": downstream,
        "conclusion": conclusion,
    }
