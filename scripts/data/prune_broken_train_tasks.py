"""
Surgically remove environment-broken / unscorable tasks from an existing
SkillsBench training dataset in the DB.

Unlike a full re-build (`prepare_skillsbench_data.py --force`), this does NOT
re-parse the SkillsBench repo and does NOT touch the eval dataset. It only
deletes the offending task rows from the training dataset, keeping everything
else (and the eval split) byte-for-byte identical.

Usage (dry-run first, then apply):
    uv run python scripts/data/prune_broken_train_tasks.py
    uv run python scripts/data/prune_broken_train_tasks.py --apply
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import select  # noqa: E402

from scripts.data.prepare_skillsbench_data import (  # noqa: E402
    BROKEN_ENV_TASKS,
    UNSCORABLE_OR_SLOW_TASKS,
)
from utu.db import DatasetSample  # noqa: E402
from utu.utils import SQLModelUtils, get_logger  # noqa: E402

logger = get_logger(__name__)


def _task_id(row: DatasetSample) -> str:
    return (row.meta or {}).get("task_id") or row.index


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune broken tasks from a SkillsBench training set")
    parser.add_argument("--train_dataset_name", default="SkillsBench-Train-40")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the rows (default is a dry-run that only reports).",
    )
    args = parser.parse_args()

    to_remove = BROKEN_ENV_TASKS | UNSCORABLE_OR_SLOW_TASKS

    if not SQLModelUtils.check_db_available():
        logger.error("Database is not available. Check your UTU_DB_URL.")
        return

    with SQLModelUtils.create_session() as session:
        rows = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == args.train_dataset_name)
        ).all()

        all_ids = sorted(_task_id(r) for r in rows)
        doomed = [r for r in rows if _task_id(r) in to_remove]
        doomed_ids = sorted(_task_id(r) for r in doomed)

        keep_ids = sorted(_task_id(r) for r in rows if _task_id(r) not in to_remove)

        print(f"Dataset '{args.train_dataset_name}' currently has {len(rows)} task(s).")
        print("\nCurrent task ids:\n  " + "\n  ".join(all_ids))
        print(
            f"\n{len(doomed_ids)} task(s) match the broken/unscorable exclusion lists "
            "(will be removed):\n  "
            + ("\n  ".join(doomed_ids) if doomed_ids else "(none)")
        )
        print(
            f"\n{len(keep_ids)} task(s) will REMAIN in the training set:\n  "
            + ("\n  ".join(keep_ids) if keep_ids else "(none)")
        )

        if not args.apply:
            print(
                f"\nDRY-RUN: nothing deleted. Re-run with --apply to remove these "
                f"{len(doomed_ids)} task(s) and leave {len(keep_ids)} task(s)."
            )
            return

        for r in doomed:
            session.delete(r)
        session.commit()
        print(
            f"\n[OK] Deleted {len(doomed_ids)} task(s). "
            f"'{args.train_dataset_name}' now has {len(keep_ids)} task(s)."
        )


if __name__ == "__main__":
    main()
