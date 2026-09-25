from __future__ import annotations

from utu.practice.experience_clusterer import ExperienceClusterer
from utu.practice.experience_models import ExperienceRecord
from utu.practice.strategy_canonicalization import (
    CANONICAL_STRATEGY_VERSION,
    CanonicalStrategyRepresentation,
    assess_strategy_compatibility,
    canonicalize_l0_strategy,
)


class UniformEmbedding:
    def embed(self, texts):
        return [[1.0, 0.0] for _text in texts]


def item(record_id: str, content: str, *, level: str = "L0", task_id: str | None = None):
    return ExperienceRecord(
        id=record_id,
        level=level,
        content=content,
        source_task_ids=[task_id or record_id],
    )


def strategy_clusterer() -> ExperienceClusterer:
    return ExperienceClusterer(
        UniformEmbedding(),
        strategy_aware_l0_clustering=True,
        l0_strategy_compatibility_threshold=0.60,
        l0_strategy_fallback_threshold=0.78,
        hard_constraint_fields=["failure_mode"],
        soft_constraint_fields=[],
    )


def test_canonicalization_removes_generic_verification_and_tool_noise():
    representation = canonicalize_l0_strategy(
        item(
            "polynomial",
            "When a polynomial should be a square, complete the square and enumerate factor pairs. "
            "Verify the final answer by back-substitution. If the Python tool fails twice, stop retrying.",
        )
    )

    assert representation.task_family == "polynomials"
    assert "complete_square_difference_squares" in representation.strategy_labels
    assert "back-substitution" not in representation.embedding_text
    assert "Python tool" not in representation.embedding_text
    assert len(representation.ignored_generic) == 2


def test_canonicalization_does_not_treat_direct_substitution_as_a_strategy():
    representation = canonicalize_l0_strategy(
        item(
            "verification-only",
            "Compute each candidate and verify it by direct substitution.",
        )
    )

    assert representation.strategy_labels == ()
    assert not representation.has_strategy_evidence
    assert representation.ignored_generic == ("Compute each candidate and verify it by direct substitution.",)


def test_task_family_prefers_problem_identity_over_secondary_checks():
    polygon = canonicalize_l0_strategy(
        item(
            "polygon",
            "For a polygon cut into triangles, use shoelace area coordinates.",
        )
    )
    diophantine = canonicalize_l0_strategy(
        item(
            "integer-system",
            "For an integer quadratic system, linearize monomials and check modulo 4.",
        )
    )

    assert polygon.task_family == "polygon_geometry"
    assert diophantine.task_family == "diophantine_equations"


def test_complete_square_and_balanced_factor_optimization_are_distinct_strategies():
    square = canonicalize_l0_strategy(
        item(
            "square",
            "Complete the square, use a difference of squares, and enumerate divisors.",
        )
    )
    optimization = canonicalize_l0_strategy(
        item(
            "factor-optimization",
            "Minimize the sum by choosing the closest factor pair near the square root.",
        )
    )

    assert square.distinctive_strategy_labels == ("complete_square_difference_squares",)
    assert optimization.distinctive_strategy_labels == ("balanced_factor_pair_optimization",)


def test_auxiliary_label_overlap_requires_high_similarity_and_strategy_anchors():
    left = CanonicalStrategyRepresentation(
        task_family="polygon_geometry",
        trigger="polygon midpoint cut",
        strategy="polygon midpoint cut with coordinates",
        procedure=(),
        boundary=(),
        ignored_generic=(),
        strategy_labels=("coordinate_vector_geometry",),
    )
    close = CanonicalStrategyRepresentation(
        task_family="polygon_geometry",
        trigger="polygon midpoint cut",
        strategy="polygon midpoint cut with a coordinate model",
        procedure=(),
        boundary=(),
        ignored_generic=(),
        strategy_labels=("coordinate_vector_geometry",),
    )
    unrelated = CanonicalStrategyRepresentation(
        task_family="polygon_geometry",
        trigger="shaded grid enumeration",
        strategy="enumerate shaded grid cells",
        procedure=(),
        boundary=(),
        ignored_generic=(),
        strategy_labels=("coordinate_vector_geometry",),
    )

    below_fallback = assess_strategy_compatibility(
        left,
        close,
        core_similarity=0.70,
        compatibility_threshold=0.60,
        fallback_threshold=0.78,
    )
    low_anchor = assess_strategy_compatibility(
        left,
        unrelated,
        core_similarity=0.99,
        compatibility_threshold=0.60,
        fallback_threshold=0.78,
    )

    assert not below_fallback.compatible
    assert below_fallback.reason == "auxiliary_only_strategy_overlap"
    assert not low_anchor.compatible
    assert low_anchor.reason == "low_strategy_anchor_overlap"


def test_strategy_anchor_tokens_exclude_generic_english_scaffolding():
    representation = CanonicalStrategyRepresentation(
        task_family="general_algebra",
        trigger="for the problem",
        strategy="For the problem, use the method and verify the final answer.",
        procedure=(),
        boundary=(),
        ignored_generic=(),
        strategy_labels=(),
    )

    assert representation.strategy_anchor_tokens == ()


def test_strategy_gate_rejects_high_embedding_similarity_across_task_families():
    records = [
        item(
            "polynomial",
            "When polynomial roots are symmetric, use Vieta and Newton power sums. Verify the result by substitution.",
        ),
        item(
            "triangulation",
            "When a plane triangulation is counted, use Euler formula and double-count edges. "
            "Verify the result by substitution.",
        ),
    ]

    report = strategy_clusterer().cluster(records, level="L0", similarity_threshold=0.80)

    assert sorted(len(cluster.experience_ids) for cluster in report.clusters) == [1, 1]
    assert report.strategy_compatibility_rejection_counts == {"task_family_mismatch": 1}
    assert set(report.canonical_representations) == {"polynomial", "triangulation"}


def test_same_strategy_with_different_wording_can_cluster():
    records = [
        item(
            "first",
            "For a polynomial equal to a perfect square, complete the square and use a difference of squares.",
        ),
        item(
            "second",
            "When a polynomial expression must be square, completing the square reduces it to factor pairs.",
        ),
    ]

    report = strategy_clusterer().cluster(records, level="L0", similarity_threshold=0.80)

    assert len(report.clusters) == 1
    assert report.clusters[0].distinct_source_task_count == 2
    assert report.strategy_compatibility_rejection_counts == {}
    assert report.canonical_strategy_version == CANONICAL_STRATEGY_VERSION


def test_strategy_aware_mode_does_not_change_l1_clustering():
    records = [
        item("upper-a", "alpha upper-level principle", level="L1"),
        item("upper-b", "beta unrelated upper-level principle", level="L1"),
    ]

    report = strategy_clusterer().cluster(records, level="L1", similarity_threshold=0.80)

    assert len(report.clusters) == 1
    assert report.canonical_representations == {}
    assert report.strategy_compatibility_rejection_counts == {}
    assert report.canonical_strategy_version is None


def test_strategy_aware_l0_ignores_failure_mode_as_outcome_metadata():
    left = item(
        "success",
        "For a polynomial square condition, complete the square and enumerate factor pairs.",
    ).model_copy(update={"failure_mode": "none"})
    right = item(
        "mixed",
        "When a polynomial must be square, use completing the square and factor pairs.",
    ).model_copy(update={"failure_mode": "mixed_outcome"})

    report = strategy_clusterer().cluster([left, right], level="L0", similarity_threshold=0.80)

    assert len(report.clusters) == 1
    assert report.metadata_constraint_splits == []
