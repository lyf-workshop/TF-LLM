"""
Unit tests for ExperienceQualityTracker.
"""

import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from utu.practice.experience_quality_tracker import ExperienceQualityTracker


def _make_sample(reward: float | None = None):
    """Create a lightweight stand-in for EvaluationSample."""
    return SimpleNamespace(reward=reward)


@pytest.fixture()
def tracker(tmp_path: Path) -> ExperienceQualityTracker:
    """Fresh tracker backed by a temp SQLite file."""
    return ExperienceQualityTracker(
        experiment_name="test",
        db_path=tmp_path / "test_quality.db",
        reward_threshold=0.5,
        recency_decay=0.9,
    )


# ------------------------------------------------------------------ #
#  record_injection
# ------------------------------------------------------------------ #

class TestRecordInjection:
    def test_creates_rows(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0", "G1"], step=0)
        stats = tracker.get_all_stats()
        assert len(stats) == 2
        ids = {s["experience_id"] for s in stats}
        assert ids == {"G0", "G1"}

    def test_updates_last_step(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        tracker.record_injection(["G0"], step=3)
        row = tracker.get_stats("G0")
        assert row["first_injected_step"] == 0
        assert row["last_injected_step"] == 3

    def test_does_not_reset_counts(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        rollouts = [_make_sample(1.0)]
        tracker.record_outcomes(rollouts, step=0, injected_ids=["G0"])
        tracker.record_injection(["G0"], step=1)
        row = tracker.get_stats("G0")
        assert row["inject_count"] == 1
        assert row["success_count"] == 1

    def test_empty_list_is_noop(self, tracker: ExperienceQualityTracker):
        tracker.record_injection([], step=0)
        assert tracker.get_all_stats() == []


# ------------------------------------------------------------------ #
#  record_outcomes
# ------------------------------------------------------------------ #

class TestRecordOutcomes:
    def test_counts_successes(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        rollouts = [
            _make_sample(1.0),
            _make_sample(0.0),
            _make_sample(0.8),
        ]
        tracker.record_outcomes(rollouts, step=0, injected_ids=["G0"])
        row = tracker.get_stats("G0")
        assert row["inject_count"] == 3
        assert row["success_count"] == 2  # 1.0 and 0.8 >= 0.5

    def test_accumulates_across_steps(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        tracker.record_outcomes(
            [_make_sample(1.0), _make_sample(0.0)],
            step=0,
            injected_ids=["G0"],
        )
        tracker.record_injection(["G0"], step=1)
        tracker.record_outcomes(
            [_make_sample(0.0), _make_sample(0.0)],
            step=1,
            injected_ids=["G0"],
        )
        row = tracker.get_stats("G0")
        assert row["inject_count"] == 4
        assert row["success_count"] == 1

    def test_multiple_ids_updated(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0", "G1"], step=0)
        rollouts = [_make_sample(1.0)]
        tracker.record_outcomes(rollouts, step=0, injected_ids=["G0", "G1"])
        for eid in ("G0", "G1"):
            row = tracker.get_stats(eid)
            assert row["inject_count"] == 1
            assert row["success_count"] == 1

    def test_none_ids_is_noop(self, tracker: ExperienceQualityTracker):
        tracker.record_outcomes([_make_sample(1.0)], step=0, injected_ids=None)
        assert tracker.get_all_stats() == []

    def test_none_reward_counted_as_failure(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        tracker.record_outcomes(
            [_make_sample(None)], step=0, injected_ids=["G0"]
        )
        row = tracker.get_stats("G0")
        assert row["inject_count"] == 1
        assert row["success_count"] == 0


# ------------------------------------------------------------------ #
#  get_quality_score
# ------------------------------------------------------------------ #

class TestGetQualityScore:
    def test_unknown_id_returns_zero(self, tracker: ExperienceQualityTracker):
        assert tracker.get_quality_score("nonexistent") == 0.0

    def test_formula_with_step(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        rollouts = [_make_sample(1.0)] * 8 + [_make_sample(0.0)] * 2
        tracker.record_outcomes(rollouts, step=0, injected_ids=["G0"])

        # success_rate = 8/10 = 0.8
        # recency_bonus = 0.9^(5-0) = 0.9^5 ≈ 0.59049
        score = tracker.get_quality_score("G0", current_step=5)
        expected = 0.7 * 0.8 + 0.3 * (0.9 ** 5)
        assert abs(score - expected) < 1e-9

    def test_no_step_defaults_recency_to_one(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        tracker.record_outcomes(
            [_make_sample(1.0)] * 10,
            step=0,
            injected_ids=["G0"],
        )
        # success_rate = 1.0, recency_bonus = 1.0
        assert abs(tracker.get_quality_score("G0") - 1.0) < 1e-9

    def test_zero_inject_count_no_division_error(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        score = tracker.get_quality_score("G0", current_step=0)
        # inject_count=0, success_rate=0/1=0, recency_bonus=0.9^0=1.0
        expected = 0.7 * 0.0 + 0.3 * 1.0
        assert abs(score - expected) < 1e-9


# ------------------------------------------------------------------ #
#  get_deprecated_ids
# ------------------------------------------------------------------ #

class TestGetDeprecatedIds:
    def test_filters_below_threshold(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0", "G1"], step=0)

        # G0: 10 rollouts, 0 successes → success_rate=0
        tracker.record_outcomes(
            [_make_sample(0.0)] * 10,
            step=0,
            injected_ids=["G0"],
        )
        # G1: 10 rollouts, 10 successes → success_rate=1
        tracker.record_outcomes(
            [_make_sample(1.0)] * 10,
            step=0,
            injected_ids=["G1"],
        )

        deprecated = tracker.get_deprecated_ids(
            threshold=0.2, min_inject_count=5, current_step=10
        )
        assert "G0" in deprecated
        assert "G1" not in deprecated

    def test_min_inject_count_respected(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        tracker.record_outcomes(
            [_make_sample(0.0)] * 3,
            step=0,
            injected_ids=["G0"],
        )
        # inject_count=3 < min_inject_count=5 → should NOT appear
        deprecated = tracker.get_deprecated_ids(
            threshold=0.2, min_inject_count=5, current_step=10
        )
        assert deprecated == []

    def test_empty_table(self, tracker: ExperienceQualityTracker):
        assert tracker.get_deprecated_ids() == []


# ------------------------------------------------------------------ #
#  Injection history
# ------------------------------------------------------------------ #

class TestInjectionHistory:
    def test_log_records(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        tracker.record_outcomes(
            [_make_sample(1.0)], step=0, injected_ids=["G0"]
        )
        tracker.record_injection(["G0"], step=1)
        tracker.record_outcomes(
            [_make_sample(0.0)], step=1, injected_ids=["G0"]
        )

        history = tracker.get_injection_history("G0")
        assert len(history) == 2
        assert history[0]["step"] == 0
        assert history[0]["num_successes"] == 1
        assert history[1]["step"] == 1
        assert history[1]["num_successes"] == 0


# ------------------------------------------------------------------ #
#  Persistence
# ------------------------------------------------------------------ #

class TestPersistence:
    def test_survives_restart(self, tmp_path: Path):
        db_path = tmp_path / "persist.db"
        t1 = ExperienceQualityTracker("exp", db_path=db_path)
        t1.record_injection(["G0"], step=0)
        t1.record_outcomes(
            [_make_sample(1.0)] * 5, step=0, injected_ids=["G0"]
        )

        t2 = ExperienceQualityTracker("exp", db_path=db_path)
        row = t2.get_stats("G0")
        assert row["inject_count"] == 5
        assert row["success_count"] == 5

    def test_default_db_path(self, tmp_path: Path, monkeypatch):
        import utu.practice.experience_quality_tracker as mod

        monkeypatch.setattr(mod, "_DEFAULT_DB_DIR", tmp_path)
        t = ExperienceQualityTracker("my_exp")
        assert Path(t._db_path).parent == tmp_path


# ------------------------------------------------------------------ #
#  Edge cases
# ------------------------------------------------------------------ #

class TestEdgeCases:
    def test_large_step_gap_does_not_error(self, tracker: ExperienceQualityTracker):
        tracker.record_injection(["G0"], step=0)
        tracker.record_outcomes(
            [_make_sample(1.0)], step=0, injected_ids=["G0"]
        )
        score = tracker.get_quality_score("G0", current_step=10_000)
        assert 0.0 <= score <= 1.0

    def test_threshold_boundary(self, tracker: ExperienceQualityTracker):
        """reward == threshold should count as success."""
        tracker.record_injection(["G0"], step=0)
        tracker.record_outcomes(
            [_make_sample(0.5)], step=0, injected_ids=["G0"]
        )
        row = tracker.get_stats("G0")
        assert row["success_count"] == 1
