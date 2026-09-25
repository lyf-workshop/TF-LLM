"""Offline audit of every practice/evaluation YAML configuration contract.

This diagnostic intentionally composes the files through Hydra before strict
Pydantic validation, matching the production loaders without opening a
database or making network requests.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

# Configuration interpolation reads these values during import.  The audit is
# offline, so stable non-secret placeholders are sufficient.
os.environ["UTU_SKIP_AUTO_SETUP"] = "1"
os.environ.setdefault("UTU_LLM_TYPE", "chat.completions")
os.environ.setdefault("UTU_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_TYPE", "chat.completions")
os.environ.setdefault("JUDGE_LLM_MODEL", "offline-config-validation")
os.environ.setdefault("JUDGE_LLM_BASE_URL", "http://127.0.0.1")
os.environ.setdefault("JUDGE_LLM_API_KEY", "offline-config-validation")

from utu.config import EvalConfig, TrainingFreeGRPOConfig  # noqa: E402
from utu.config.eval_config import DataConfig  # noqa: E402
from utu.eval.experience_filter import ExperienceFilter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"


def _compose(path: Path) -> dict[str, Any]:
    config_name = path.relative_to(CONFIG_DIR).with_suffix("").as_posix()
    with initialize_config_dir(version_base="1.3", config_dir=str(CONFIG_DIR)):
        cfg = compose(config_name=config_name)
        OmegaConf.resolve(cfg)
        value = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected a mapping after Hydra composition")
    return value


def _catalog(path: Path, *, with_reason: bool = False) -> dict[str, str | None]:
    entries: dict[str, str | None] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if with_reason:
            name, reason = line.split("\t", maxsplit=1)
        else:
            name, reason = line, None
        if name in entries:
            raise ValueError(f"duplicate catalog entry {name!r} in {path}")
        entries[name] = reason
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict-all",
        action="store_true",
        help="Also fail when a catalogued legacy configuration is invalid.",
    )
    args = parser.parse_args(argv)

    failed = 0
    counts = {"supported": 0, "legacy": 0, "fragment": 0, "unclassified": 0}
    for family, model in (
        ("practice", TrainingFreeGRPOConfig),
        ("eval", EvalConfig),
    ):
        base = CONFIG_DIR / family
        supported = _catalog(base / "SUPPORTED_CONFIGS.txt")
        legacy = _catalog(base / "LEGACY_CONFIGS.txt", with_reason=True)
        overlap = set(supported) & set(legacy)
        if overlap:
            failed += 1
            print(f"FAIL {family}: entries classified twice: {sorted(overlap)}")

        print(f"### {family}")
        for path in sorted(
            path
            for path in base.rglob("*.yaml")
            if "smoke" not in path.stem.lower()
        ):
            relative = path.relative_to(base).with_suffix("").as_posix()
            if family == "eval" and path.parent == base / "data":
                classification = "fragment"
                reason = None
            elif relative in supported:
                classification = "supported"
                reason = None
            elif relative in legacy:
                classification = "legacy"
                reason = legacy[relative]
            else:
                classification = "unclassified"
                reason = None
            counts[classification] += 1

            try:
                if family == "eval" and path.parent.name == "data":
                    raw = OmegaConf.to_container(OmegaConf.load(path), resolve=True)
                    DataConfig.model_validate(raw, extra="forbid")
                else:
                    raw = _compose(path)
                    config = model.model_validate(raw, extra="forbid")
                    if classification == "supported" and family == "eval":
                        declared_filter = raw.get("experience_filter")
                        if declared_filter is not None and not declared_filter.get("enabled", False):
                            if set(declared_filter) - {"enabled"}:
                                raise ValueError(
                                    "disabled experience_filter contains dead runtime parameters"
                                )
                        source_value = config.experience_filter.experience_source
                        if config.experience_filter.enabled and source_value:
                            source = Path(source_value)
                            if not source.is_absolute():
                                source = ROOT / source
                            if not source.is_file():
                                raise FileNotFoundError(
                                    f"declared experience source does not exist: {source}"
                                )
                            instructions = config.agent.agent.instructions or ""
                            if ExperienceFilter.contains_injected_experience_section(instructions):
                                raise ValueError(
                                    "external experience source is combined with baked experiences"
                                )
                    elif classification == "supported" and family == "practice":
                        hierarchy = config.practice.hierarchical_learning
                        if hierarchy.export_include_l0 and hierarchy.export_max_l0 not in {None, 0}:
                            raise ValueError("supported practice config must export all or no L0 records")
            except Exception as exc:  # diagnostic reports all failures together
                detail = " ".join(str(exc).splitlines())
                if classification == "legacy" and not args.strict_all:
                    print(
                        f"LEGACY {relative} [{reason}]: "
                        f"{type(exc).__name__}: {detail}"
                    )
                else:
                    failed += 1
                    print(
                        f"FAIL {relative} [{classification}]: "
                        f"{type(exc).__name__}: {detail}"
                    )
            else:
                if classification == "unclassified":
                    failed += 1
                    print(f"FAIL {relative} [unclassified]: add it to a catalog")
                elif classification == "legacy":
                    print(f"LEGACY-VALID {relative} [{reason}]")
                else:
                    print(f"OK {relative} [{classification}]")

        catalogued = set(supported) | set(legacy)
        actual = {
            path.relative_to(base).with_suffix("").as_posix()
            for path in base.rglob("*.yaml")
            if "smoke" not in path.stem.lower()
            and not (family == "eval" and path.parent == base / "data")
        }
        missing = catalogued - actual
        if missing:
            failed += 1
            print(f"FAIL {family}: catalog entries without YAML files: {sorted(missing)}")

    print(
        "### summary "
        + " ".join(f"{name}={value}" for name, value in counts.items())
        + f" failures={failed}"
    )
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
