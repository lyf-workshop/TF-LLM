"""
Test script for KORGym adapter integration.

This script tests the KORGym adapter by:
1. Starting a 2048 game server
2. Playing a few game rounds
3. Extracting L0 experiences
4. Verifying the integration works
"""

import asyncio
import os
import subprocess
import sys
import time
import requests
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.agents import get_agent
from utu.config import ConfigLoader
from utu.practice.korgym_adapter import KORGymAdapter
from utu.practice.korgym_experience_extractor import KORGymExperienceExtractor
from utu.utils import get_logger

logger = get_logger(__name__)


class GameServerManager:
    """Manages KORGym game server lifecycle."""
    
    def __init__(self, game_path: str, port: int = 8775):
        self.game_path = game_path
        self.port = port
        self.process = None
    
    def check_health(self, max_retries: int = 10, retry_delay: float = 1.0) -> bool:
        """Check if server is healthy."""
        for i in range(max_retries):
            try:
                response = requests.get(f"http://localhost:{self.port}/docs", timeout=2)
                if response.status_code == 200:
                    return True
            except:
                pass
            
            if i < max_retries - 1:
                logger.info(f"   Waiting for server... ({i+1}/{max_retries})")
                time.sleep(retry_delay)
        
        return False
    
    def start(self):
        """Start the game server."""
        logger.info(f"Starting game server at port {self.port}...")
        
        # Change to game directory
        game_dir = Path(self.game_path).parent
        game_file = Path(self.game_path).name
        
        logger.info(f"   Game directory: {game_dir}")
        logger.info(f"   Game file: {game_file}")
        
        # Start server
        self.process = subprocess.Popen(
            [sys.executable, game_file, "-p", str(self.port), "-H", "0.0.0.0"],
            cwd=game_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        logger.info(f"   Server process started (PID: {self.process.pid})")
        
        # Wait for server to be healthy
        if self.check_health():
            logger.info(f"   ✓ Game server is ready at http://localhost:{self.port}")
            logger.info(f"   ✓ API docs: http://localhost:{self.port}/docs")
        else:
            # Get error output
            stderr_output = self.process.stderr.read() if self.process.stderr else ""
            stdout_output = self.process.stdout.read() if self.process.stdout else ""
            
            logger.error(f"   ✗ Server failed to start within timeout")
            if stdout_output:
                logger.error(f"   STDOUT: {stdout_output[:500]}")
            if stderr_output:
                logger.error(f"   STDERR: {stderr_output[:500]}")
            
            self.stop()
            raise RuntimeError(f"Game server failed to start on port {self.port}")
    
    def stop(self):
        """Stop the game server."""
        if self.process:
            logger.info("Stopping game server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Server did not stop gracefully, killing...")
                self.process.kill()
                self.process.wait()
            logger.info("Game server stopped")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


async def test_korgym_adapter():
    """Test the KORGym adapter with 2048 game."""
    
    logger.info("=" * 60)
    logger.info("Testing KORGym Adapter Integration")
    logger.info("=" * 60)
    
    # Configuration
    game_lib_path = Path(__file__).parent.parent / "KORGym" / "game_lib"
    game_2048_path = game_lib_path / "3-2048" / "game_lib.py"
    
    if not game_2048_path.exists():
        logger.error(f"Game file not found: {game_2048_path}")
        logger.error("Please ensure KORGym is in the project root directory")
        return
    
    # Start game server
    with GameServerManager(str(game_2048_path), port=8775):
        
        # Initialize adapter
        logger.info("\n1. Initializing KORGym Adapter...")
        adapter = KORGymAdapter(
            game_name="3-2048",
            game_host="localhost",
            game_port=8775,
            level=4,
            max_rounds=100
        )
        
        logger.info(f"   Game Category: {adapter.game_category}")
        logger.info(f"   Game Type: {adapter.game_type}")
        logger.info(f"   Is Multimodal: {adapter.is_multimodal}")
        
        # Load agent
        logger.info("\n2. Loading Agent...")
        agent_config = ConfigLoader.load_agent_config(
            "practice/logic_agent_hierarchical_learning_clean"
        )
        agent = get_agent(agent_config)
        logger.info(f"   Agent loaded: {agent.config.agent.name}")
        
        # Initialize experience extractor
        logger.info("\n3. Initializing Experience Extractor...")
        extractor = KORGymExperienceExtractor(
            llm_config=agent_config.model.model_provider.model_dump()
        )
        
        # Play a few game rounds
        logger.info("\n4. Playing Game Rounds...")
        results = []
        
        for seed in range(3):  # Play 3 games
            logger.info(f"\n   Playing game with seed {seed}...")
            
            try:
                result = await adapter.play_game(agent, seed)
                results.append(result)
                
                logger.info(f"   ✓ Game completed:")
                logger.info(f"     - Success: {result['success']}")
                logger.info(f"     - Score: {result.get('final_score', result.get('score', 0))}")
                logger.info(f"     - Rounds: {result.get('rounds', 1)}")
                logger.info(f"     - Time: {result['response_time']:.2f}s")
                
            except Exception as e:
                logger.error(f"   ✗ Game failed: {e}")
                continue
        
        # Extract experiences
        logger.info("\n5. Extracting L0 Experiences...")
        experiences = []
        
        for i, result in enumerate(results):
            logger.info(f"\n   Extracting experience from game {i}...")
            
            try:
                experience = await extractor.extract_l0_from_round(
                    result,
                    adapter.game_category,
                    adapter.game_type
                )
                experiences.append(experience)
                
                logger.info(f"   ✓ Experience extracted:")
                logger.info(f"     {experience[:150]}...")
                
            except Exception as e:
                logger.error(f"   ✗ Extraction failed: {e}")
                continue
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("Test Summary")
        logger.info("=" * 60)
        logger.info(f"Games Played: {len(results)}")
        logger.info(f"Experiences Extracted: {len(experiences)}")
        
        if results:
            logger.info(f"Success Rate: {sum(r['success'] for r in results) / len(results) * 100:.1f}%")
            logger.info(f"Avg Score: {sum(r.get('final_score', r.get('score', 0)) for r in results) / len(results):.1f}")
            logger.info(f"Avg Rounds: {sum(r.get('rounds', 1) for r in results) / len(results):.1f}")
        else:
            logger.warning("No games completed successfully!")
        
        logger.info("=" * 60)
        
        # Save test results
        output_dir = Path("workspace") / "korgym_test"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        import json
        with open(output_dir / "test_results.json", "w") as f:
            json.dump({
                'games': results,
                'experiences': experiences,
                'summary': {
                    'num_games': len(results),
                    'num_experiences': len(experiences),
                    'success_rate': sum(r['success'] for r in results) / len(results) if results else 0,
                }
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\nTest results saved to: {output_dir / 'test_results.json'}")
        logger.info("\n✓ KORGym adapter test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_korgym_adapter())


