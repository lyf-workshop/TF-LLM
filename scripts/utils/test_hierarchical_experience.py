#!/usr/bin/env python3
"""
Test hierarchical experience generation (L0/L1/L2).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.config import AgentConfig
from utu.practice.hierarchical_experience_manager import HierarchicalExperienceManager


class MockHierarchicalConfig:
    """Mock hierarchical learning configuration."""
    enabled = True
    l1_aggregation_threshold = 5
    l2_aggregation_threshold = 3
    max_l0_per_problem = 1
    max_l1_total = 50
    max_l2_total = 10
    include_l0_in_prompt = True
    max_l0_recent = 10
    l1_confidence_threshold = 0.7
    l2_confidence_threshold = 0.8
    experience_save_path = "workspace/hierarchical_experiences/test_hierarchical.json"


async def test_hierarchical_experience():
    """Test hierarchical experience generation."""
    
    print("=" * 80)
    print("Testing Hierarchical Experience Manager (L0/L1/L2)")
    print("=" * 80)
    
    # Mock agent config
    from utu.config import ConfigLoader
    agent_config = ConfigLoader.load_agent_config("agents/practice/logic_agent_hierarchical_learning")
    
    # Create hierarchical experience manager
    h_config = MockHierarchicalConfig()
    manager = HierarchicalExperienceManager(
        config=agent_config,
        hierarchical_config=h_config,
        agent_objective="Solve logic puzzles",
        learning_objective="Improve logical reasoning",
    )
    
    print(f"\n✓ Manager initialized")
    print(f"  - L0 experiences: {len(manager.l0_experiences)}")
    print(f"  - L1 experiences: {len(manager.l1_experiences)}")
    print(f"  - L2 experiences: {len(manager.l2_experiences)}")
    
    # Simulate adding experiences from multiple steps
    print("\n" + "=" * 80)
    print("Simulating Training Steps")
    print("=" * 80)
    
    # Step 0: 9 experiences from 30 problems
    step0_experiences = {
        "G0": "Constraint validation: Validate interdependent positional clues immediately during assignment to avoid logical contradictions.",
        "G1": "Grid initialization: Use a grid/table to track attributes per house from the beginning for better uniqueness enforcement.",
        "G2": "Grid cross-referencing: Validate clue relationships proactively during assignment using a grid-based method.",
        "G3": "Track alternatives: Explicitly document alternative placements for positional constraints.",
        "G4": "Positional constraints: Explicitly reference all clues related to relative positions simultaneously.",
        "G5": "Interdependency handling: Integrate interdependent clues early in deduction processes.",
        "G6": "Structure-First Principle: Build a formal grid/table to track all attributes from the start.",
        "G7": "Uniqueness tracking: Use centralized tracking to enforce uniqueness constraints explicitly.",
        "G8": "Assumption logging: Document assumptions immediately and test them against all constraints.",
    }
    
    print(f"\nStep 0: Processing {len(step0_experiences)} experiences from 30 problems...")
    await manager.process_step_experiences(step0_experiences, step=0, problem_count=30)
    print(f"  ✓ L0: {len(manager.l0_experiences)} | L1: {len(manager.l1_experiences)} | L2: {len(manager.l2_experiences)}")
    
    # Step 1: 14 experiences from 29 problems
    step1_experiences = {
        "G0": "Constraint validation: Validate interdependent positional clues immediately.",
        "G1": "Grid initialization: Use a grid/table starting with deterministic clues.",
        "G2": "Grid cross-referencing: Proactively validate clue relationships during assignment.",
        "G3": "Track alternatives: Explicitly document alternative placements for adjacency constraints.",
        "G4": "Positional constraints: Explicitly reference all relative position clues.",
        "G9": "Proactive Validation: Enforce positional constraints during assignment.",
        "G10": "Constraint-Driven Reasoning: Systematically validate all clues at each deduction step.",
        "G11": "Proactive Cross-Referencing: Standardize real-time cross-checking of all constraints.",
        "G12": "Clue validation: Explicitly check positional relationships during attribute application.",
        "G13": "Constraint Validation as a Meta-Strategy: Explicitly map interdependent clues to the grid.",
    }
    
    print(f"\nStep 1: Processing {len(step1_experiences)} experiences from 29 problems...")
    await manager.process_step_experiences(step1_experiences, step=1, problem_count=29)
    print(f"  ✓ L0: {len(manager.l0_experiences)} | L1: {len(manager.l1_experiences)} | L2: {len(manager.l2_experiences)}")
    
    # Step 2: 15 experiences from 28 problems
    step2_experiences = {
        "G0": "Constraint validation: Validate interdependent positional clues immediately.",
        "G1": "Grid initialization: Use a grid/table starting with deterministic clues.",
        "G2": "Grid cross-referencing: Proactively validate clue relationships.",
        "G3": "Track alternatives: Explicitly document alternative placements.",
        "G4": "Positional constraints: Explicitly reference all relative position clues.",
        "G14": "Chain Tracking: Systematically represent interdependent attribute chains in the grid.",
    }
    
    print(f"\nStep 2: Processing {len(step2_experiences)} experiences from 28 problems...")
    await manager.process_step_experiences(step2_experiences, step=2, problem_count=28)
    print(f"  ✓ L0: {len(manager.l0_experiences)} | L1: {len(manager.l1_experiences)} | L2: {len(manager.l2_experiences)}")
    
    # Display summary
    print("\n" + "=" * 80)
    print("Final Summary")
    print("=" * 80)
    print(f"\nTotal Experiences Generated:")
    print(f"  • L0 (Case-Specific):   {len(manager.l0_experiences)} experiences")
    print(f"  • L1 (Pattern-Level):   {len(manager.l1_experiences)} experiences")
    print(f"  • L2 (Meta-Strategy):   {len(manager.l2_experiences)} experiences")
    
    # Show L2 experiences
    if manager.l2_experiences:
        print(f"\n" + "=" * 80)
        print("L2 Meta-Strategies")
        print("=" * 80)
        for l2 in manager.l2_experiences:
            print(f"\n[{l2['id']}] (from {len(l2['source_l1_ids'])} L1)")
            print(f"  {l2['content']}")
    
    # Show L1 experiences
    if manager.l1_experiences:
        print(f"\n" + "=" * 80)
        print("L1 Patterns")
        print("=" * 80)
        for l1 in manager.l1_experiences:
            print(f"\n[{l1['id']}] (from {len(l1['source_l0_ids'])} L0)")
            print(f"  {l1['content']}")
    
    # Show recent L0 experiences
    recent_l0 = manager.get_recent_l0_experiences(5)
    if recent_l0:
        print(f"\n" + "=" * 80)
        print("Recent L0 Cases (Last 5)")
        print("=" * 80)
        for l0 in recent_l0:
            print(f"\n[{l0['id']}] (step {l0['step']}, {l0['problem_count']} problems)")
            print(f"  {l0['content'][:100]}...")
    
    print(f"\n" + "=" * 80)
    print("✓ Test completed successfully!")
    print(f"✓ Experiences saved to: {h_config.experience_save_path}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_hierarchical_experience())




























