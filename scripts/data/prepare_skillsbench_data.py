"""
Prepare SkillsBench datasets for training and evaluation.

This script parses a locally cloned SkillsBench repository and writes
DatasetSample records into the project database.

Each task folder has the structure:
    tasks/<task-id>/
        instruction.md      # task description shown to the agent
        task.toml           # metadata: domain, difficulty, skills_dir, etc.
        environment/        # Dockerfile (used by harbor)
        tests/test.sh       # deterministic verifier

Usage:
    uv run python scripts/data/prepare_skillsbench_data.py \\
        --repo_path ./SkillsBench-repo \\
        [--eval_dataset_name SkillsBench-Eval-77] \\
        [--train_dataset_name SkillsBench-Train-40] \\
        [--train_ratio 0.5]
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # fallback
    except ImportError:
        tomllib = None

try:
    import yaml
except ImportError:
    yaml = None

from utu.db import DatasetSample, DBService  # noqa: E402
from utu.skillsbench_data import assert_task_ids_disjoint, load_task_split_manifest  # noqa: E402
from utu.utils import SQLModelUtils, get_logger  # noqa: E402

logger = get_logger(__name__)

PAPER_87_MANIFEST = project_root / "configs" / "eval" / "skillsbench" / "skillsbench_paper_87_tasks.tsv"

# Tasks that require external API keys are excluded from the self-contained subset.
# This list mirrors the exclusion list referenced on skillsbench.ai (86 - 9 = 77).
EXTERNAL_API_TASKS = {
    "enterprise-information-search",
    "citation-check",
    "azure-bgp-oscillation-route-leak",
    "energy-market-pricing",
    "energy-ac-optimal-power-flow",
    "earthquake-phase-association",
    "dapt-intrusion-detection",
    "dynamic-object-aware-egomotion",
    "exoplanet-detection-period",
}

# Tasks whose Docker environment effectively never gives the agent a fair, scored
# attempt in this setup, so they ALWAYS yield reward=0 regardless of agent
# capability. Keeping them in the TRAINING set poisons Training-Free GRPO: every
# rollout in their group fails for infrastructure reasons, giving zero reward
# variance and therefore zero learning signal, while still burning hours of
# wall-clock time.
#
# These were chosen EMPIRICALLY from the training log: each one has 0 passes and
# is dominated by docker compose build/up failures, "no container for service
# main", missing external-service env vars (CLAUDE_CODE_* / GOOGLE_AUTH_*), or
# never producing a verifier reward file.
#
# IMPORTANT: tasks that occasionally pass (hvac-control, flood-risk-analysis,
# gravitational-wave-detection, grid-dispatch-operator, travel-planning,
# fix-druid-loophole-cve, offer-letter-generator) are deliberately NOT here —
# they produce reward variance and are exactly the signal GRPO needs, even if
# their environments are flaky.
BROKEN_ENV_TASKS = {
    "scheduling-email-assistant",    # 0 pass; 30 infra fails (needs external API creds)
    "multilingual-video-dubbing",    # 0 pass; 45 infra fails (build never succeeds)
    "speaker-diarization-subtitles", # 0 pass; 15 infra fails (build never succeeds)
    "video-tutorial-indexer",        # 0 pass; build fails + wall-clock timeout
    "pg-essay-to-audiobook",         # 0 pass; never produces a verifier reward file
    "flink-query",                   # 0 pass; container never becomes healthy (up --wait)
    "suricata-custom-exfil",         # 0 pass; dominated by build failures
    "parallel-tfidf-search",         # 0 pass; task.toml name field fails harbor TaskConfig
                                     # validation ("Parallel TF-IDF Similarity Search" is
                                     # not a valid 'org/name' slug); fails before any agent
                                     # step, every retry, every run.
}

# Tasks that are NOT environment-broken but never finish a scored attempt because
# they need far more than the configured wall-clock timeout. Excluded from
# TRAINING by default, but kept separate so they can be re-enabled by raising
# `task_timeout_sec` instead.
UNSCORABLE_OR_SLOW_TASKS = {
    "simpo-code-reproduction",       # 0 pass; every attempt hits the 900s timeout
}


def _read_toml(path: Path) -> dict:
    """Read a TOML file and return its contents as a dict."""
    if not path.exists():
        return {}
    if tomllib is None:
        logger.warning(
            "tomllib / tomli not available. Install tomli via `pip install tomli` "
            "for Python < 3.11. Returning empty metadata."
        )
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _read_task_md(path: Path) -> tuple[dict, str]:
    """Read a SkillsBench v1.x task.md with optional YAML frontmatter."""
    if not path.exists():
        return {}, ""

    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    frontmatter = parts[1].strip()
    body = parts[2].strip()
    if yaml is None:
        logger.warning("PyYAML not available; task.md metadata will be empty.")
        return {}, body

    try:
        data = yaml.safe_load(frontmatter) or {}
        return data, body
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to parse task.md frontmatter at {path}: {exc}")
        return {}, body


def _read_instruction(task_dir: Path) -> str:
    """Read instruction.md for the task."""
    instruction_path = task_dir / "instruction.md"
    if instruction_path.exists():
        return instruction_path.read_text(encoding="utf-8").strip()
    # Some tasks may use README.md as instruction
    readme_path = task_dir / "README.md"
    if readme_path.exists():
        return readme_path.read_text(encoding="utf-8").strip()
    task_md_path = task_dir / "task.md"
    if task_md_path.exists():
        _, body = _read_task_md(task_md_path)
        return body
    return f"Complete the task in directory: {task_dir.name}"


def _collect_skills_text(skills_dir: Path) -> str:
    """Collect all text from a skills directory (markdown / text files)."""
    if not skills_dir or not skills_dir.exists():
        return ""
    texts = []
    for md_file in sorted(skills_dir.rglob("*.md")):
        texts.append(f"## {md_file.stem}\n{md_file.read_text(encoding='utf-8', errors='replace')}")
    for txt_file in sorted(skills_dir.rglob("*.txt")):
        texts.append(txt_file.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(texts)


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _load_task_manifest(path: Path | None) -> dict[str, dict]:
    """Load an optional paper-alignment manifest keyed by task_id."""
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Task manifest not found: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return {}
    header = [h.strip() for h in lines[0].split("\t")]
    required = {"task_id", "domain", "capability", "diff"}
    missing = required - set(header)
    if missing:
        raise ValueError(f"Manifest {path} is missing columns: {sorted(missing)}")

    manifest: dict[str, dict] = {}
    for lineno, line in enumerate(lines[1:], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != len(header):
            raise ValueError(f"Malformed manifest row {lineno} in {path}: {line}")
        row = dict(zip(header, (p.strip() for p in parts), strict=True))
        task_id = row["task_id"]
        if task_id in manifest:
            raise ValueError(f"Duplicate task_id in manifest {path}: {task_id}")
        manifest[task_id] = row
    return manifest


def parse_skillsbench_tasks(
    repo_path: Path,
    exclude_external_api: bool = True,
    task_manifest: Path | None = None,
    allow_missing_manifest_tasks: bool = False,
) -> list[dict]:
    """
    Parse all task folders inside <repo_path>/tasks/.

    Returns a list of dicts with keys:
        task_id, domain, difficulty, instruction, task_path, skills_dir, skills_text
    """
    manifest = _load_task_manifest(task_manifest)

    tasks_dir = repo_path / "tasks"
    if not tasks_dir.exists():
        # Some repo layouts put tasks directly at the root
        tasks_dir = repo_path
        logger.warning(
            f"'tasks/' subdirectory not found under {repo_path}. "
            f"Scanning {repo_path} directly."
        )

    parsed = []
    seen_manifest_tasks: set[str] = set()
    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue

        task_id = task_dir.name
        manifest_row = manifest.get(task_id)
        if manifest and manifest_row is None:
            continue
        if manifest_row is not None:
            seen_manifest_tasks.add(task_id)

        if exclude_external_api and task_id in EXTERNAL_API_TASKS:
            logger.info(f"  Skipping external-API task: {task_id}")
            continue

        # Skip incomplete tasks that are missing required harbor files.
        # Supported layouts:
        #   old: task.toml + instruction.md + environment/ + tests/
        #   new: task.md + environment/ + verifier/
        toml_path = task_dir / "task.toml"
        task_md_path = task_dir / "task.md"
        if not toml_path.exists() and not task_md_path.exists():
            logger.warning(f"  Skipping incomplete task (no task.toml/task.md): {task_id}")
            continue
        if not (
            (task_dir / "instruction.md").exists()
            or (task_dir / "README.md").exists()
            or task_md_path.exists()
        ):
            logger.warning(f"  Skipping incomplete task (no instruction/task.md): {task_id}")
            continue

        # Read metadata from either legacy task.toml or paper-release task.md.
        toml_data = _read_toml(toml_path)
        task_md_data, _ = _read_task_md(task_md_path)
        task_data = toml_data or task_md_data
        metadata = task_data.get("metadata", {})
        task_section = task_data.get("task", {})
        env_section = task_data.get("environment", {})

        domain = (
            manifest_row.get("domain")
            if manifest_row is not None
            else metadata.get("category", metadata.get("domain", "general"))
        )
        difficulty_raw = metadata.get("difficulty", metadata.get("difficulty_explanation", "medium"))
        # Normalise difficulty to easy / medium / hard
        difficulty = "medium"
        for level in ("easy", "hard"):
            if level in str(difficulty_raw).lower():
                difficulty = level
                break
        else:
            if "medium" in str(difficulty_raw).lower():
                difficulty = "medium"

        instruction = _read_instruction(task_dir)
        task_types = _string_list(metadata.get("task_type"))
        required_tools = _string_list(metadata.get("interface"))
        required_capabilities = _string_list(metadata.get("skill_type"))
        if manifest_row is not None and manifest_row.get("capability"):
            required_capabilities = sorted(
                set(required_capabilities) | {manifest_row["capability"]}
            )

        # Skills directory (if the task ships curated skills)
        skills_dir_name = env_section.get("skills_dir")
        skills_dir_path: Path | None = None
        if skills_dir_name:
            candidate = task_dir / skills_dir_name
            if candidate.exists():
                skills_dir_path = candidate
        # Paper release layout: task/environment/skills/<skill>/SKILL.md
        if skills_dir_path is None:
            candidate = task_dir / "environment" / "skills"
            if candidate.exists():
                skills_dir_path = candidate
        # Also check top-level skills/ folder in the repo
        if skills_dir_path is None:
            top_skills = repo_path / "skills" / task_id
            if top_skills.exists():
                skills_dir_path = top_skills
        if skills_dir_path is None:
            candidate = task_dir / "skills"
            if candidate.exists():
                skills_dir_path = candidate

        skills_text = _collect_skills_text(skills_dir_path)

        parsed.append(
            {
                "task_id": task_id,
                "domain": domain,
                "difficulty": difficulty,
                "instruction": instruction,
                "task_path": str(task_dir.resolve()),
                "skills_dir": str(skills_dir_path.resolve()) if skills_dir_path else "",
                "skills_text": skills_text,
                "description": task_section.get("description", metadata.get("subcategory", "")),
                "task_family": task_types[0] if task_types else "unknown",
                "all_task_types": task_types,
                "required_tools": required_tools,
                "required_capabilities": required_capabilities,
                "paper_domain": manifest_row.get("domain") if manifest_row is not None else "",
                "paper_capability": manifest_row.get("capability") if manifest_row is not None else "",
                "paper_diff": manifest_row.get("diff") if manifest_row is not None else "",
            }
        )

    if manifest:
        missing = sorted(set(manifest) - seen_manifest_tasks)
        if missing and not allow_missing_manifest_tasks:
            raise ValueError(
                f"SkillsBench repo at {repo_path} is missing {len(missing)} manifest task(s): "
                + ", ".join(missing)
                + ". Update SkillsBench-repo to the paper-aligned revision, or pass "
                "--allow_missing_manifest_tasks for a non-paper-complete dry run."
            )
        if missing:
            logger.warning(
                f"Proceeding with {len(missing)} missing manifest task(s): "
                + ", ".join(missing)
            )

    logger.info(f"Parsed {len(parsed)} SkillsBench tasks from {repo_path}")
    return parsed


def create_skillsbench_datasets(
    repo_path: Path,
    eval_dataset_name: str = "SkillsBench-Eval-77",
    train_dataset_name: str = "SkillsBench-Train-40",
    train_ratio: float = 0.5,
    exclude_external_api: bool = True,
    shuffle_seed: int = 42,
    exclude_broken_from_train: bool = True,
    task_manifest: Path | None = None,
    eval_only: bool = False,
    allow_missing_manifest_tasks: bool = False,
    split_manifest_path: Path | None = None,
    split_name: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict | None:
    """
    Parse SkillsBench tasks and write two DatasetSample collections to the DB.

    Args:
        repo_path: Local path to the cloned SkillsBench repository.
        eval_dataset_name: Name for the evaluation dataset.
        train_dataset_name: Name for the training dataset.
        train_ratio: Fraction of tasks to use for training (rest for eval).
        exclude_external_api: Whether to skip tasks that need external API keys.
        shuffle_seed: Random seed used to split train / eval.
        exclude_broken_from_train: Drop BROKEN_ENV_TASKS / UNSCORABLE_OR_SLOW_TASKS
            from the TRAIN split only. This keeps the eval split (and the shuffle
            pool) byte-for-byte identical to previous runs, so prior eval results
            stay comparable, while removing tasks that can never produce a GRPO
            learning signal from training.
        dry_run: Validate and return the exact task lists without a database write.
        force: If True, delete any existing rows of the target datasets before
            re-inserting (otherwise existing task_ids are skipped / de-duped).
    """
    if not repo_path.exists():
        logger.error(f"SkillsBench repo not found at: {repo_path}")
        logger.error(
            "Clone it first:\n"
            "  git clone https://github.com/benchflow-ai/SkillsBench ./SkillsBench-repo"
        )
        return

    tasks = parse_skillsbench_tasks(
        repo_path,
        exclude_external_api=exclude_external_api,
        task_manifest=task_manifest,
        allow_missing_manifest_tasks=allow_missing_manifest_tasks,
    )
    if not tasks:
        logger.error("No tasks parsed. Check the repo_path structure.")
        return

    split_metadata: dict = {}
    if split_manifest_path or split_name:
        if not split_manifest_path or not split_name:
            raise ValueError("Both split_manifest_path and split_name are required")
        split_manifest = load_task_split_manifest(split_manifest_path)
        try:
            split = split_manifest["splits"][split_name]
        except KeyError as error:
            raise ValueError(f"Unknown split {split_name!r} in {split_manifest_path}") from error
        train_ids = list(split["train_task_ids"])
        eval_ids = list(split["eval_task_ids"])
        assert_task_ids_disjoint(train_ids, eval_ids)
        by_id = {task["task_id"]: task for task in tasks}
        missing = sorted((set(train_ids) | set(eval_ids)) - set(by_id))
        if missing:
            raise ValueError(f"Split {split_name!r} references missing tasks: {missing}")
        train_tasks = [by_id[task_id] for task_id in train_ids]
        eval_tasks = [by_id[task_id] for task_id in eval_ids]
        dataset_metadata = split_manifest["dataset"]
        split_metadata = {
            "dataset_version": dataset_metadata["version"],
            "repository_commit": dataset_metadata["repository_commit"],
            "inventory_sha256": dataset_metadata["inventory_sha256"],
            "manifest_sha256": split_manifest["manifest_sha256"],
            "split_name": split_name,
            "split_sha256": split["split_sha256"],
            "train_task_ids_sha256": split["train_task_ids_sha256"],
            "eval_task_ids_sha256": split["eval_task_ids_sha256"],
        }
    elif eval_only:
        # Paper-aligned evaluation uses the fixed manifest order and no train split.
        train_tasks = []
        eval_tasks = tasks
    else:
        # Deterministic shuffle for reproducible train/eval split
        import random
        rng = random.Random(shuffle_seed)
        shuffled = tasks[:]
        rng.shuffle(shuffled)

        n_train = max(1, int(len(shuffled) * train_ratio))
        train_tasks = shuffled[:n_train]
        eval_tasks = shuffled[n_train:]

    # Remove environment-broken / unscorable tasks from TRAINING only.
    # We intentionally filter *after* the split so the eval membership and the
    # shuffle pool are unchanged (prior eval numbers stay comparable).
    if exclude_broken_from_train and not split_metadata:
        broken = BROKEN_ENV_TASKS | UNSCORABLE_OR_SLOW_TASKS
        dropped = [t["task_id"] for t in train_tasks if t["task_id"] in broken]
        train_tasks = [t for t in train_tasks if t["task_id"] not in broken]
        if dropped:
            logger.warning(
                f"Dropped {len(dropped)} broken/unscorable task(s) from the "
                f"training split (they always score 0 → no GRPO signal): "
                + ", ".join(sorted(dropped))
            )

    def _make_sample(task: dict, dataset_name: str, dataset_type: str) -> DatasetSample:
        return DatasetSample(
            dataset=dataset_name,
            source="SkillsBench",
            index=task["task_id"],
            question=task["instruction"],
            answer="",  # No text answer; reward comes from harbor verifier
            level=task["difficulty"],
            meta={
                "task_id": task["task_id"],
                "domain": task["domain"],
                "difficulty": task["difficulty"],
                "task_path": task["task_path"],
                "skills_dir": task["skills_dir"],
                "skills_text": task["skills_text"],
                "description": task["description"],
                "dataset_type": dataset_type,
                "paper_domain": task.get("paper_domain", ""),
                "paper_capability": task.get("paper_capability", ""),
                "paper_diff": task.get("paper_diff", ""),
                "task_family": task["task_family"],
                "all_task_types": task["all_task_types"],
                "required_tools": task["required_tools"],
                "required_capabilities": task["required_capabilities"],
                **split_metadata,
            },
        )

    eval_samples = [_make_sample(t, eval_dataset_name, "eval") for t in eval_tasks]
    train_samples = [_make_sample(t, train_dataset_name, "train") for t in train_tasks]

    preparation_report = {
        "dry_run": dry_run,
        "train_dataset_name": train_dataset_name,
        "eval_dataset_name": eval_dataset_name,
        "train_task_ids": [task["task_id"] for task in train_tasks],
        "eval_task_ids": [task["task_id"] for task in eval_tasks],
        "split_metadata": split_metadata,
    }
    assert_task_ids_disjoint(
        preparation_report["train_task_ids"], preparation_report["eval_task_ids"]
    )
    if dry_run:
        logger.info("SkillsBench dataset dry run (database unchanged): %s", preparation_report)
        return preparation_report

    if not SQLModelUtils.check_db_available():
        logger.error("Database is not available. Please check your UTU_DB_URL environment variable.")
        return

    def _delete_dataset(dataset_name: str) -> int:
        """Delete all rows of a dataset so it can be rebuilt from scratch."""
        from sqlmodel import select as _select
        with SQLModelUtils.create_session() as session:
            rows = session.exec(
                _select(DatasetSample).where(DatasetSample.dataset == dataset_name)
            ).all()
            for r in rows:
                session.delete(r)
            session.commit()
        return len(rows)

    if force:
        datasets_to_delete = [eval_dataset_name] if eval_only else [eval_dataset_name, train_dataset_name]
        for ds in datasets_to_delete:
            n_deleted = _delete_dataset(ds)
            logger.warning(f"--force: deleted {n_deleted} existing rows from '{ds}'.")

    def _upload_deduped(samples: list[DatasetSample], dataset_name: str) -> int:
        """Insert samples, skipping any task_id already present in this dataset."""
        from sqlmodel import select as _select
        with SQLModelUtils.create_session() as session:
            existing = session.exec(
                _select(DatasetSample).where(DatasetSample.dataset == dataset_name)
            ).all()
        existing_ids = {
            (r.meta or {}).get("task_id") or r.index
            for r in existing
        }
        new_samples = [
            s for s in samples
            if ((s.meta or {}).get("task_id") or s.index) not in existing_ids
        ]
        skipped = len(samples) - len(new_samples)
        if skipped:
            logger.warning(
                f"  Skipping {skipped} tasks already in '{dataset_name}' "
                "(re-run with --force to overwrite)."
            )
        if new_samples:
            DBService.add(new_samples)
        return len(new_samples)

    logger.info(f"\nUploading evaluation samples → '{eval_dataset_name}' ...")
    n = _upload_deduped(eval_samples, eval_dataset_name)
    logger.info(f"✓ Evaluation dataset updated: {eval_dataset_name} ({n} new tasks added)")

    if not eval_only:
        logger.info(f"\nUploading training samples → '{train_dataset_name}' ...")
        n = _upload_deduped(train_samples, train_dataset_name)
        logger.info(f"✓ Training dataset updated: {train_dataset_name} ({n} new tasks added)")

    # Print domain breakdown
    from collections import Counter
    eval_domains = Counter(t["domain"] for t in eval_tasks)
    logger.info("\n📊 Evaluation dataset domain breakdown:")
    for domain, count in sorted(eval_domains.items(), key=lambda x: -x[1]):
        logger.info(f"  {domain}: {count}")

    logger.info("\n✅ SkillsBench datasets created successfully!")
    logger.info(f"  Eval  → {eval_dataset_name}  ({len(eval_samples)} tasks)")
    if not eval_only:
        logger.info(f"  Train → {train_dataset_name} ({len(train_samples)} tasks)")
    return preparation_report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare SkillsBench datasets")
    parser.add_argument(
        "--repo_path",
        type=str,
        default="./SkillsBench-repo",
        help="Path to the locally cloned SkillsBench repository",
    )
    parser.add_argument(
        "--eval_dataset_name",
        type=str,
        default="SkillsBench-Eval-77",
        help="Name for the evaluation dataset",
    )
    parser.add_argument(
        "--train_dataset_name",
        type=str,
        default="SkillsBench-Train-40",
        help="Name for the training dataset",
    )
    parser.add_argument(
        "--train_ratio",
        type=float,
        default=0.5,
        help="Fraction of tasks allocated to training (default: 0.5)",
    )
    parser.add_argument(
        "--include_external_api",
        action="store_true",
        help="Include tasks that require external API keys (excluded by default)",
    )
    parser.add_argument(
        "--paper_87",
        action="store_true",
        help="Use the paper Table 19 87-task manifest, include external-API tasks, "
             "and create an eval-only dataset named SkillsBench-Paper-87 unless overridden.",
    )
    parser.add_argument(
        "--task_manifest",
        type=str,
        default=None,
        help="Optional TSV manifest with task_id/domain/capability/diff columns.",
    )
    parser.add_argument(
        "--eval_only",
        action="store_true",
        help="Create only the eval dataset from the parsed tasks; do not create a train split.",
    )
    parser.add_argument(
        "--allow_missing_manifest_tasks",
        action="store_true",
        help="Allow a manifest-backed run to proceed even if the local SkillsBench repo "
             "is missing some manifest tasks. This is useful only for dry runs, not paper alignment.",
    )
    parser.add_argument(
        "--include_broken",
        action="store_true",
        help="Keep environment-broken / unscorable tasks in the training split "
             "(excluded by default; they always score 0 and give no GRPO signal)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing rows of the target datasets before re-inserting "
             "(use this to rebuild the training set after editing exclusion lists)",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Validate and print exact task lists without writing to the database.",
    )
    parser.add_argument(
        "--split_manifest",
        type=str,
        default=None,
        help="Versioned JSON task inventory/split manifest.",
    )
    parser.add_argument(
        "--split_name",
        type=str,
        default=None,
        help="Exact split key to materialize from --split_manifest.",
    )
    parser.add_argument(
        "--shuffle_seed",
        type=int,
        default=42,
        help="Random seed for train/eval split (default: 42)",
    )

    args = parser.parse_args()
    if args.paper_87:
        if args.eval_dataset_name == "SkillsBench-Eval-77":
            args.eval_dataset_name = "SkillsBench-Paper-87"
        args.task_manifest = args.task_manifest or str(PAPER_87_MANIFEST)
        args.eval_only = True
        args.include_external_api = True

    report = create_skillsbench_datasets(
        repo_path=Path(args.repo_path),
        eval_dataset_name=args.eval_dataset_name,
        train_dataset_name=args.train_dataset_name,
        train_ratio=args.train_ratio,
        exclude_external_api=not args.include_external_api,
        shuffle_seed=args.shuffle_seed,
        exclude_broken_from_train=not args.include_broken,
        task_manifest=Path(args.task_manifest) if args.task_manifest else None,
        eval_only=args.eval_only,
        allow_missing_manifest_tasks=args.allow_missing_manifest_tasks,
        split_manifest_path=Path(args.split_manifest) if args.split_manifest else None,
        split_name=args.split_name,
        dry_run=args.dry_run,
        force=args.force,
    )
    if args.dry_run and report is not None:
        print(json.dumps(report, ensure_ascii=False, indent=2))
