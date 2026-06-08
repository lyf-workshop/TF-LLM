"""
Quick test script to verify LLM API connection for experience reranking.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.config import LLMRerankConfig
from utu.eval.llm_experience_reranker import LLMExperienceReranker
from utu.eval.experience_filter import ParsedExperience
from utu.utils import get_logger

logger = get_logger(__name__)


async def test_api_connection():
    """Test LLM API connection with a simple reranking task."""
    print("\n" + "="*60)
    print("Testing LLM API Connection")
    print("="*60)
    
    # Create test experiences
    test_experiences = [
        ParsedExperience(
            id="TEST_1",
            level="L1",
            content="[L1-Pattern] Use high-frequency letters in opening moves",
            order=0
        ),
        ParsedExperience(
            id="TEST_2",
            level="L0",
            content="[L0-Case] Start with 'STARE' or 'RAISE' for 5-letter words",
            order=1
        ),
        ParsedExperience(
            id="TEST_3",
            level="L2",
            content="[L2-Meta] Maximize information gain through constraint satisfaction",
            order=2
        ),
    ]
    
    # Create reranker config
    config = LLMRerankConfig(
        enabled=True,
        model="qwen3-32b",
        temperature=0.1,
        max_candidates=3,
        final_top_k=3,
        include_reasoning=True,
        timeout=30
    )
    
    print(f"\n📋 Configuration:")
    print(f"   Model: {config.model}")
    print(f"   Temperature: {config.temperature}")
    print(f"   Timeout: {config.timeout}s")
    
    # Create reranker
    reranker = LLMExperienceReranker(config)
    
    # Test task context
    task_context = "Wordle game: Guess a 5-letter word using feedback constraints"
    
    print(f"\n🔄 Calling LLM API for reranking...")
    print(f"   Task: {task_context}")
    print(f"   Experiences: {len(test_experiences)}")
    
    try:
        # Call reranker
        reranked = await reranker.rerank(task_context, test_experiences, config)
        
        print(f"\n✅ API call successful!")
        print(f"   Returned {len(reranked)} reranked experiences")
        
        print(f"\n📊 Reranked results:")
        for i, exp in enumerate(reranked, 1):
            print(f"   {i}. [{exp.id}] ({exp.level})")
            print(f"      {exp.content[:80]}...")
        
        return True
        
    except Exception as e:
        print(f"\n❌ API call failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run API connection test."""
    print("\n" + "🔌"*30)
    print("LLM API Connection Test")
    print("🔌"*30)
    
    success = await test_api_connection()
    
    if success:
        print("\n" + "="*60)
        print("✅ LLM API is working correctly!")
        print("="*60)
        print("\nYou can now run the full test suite:")
        print("  uv run python scripts/test_llm_experience_filter.py")
        print("\nOr run evaluation:")
        print("  uv run python scripts/run_eval.py --config_name korgym/wordle_eval_llm")
    else:
        print("\n" + "="*60)
        print("❌ API connection failed. Please check:")
        print("="*60)
        print("1. Your .env file contains:")
        print("   UTU_LLM_API_KEY=sk-your-key-here")
        print("   UTU_LLM_BASE_URL=https://api.zhizengzeng.com/v1")
        print("\n2. The API key is valid and has sufficient quota")
        print("\n3. The base URL is correct for your provider")


if __name__ == "__main__":
    asyncio.run(main())
