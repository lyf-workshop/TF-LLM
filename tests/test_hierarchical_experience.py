"""Offline integration test for the hierarchical manager."""

from __future__ import annotations

import json
from types import SimpleNamespace

from utu.practice.experience_clusterer import HashingEmbeddingProvider
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager


class MockLLM:
    async def query_one(self, **_kwargs):
        return json.dumps(
            {
                "decision": "aggregate",
                "title": "Constraint table workflow",
                "principle": "Record constraints in one table and validate each assignment immediately.",
                "applicable_when": ["a task has interdependent finite constraints"],
                "not_applicable_when": ["the task has no cross-dependent constraints"],
                "recommended_actions": ["build the table", "check every assignment"],
                "evidence_summary": "The supplied cases use explicit constraint tracking and validation.",
                "confidence": 0.9,
            }
        )


async def test_hierarchical_experience(tmp_path):
    hierarchy = SimpleNamespace(
        experience_save_path=str(tmp_path / "hierarchy.json"),
        clustering_audit_path=str(tmp_path / "clusters.jsonl"),
        clustering_enabled=False,
        min_l0_per_l1=2,
        min_l1_per_l2=2,
        max_cluster_size=20,
        max_l0_per_problem=10,
        max_l1_total=50,
        max_l2_total=10,
        l1_confidence_threshold=0.7,
        l2_confidence_threshold=0.8,
        aggregation_temperature=0.0,
        include_l0_in_prompt=True,
        max_l0_recent=10,
        random_seed=42,
    )
    manager = HierarchicalExperienceManager(
        config=SimpleNamespace(),
        hierarchical_config=hierarchy,
        agent_objective="Solve logic puzzles",
        learning_objective="Improve logical reasoning",
        llm=MockLLM(),
        embedding_provider=HashingEmbeddingProvider(seed=42),
    )
    await manager.process_step_experiences(
        [
            {"content": f"Track constraint group {index} in a table.", "source_task_ids": [f"task-{index}"]}
            for index in range(6)
        ],
        step=0,
    )
    await manager.aggregate_epoch(epoch=0)

    assert len(manager.l0_experiences) == 6
    assert len(manager.l1_experiences) == 3
    assert len(manager.l2_experiences) == 1
    assert all(item["source_l0_ids"] == item["parent_ids"] for item in manager.l1_experiences)
    assert manager.l2_experiences[0]["source_l1_ids"] == manager.l2_experiences[0]["parent_ids"]
