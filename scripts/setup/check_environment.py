#!/usr/bin/env python3
"""Cross-platform preflight checks for TF-LLM experiment profiles."""

from __future__ import annotations

import argparse
import importlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILLSBENCH_REF = "b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af"
FAILURES: list[str] = []


def ok(message: str) -> None:
    print(f"[ OK ] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"[FAIL] {message}")


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def merged_env() -> dict[str, str]:
    values = read_env_file(ROOT / ".env")
    values.update({key: value for key, value in os.environ.items() if value})
    return values


def command_output(command: list[str], timeout: int = 15) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, result.stdout.strip()


def check_import(module: str, label: str | None = None) -> None:
    try:
        importlib.import_module(module)
    except Exception as exc:
        fail(f"Python import {label or module}: {type(exc).__name__}: {exc}")
    else:
        ok(f"Python import {label or module}")


def check_core(args: argparse.Namespace, env: dict[str, str]) -> None:
    if sys.version_info < (3, 12):
        fail(f"Python 3.12+ required for the full project; found {platform.python_version()}")
    else:
        ok(f"Python {platform.python_version()}")

    for relative in ("pyproject.toml", "uv.lock", "configs", "utu", "scripts"):
        if (ROOT / relative).exists():
            ok(f"Project path {relative}")
        else:
            fail(f"Missing project path {relative}")

    for module, label in (
        ("utu", "utu"),
        ("openai", "openai"),
        ("sqlmodel", "sqlmodel"),
        ("hydra", "hydra-core"),
        ("datasets", "datasets"),
    ):
        check_import(module, label)

    for key in ("UTU_LLM_TYPE", "UTU_LLM_MODEL", "UTU_LLM_BASE_URL"):
        if env.get(key):
            ok(f"Environment variable {key}")
        else:
            fail(f"Missing environment variable {key}")

    if env.get("UTU_LLM_API_KEY"):
        ok("Environment variable UTU_LLM_API_KEY is set")
    elif args.allow_missing_api_key:
        warn("UTU_LLM_API_KEY is empty; deployment can finish, experiments cannot")
    else:
        fail("Missing environment variable UTU_LLM_API_KEY")


def check_korgym() -> None:
    for module in ("fastapi", "uvicorn", "pandas", "PIL"):
        check_import(module)
    games = ("8-word_puzzle", "22-alphabetical_sorting", "33-wordle")
    for game in games:
        path = ROOT / "KORGym" / "game_lib" / game / "game_lib.py"
        if path.exists():
            ok(f"KORGym server {game}")
        else:
            fail(f"Missing KORGym server {path}")


def check_skillsbench(args: argparse.Namespace) -> None:
    docker = shutil.which("docker")
    if not docker:
        fail("Docker CLI not found")
    else:
        success, output = command_output([docker, "info"], timeout=20)
        if success:
            ok("Docker daemon is reachable")
        else:
            fail(f"Docker daemon is unavailable: {output[-300:]}")

    harbor = shutil.which("harbor")
    if not harbor:
        fail("Harbor CLI not found; install harbor==0.3.0 with uv tool")
    else:
        success, output = command_output([harbor, "--version"])
        version = output.splitlines()[0] if output else "unknown"
        if success and version == "0.3.0":
            ok("Harbor 0.3.0")
        else:
            fail(f"Expected Harbor 0.3.0, found {version}")

    repo = args.skillsbench_repo.resolve()
    tasks_dir = repo / "tasks"
    if not tasks_dir.is_dir():
        fail(f"SkillsBench tasks directory not found: {tasks_dir}")
        return

    success, current_ref = command_output(["git", "-C", str(repo), "rev-parse", "HEAD"])
    if success and current_ref == args.skillsbench_ref:
        ok(f"SkillsBench commit {current_ref[:12]}")
    elif success:
        fail(f"SkillsBench commit mismatch: {current_ref} != {args.skillsbench_ref}")
    else:
        fail("Cannot read SkillsBench git commit")

    manifest = ROOT / "configs" / "eval" / "skillsbench" / "skillsbench_paper_87_tasks.tsv"
    task_ids = [
        line.split("\t", 1)[0]
        for line in manifest.read_text(encoding="utf-8").splitlines()[1:]
        if line.strip()
    ]
    missing = [task_id for task_id in task_ids if not (tasks_dir / task_id).is_dir()]
    if len(task_ids) == 87 and not missing:
        ok("SkillsBench paper manifest: 87/87 task directories")
    else:
        fail(f"SkillsBench paper manifest: {len(task_ids)} entries, {len(missing)} missing")


def check_api(env: dict[str, str]) -> None:
    required = ("UTU_LLM_MODEL", "UTU_LLM_BASE_URL", "UTU_LLM_API_KEY")
    if any(not env.get(key) for key in required):
        fail("Cannot check API until model, base URL, and API key are configured")
        return
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=env["UTU_LLM_API_KEY"],
            base_url=env["UTU_LLM_BASE_URL"],
            timeout=30.0,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=env["UTU_LLM_MODEL"],
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=8,
            temperature=0,
        )
    except Exception as exc:
        fail(f"LLM API health check: {type(exc).__name__}: {exc}")
    else:
        ok(f"LLM API health check; observed model={response.model}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("core", "korgym", "skillsbench", "all"),
        default="core",
    )
    parser.add_argument("--skillsbench-repo", type=Path, default=ROOT / "SkillsBench-repo")
    parser.add_argument("--skillsbench-ref", default=DEFAULT_SKILLSBENCH_REF)
    parser.add_argument("--allow-missing-api-key", action="store_true")
    parser.add_argument("--check-api", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = merged_env()
    print(f"TF-LLM preflight: profile={args.profile}, root={ROOT}")

    check_core(args, env)
    if args.profile in ("korgym", "all"):
        check_korgym()
    if args.profile in ("skillsbench", "all"):
        check_skillsbench(args)
    if args.check_api:
        check_api(env)

    try:
        proc_version = Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        proc_version = ""
    if "microsoft" in proc_version and str(ROOT).startswith("/mnt/"):
        warn("Project is under /mnt/*; WSL-native storage is faster for SQLite and Docker builds")

    if FAILURES:
        print(f"\nPreflight failed: {len(FAILURES)} check(s) need attention.")
        return 1
    print("\nPreflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
