"""
Regenerate configs/agents/practice/skillsbench_practice_agent.yaml
from the existing workspace/hierarchical_experiences/skillsbench_practice.json,
using the current (zone-based) experience injection format.

Usage:
    python scripts/regen_practice_agent_yaml.py
"""

import json
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

EXPERIENCES_JSON = REPO_ROOT / "workspace" / "hierarchical_experiences" / "skillsbench_practice.json"
BASE_AGENT_YAML  = REPO_ROOT / "configs" / "agents" / "practice" / "skillsbench_agent.yaml"
OUT_YAML         = REPO_ROOT / "configs" / "agents" / "practice" / "skillsbench_practice_agent.yaml"
MAX_L0_RECENT    = 40   # keep in sync with skillsbench_practice.yaml → max_l0_recent


def load_experiences(path: Path) -> tuple[list, list, list]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return (
        data.get("l2_experiences", []),
        data.get("l1_experiences", []),
        data.get("l0_experiences", []),
    )


def build_instructions(base_instructions: str, l2: list, l1: list, l0: list) -> str:
    """Apply three-zone injection (same logic as training_free_grpo.py)."""
    instructions = base_instructions

    # ZONE 1 — L2 meta-strategies prepended (highest attention)
    if l2:
        bullets = "\n".join(f"• {e['content']}" for e in l2)
        block = (
            "You have developed the following principles through experience "
            "completing similar tasks. Apply them proactively:\n"
            f"{bullets}\n\n"
        )
        instructions = block + instructions

    # ZONE 2 — L1 patterns appended as operational guidelines
    if l1:
        bullets = "\n".join(f"• {e['content']}" for e in l1)
        block = f"\n\nProven patterns from past tasks:\n{bullets}"
        instructions = instructions + block

    # ZONE 3 — recent L0 cases (most-recent MAX_L0_RECENT entries)
    recent_l0 = l0[-MAX_L0_RECENT:] if len(l0) > MAX_L0_RECENT else l0
    if recent_l0:
        bullets = "\n".join(f"• {e['content']}" for e in recent_l0)
        block = f"\n\nSpecific lessons from recent tasks:\n{bullets}"
        instructions = instructions + block

    return instructions


def main() -> None:
    if not EXPERIENCES_JSON.exists():
        sys.exit(f"ERROR: experiences file not found: {EXPERIENCES_JSON}")
    if not BASE_AGENT_YAML.exists():
        sys.exit(f"ERROR: base agent yaml not found: {BASE_AGENT_YAML}")

    l2, l1, l0 = load_experiences(EXPERIENCES_JSON)
    print(f"Loaded  L2={len(l2)}  L1={len(l1)}  L0={len(l0)} experiences")

    with open(BASE_AGENT_YAML, encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)

    base_instructions = base_cfg.get("agent", {}).get(
        "instructions", "You are a helpful assistant."
    )

    new_instructions = build_instructions(base_instructions, l2, l1, l0)

    out_cfg = {
        "agent": {
            "name": base_cfg.get("agent", {}).get("name", "skillsbench_agent"),
            "instructions": new_instructions,
        }
    }
    # Carry over model / toolkits if present in the base yaml
    for key in ("model", "toolkits"):
        if key in base_cfg:
            out_cfg[key] = base_cfg[key]

    header = "# @package _global_\ndefaults:\n  - _self_\n\n"
    yaml_text = yaml.dump(out_cfg, default_flow_style=False, allow_unicode=True, sort_keys=False)

    OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_YAML, "w", encoding="utf-8") as f:
        f.write(header + yaml_text)

    print(f"Written → {OUT_YAML}")
    print(f"  Zone-1 L2 : {len(l2)} principles prepended")
    print(f"  Zone-2 L1 : {len(l1)} patterns appended")
    print(f"  Zone-3 L0 : {min(len(l0), MAX_L0_RECENT)} recent cases appended")


if __name__ == "__main__":
    main()
