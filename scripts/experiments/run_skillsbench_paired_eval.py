"""Run paper-aligned SkillsBench baseline and experience trials as AB/BA pairs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tqdm import tqdm

from utu.config import ConfigLoader, EvalConfig
from utu.eval import BaseBenchmark
from utu.eval.data import EvaluationSample
from utu.skillsbench_reliability import FatalSkillsBenchError
from utu.utils import DIR_ROOT, get_logger

logger = get_logger(__name__, "INFO")

DEFAULT_BASELINE_CONFIG = "skillsbench/skillsbench_paper_baseline_eval"
DEFAULT_EXPERIENCE_CONFIG = "skillsbench/skillsbench_paper_tf_grpo_eval"


class IncompleteSkillsBenchComparison(RuntimeError):
    """The run is persisted but cannot yet be reported as a comparison."""


_MATCHED_RUNTIME_FIELDS = (
    "inject_curated_skills",
    "task_timeout_sec",
    "max_agent_iterations",
    "env_build_timeout_multiplier",
    "docker_cleanup_after_task",
    "docker_cleanup_builder_every_n",
    "max_retries",
    "retry_delay_sec",
    "retry_on_timeout",
    "llm_connect_timeout_sec",
    "llm_read_timeout_sec",
    "llm_max_retries",
    "llm_retry_initial_delay_sec",
    "llm_retry_max_delay_sec",
    "circuit_breaker_enabled",
    "circuit_breaker_failure_threshold",
    "circuit_breaker_cooldown_sec",
    "healthcheck_enabled",
    "healthcheck_attempts",
    "expected_num_tasks",
    "require_complete_coverage",
)


@dataclass
class PairedWorkItem:
    """One task/trial pair and its deterministic execution order."""

    key: tuple[str, int]
    order: tuple[str, str]
    baseline: EvaluationSample | None
    experience: EvaluationSample | None


def _meta(sample: EvaluationSample) -> dict[str, Any]:
    value = sample.meta or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    return value if isinstance(value, dict) else {}


def _sample_key(sample: EvaluationSample) -> tuple[str, int]:
    meta = _meta(sample)
    task_id = str(meta.get("task_id") or sample.dataset_index)
    return task_id, int(meta.get("trial_index", 0))


def build_paired_schedule(
    baseline_samples: list[EvaluationSample],
    experience_samples: list[EvaluationSample],
    *,
    seed: int,
) -> list[PairedWorkItem]:
    """Create a balanced, deterministic AB/BA schedule over pending rows."""

    baseline_by_key = {_sample_key(sample): sample for sample in baseline_samples}
    experience_by_key = {_sample_key(sample): sample for sample in experience_samples}
    if len(baseline_by_key) != len(baseline_samples):
        raise ValueError("Duplicate baseline task/trial keys detected")
    if len(experience_by_key) != len(experience_samples):
        raise ValueError("Duplicate experience task/trial keys detected")

    keys = sorted(set(baseline_by_key) | set(experience_by_key))
    random.Random(seed).shuffle(keys)
    schedule: list[PairedWorkItem] = []
    for index, key in enumerate(keys):
        order = ("baseline", "experience") if index % 2 == 0 else ("experience", "baseline")
        schedule.append(
            PairedWorkItem(
                key=key,
                order=order,
                baseline=baseline_by_key.get(key),
                experience=experience_by_key.get(key),
            )
        )
    return schedule


def _model_name(config: EvalConfig) -> str:
    provider = config.agent.model.model_provider if config.agent and config.agent.model else None
    return str(getattr(provider, "model", "") or "")


def _temperature(config: EvalConfig) -> float:
    settings = config.agent.model.model_settings if config.agent and config.agent.model else None
    value = getattr(settings, "temperature", None)
    return float(value) if value is not None else 0.0


def _validate_configs(baseline: EvalConfig, experience: EvalConfig) -> None:
    if baseline.exp_id == experience.exp_id:
        raise ValueError("Baseline and experience exp_id values must be different")
    if "_v4" not in baseline.exp_id or "_v4" not in experience.exp_id:
        raise ValueError("Paired paper evaluation requires fresh exp_id values containing '_v4'")
    if baseline.data.dataset != experience.data.dataset:
        raise ValueError("Both conditions must use the same dataset")
    if baseline.pass_k != experience.pass_k:
        raise ValueError("Both conditions must use the same pass_k")
    if not baseline.skillsbench.enabled or not experience.skillsbench.enabled:
        raise ValueError("SkillsBench harbor execution must be enabled for both conditions")
    if _model_name(baseline) != _model_name(experience) or not _model_name(baseline):
        raise ValueError(
            "Both conditions must request the same non-empty model. "
            "Use --agent-model to pin one model version for both."
        )
    if _temperature(baseline) != 0.0 or _temperature(experience) != 0.0:
        raise ValueError("Paper-aligned paired evaluation requires temperature=0.0")
    if baseline.agent.model.model_provider.type != experience.agent.model.model_provider.type:
        raise ValueError("Both conditions must use the same model provider type")
    if (
        baseline.agent.model.model_settings.model_dump()
        != experience.agent.model.model_settings.model_dump()
    ):
        raise ValueError("Both conditions must use identical model_settings")
    if baseline.agent.model.model_params.model_dump() != experience.agent.model.model_params.model_dump():
        raise ValueError("Both conditions must use identical model_params")

    mismatches = []
    for field in _MATCHED_RUNTIME_FIELDS:
        baseline_value = getattr(baseline.skillsbench, field)
        experience_value = getattr(experience.skillsbench, field)
        if baseline_value != experience_value:
            mismatches.append(f"{field}: {baseline_value!r} != {experience_value!r}")
    if mismatches:
        raise ValueError("SkillsBench runtime settings differ:\n  " + "\n  ".join(mismatches))

    expected_tasks = baseline.skillsbench.expected_num_tasks
    if expected_tasks != 87 or baseline.pass_k != 3:
        raise ValueError(
            "Paper-87 protocol requires expected_num_tasks=87 and pass_k=3 "
            f"(got {expected_tasks!r} and {baseline.pass_k!r})"
        )


def _load_configs(args: argparse.Namespace) -> tuple[EvalConfig, EvalConfig]:
    baseline = ConfigLoader.load_eval_config(args.baseline_config)
    experience = ConfigLoader.load_eval_config(args.experience_config)
    if args.baseline_exp_id:
        baseline.exp_id = args.baseline_exp_id
    if args.experience_exp_id:
        experience.exp_id = args.experience_exp_id
    if args.agent_model:
        baseline.agent.model.model_provider.model = args.agent_model
        experience.agent.model.model_provider.model = args.agent_model
    _validate_configs(baseline, experience)
    return baseline, experience


def _existing_pair_run_id(runners: tuple[BaseBenchmark, BaseBenchmark]) -> str | None:
    run_ids: set[str] = set()
    unstamped_started = []
    for runner in runners:
        for sample in runner.dataset.get_samples():
            pair_run_id = _meta(sample).get("paired_run_id")
            if pair_run_id:
                run_ids.add(str(pair_run_id))
            elif sample.stage != "init":
                unstamped_started.append(f"{sample.exp_id}:{sample.id}:{sample.stage}")
    if unstamped_started:
        raise RuntimeError(
            "Existing started rows were not created by the paired v4 runner. "
            "Use fresh _v4 experiment IDs instead of mixing those records."
        )
    if len(run_ids) > 1:
        raise RuntimeError(f"Multiple paired_run_id values found: {sorted(run_ids)}")
    return next(iter(run_ids), None)


def _stamp_pair_metadata(
    runners: tuple[BaseBenchmark, BaseBenchmark],
    *,
    run_id: str,
    seed: int,
) -> None:
    for condition, runner in zip(("baseline", "experience"), runners, strict=True):
        samples = runner.dataset.get_samples()
        changed = []
        for sample in samples:
            meta = _meta(sample)
            existing = meta.get("paired_run_id")
            if existing and existing != run_id:
                raise RuntimeError(
                    f"{sample.exp_id} contains paired_run_id={existing!r}, expected {run_id!r}"
                )
            meta.update(
                paired_run_id=run_id,
                paired_condition=condition,
                paired_seed=seed,
            )
            sample.update(meta=meta)
            changed.append(sample)
        runner.dataset.save(changed)


def _safe_run_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _report_path(run_id: str) -> Path:
    output_dir = DIR_ROOT / "workspace" / "skillsbench_runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{_safe_run_id(run_id)}.json"


def _read_report(run_id: str) -> dict[str, Any]:
    output_path = _report_path(run_id)
    if not output_path.exists():
        return {}
    try:
        value = json.loads(output_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_report(run_id: str, payload: dict[str, Any]) -> Path:
    output_path = _report_path(run_id)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _observed_models(runner: BaseBenchmark) -> list[str]:
    models: set[str] = set()
    for sample in runner.dataset.get_samples():
        meta = _meta(sample)
        for key in ("actual_models", "healthcheck_models"):
            value = meta.get(key) or []
            if isinstance(value, str):
                value = [value]
            models.update(str(model) for model in value if model)
    return sorted(models)


def _metrics(stat_results: list[dict]) -> dict[str, Any]:
    if len(stat_results) != 1:
        raise RuntimeError(f"Expected one SkillsBench metric group, got {len(stat_results)}")
    return stat_results[0]["metrics"]


async def _run_schedule(
    schedule: list[PairedWorkItem],
    baseline_runner: BaseBenchmark,
    experience_runner: BaseBenchmark,
    *,
    pair_concurrency: int,
) -> None:
    runners = {"baseline": baseline_runner, "experience": experience_runner}
    semaphore = asyncio.Semaphore(max(1, pair_concurrency))

    async def run_pair(item: PairedWorkItem) -> None:
        samples = {"baseline": item.baseline, "experience": item.experience}
        async with semaphore:
            for condition in item.order:
                sample = samples[condition]
                if sample is not None:
                    await runners[condition].rollout_sample(sample)

    tasks = [asyncio.create_task(run_pair(item)) for item in schedule]
    try:
        for task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Paired AB/BA rollout"):
            await task
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def run(args: argparse.Namespace) -> Path:
    baseline_config, experience_config = _load_configs(args)
    baseline_runner = BaseBenchmark(baseline_config)
    experience_runner = BaseBenchmark(experience_config)
    runners = (baseline_runner, experience_runner)

    existing_run_id = _existing_pair_run_id(runners)
    run_id = existing_run_id or (
        f"skillsbench_v4_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{args.seed}"
    )
    _stamp_pair_metadata(runners, run_id=run_id, seed=args.seed)

    # One adapter and one breaker means connection failures in either condition
    # pause scheduling for both conditions.
    experience_runner._skillsbench_adapter = baseline_runner._skillsbench_adapter
    experience_runner._skillsbench_circuit_breaker = baseline_runner._skillsbench_circuit_breaker

    endpoint = os.getenv("UTU_LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", ""))
    attempt_started_at = datetime.now(UTC).isoformat()
    previous_report = _read_report(run_id)
    attempts = list(previous_report.get("attempts") or [])
    attempts.append({"step": args.step, "started_at": attempt_started_at, "status": "RUNNING"})
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": previous_report.get("started_at", attempt_started_at),
        "attempts": attempts,
        "step": args.step,
        "seed": args.seed,
        "pair_concurrency": args.pair_concurrency,
        "dataset": baseline_config.data.dataset,
        "pass_k": baseline_config.pass_k,
        "requested_model": _model_name(baseline_config),
        "temperature": _temperature(baseline_config),
        "endpoint_fingerprint": hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:16],
        "baseline_exp_id": baseline_config.exp_id,
        "experience_exp_id": experience_config.exp_id,
        "baseline_config_fingerprint": baseline_runner._config_fingerprint,
        "experience_config_fingerprint": experience_runner._config_fingerprint,
        "baseline_prompt_fingerprint": baseline_runner._skillsbench_runtime_metadata()[
            "prompt_fingerprint"
        ],
        "experience_prompt_fingerprint": experience_runner._skillsbench_runtime_metadata()[
            "prompt_fingerprint"
        ],
        "status": "RUNNING",
    }
    output_path = _write_report(run_id, report)

    if args.step != "stat":
        await baseline_runner._apply_experience_filter()
        await experience_runner._apply_experience_filter()
        if args.step == "retry-infra":
            baseline_runner.reset_infra()
            experience_runner.reset_infra()

        baseline_runner.preprocess()
        experience_runner.preprocess()
        baseline_pending = baseline_runner.dataset.get_samples(stage="init")
        experience_pending = experience_runner.dataset.get_samples(stage="init")
        schedule = build_paired_schedule(
            baseline_pending,
            experience_pending,
            seed=args.seed,
        )
        report["scheduled_pairs_or_singles"] = len(schedule)
        report["baseline_pending_trials"] = len(baseline_pending)
        report["experience_pending_trials"] = len(experience_pending)
        _write_report(run_id, report)

        if schedule:
            await baseline_runner.ensure_skillsbench_health()
            experience_runner._skillsbench_healthchecked = True
            experience_runner._skillsbench_health_models = list(
                baseline_runner._skillsbench_health_models
            )
            await _run_schedule(
                schedule,
                baseline_runner,
                experience_runner,
                pair_concurrency=args.pair_concurrency,
            )

        await baseline_runner.judge(stage="rollout")
        await experience_runner.judge(stage="rollout")

    baseline_metrics = _metrics(await baseline_runner.stat())
    experience_metrics = _metrics(await experience_runner.stat())
    baseline_models = _observed_models(baseline_runner)
    experience_models = _observed_models(experience_runner)
    models_match = len(baseline_models) == 1 and baseline_models == experience_models
    publishable = bool(
        baseline_metrics.get("publishable")
        and experience_metrics.get("publishable")
        and models_match
    )
    report.update(
        finished_at=datetime.now(UTC).isoformat(),
        status="COMPLETE" if publishable else "INCOMPLETE",
        publishable=publishable,
        baseline_metrics=baseline_metrics,
        experience_metrics=experience_metrics,
        baseline_observed_models=baseline_models,
        experience_observed_models=experience_models,
        observed_models_match=models_match,
    )
    if publishable:
        report["pass_rate_delta"] = (
            experience_metrics["pass_rate"] - baseline_metrics["pass_rate"]
        )
    report["attempts"][-1].update(
        finished_at=report["finished_at"],
        status=report["status"],
    )
    output_path = _write_report(run_id, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Paired run report: {output_path}")
    if not publishable:
        raise IncompleteSkillsBenchComparison(
            "Comparison withheld: both conditions need 261/261 valid judged trials "
            "and matching observed model IDs. Run --step retry-infra after fixing infrastructure."
        )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-config", default=DEFAULT_BASELINE_CONFIG)
    parser.add_argument("--experience-config", default=DEFAULT_EXPERIENCE_CONFIG)
    parser.add_argument("--baseline-exp-id")
    parser.add_argument("--experience-exp-id")
    parser.add_argument("--agent-model", help="Pin the same model/version in both conditions")
    parser.add_argument("--pair-concurrency", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--step", choices=("run", "retry-infra", "stat"), default="run")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except FatalSkillsBenchError as exc:
        raise SystemExit(f"Fatal SkillsBench configuration error: {exc}") from None
    except IncompleteSkillsBenchComparison as exc:
        raise SystemExit(str(exc)) from None
