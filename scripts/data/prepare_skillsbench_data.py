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

from utu.db import DatasetSample, DBService
from utu.utils import SQLModelUtils, get_logger

logger = get_logger(__name__)

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


def _read_instruction(task_dir: Path) -> str:
    """Read instruction.md for the task."""
    instruction_path = task_dir / "instruction.md"
    if instruction_path.exists():
        return instruction_path.read_text(encoding="utf-8").strip()
    # Some tasks may use README.md as instruction
    readme_path = task_dir / "README.md"
    if readme_path.exists():
        return readme_path.read_text(encoding="utf-8").strip()
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


def parse_skillsbench_tasks(repo_path: Path, exclude_external_api: bool = True) -> list[dict]:
    """
    Parse all task folders inside <repo_path>/tasks/.

    Returns a list of dicts with keys:
        task_id, domain, difficulty, instruction, task_path, skills_dir, skills_text
    """
    tasks_dir = repo_path / "tasks"
    if not tasks_dir.exists():
        # Some repo layouts put tasks directly at the root
        tasks_dir = repo_path
        logger.warning(
            f"'tasks/' subdirectory not found under {repo_path}. "
            f"Scanning {repo_path} directly."
        )

    parsed = []
    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue

        task_id = task_dir.name

        if exclude_external_api and task_id in EXTERNAL_API_TASKS:
            logger.info(f"  Skipping external-API task: {task_id}")
            continue

        # Skip incomplete tasks that are missing required harbor files.
        # A valid task must have at minimum task.toml and instruction.md.
        toml_path = task_dir / "task.toml"
        if not toml_path.exists():
            logger.warning(f"  Skipping incomplete task (no task.toml): {task_id}")
            continue
        if not (task_dir / "instruction.md").exists() and not (task_dir / "README.md").exists():
            logger.warning(f"  Skipping incomplete task (no instruction): {task_id}")
            continue

        # Read task.toml metadata
        toml_data = _read_toml(toml_path)
        metadata = toml_data.get("metadata", {})
        task_section = toml_data.get("task", {})
        env_section = toml_data.get("environment", {})

        domain = metadata.get("category", metadata.get("domain", "general"))
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

        # Skills directory (if the task ships curated skills)
        skills_dir_name = env_section.get("skills_dir")
        skills_dir_path: Path | None = None
        if skills_dir_name:
            candidate = task_dir / skills_dir_name
            if candidate.exists():
                skills_dir_path = candidate
        # Also check top-level skills/ folder in the repo
        if skills_dir_path is None:
            top_skills = repo_path / "skills" / task_id
            if top_skills.exists():
                skills_dir_path = top_skills

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
                "description": task_section.get("description", ""),
            }
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
) -> None:
    """
    Parse SkillsBench tasks and write two DatasetSample collections to the DB.

    Args:
        repo_path: Local path to the cloned SkillsBench repository.
        eval_dataset_name: Name for the evaluation dataset.
        train_dataset_name: Name for the training dataset.
        train_ratio: Fraction of tasks to use for training (rest for eval).
        exclude_external_api: Whether to skip tasks that need external API keys.
        shuffle_seed: Random seed used to split train / eval.
    """
    if not repo_path.exists():
        logger.error(f"SkillsBench repo not found at: {repo_path}")
        logger.error(
            "Clone it first:\n"
            "  git clone https://github.com/benchflow-ai/SkillsBench ./SkillsBench-repo"
        )
        return

    tasks = parse_skillsbench_tasks(repo_path, exclude_external_api=exclude_external_api)
    if not tasks:
        logger.error("No tasks parsed. Check the repo_path structure.")
        return

    # Deterministic shuffle for reproducible train/eval split
    import random
    rng = random.Random(shuffle_seed)
    shuffled = tasks[:]
    rng.shuffle(shuffled)

    n_train = max(1, int(len(shuffled) * train_ratio))
    train_tasks = shuffled[:n_train]
    eval_tasks = shuffled[n_train:]

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
            },
        )

    eval_samples = [_make_sample(t, eval_dataset_name, "eval") for t in eval_tasks]
    train_samples = [_make_sample(t, train_dataset_name, "train") for t in train_tasks]

    if not SQLModelUtils.check_db_available():
        logger.error("Database is not available. Please check your UTU_DB_URL environment variable.")
        return

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
    logger.info(f"  Train → {train_dataset_name} ({len(train_samples)} tasks)")


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
        "--shuffle_seed",
        type=int,
        default=42,
        help="Random seed for train/eval split (default: 42)",
    )

    args = parser.parse_args()

    create_skillsbench_datasets(
        repo_path=Path(args.repo_path),
        eval_dataset_name=args.eval_dataset_name,
        train_dataset_name=args.train_dataset_name,
        train_ratio=args.train_ratio,
        exclude_external_api=not args.include_external_api,
        shuffle_seed=args.shuffle_seed,
    )
