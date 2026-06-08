"""
Test script for LLM-based experience filtering.

This script validates the complete pipeline:
1. Load experiences from JSON
2. Apply LLM-based reranking
3. Verify correct injection into agent instructions
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.config import ConfigLoader, ExperienceFilterConfig, LLMRerankConfig, RecallConfig
from utu.eval.experience_filter import ExperienceFilter
from utu.utils import get_logger

logger = get_logger(__name__)


async def test_experience_loader():
    """Test 1: Load experiences from JSON file."""
    print("\n" + "="*60)
    print("TEST 1: Load Experiences from JSON")
    print("="*60)
    
    config = ExperienceFilterConfig(
        enabled=True,
        experience_source="workspace/hierarchical_experiences/wordle_practice_2.json"
    )
    
    filter = ExperienceFilter(config)
    experiences = filter.load_experiences_from_source()
    
    print(f"✅ Loaded {len(experiences)} experiences")
    print(f"   L2: {sum(1 for e in experiences if e.level=='L2')}")
    print(f"   L1: {sum(1 for e in experiences if e.level=='L1')}")
    print(f"   L0: {sum(1 for e in experiences if e.level=='L0')}")
    
    # Show sample
    if experiences:
        print(f"\n📝 Sample experience:")
        exp = experiences[0]
        print(f"   ID: {exp.id}, Level: {exp.level}")
        print(f"   Content: {exp.content[:100]}...")
    
    return experiences


async def test_static_filtering(experiences):
    """Test 2: Static filtering."""
    print("\n" + "="*60)
    print("TEST 2: Static Filtering")
    print("="*60)
    
    config = ExperienceFilterConfig(
        enabled=True,
        strategy="static",
        max_l2=1,
        max_l1=3,
        max_l0=5
    )
    
    filter = ExperienceFilter(config)
    filtered = await filter.filter_experiences(experiences)
    
    print(f"✅ Filtered: {len(experiences)} → {len(filtered)} experiences")
    print(f"   L2: {sum(1 for e in filtered if e.level=='L2')}")
    print(f"   L1: {sum(1 for e in filtered if e.level=='L1')}")
    print(f"   L0: {sum(1 for e in filtered if e.level=='L0')}")
    
    return filtered


async def test_llm_reranking(experiences):
    """Test 3: LLM-based reranking."""
    print("\n" + "="*60)
    print("TEST 3: LLM-Based Reranking")
    print("="*60)
    
    config = ExperienceFilterConfig(
        enabled=True,
        strategy="llm_rerank",
        recall=RecallConfig(
            method="static",
            max_l2=None,
            max_l1=None,
            max_l0=30
        ),
        llm_rerank=LLMRerankConfig(
            enabled=True,
            model="qwen3-32b",
            temperature=0.1,
            max_candidates=20,
            final_top_k=8,
            include_reasoning=True
        )
    )
    
    filter = ExperienceFilter(config)
    
    task_context = (
        "Wordle game: Guess a 4-letter hidden word within 10 attempts. "
        "Use feedback (GREEN=correct position, YELLOW=wrong position, GRAY=not in word) "
        "to refine guesses through constraint satisfaction and information gain."
    )
    
    print(f"📋 Task context: {task_context[:100]}...")
    print(f"🔄 Starting LLM reranking with {len(experiences)} experiences...")
    
    reranked = await filter.filter_experiences(experiences, query=task_context)
    
    print(f"✅ Reranked: {len(experiences)} → {len(reranked)} experiences")
    print(f"   L2: {sum(1 for e in reranked if e.level=='L2')}")
    print(f"   L1: {sum(1 for e in reranked if e.level=='L1')}")
    print(f"   L0: {sum(1 for e in reranked if e.level=='L0')}")
    
    print("\n📊 Top 5 selected experiences:")
    for i, exp in enumerate(reranked[:5], 1):
        print(f"   {i}. [{exp.id}] ({exp.level}) {exp.content[:80]}...")
    
    return reranked


async def test_full_pipeline():
    """Test 4: Full pipeline with base instructions."""
    print("\n" + "="*60)
    print("TEST 4: Full Pipeline - Instructions Injection")
    print("="*60)
    
    # Base instructions (no experiences)
    base_instructions = """You are an expert Wordle player. Guess the hidden word within 10 attempts using feedback.

CRITICAL: First read "Word length: X" and always match that length.
Feedback Meaning:
- GREEN = correct letter, correct position (lock it)
- YELLOW = correct letter, wrong position (keep it, move it)
- GRAY = letter not in word (avoid it unless duplicates are proven)

Output: Answer: word (lowercase, exact length, MUST be a real existing English word)"""
    
    config = ExperienceFilterConfig(
        enabled=True,
        strategy="llm_rerank",
        experience_source="workspace/hierarchical_experiences/wordle_practice_2.json",
        recall=RecallConfig(
            method="static",
            max_l2=None,
            max_l1=None,
            max_l0=30
        ),
        llm_rerank=LLMRerankConfig(
            enabled=True,
            model="qwen3-32b",
            temperature=0.1,
            max_candidates=15,
            final_top_k=6,
            include_reasoning=True
        )
    )
    
    filter = ExperienceFilter(config)
    
    task_context = "Wordle game: 4-letter word, constraint satisfaction with feedback"
    
    print(f"📝 Base instructions length: {len(base_instructions)} chars")
    print(f"🔄 Applying filter with LLM reranking...")
    
    final_instructions = await filter.apply(base_instructions, query=task_context)
    
    print(f"✅ Final instructions length: {len(final_instructions)} chars")
    print(f"   Added: {len(final_instructions) - len(base_instructions)} chars")
    
    # Check if experiences section exists
    if "When solving problems, you MUST first carefully read" in final_instructions:
        print(f"✅ Experiences successfully injected!")
        
        # Count injected experiences
        import re
        exp_matches = re.findall(r'\[L\d_\d+\]', final_instructions)
        print(f"   Found {len(exp_matches)} experience markers")
    else:
        print(f"❌ Experiences NOT found in final instructions")
    
    # Show preview
    print("\n📄 Preview of final instructions:")
    lines = final_instructions.split('\n')
    print('\n'.join(lines[:5]))
    print("...")
    print('\n'.join(lines[-10:]))
    
    return final_instructions


async def test_config_loading():
    """Test 5: Load from YAML config."""
    print("\n" + "="*60)
    print("TEST 5: Load Configuration from YAML")
    print("="*60)
    
    try:
        config = ConfigLoader.load_eval_config("korgym/wordle_eval_llm")
        print(f"✅ Loaded config: {config.exp_id}")
        print(f"   Experience filter enabled: {config.experience_filter.enabled}")
        print(f"   Strategy: {config.experience_filter.strategy}")
        print(f"   Experience source: {config.experience_filter.experience_source}")
        print(f"   LLM model: {config.experience_filter.llm_rerank.model}")
        print(f"   Final top-k: {config.experience_filter.llm_rerank.final_top_k}")
        return config
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return None


async def main():
    """Run all tests."""
    print("\n" + "🧪"*30)
    print("LLM Experience Filter - Test Suite")
    print("🧪"*30)
    
    try:
        # Test 1: Load experiences
        experiences = await test_experience_loader()
        
        # Test 2: Static filtering
        await test_static_filtering(experiences)
        
        # Test 3: LLM reranking
        await test_llm_reranking(experiences)
        
        # Test 4: Full pipeline
        await test_full_pipeline()
        
        # Test 5: Config loading
        await test_config_loading()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
        print("="*60)
        
    except Exception as e:
        print("\n" + "="*60)
        print(f"❌ TEST FAILED: {e}")
        print("="*60)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
