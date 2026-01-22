#!/usr/bin/env python3
"""
Test script to verify conversation history is properly maintained in multi-round games.

This script tests whether the Agent correctly accumulates conversation history
across multiple rounds, which is critical for reasoning continuity.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.agents import get_agent
from utu.config import ConfigLoader
from utu.practice.korgym_adapter import KORGymAdapter
from utu.utils import get_logger

logger = get_logger(__name__)


async def test_conversation_history():
    """Test that conversation history is maintained across rounds."""
    
    print("=" * 70)
    print("Testing Conversation History in Multi-Round Games")
    print("=" * 70)
    print()
    
    # Load config
    config_name = "korgym/wordle_baseline"
    print(f"Loading config: {config_name}")
    config = ConfigLoader.load_eval_config(config_name)
    
    # Initialize agent
    print("Initializing agent...")
    agent = get_agent(config.agent)
    if hasattr(agent, "build"):
        await agent.build()
    
    # Initialize adapter
    print("Initializing KORGym adapter...")
    adapter = KORGymAdapter(
        game_name="33-wordle",
        game_host="localhost",
        game_port=8777,
        level=4,
        max_rounds=3  # Only test 3 rounds
    )
    
    print()
    print("=" * 70)
    print("Test 1: Check conversation history accumulation")
    print("=" * 70)
    print()
    
    # Generate game
    seed = 1
    game_state = adapter.generate_game_instance(seed)
    
    print(f"Initial input_items length: {len(agent.input_items)}")
    print()
    
    # Round 1
    print("Round 1:")
    prompt1 = adapter.get_game_prompt(game_state)
    print(f"  Prompt length: {len(prompt1)} chars")
    
    result1 = await agent.run(prompt1, save=True)
    print(f"  Agent response: {result1.final_output[:50]}...")
    print(f"  After Round 1 - input_items length: {len(agent.input_items)}")
    
    action1 = adapter._extract_action(result1.final_output)
    game_state['action'] = action1
    game_state = adapter.verify_action(game_state)
    print(f"  Action: {action1}")
    print(f"  Game state: score={game_state.get('score')}, is_end={game_state.get('is_end')}")
    print()
    
    if game_state.get('is_end'):
        print("✅ Game ended in Round 1 (guessed correctly)")
        return
    
    # Round 2
    print("Round 2:")
    prompt2 = adapter.get_game_prompt(game_state)
    print(f"  Prompt length: {len(prompt2)} chars")
    print(f"  Prompt includes history: {'History:' in prompt2}")
    
    result2 = await agent.run(prompt2, save=True)
    print(f"  Agent response: {result2.final_output[:50]}...")
    print(f"  After Round 2 - input_items length: {len(agent.input_items)}")
    
    action2 = adapter._extract_action(result2.final_output)
    game_state['action'] = action2
    game_state = adapter.verify_action(game_state)
    print(f"  Action: {action2}")
    print(f"  Game state: score={game_state.get('score')}, is_end={game_state.get('is_end')}")
    print()
    
    if game_state.get('is_end'):
        print("✅ Game ended in Round 2")
        return
    
    # Round 3
    print("Round 3:")
    prompt3 = adapter.get_game_prompt(game_state)
    print(f"  Prompt length: {len(prompt3)} chars")
    print(f"  Prompt includes history: {'History:' in prompt3}")
    
    result3 = await agent.run(prompt3, save=True)
    print(f"  Agent response: {result3.final_output[:50]}...")
    print(f"  After Round 3 - input_items length: {len(agent.input_items)}")
    
    action3 = adapter._extract_action(result3.final_output)
    game_state['action'] = action3
    game_state = adapter.verify_action(game_state)
    print(f"  Action: {action3}")
    print(f"  Game state: score={game_state.get('score')}, is_end={game_state.get('is_end')}")
    print()
    
    # Summary
    print("=" * 70)
    print("Test Results")
    print("=" * 70)
    print()
    
    expected_length = 6  # 3 rounds * 2 messages per round (user + assistant)
    actual_length = len(agent.input_items)
    
    print(f"Expected input_items length: {expected_length}")
    print(f"Actual input_items length: {actual_length}")
    
    if actual_length == expected_length:
        print()
        print("✅ PASS: Conversation history is properly accumulated!")
        print()
        print("This means:")
        print("  - Agent remembers previous reasoning")
        print("  - Each round builds on previous rounds")
        print("  - Reasoning continuity is maintained")
    elif actual_length == 2:
        print()
        print("❌ FAIL: Conversation history is NOT accumulated!")
        print()
        print("This means:")
        print("  - save=True is not being used")
        print("  - Each round is independent")
        print("  - Agent forgets previous reasoning")
        print()
        print("Fix: Add save=True to agent.run() calls in korgym_adapter.py")
    else:
        print()
        print(f"⚠️  UNEXPECTED: input_items length is {actual_length}")
        print("    (expected either 2 or 6)")
    
    print()
    print("=" * 70)


async def main():
    try:
        await test_conversation_history()
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        print()
        print("=" * 70)
        print("❌ Test failed with error")
        print("=" * 70)
        print(f"Error: {e}")
        print()
        print("Make sure:")
        print("  1. Wordle server is running on localhost:8777")
        print("  2. Agent config is valid")
        print("  3. All dependencies are installed")


if __name__ == "__main__":
    asyncio.run(main())

