from utu.config import ConfigLoader
from utu.db import EvaluationSample
from utu.eval.processer.training_free_grpo_processor import TrainingFreeGRPOProcesser
from utu.practice.experience_retriever import ExperienceRetriever
from utu.practice.training_free_grpo import TrainingFreeGRPO
from utu.practice.utils import TaskRecorder
from utu.utils.experience_injection import INJECTED_EXPERIENCE_IDS_META_KEY


def _processor() -> TrainingFreeGRPOProcesser:
    processor = TrainingFreeGRPOProcesser.__new__(TrainingFreeGRPOProcesser)
    processor.prompts = {
        "PROBLEM_WITH_EXPERIENCE_TEMPLATE": "Problem: {{ problem }}\nExperiences:\n{{ experiences }}"
    }
    processor._experience_retriever = ExperienceRetriever()
    processor._indexed_l0_experiences = ()
    return processor


def _sample(question: str) -> EvaluationSample:
    return EvaluationSample(
        dataset="test",
        dataset_index=0,
        source="training_free_grpo",
        raw_question=question,
        meta={"task_id": "test:0"},
    )


def test_retrieves_relevant_l0_and_keeps_upper_levels():
    recorder = TaskRecorder(
        experiences={
            "L2_global": "Verify the final answer independently.",
            "L0_geometry": "For triangle angle geometry, use cyclic angle relations.",
            "L0_number_theory": "For prime divisibility, use modular arithmetic.",
        },
        l0_injection_top_k=1,
    )
    sample = _sample("Find an angle in a cyclic triangle geometry problem.")

    _processor().preprocess_one(sample, recorder)

    assert "Verify the final answer independently." in sample.augmented_question
    assert "cyclic angle relations" in sample.augmented_question
    assert "prime divisibility" not in sample.augmented_question
    assert sample.meta[INJECTED_EXPERIENCE_IDS_META_KEY] == [
        "L2_global",
        "L0_geometry",
    ]


def test_zero_top_k_preserves_legacy_full_pool_injection():
    recorder = TaskRecorder(
        experiences={"L0_first": "First lesson.", "L0_second": "Second lesson."},
        l0_injection_top_k=0,
    )
    sample = _sample("An unrelated question")

    _processor().preprocess_one(sample, recorder)

    assert "First lesson." in sample.augmented_question
    assert "Second lesson." in sample.augmented_question
    assert sample.meta[INJECTED_EXPERIENCE_IDS_META_KEY] == ["L0_first", "L0_second"]


def test_no_lexical_match_does_not_inject_arbitrary_l0():
    recorder = TaskRecorder(
        experiences={"L0_geometry": "Triangle geometry angle relations."},
        l0_injection_top_k=1,
    )
    sample = _sample("Completely unrelated vocabulary")

    _processor().preprocess_one(sample, recorder)

    assert "Triangle geometry" not in sample.augmented_question
    assert sample.meta[INJECTED_EXPERIENCE_IDS_META_KEY] == []


def test_dapo_config_enables_top_k_injection_on_training_recorder():
    config = ConfigLoader.load_training_free_grpo_config(
        "math/math_dapo_100_full_hierarchy"
    )

    training = TrainingFreeGRPO(config)

    assert config.practice.hierarchical_learning.l0_injection_top_k == 5
    assert training.recorder.l0_injection_top_k == 5
