"""
Prepare LiveCodeBench datasets for training and evaluation.

Downloads livecodebench/code_generation_lite from HuggingFace and writes
DatasetSample records into the project database.

Train split  : 30 problems  (medium difficulty preferred, earlier contests)
Eval  split  : 50 problems  (balanced difficulty, later contests to avoid leakage)

Usage:
    uv run python scripts/data/prepare_livecodebench_data.py
    uv run python scripts/data/prepare_livecodebench_data.py \\
        --version_tag release_v5 \\
        --train_count 30 --eval_count 50
"""
from __future__ import annotations

import json
import random
import sys
import traceback
from collections import Counter
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utu.db import DatasetSample, DBService
from utu.utils import SQLModelUtils, get_logger

logger = get_logger(__name__)


def _log(msg: str) -> None:
    """Print to stdout immediately (bypasses logger level filtering)."""
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Field normalisation helpers
# ---------------------------------------------------------------------------

def _to_json_str(value) -> str:
    """Convert any value to a JSON string (for storing test cases in meta)."""
    if value is None:
        return "[]"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return "[]"


def _count_public_tests(row: dict) -> int:
    """Return number of public test cases available."""
    raw = row.get("public_test_cases")
    if raw is None:
        return 0
    try:
        if isinstance(raw, str):
            tests = json.loads(raw)
        else:
            tests = raw  # already a list
        return len(tests) if isinstance(tests, list) else 0
    except Exception:
        return 0


def _format_question(row: dict) -> str:
    """Build the prompt shown to the agent."""
    title   = (row.get("question_title") or "").strip()
    content = (row.get("question_content") or "").strip()
    starter = (row.get("starter_code") or "").strip()

    parts = []
    if title:
        parts.append(f"## {title}\n")
    if content:
        parts.append(content)
    if starter:
        parts.append(f"\n\n### Starter Code\n```python\n{starter}\n```")
    parts.append(
        "\n\nWrite a complete Python solution. "
        "Wrap your final code in a ```python ... ``` block."
    )
    return "\n".join(parts)


def _extract_func_name(row: dict) -> str:
    """Extract function/method name from LeetCode-style metadata."""
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            return ""
    if isinstance(meta, dict):
        return meta.get("func_name") or meta.get("function_name") or ""
    return ""


def _row_to_dict(row) -> dict:
    """Safely convert a HuggingFace dataset row to a plain dict."""
    try:
        return dict(row)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Split logic
# ---------------------------------------------------------------------------

def _split_problems(
    problems: list[dict],
    train_count: int,
    eval_count: int,
    seed: int,
) -> tuple[list[dict], list[dict]]:
    """
    Split problems into train and eval sets.

    - Eval  : newest eval_count problems (by contest_date) → reduces contamination
    - Train : sample from the remainder, preferring 'medium' difficulty
    """
    total_needed = train_count + eval_count
    if len(problems) < total_needed:
        logger.warning(
            f"Only {len(problems)} problems available; requested {total_needed}. "
            "Adjusting counts."
        )
        eval_count  = min(eval_count,  len(problems) * 2 // 3)
        train_count = min(train_count, len(problems) - eval_count)

    sorted_probs = sorted(
        problems,
        key=lambda r: str(r.get("contest_date") or ""),
    )

    eval_probs = sorted_probs[-eval_count:]
    remaining  = sorted_probs[: len(sorted_probs) - eval_count]

    rng    = random.Random(seed)
    medium = [p for p in remaining if str(p.get("difficulty") or "").lower() == "medium"]
    others = [p for p in remaining if p not in medium]

    if len(medium) >= train_count:
        train_probs = rng.sample(medium, train_count)
    else:
        extra       = rng.sample(others, min(train_count - len(medium), len(others)))
        train_probs = medium + extra
        rng.shuffle(train_probs)

    print(
        f"  Split → train={len(train_probs)} eval={len(eval_probs)} "
        f"(medium in train: "
        f"{sum(1 for p in train_probs if str(p.get('difficulty') or '').lower() == 'medium')})",
        flush=True,
    )
    return train_probs, eval_probs


# ---------------------------------------------------------------------------
# Sample construction
# ---------------------------------------------------------------------------

def _make_sample(row: dict, dataset_name: str, dataset_type: str) -> DatasetSample:
    return DatasetSample(
        dataset=dataset_name,
        source="LiveCodeBench",
        index=str(row.get("question_id") or ""),
        question=_format_question(row),
        answer="pass_all_tests",
        level=str(row.get("difficulty") or "medium").lower(),
        meta={
            "question_id":       str(row.get("question_id") or ""),
            "question_title":    str(row.get("question_title") or ""),
            "platform":          str(row.get("platform") or "").lower(),
            "difficulty":        str(row.get("difficulty") or "medium").lower(),
            "contest_id":        str(row.get("contest_id") or ""),
            "contest_date":      str(row.get("contest_date") or ""),
            "starter_code":      (row.get("starter_code") or "").strip(),
            "func_name":         _extract_func_name(row),
            "public_test_cases":  _to_json_str(row.get("public_test_cases")),
            "private_test_cases": _to_json_str(row.get("private_test_cases")),
            "dataset_type":      dataset_type,
        },
    )


# ---------------------------------------------------------------------------
# DB upload
# ---------------------------------------------------------------------------

def _upload_deduped(samples: list[DatasetSample], dataset_name: str) -> int:
    from sqlmodel import select as _select
    with SQLModelUtils.create_session() as session:
        existing = session.exec(
            _select(DatasetSample).where(DatasetSample.dataset == dataset_name)
        ).all()
    existing_ids = {
        (r.meta or {}).get("question_id") or r.index for r in existing
    }
    new = [
        s for s in samples
        if ((s.meta or {}).get("question_id") or s.index) not in existing_ids
    ]
    skipped = len(samples) - len(new)
    if skipped:
        print(f"  Skipping {skipped} already-present problems in '{dataset_name}'.", flush=True)
    if new:
        DBService.add(new)
    return len(new)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def prepare_livecodebench_data(
    version_tag: str = "release_v5",
    train_dataset_name: str = "LiveCodeBench-Train-30",
    eval_dataset_name:  str = "LiveCodeBench-Eval-50",
    train_count: int = 30,
    eval_count:  int = 50,
    seed: int = 42,
    min_public_tests: int = 1,
) -> None:
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        print("ERROR: Package 'datasets' not found. Install with:\n  uv pip install datasets", flush=True)
        sys.exit(1)

    # --- 1. Download ---
    _log(f"\n[1/6] Loading LiveCodeBench ({version_tag}) from HuggingFace …")
    try:
        raw = load_dataset(
            "livecodebench/code_generation_lite",
            version_tag=version_tag,
            trust_remote_code=True,
        )
        print(f"[DEBUG] load_dataset returned: type={type(raw)}", flush=True)
    except BaseException as exc:
        print(f"\nERROR: Failed to load dataset ({type(exc).__name__}): {exc}", flush=True)
        traceback.print_exc()
        print(
            "Tips:\n"
            "  • Install datasets: uv pip install datasets\n"
            "  • HuggingFace blocked? Try: export HF_ENDPOINT=https://hf-mirror.com\n"
            "  • Try a smaller version: --version_tag v4_v5",
            flush=True,
        )
        sys.exit(1)

    # --- 2. Resolve split ---
    _log("[2/6] Resolving split …")
    if hasattr(raw, "keys"):
        splits = list(raw.keys())
        _log(f"  Available splits: {splits}")
        split_name = "test" if "test" in splits else splits[0]
        ds = raw[split_name]
    else:
        split_name = "default"
        ds = raw
    _log(f"  Using split '{split_name}' with {len(ds)} problems")

    # --- 3. Convert to plain dicts ---
    _log("[3/6] Converting dataset rows …")
    try:
        problems_raw = [_row_to_dict(row) for row in ds]
    except Exception as exc:
        print(f"\nERROR: Failed to iterate dataset: {exc}", flush=True)
        traceback.print_exc()
        sys.exit(1)

    _log(f"  Converted {len(problems_raw)} rows")
    if problems_raw:
        _log(f"  Fields: {sorted(problems_raw[0].keys())}")

    # --- 4. Filter ---
    _log(f"[4/6] Filtering (min_public_tests={min_public_tests}) …")
    problems = [r for r in problems_raw if _count_public_tests(r) >= min_public_tests]
    _log(f"  {len(problems)} problems pass the filter")
    if not problems:
        print("ERROR: No usable problems after filtering.", flush=True)
        sys.exit(1)

    diff_dist     = Counter(str(r.get("difficulty") or "?").lower() for r in problems)
    platform_dist = Counter(str(r.get("platform")   or "?").lower() for r in problems)
    _log(f"  Difficulty : {dict(diff_dist)}")
    _log(f"  Platform   : {dict(platform_dist)}")

    # --- 5. Split ---
    _log(f"[5/6] Splitting into train={train_count} / eval={eval_count} …")
    train_probs, eval_probs = _split_problems(problems, train_count, eval_count, seed)

    train_samples = [_make_sample(r, train_dataset_name, "train") for r in train_probs]
    eval_samples  = [_make_sample(r, eval_dataset_name,  "eval")  for r in eval_probs]

    t_diff = Counter(str(r.get("difficulty") or "?").lower() for r in train_probs)
    e_diff = Counter(str(r.get("difficulty") or "?").lower() for r in eval_probs)
    _log(f"  Train difficulty : {dict(t_diff)}")
    _log(f"  Eval  difficulty : {dict(e_diff)}")

    # --- 6. DB upload ---
    _log("[6/6] Uploading to database …")
    if not SQLModelUtils.check_db_available():
        print("ERROR: Database unavailable. Check UTU_DB_URL in .env", flush=True)
        sys.exit(1)

    n_train = _upload_deduped(train_samples, train_dataset_name)
    _log(f"  ✓ {train_dataset_name}: {n_train} new problems written")

    n_eval = _upload_deduped(eval_samples, eval_dataset_name)
    _log(f"  ✓ {eval_dataset_name}: {n_eval} new problems written")

    _log("\n✅ Done!")
    _log(f"  Train → {train_dataset_name}  ({len(train_samples)} problems)")
    _log(f"  Eval  → {eval_dataset_name}   ({len(eval_samples)} problems)")
    _log("\nNext steps:")
    _log("  uv run python scripts/run_eval.py --config_name livecodebench/lcb_baseline_eval")
    _log("  uv run python scripts/run_training_free_GRPO.py --config_name livecodebench/lcb_practice")
    _log("  uv run python scripts/run_eval.py --config_name livecodebench/lcb_practice_eval")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare LiveCodeBench datasets")
    parser.add_argument("--version_tag",        default="release_v5",
                        help="HF dataset version tag (default: release_v5, 880 problems)")
    parser.add_argument("--train_dataset_name", default="LiveCodeBench-Train-30")
    parser.add_argument("--eval_dataset_name",  default="LiveCodeBench-Eval-50")
    parser.add_argument("--train_count",        type=int, default=30)
    parser.add_argument("--eval_count",         type=int, default=50)
    parser.add_argument("--seed",               type=int, default=42)
    parser.add_argument("--min_public_tests",   type=int, default=1,
                        help="Skip problems with fewer public test cases (default: 1)")
    args = parser.parse_args()

    try:
        prepare_livecodebench_data(
            version_tag=args.version_tag,
            train_dataset_name=args.train_dataset_name,
            eval_dataset_name=args.eval_dataset_name,
            train_count=args.train_count,
            eval_count=args.eval_count,
            seed=args.seed,
            min_public_tests=args.min_public_tests,
        )
    except BaseException as exc:
        print(f"\nFATAL ERROR ({type(exc).__name__}): {exc}", flush=True)
        traceback.print_exc()
        sys.exit(1)
