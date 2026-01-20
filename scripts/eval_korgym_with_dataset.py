"""
Evaluate KORGym agent using dataset-based approach (similar to training)
Load game seeds from database and evaluate using KORGymAdapter directly
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict

import numpy as np
from tqdm import tqdm

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.agents import get_agent
from utu.config import ConfigLoader
from utu.practice.korgym_adapter import KORGymAdapter
from utu.utils import get_logger, SQLModelUtils
from utu.db import DatasetSample
from sqlmodel import select

logger = get_logger(__name__)


class DatasetBasedEvaluator:
    """从数据库加载游戏种子进行评估"""
    
    def __init__(
        self,
        agent_config_name: str,
        dataset_name: str,
        game_name: str = "8-word_puzzle",
        game_port: int = 8775,
        level: int = 4,
    ):
        self.agent_config_name = agent_config_name
        self.dataset_name = dataset_name
        self.game_name = game_name
        self.level = level
        
        # 初始化 KORGym Adapter
        self.adapter = KORGymAdapter(
            game_name=game_name,
            game_host="localhost",
            game_port=game_port,
            level=level,
            max_rounds=50
        )
        
        # 加载 Agent
        logger.info(f"Loading agent config: {agent_config_name}")
        agent_config = ConfigLoader.load_agent_config(agent_config_name)
        self.agent = get_agent(agent_config)
        logger.info(f"✓ Agent loaded: {agent_config.agent.name}")
        
        # 从数据库加载游戏种子
        self.seeds = self._load_seeds_from_db()
        logger.info(f"✓ Loaded {len(self.seeds)} game seeds from dataset: {dataset_name}")
    
    def _load_seeds_from_db(self) -> List[int]:
        """从数据库加载游戏种子"""
        seeds = []
        with SQLModelUtils.create_session() as session:
            samples = session.exec(
                select(DatasetSample).where(DatasetSample.dataset == self.dataset_name)
            ).all()
            
            if not samples:
                raise ValueError(f"Dataset {self.dataset_name} not found in database")
            
            for sample in samples:
                if sample.meta and "seed" in sample.meta:
                    seeds.append(sample.meta["seed"])
                else:
                    logger.warning(f"Sample {sample.dataset_index} has no seed in meta")
        
        return sorted(seeds)
    
    async def evaluate_single_game(self, seed: int) -> Dict:
        """评估单个游戏实例"""
        try:
            # 使用 adapter 的 play_game 方法
            result = await self.adapter.play_game(self.agent, seed)
            
            return {
                'seed': seed,
                'score': result.get('score', 0.0),
                'success': result.get('success', False),
                'action': result.get('action', ''),
                'response': result.get('response', '')[:200] if result.get('response') else '',
            }
        except Exception as e:
            logger.error(f"Error evaluating seed {seed}: {e}")
            return {
                'seed': seed,
                'score': 0.0,
                'success': False,
                'error': str(e)
            }
    
    async def evaluate_all(self) -> Dict:
        """评估所有游戏"""
        logger.info(f"Starting evaluation of {len(self.seeds)} games")
        
        results = []
        for seed in tqdm(self.seeds, desc="Evaluating"):
            result = await self.evaluate_single_game(seed)
            results.append(result)
        
        # 计算统计信息
        scores = [r['score'] for r in results]
        avg_score = np.mean(scores)
        std_score = np.std(scores)
        
        summary = {
            'num_games': len(results),
            'average_score': float(avg_score),
            'std_score': float(std_score),
            'min_score': float(np.min(scores)),
            'max_score': float(np.max(scores)),
            'success_rate': float(np.mean([s > 0 for s in scores])),
            'detailed_results': results
        }
        
        return summary


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent_config', type=str, required=True, 
                       help='Agent config name (e.g., practice/word_puzzle_qwen_temp1)')
    parser.add_argument('--dataset_name', type=str, required=True,
                       help='Dataset name in database (e.g., KORGym-WordPuzzle-Eval-50)')
    parser.add_argument('--exp_id', type=str, required=True,
                       help='Experiment ID for saving results')
    parser.add_argument('--output_dir', type=str, default='workspace/korgym_eval',
                       help='Output directory for results')
    parser.add_argument('--game_port', type=int, default=8775,
                       help='KORGym server port (default: 8775)')
    parser.add_argument('--game_name', type=str, default='8-word_puzzle',
                       help='KORGym game name (e.g., 8-word_puzzle, 33-wordle, 22-alphabetical_sorting)')
    args = parser.parse_args()
    
    # 创建评估器
    evaluator = DatasetBasedEvaluator(
        agent_config_name=args.agent_config,
        dataset_name=args.dataset_name,
        game_name=args.game_name,
        game_port=args.game_port
    )
    
    # 运行评估
    results = await evaluator.evaluate_all()
    
    # 打印结果
    logger.info("=" * 60)
    logger.info(f"Evaluation Results: {args.exp_id}")
    logger.info("=" * 60)
    logger.info(f"Agent: {args.agent_config}")
    logger.info(f"Dataset: {args.dataset_name}")
    logger.info(f"Games evaluated: {results['num_games']}")
    logger.info(f"Average score: {results['average_score']:.4f}")
    logger.info(f"Std deviation: {results['std_score']:.4f}")
    logger.info(f"Success rate: {results['success_rate']:.2%}")
    logger.info("=" * 60)
    
    # 保存结果
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"{args.exp_id}.json"
    results['experiment_id'] = args.exp_id
    results['agent_config'] = args.agent_config
    results['dataset_name'] = args.dataset_name
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())

