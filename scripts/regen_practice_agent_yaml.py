#!/usr/bin/env python3
"""Rebuild a practice Agent YAML from a persisted hierarchy snapshot.

The selected practice config is the single source of truth for the base Agent
and export policy. This command only reads local configuration/snapshot files;
it does not run rollouts, call an LLM, or load a sentence-transformer model.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from utu.config import ConfigLoader, TrainingFreeGRPOConfig  # noqa: E402
from utu.practice.experience_clusterer import HashingEmbeddingProvider  # noqa: E402
from utu.practice.hierarchical_experience_manager import (  # noqa: E402
    HierarchicalExperienceManager,
)
from utu.practice.training_free_grpo import TrainingFreeGRPO  # noqa: E402


class _OfflineLLM:
    """Fail closed if a read-only export unexpectedly attempts generation."""

    async def query_one(self, **_kwargs) -> NoReturn:
        raise RuntimeError("Agent regeneration is offline and must not call an LLM")


def _repo_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    return resolved.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild an Agent YAML using a strict practice config and local hierarchy snapshot.",
    )
    parser.add_argument(
        "--config_name",
        required=True,
        help="Practice config name relative to configs/practice (for example math/my_run).",
    )
    parser.add_argument(
        "--experiences",
        type=Path,
        help="Optional hierarchy snapshot override; defaults to the config's experience_save_path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional Agent YAML path override; defaults to configs/agents/practice/<exp_id>_agent.yaml.",
    )
    return parser


def _load_manager(config: TrainingFreeGRPOConfig) -> HierarchicalExperienceManager:
    hierarchy = config.practice.hierarchical_learning
    if not hierarchy.enabled:
        raise ValueError(
            "regen_practice_agent_yaml requires hierarchical_learning.enabled=true "
            "because experience_save_path is a hierarchy snapshot"
        )

    snapshot_path = _repo_path(hierarchy.experience_save_path)
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"Hierarchy snapshot not found: {snapshot_path}")
    hierarchy.experience_save_path = str(snapshot_path)

    # Loading a snapshot needs neither semantic embeddings nor a model call.
    # Supplying both dependencies explicitly keeps this maintenance command
    # deterministic and prevents accidental downloads/network traffic.
    return HierarchicalExperienceManager(
        config=config.runtime.agent,
        hierarchical_config=hierarchy,
        agent_objective=config.practice.agent_objective or "",
        learning_objective=config.practice.learning_objective or "",
        llm=_OfflineLLM(),
        embedding_provider=HashingEmbeddingProvider(seed=hierarchy.random_seed),
    )


def regenerate_agent_config(
    config_name: str,
    *,
    experiences_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Regenerate one Agent artifact using the normal runtime exporter."""

    config = ConfigLoader.load_training_free_grpo_config(config_name)
    hierarchy = config.practice.hierarchical_learning
    if experiences_path is not None:
        hierarchy.experience_save_path = str(_repo_path(experiences_path))

    manager = _load_manager(config)
    runner = TrainingFreeGRPO(config)
    runner.hierarchical_experience_manager = manager
    runner.original_temperature = config.runtime.agent.model.model_settings.temperature

    explicit_output = _repo_path(output_path) if output_path is not None else None
    generated = runner._create_agent_config_with_experiences(
        {},
        output_path=explicit_output,
    )
    return Path(generated).resolve()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = regenerate_agent_config(
        args.config_name,
        experiences_path=args.experiences,
        output_path=args.output,
    )
    print(f"Agent configuration regenerated at: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
