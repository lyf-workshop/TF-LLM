"""
Experience Quality Tracker — monitors how well each injected experience
contributes to rollout success, without modifying core TF-GRPO logic.

Persists per-experience stats (inject_count, success_count, success_rate)
in a local SQLite database so metrics survive process restarts.

Usage (inside training_free_grpo.py main loop):

    # before rollout
    tracker.record_injection(experience_ids, step)

    # after rollout + judge
    tracker.record_outcomes(rollouts, step, experience_ids)

    # any time
    score = tracker.get_quality_score("G3", current_step=step)
    stale = tracker.get_deprecated_ids(threshold=0.2, min_inject_count=5, current_step=step)
"""

from __future__ import annotations

import datetime
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..utils import DIR_ROOT, get_logger

if TYPE_CHECKING:
    from ..db import EvaluationSample

logger = get_logger(__name__)

_DEFAULT_DB_DIR = DIR_ROOT / "workspace" / "quality_tracking"


class ExperienceQualityTracker:
    """Track injection count, success rate, and quality score per experience.

    Thread-safe: all writes are guarded by a ``threading.Lock``.
    """

    def __init__(
        self,
        experiment_name: str,
        db_path: str | Path | None = None,
        reward_threshold: float = 0.5,
        recency_decay: float = 0.9,
    ):
        """
        Args:
            experiment_name: Used to derive the default DB filename.
            db_path: Explicit path to the SQLite file; ``None`` → auto.
            reward_threshold: A rollout with ``reward >= threshold`` counts as
                a *success* when computing ``success_rate``.
            recency_decay: Base of the exponential decay for the recency bonus.
                ``recency_bonus = recency_decay ** (current_step - last_injected_step)``
        """
        self.experiment_name = experiment_name
        self.reward_threshold = reward_threshold
        self.recency_decay = recency_decay
        self._lock = threading.Lock()

        if db_path is None:
            db_dir = _DEFAULT_DB_DIR
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / f"{experiment_name}_quality.db"
        self._db_path = str(db_path)
        self._init_db()

    # ------------------------------------------------------------------
    #  DB bootstrap
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experience_quality (
                    experience_id       TEXT PRIMARY KEY,
                    inject_count        INTEGER DEFAULT 0,
                    success_count       INTEGER DEFAULT 0,
                    first_injected_step INTEGER,
                    last_injected_step  INTEGER,
                    created_at          TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS injection_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    step            INTEGER,
                    experience_id   TEXT,
                    num_rollouts    INTEGER DEFAULT 0,
                    num_successes   INTEGER DEFAULT 0,
                    mean_reward     REAL    DEFAULT 0.0,
                    recorded_at     TEXT
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    # ------------------------------------------------------------------
    #  Core public API
    # ------------------------------------------------------------------

    def record_injection(self, experience_ids: list[str], step: int) -> None:
        """Record which experience IDs are about to be injected into the
        prompt **before** the rollout starts.

        Creates rows for newly seen IDs and updates ``last_injected_step``
        for all of them.
        """
        if not experience_ids:
            return
        now = datetime.datetime.now().isoformat()
        with self._lock, self._connect() as conn:
            for eid in experience_ids:
                conn.execute(
                    """
                    INSERT INTO experience_quality
                        (experience_id, inject_count, success_count,
                         first_injected_step, last_injected_step, created_at)
                    VALUES (?, 0, 0, ?, ?, ?)
                    ON CONFLICT(experience_id) DO UPDATE SET
                        last_injected_step = excluded.last_injected_step
                    """,
                    (eid, step, step, now),
                )
        logger.debug(
            f"Recorded injection of {len(experience_ids)} experiences at step {step}"
        )

    def record_outcomes(
        self,
        rollouts: list[EvaluationSample],
        step: int,
        injected_ids: list[str] | None = None,
    ) -> None:
        """Update ``inject_count`` / ``success_count`` after rollout + judge.

        Every rollout sample is treated as an independent trial for every
        injected experience.  This means that for a batch of *N* rollouts,
        each experience's ``inject_count`` is incremented by *N* and
        ``success_count`` is incremented by the number of successful rollouts.
        """
        if not injected_ids or not rollouts:
            return

        num_rollouts = len(rollouts)
        num_successes = sum(
            1
            for r in rollouts
            if r.reward is not None and r.reward >= self.reward_threshold
        )
        rewards = [r.reward for r in rollouts if r.reward is not None]
        mean_reward = sum(rewards) / max(len(rewards), 1)

        now = datetime.datetime.now().isoformat()
        with self._lock, self._connect() as conn:
            for eid in injected_ids:
                conn.execute(
                    """
                    UPDATE experience_quality
                    SET inject_count  = inject_count  + ?,
                        success_count = success_count + ?
                    WHERE experience_id = ?
                    """,
                    (num_rollouts, num_successes, eid),
                )
                conn.execute(
                    """
                    INSERT INTO injection_log
                        (step, experience_id, num_rollouts,
                         num_successes, mean_reward, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (step, eid, num_rollouts, num_successes, mean_reward, now),
                )
        logger.info(
            f"Step {step}: updated {len(injected_ids)} experiences — "
            f"{num_successes}/{num_rollouts} successes "
            f"(mean_reward={mean_reward:.3f})"
        )

    # ------------------------------------------------------------------
    #  Quality scoring
    # ------------------------------------------------------------------

    def get_quality_score(
        self, experience_id: str, current_step: int | None = None
    ) -> float:
        """``quality_score = 0.7 * success_rate + 0.3 * recency_bonus``

        ``recency_bonus = recency_decay ** (current_step - last_injected_step)``
        Falls back to ``recency_bonus = 1.0`` when ``current_step`` is *None*.
        """
        row = self._get_row(experience_id)
        if row is None:
            return 0.0

        inject_count, success_count, last_step = row
        success_rate = success_count / max(inject_count, 1)

        if current_step is not None and last_step is not None:
            gap = max(current_step - last_step, 0)
            recency_bonus = self.recency_decay ** gap
        else:
            recency_bonus = 1.0

        return 0.7 * success_rate + 0.3 * recency_bonus

    def get_deprecated_ids(
        self,
        threshold: float = 0.2,
        min_inject_count: int = 5,
        current_step: int | None = None,
    ) -> list[str]:
        """Return experience IDs whose ``quality_score < threshold`` and
        ``inject_count >= min_inject_count``."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT experience_id, inject_count, success_count,
                       last_injected_step
                FROM experience_quality
                WHERE inject_count >= ?
                """,
                (min_inject_count,),
            ).fetchall()

        deprecated: list[str] = []
        for eid, inject_count, success_count, last_step in rows:
            success_rate = success_count / max(inject_count, 1)
            if current_step is not None and last_step is not None:
                gap = max(current_step - last_step, 0)
                recency_bonus = self.recency_decay ** gap
            else:
                recency_bonus = 1.0
            score = 0.7 * success_rate + 0.3 * recency_bonus
            if score < threshold:
                deprecated.append(eid)
        return deprecated

    # ------------------------------------------------------------------
    #  Convenience / debugging helpers
    # ------------------------------------------------------------------

    def _get_row(
        self, experience_id: str
    ) -> tuple[int, int, int | None] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT inject_count, success_count, last_injected_step
                FROM experience_quality
                WHERE experience_id = ?
                """,
                (experience_id,),
            ).fetchone()
        return row

    def get_stats(self, experience_id: str) -> dict[str, Any] | None:
        """Return the full row for a single experience, or *None*."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT experience_id, inject_count, success_count,
                       first_injected_step, last_injected_step, created_at
                FROM experience_quality
                WHERE experience_id = ?
                """,
                (experience_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "experience_id": row[0],
            "inject_count": row[1],
            "success_count": row[2],
            "success_rate": row[2] / max(row[1], 1),
            "first_injected_step": row[3],
            "last_injected_step": row[4],
            "created_at": row[5],
        }

    def get_all_stats(self) -> list[dict[str, Any]]:
        """Dump the full quality table (sorted by experience_id)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT experience_id, inject_count, success_count,
                       first_injected_step, last_injected_step, created_at
                FROM experience_quality
                ORDER BY experience_id
                """
            ).fetchall()
        return [
            {
                "experience_id": r[0],
                "inject_count": r[1],
                "success_count": r[2],
                "success_rate": r[2] / max(r[1], 1),
                "first_injected_step": r[3],
                "last_injected_step": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]

    def get_injection_history(
        self, experience_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return per-step injection log entries."""
        with self._connect() as conn:
            if experience_id is not None:
                rows = conn.execute(
                    """
                    SELECT step, experience_id, num_rollouts,
                           num_successes, mean_reward, recorded_at
                    FROM injection_log
                    WHERE experience_id = ?
                    ORDER BY step
                    """,
                    (experience_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT step, experience_id, num_rollouts,
                           num_successes, mean_reward, recorded_at
                    FROM injection_log
                    ORDER BY step
                    """
                ).fetchall()
        return [
            {
                "step": r[0],
                "experience_id": r[1],
                "num_rollouts": r[2],
                "num_successes": r[3],
                "mean_reward": r[4],
                "recorded_at": r[5],
            }
            for r in rows
        ]
