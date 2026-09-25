import pytest

from scripts.experiments.run_retrieval_ab import (
    Experience,
    Selection,
    Task,
    combine_usage,
    make_user_prompt,
    parse_gate_decision,
)


def _candidate(experience_id: str) -> Selection:
    return Selection(
        Experience(experience_id, "L0", f"lesson {experience_id}", {}),
        score=1.0,
        lexical_score=2.0,
        dense_score=0.5,
    )


def test_gate_accepts_only_known_ids_up_to_limit() -> None:
    candidates = [_candidate("a"), _candidate("b"), _candidate("c")]

    selected, decision = parse_gate_decision(
        '{"use_retrieval": true, "confidence": 0.9, '
        '"selected_ids": ["b", "unknown", "a", "c"], "reason": "applicable"}',
        candidates,
        confidence_threshold=0.8,
        max_selected=2,
    )

    assert [item.experience.id for item in selected] == ["b", "a"]
    assert decision["accepted"] is True
    assert decision["valid_ids"] == ["b", "a"]


def test_gate_fails_closed_below_threshold() -> None:
    selected, decision = parse_gate_decision(
        '{"use_retrieval": true, "confidence": 0.79, "selected_ids": ["a"]}',
        [_candidate("a")],
        confidence_threshold=0.8,
        max_selected=2,
    )

    assert selected == []
    assert decision["accepted"] is False


def test_gate_rejects_non_json_response() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_gate_decision(
            "no applicable lesson",
            [_candidate("a")],
            confidence_threshold=0.8,
            max_selected=2,
        )


def test_gate_recovers_only_explicit_malformed_rejection() -> None:
    selected, decision = parse_gate_decision(
        '{"use_retrieval": false, "confidence": 0.0, "selected_ids": []',
        [_candidate("a")],
        confidence_threshold=0.8,
        max_selected=2,
    )

    assert selected == []
    assert decision["accepted"] is False

    with pytest.raises(ValueError):
        parse_gate_decision(
            '{"use_retrieval": true, "confidence": 0.9, "selected_ids": ["a"]',
            [_candidate("a")],
            confidence_threshold=0.8,
            max_selected=2,
        )


def test_abstention_prompt_and_combined_usage() -> None:
    question = "What is 1+1?"

    assert make_user_prompt(Task(0, question, "2", "unit"), "") == question
    assert combine_usage(
        {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    ) == {"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200}
