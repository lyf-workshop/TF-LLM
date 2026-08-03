"""
Move (or copy) specific SkillsBench tasks between two datasets in the DB.

Default behaviour is MOVE: each task is removed from --from and added to --to,
so a task is never in both datasets at once (no train/eval leakage). Use --copy
to keep the task in --from as well (NOT recommended for train/eval).

Usage (dry-run first, then apply):
    uv run python scripts/data/move_dataset_tasks.py \
        --tasks court-form-filling,dialogue-parser
    uv run python scripts/data/move_dataset_tasks.py \
        --tasks court-form-filling,dialogue-parser --apply
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlmodel import select  # noqa: E402

from utu.db import DatasetSample  # noqa: E402
from utu.utils import SQLModelUtils, get_logger  # noqa: E402

logger = get_logger(__name__)


def _task_id(row: DatasetSample) -> str:
    return (row.meta or {}).get("task_id") or row.index


def main() -> None:
    parser = argparse.ArgumentParser(description="Move/copy tasks between datasets")
    parser.add_argument("--tasks", required=True, help="Comma-separated task ids")
    parser.add_argument("--from", dest="src", default="SkillsBench-Eval-77")
    parser.add_argument("--to", dest="dst", default="SkillsBench-Train-40")
    parser.add_argument("--dst_type", default="train", help="meta.dataset_type for new rows")
    parser.add_argument("--copy", action="store_true", help="Keep the row in --from too")
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    args = parser.parse_args()

    wanted = [t.strip() for t in args.tasks.split(",") if t.strip()]

    if not SQLModelUtils.check_db_available():
        logger.error("Database is not available. Check your UTU_DB_URL.")
        return

    with SQLModelUtils.create_session() as session:
        src_rows = session.exec(select(DatasetSample).where(DatasetSample.dataset == args.src)).all()
        dst_rows = session.exec(select(DatasetSample).where(DatasetSample.dataset == args.dst)).all()
        src_by_id = {_task_id(r): r for r in src_rows}
        dst_ids = {_task_id(r) for r in dst_rows}

        plan_add, missing, already = [], [], []
        for t in wanted:
            if t in dst_ids:
                already.append(t)
            elif t in src_by_id:
                plan_add.append(t)
            else:
                missing.append(t)

        action = "COPY" if args.copy else "MOVE"
        print(f"{action} {len(plan_add)} task(s) from '{args.src}' -> '{args.dst}':")
        for t in plan_add:
            print("  ", t)
        if already:
            print(f"\nAlready in '{args.dst}' (skipped): {already}")
        if missing:
            print(f"\nNOT found in '{args.src}' (skipped): {missing}")

        print(f"\n'{args.dst}' size: {len(dst_ids)} -> {len(dst_ids) + len(plan_add)}")
        if not args.copy:
            print(f"'{args.src}' size: {len(src_rows)} -> {len(src_rows) - len(plan_add)}")

        if not args.apply:
            print("\nDRY-RUN: nothing written. Re-run with --apply.")
            return

        for t in plan_add:
            src = src_by_id[t]
            new_meta = dict(src.meta or {})
            new_meta["dataset_type"] = args.dst_type
            session.add(
                DatasetSample(
                    dataset=args.dst,
                    source=src.source,
                    index=src.index,
                    question=src.question,
                    answer=src.answer,
                    level=src.level,
                    meta=new_meta,
                )
            )
            if not args.copy:
                session.delete(src)
        session.commit()
        print(f"\n[OK] {action} complete for {len(plan_add)} task(s).")


if __name__ == "__main__":
    main()
