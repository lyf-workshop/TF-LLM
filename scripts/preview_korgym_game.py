"""
Preview a KORGym game by seed
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.practice.korgym_adapter import KORGymAdapter
from utu.config.practice_config import KORGymConfig
import json


def preview_game(game_name: str, seed: int, game_port: int = 8765):
    """Preview a specific KORGym game"""
    
    print(f"\n{'='*80}")
    print(f"Previewing KORGym Game")
    print(f"{'='*80}")
    print(f"Game: {game_name}")
    print(f"Seed: {seed}")
    print(f"Port: {game_port}")
    print()
    
    # Initialize KORGym adapter
    adapter = KORGymAdapter(
        game_name=game_name,
        game_host="localhost",
        game_port=game_port,
        level=4,
        max_rounds=100
    )
    
    try:
        # Generate the game with the specific seed
        game_state = adapter.generate_game_instance(seed)
        prompt = adapter.get_game_prompt(game_state)
        
        print(f"{'='*80}")
        print(f"Game Prompt (What the Agent Sees):")
        print(f"{'='*80}")
        print(prompt)
        print()
        
        print(f"{'='*80}")
        print(f"Game State Metadata:")
        print(f"{'='*80}")
        print(f"Seed: {game_state.get('seed', 'N/A')}")
        print(f"State Keys: {list(game_state.keys())}")
        if 'info' in game_state:
            print(f"Info: {json.dumps(game_state['info'], indent=2)}")
        print()
        
        # Show what a sample action would look like
        print(f"{'='*80}")
        print(f"Expected Action Format:")
        print(f"{'='*80}")
        print('Agent should respond with: Answer: ["WORD1", "WORD2", ...]')
        print('(A list of words that form valid connections)')
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure KORGym server is running on the specified port!")
        print(f"Start server with: cd KORGym && python -m korgym.server --port {game_port}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--game_name', type=str, default="Word Problem",
                       help='Name of the KORGym game')
    parser.add_argument('--seed', type=int, required=True,
                       help='Game seed to preview')
    parser.add_argument('--game_port', type=int, default=8765,
                       help='KORGym server port')
    args = parser.parse_args()
    
    preview_game(args.game_name, args.seed, args.game_port)

