"""
Quick script to start a KORGym game server.

Usage:
    uv run python scripts/korgym/start_korgym_server.py 3-2048
    uv run python scripts/korgym/start_korgym_server.py 4-SudoKu --port 8776
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Start a KORGym game server")
    parser.add_argument(
        "game_name",
        type=str,
        help="Game name (e.g., '3-2048', '4-SudoKu')"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8775,
        help="Port number (default: 8775)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address (default: 0.0.0.0)"
    )
    
    args = parser.parse_args()
    
    # Find game directory
    game_lib_path = Path(__file__).resolve().parents[2] / "KORGym" / "game_lib"
    game_path = game_lib_path / args.game_name / "game_lib.py"
    
    if not game_path.exists():
        print(f"❌ Game not found: {game_path}")
        print(f"\nAvailable games:")
        if game_lib_path.exists():
            for game_dir in sorted(game_lib_path.iterdir()):
                if game_dir.is_dir() and not game_dir.name.startswith('.'):
                    print(f"  - {game_dir.name}")
        sys.exit(1)
    
    print(f"🎮 Starting {args.game_name} server...")
    print(f"   Host: {args.host}")
    print(f"   Port: {args.port}")
    print(f"   Path: {game_path}")
    print(f"\n📊 API docs: http://localhost:{args.port}/docs")
    print(f"🛑 Press Ctrl+C to stop\n")
    
    # Start server
    try:
        subprocess.run(
            [sys.executable, "game_lib.py", "-H", args.host, "-p", str(args.port)],
            cwd=game_path.parent
        )
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped")


if __name__ == "__main__":
    main()












