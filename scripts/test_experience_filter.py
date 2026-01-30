#!/usr/bin/env python3
"""
Test script for experience filter functionality.

This script validates that the experience filtering system works correctly:
1. Parses experiences from agent instructions
2. Filters based on configuration
3. Renders filtered experiences back to instructions format
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.config import ConfigLoader, ExperienceFilterConfig
from utu.eval.experience_filter import ExperienceFilter


def test_parse_experiences():
    """Test parsing experiences from instructions."""
    print("\n" + "="*60)
    print("TEST 1: Parse Experiences")
    print("="*60)
    
    # Sample instructions with experiences
    instructions = """You are an expert Wordle player.

When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:

[G0]. [L2-Meta] **Principle: Systematic Iterative Refinement.** This approach works by continuously updating constraints.

[G1]. [L1-Pattern] **L1 Strategy**: Systematically integrate and update constraints from feedback.

[G2]. [L1-Pattern] **L1 Strategy**: Explore and refine letter positions.

[G3]. [L1-Pattern] **L1 Strategy**: Start with high-information words.
"""
    
    config = ExperienceFilterConfig(enabled=False)
    filter = ExperienceFilter(config)
    
    base, experiences = filter.parse_experiences(instructions)
    
    print(f"✓ Base instructions length: {len(base)} chars")
    print(f"✓ Parsed {len(experiences)} experiences:")
    for exp in experiences:
        print(f"  - {exp.id} [{exp.level}]: {exp.content[:50]}...")
    
    assert len(experiences) == 4, f"Expected 4 experiences, got {len(experiences)}"
    assert experiences[0].level == "L2", f"Expected L2, got {experiences[0].level}"
    assert experiences[1].level == "L1", f"Expected L1, got {experiences[1].level}"
    
    print("✅ PASS: Experience parsing works correctly\n")


def test_static_filtering():
    """Test static filtering with max counts."""
    print("="*60)
    print("TEST 2: Static Filtering")
    print("="*60)
    
    instructions = """You are an expert.

When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:

[G0]. [L2-Meta] L2 experience 1
[G1]. [L2-Meta] L2 experience 2
[G2]. [L2-Meta] L2 experience 3
[G3]. [L1-Pattern] L1 experience 1
[G4]. [L1-Pattern] L1 experience 2
[G5]. [L1-Pattern] L1 experience 3
[G6]. [L1-Pattern] L1 experience 4
[G7]. [L1-Pattern] L1 experience 5
[G8]. [L1-Pattern] L1 experience 6
[G9]. [L0-Case] L0 experience 1
[G10]. [L0-Case] L0 experience 2
"""
    
    # Configure filter: max_l2=2, max_l1=3, max_l0=0
    config = ExperienceFilterConfig(
        enabled=True,
        strategy="static",
        max_l2=2,
        max_l1=3,
        max_l0=0
    )
    filter = ExperienceFilter(config)
    
    # Apply filtering
    filtered_instructions = filter.apply(instructions)
    
    # Parse filtered result
    _, filtered_exps = filter.parse_experiences(filtered_instructions)
    
    l2_count = sum(1 for e in filtered_exps if e.level == "L2")
    l1_count = sum(1 for e in filtered_exps if e.level == "L1")
    l0_count = sum(1 for e in filtered_exps if e.level == "L0")
    
    print(f"✓ Original: 3 L2, 6 L1, 2 L0")
    print(f"✓ Filtered: {l2_count} L2, {l1_count} L1, {l0_count} L0")
    
    assert l2_count == 2, f"Expected 2 L2, got {l2_count}"
    assert l1_count == 3, f"Expected 3 L1, got {l1_count}"
    assert l0_count == 0, f"Expected 0 L0, got {l0_count}"
    
    print("✅ PASS: Static filtering works correctly\n")


def test_wordle_config():
    """Test with actual Wordle evaluation config."""
    print("="*60)
    print("TEST 3: Wordle Config Integration")
    print("="*60)
    
    try:
        # Load the Wordle evaluation config
        config = ConfigLoader.load_eval_config("korgym/wordle_practice_20_eval")
        
        print(f"✓ Loaded config: {config.exp_id}")
        print(f"✓ Experience filter enabled: {config.experience_filter.enabled}")
        
        if config.experience_filter.enabled:
            print(f"  - Strategy: {config.experience_filter.strategy}")
            print(f"  - max_l2: {config.experience_filter.max_l2}")
            print(f"  - max_l1: {config.experience_filter.max_l1}")
            print(f"  - max_l0: {config.experience_filter.max_l0}")
            
            # Create filter and apply to agent instructions
            filter = ExperienceFilter(config.experience_filter)
            original_instructions = config.agent.instructions
            filtered_instructions = filter.apply(original_instructions)
            
            # Parse both
            _, original_exps = filter.parse_experiences(original_instructions)
            _, filtered_exps = filter.parse_experiences(filtered_instructions)
            
            print(f"\n✓ Original experiences: {len(original_exps)}")
            print(f"✓ Filtered experiences: {len(filtered_exps)}")
            print(f"✓ Instruction size: {len(original_instructions)} → {len(filtered_instructions)} chars")
            
            # Count by level
            orig_l2 = sum(1 for e in original_exps if e.level == "L2")
            orig_l1 = sum(1 for e in original_exps if e.level == "L1")
            orig_l0 = sum(1 for e in original_exps if e.level == "L0")
            
            filt_l2 = sum(1 for e in filtered_exps if e.level == "L2")
            filt_l1 = sum(1 for e in filtered_exps if e.level == "L1")
            filt_l0 = sum(1 for e in filtered_exps if e.level == "L0")
            
            print(f"\n✓ Level distribution:")
            print(f"  - L2: {orig_l2} → {filt_l2}")
            print(f"  - L1: {orig_l1} → {filt_l1}")
            print(f"  - L0: {orig_l0} → {filt_l0}")
            
            # Verify filtering respects limits
            assert filt_l2 <= config.experience_filter.max_l2, f"L2 limit exceeded"
            assert filt_l1 <= config.experience_filter.max_l1, f"L1 limit exceeded"
            assert filt_l0 <= config.experience_filter.max_l0, f"L0 limit exceeded"
            
        print("\n✅ PASS: Wordle config integration works correctly\n")
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_backward_compatibility():
    """Test that configs without experience_filter still work."""
    print("="*60)
    print("TEST 4: Backward Compatibility")
    print("="*60)
    
    # Create a config without experience_filter
    from utu.config import EvalConfig, DataConfig, AgentConfig
    
    config = EvalConfig(
        exp_id="test_compat",
        data=DataConfig(dataset="test", type="single"),
        agent=AgentConfig(
            name="test_agent",
            instructions="Test instructions without experiences."
        )
    )
    
    # Should not crash when experience_filter is not configured
    print(f"✓ Config created without experience_filter")
    print(f"✓ Experience filter enabled: {config.experience_filter.enabled}")
    
    assert not config.experience_filter.enabled, "Default should be disabled"
    
    print("✅ PASS: Backward compatibility maintained\n")


def main():
    """Run all tests."""
    print("\n" + "🧪 "*30)
    print("EXPERIENCE FILTER TEST SUITE")
    print("🧪 "*30)
    
    try:
        test_parse_experiences()
        test_static_filtering()
        test_backward_compatibility()
        test_wordle_config()
        
        print("="*60)
        print("🎉 ALL TESTS PASSED! 🎉")
        print("="*60)
        print("\n✅ Experience filter is ready to use!")
        print("\nNext steps:")
        print("  1. Run evaluation: python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval")
        print("  2. Check logs for 'Experience filtering enabled'")
        print("  3. Compare results with full experience baseline\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
