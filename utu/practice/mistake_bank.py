"""
Mistake bank for practice/evaluation loops.

Goals:
- Persist "active mistakes" per problem (dataset + dataset_index) across epochs.
- Prefer sampling recent/high-value failures in the next epoch (curriculum-like).
- Store a concise failure experience for each active mistake; once solved, store a
  success experience and remove the active failure experience.

This module is environment-agnostic. It relies only on `EvaluationSample` fields
and optional `meta` keys when available.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..db import EvaluationSample
from ..utils import DIR_ROOT, get_logger

logger = get_logger(__name__)


def _now_ts() -> float:
    return time.time()


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    cleaned = []
    for ch in text.lower():
        cleaned.append(ch if ch.isalnum() else " ")
    return {w for w in "".join(cleaned).split() if w}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


@dataclass
class MistakeRecord:
    key: str
    dataset: str
    dataset_index: int
    source: str | None = None
    question: str | None = None
    meta: dict[str, Any] | None = None

    status: str = "failed"  # failed | solved
    last_updated_ts: float = field(default_factory=_now_ts)
    first_seen_ts: float = field(default_factory=_now_ts)

    attempts: int = 0
    last_reward: float = 0.0

    failure_experience: str | None = None
    success_experience: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "dataset": self.dataset,
            "dataset_index": self.dataset_index,
            "source": self.source,
            "question": self.question,
            "meta": self.meta,
            "status": self.status,
            "last_updated_ts": self.last_updated_ts,
            "first_seen_ts": self.first_seen_ts,
            "attempts": self.attempts,
            "last_reward": self.last_reward,
            "failure_experience": self.failure_experience,
            "success_experience": self.success_experience,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "MistakeRecord":
        rec = MistakeRecord(
            key=d["key"],
            dataset=d.get("dataset", ""),
            dataset_index=int(d.get("dataset_index", 0)),
            source=d.get("source"),
            question=d.get("question"),
            meta=d.get("meta"),
        )
        rec.status = d.get("status", "failed")
        rec.last_updated_ts = float(d.get("last_updated_ts", _now_ts()))
        rec.first_seen_ts = float(d.get("first_seen_ts", rec.last_updated_ts))
        rec.attempts = int(d.get("attempts", 0))
        rec.last_reward = _safe_float(d.get("last_reward"), 0.0)
        rec.failure_experience = d.get("failure_experience")
        rec.success_experience = d.get("success_experience")
        return rec


class MistakeBank:
    """Persistent mistake bank for a single experiment (base exp_id)."""

    def __init__(self, exp_id: str, root_dir: str | Path | None = None):
        self.exp_id = exp_id
        self.root_dir = Path(root_dir) if root_dir is not None else (DIR_ROOT / "workspace" / "mistake_bank")
        self.path = self.root_dir / f"{exp_id}.json"
        self.records: dict[str, MistakeRecord] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            self.records = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            recs = data.get("records", {})
            self.records = {k: MistakeRecord.from_dict(v) for k, v in recs.items()}
        except Exception as e:
            logger.warning(f"Failed to load mistake bank from {self.path}: {e}")
            self.records = {}

    def save(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "exp_id": self.exp_id,
            "updated_ts": _now_ts(),
            "records": {k: v.to_dict() for k, v in self.records.items()},
        }
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self.path)

    @staticmethod
    def problem_key(dataset: str, dataset_index: int) -> str:
        return f"{dataset}::{dataset_index}"

    def score_for_sampling(self, rec: MistakeRecord, now_ts: float | None = None) -> float:
        """Compute a priority score for sampling.

        Higher score => earlier sampling.
        """
        now_ts = now_ts or _now_ts()
        recency = max(0.0, now_ts - rec.last_updated_ts)
        recency_score = 1.0 / (1.0 + recency / 3600.0)  # within hours
        attempts_score = min(1.0, rec.attempts / 10.0)

        # "High-value failure": low reward and recently seen.
        reward_penalty = 1.0 / (1.0 + max(0.0, rec.last_reward))

        base = 0.0
        if rec.status == "failed":
            base = 10.0
        elif rec.status == "solved":
            base = 1.0

        return base + 2.0 * recency_score + 1.0 * attempts_score + 2.0 * reward_penalty

    def update_from_judged_samples(self, samples: list[EvaluationSample]) -> None:
        """Update bank based on judged samples.

        Contract:
        - If sample is incorrect/low reward => create/update active failure record with failure_experience.
        - If sample becomes correct/success => mark as solved, store success_experience, and clear active failure_experience.
        """
        self.load()
        changed = False
        now_ts = _now_ts()

        for s in samples:
            dataset = getattr(s, "dataset", "") or ""
            dataset_index = int(getattr(s, "dataset_index", 0) or 0)
            key = self.problem_key(dataset, dataset_index)

            rec = self.records.get(key)
            if rec is None:
                rec = MistakeRecord(
                    key=key,
                    dataset=dataset,
                    dataset_index=dataset_index,
                    source=getattr(s, "source", None),
                    question=getattr(s, "raw_question", None),
                    meta=getattr(s, "meta", None),
                )
                self.records[key] = rec
                changed = True

            # Keep latest metadata
            rec.source = getattr(s, "source", None)
            rec.question = getattr(s, "raw_question", None)
            rec.meta = getattr(s, "meta", None)
            rec.last_updated_ts = now_ts
            rec.attempts += 1
            raw_reward = getattr(s, "reward", None)
            reward_value = _safe_float(raw_reward, 0.0)
            rec.last_reward = reward_value

            is_correct = getattr(s, "correct", None)
            if raw_reward is not None:
                is_success = reward_value >= 0.5
            else:
                is_success = bool(is_correct)

            if is_success:
                # Solved: record success experience, clear failure experience.
                rec.status = "solved"
                rec.success_experience = self._summarize_success(s)
                rec.failure_experience = None
                changed = True
            else:
                # Still failing: keep an active failure experience (cautious update).
                rec.status = "failed"
                new_failure = self._summarize_failure(s)
                # Per-game dedup (cautious): reuse an existing very-similar failure experience
                # within the same game_name when available.
                new_failure = self._reuse_similar_failure_in_game(s, new_failure, threshold=0.97)
                if rec.failure_experience is None:
                    rec.failure_experience = new_failure
                    changed = True
                else:
                    if not self._too_similar(rec.failure_experience, new_failure, threshold=0.92):
                        rec.failure_experience = new_failure
                        changed = True

        if changed:
            self.save()

    def _too_similar(self, a: str, b: str, threshold: float) -> bool:
        return _jaccard(_tokenize(a), _tokenize(b)) >= threshold

    def _reuse_similar_failure_in_game(self, sample: EvaluationSample, new_failure: str, threshold: float) -> str:
        meta = getattr(sample, "meta", None) or {}
        game_name = meta.get("game_name")
        if not game_name:
            return new_failure

        new_tokens = _tokenize(new_failure)
        for other in self.records.values():
            if other.status != "failed" or not other.failure_experience:
                continue
            other_meta = other.meta or {}
            if other_meta.get("game_name") != game_name:
                continue
            if _jaccard(new_tokens, _tokenize(other.failure_experience)) >= threshold:
                return other.failure_experience
        return new_failure

    def _summarize_failure(self, sample: EvaluationSample) -> str:
        reward = _safe_float(getattr(sample, "reward", None), 0.0)
        response = (getattr(sample, "response", None) or "").strip()
        meta = getattr(sample, "meta", None) or {}

        hints: list[str] = []
        if not response:
            hints.append("empty response")
        if "answer" not in response.lower():
            hints.append("missing explicit Answer field")

        game_name = meta.get("game_name")
        seed = meta.get("seed") or meta.get("game_seed")
        if game_name or seed:
            hints.append(f"context={game_name or 'unknown'} seed={seed or 'N/A'}")

        hint_str = "; ".join(hints) if hints else "no obvious format issue"
        return f"[Mistake] Failure mode: reward={reward}. Likely issue(s): {hint_str}. Fix: follow output format strictly and adjust strategy based on feedback."

    def _summarize_success(self, sample: EvaluationSample) -> str:
        reward = _safe_float(getattr(sample, "reward", None), 0.0)
        meta = getattr(sample, "meta", None) or {}
        game_name = meta.get("game_name")
        seed = meta.get("seed") or meta.get("game_seed")
        ctx = f"{game_name or 'task'} seed={seed or 'N/A'}"
        return f"[Success] Solved {ctx} with reward={reward}. Preserve the key strategy choices that led to this outcome and reuse under similar conditions."
