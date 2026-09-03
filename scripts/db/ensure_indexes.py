#!/usr/bin/env python3
"""Inspect or create the indexes declared by TF-LLM's SQLModel tables."""

from __future__ import annotations

import argparse
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-url",
        help="Database URL override. Defaults to UTU_DB_URL (or sqlite:///test.db).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create missing indexes. Without this flag no indexes are created.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Importing utu normally initializes tracing, which may open and initialize
    # a database before this maintenance command can honor --db-url. Suppress
    # that application startup path so a dry run only inspects indexes.
    os.environ["UTU_SKIP_AUTO_SETUP"] = "1"
    from utu.utils import SQLModelUtils

    engine = SQLModelUtils.configure(args.db_url, initialize_schema=False)
    missing = SQLModelUtils.missing_indexes(engine)
    if not missing:
        print("All declared database indexes already exist.")
        return 0

    print(f"Missing indexes: {len(missing)}")
    for table, index in missing:
        print(f"  {table}: {index}")
    if not args.apply:
        print("Dry run only. Re-run with --apply during a maintenance window.")
        return 0

    created = SQLModelUtils.ensure_indexes(engine)
    print(f"Created indexes: {len(created)}")
    for table, index in created:
        print(f"  {table}: {index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
