#!/usr/bin/env python3
"""
KORGym Evaluation Script

Evaluates an agent on KORGym games by playing multiple game instances.

Usage:
    python scripts/run_korgym_eval.py --config_name korgym/word_puzzle_baseline
"""

import argparse
import asyncio
import time
from datetime import datetime
from pathlib import Path

from utu.agents import get_agent
from utu.config import ConfigLoader
from utu.db import EvaluationSample
from utu.practice.korgym_adapter import KORGymAdapter
from utu.utils import get_logger, SQLModelUtils

logger = get_logger(__name__)


async def evaluate_korgym(config_name: str):
    """
    Evaluate agent on KORGym game.
    
    Args:
        config_name: Name of the evaluation config
    """
    logger.info(f"Loading config: {config_name}")
    config = ConfigLoader.load_eval_config(config_name)
    
    # Check if KORGym is enabled
    if not hasattr(config, 'korgym') or not config.korgym.enabled:
        logger.error("KORGym is not enabled in this config")
        return
    
    exp_id = config.exp_id
    game_name = config.korgym.game_name
    num_seeds = config.korgym.num_seeds
    
    logger.info(f"=" * 70)
    logger.info(f"KORGym Evaluation: {exp_id}")
    logger.info(f"=" * 70)
    logger.info(f"Game: {game_name}")
    logger.info(f"Number of games: {num_seeds}")
    logger.info(f"Agent: {config.agent.agent.name}")
    logger.info("")
    
    # Initialize KORGym adapter
    adapter = KORGymAdapter(
        game_name=game_name,
        game_host=config.korgym.game_host,
        game_port=config.korgym.game_port,
        level=config.korgym.level,
        max_rounds=getattr(config.korgym, 'max_rounds', 50)
    )
    
    logger.info(f"Game Category: {adapter.game_category}")
    logger.info(f"Game Type: {adapter.game_type}")
    logger.info(f"Is Multimodal: {adapter.is_multimodal}")
    logger.info("")
    
    # Load agent
    logger.info("Loading agent...")
    agent = get_agent(config.agent)
    logger.info(f"✓ Agent loaded: {config.agent.agent.name}")
    logger.info("")
    
    # Play games and collect results
    results = []
    db = SQLModelUtils.create_session()
    
    try:
        logger.info(f"Starting evaluation ({num_seeds} games)...")
        logger.info("")
        
        for seed in range(num_seeds):
            logger.info(f"Game {seed + 1}/{num_seeds} (seed={seed})...")
            
            try:
                # Play game
                start_time = time.time()
                result = await adapter.play_game(agent, seed)
                elapsed = time.time() - start_time
                
                success = result.get('success', False)
                score = result.get('final_score', result.get('score', 0))
                rounds = result.get('rounds', 1)
                
                logger.info(f"  Result: {'✓ Success' if success else '✗ Failed'}")
                logger.info(f"  Score: {score}")
                logger.info(f"  Rounds: {rounds}")
                logger.info(f"  Time: {elapsed:.2f}s")
                
                # Save to database
                eval_sample = EvaluationSample(
                    exp_id=exp_id,
                    dataset=config.data.dataset if hasattr(config, 'data') else f"KORGym-{game_name}",
                    dataset_index=seed,
                    source=game_name,
                    raw_question=f"Play {game_name} (seed={seed})",
                    correct=success,
                    response=str(result.get('response', '')),
                    time_cost=elapsed,
                    stage="judged",
                    reward=score / 100.0 if score > 0 else 0.0,  # Normalize to 0-1
                    meta={
                        'game_name': game_name,
                        'seed': seed,
                        'score': score,
                        'rounds': rounds,
                        'game_category': adapter.game_category,
                        'game_type': adapter.game_type,
                        'success': success,
                    }
                )
                db.add(eval_sample)
                db.commit()
                
                results.append({
                    'seed': seed,
                    'success': success,
                    'score': score,
                    'rounds': rounds,
                    'time': elapsed
                })
                
            except Exception as e:
                logger.error(f"  ✗ Game failed: {e}")
                # Save failure to database
                eval_sample = EvaluationSample(
                    exp_id=exp_id,
                    dataset=config.data.dataset if hasattr(config, 'data') else f"KORGym-{game_name}",
                    dataset_index=seed,
                    source=game_name,
                    raw_question=f"Play {game_name} (seed={seed})",
                    correct=False,
                    response=f"Error: {str(e)}",
                    time_cost=0,
                    stage="judged",
                    reward=0.0,
                    meta={
                        'game_name': game_name,
                        'seed': seed,
                        'error': str(e),
                        'game_category': adapter.game_category,
                        'game_type': adapter.game_type,
                    }
                )
                db.add(eval_sample)
                db.commit()
                
                results.append({
                    'seed': seed,
                    'success': False,
                    'score': 0,
                    'error': str(e)
                })
            
            logger.info("")
        
        # Print summary
        logger.info("=" * 70)
        logger.info("Evaluation Summary")
        logger.info("=" * 70)
        logger.info(f"Experiment ID: {exp_id}")
        logger.info(f"Total games: {len(results)}")
        logger.info(f"Successful: {sum(1 for r in results if r['success'])}")
        logger.info(f"Failed: {sum(1 for r in results if not r['success'])}")
        
        if results:
            success_rate = sum(1 for r in results if r['success']) / len(results) * 100
            avg_score = sum(r['score'] for r in results) / len(results)
            logger.info(f"Success rate: {success_rate:.1f}%")
            logger.info(f"Average score: {avg_score:.2f}")
        
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"✓ Results saved to database with exp_id: {exp_id}")
        logger.info(f"  Query: SELECT * FROM evaluation_data WHERE exp_id='{exp_id}';")
        
    finally:
        db.close()
    
    return results


def main():
    parser = argparse.ArgumentParser(description="KORGym Evaluation")
    parser.add_argument(
        '--config_name',
        type=str,
        required=True,
        help='Config name (e.g., korgym/word_puzzle_baseline)'
    )
    
    args = parser.parse_args()
    
    # Run evaluation
    asyncio.run(evaluate_korgym(args.config_name))


if __name__ == "__main__":
    main()

