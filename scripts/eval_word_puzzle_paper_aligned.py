#!/usr/bin/env python3
"""
Word Puzzle 论文对齐评估脚本

严格按照 KORGym 论文的评估方式：
- 评估 50 个不同 seed 的游戏
- 计算平均得分（与论文表格中的数值一致）
- 输出格式与论文相同

Usage:
    python scripts/eval_word_puzzle_paper_aligned.py --exp_id my_baseline_eval
"""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import List, Dict

import numpy as np
from tqdm import tqdm

from utu.agents import get_agent
from utu.config import ConfigLoader
from utu.practice.korgym_adapter import KORGymAdapter
from utu.utils import get_logger

logger = get_logger(__name__)


class PaperAlignedEvaluator:
    """与 KORGym 论文对齐的评估器"""
    
    def __init__(
        self,
        agent_config_name: str,
        game_name: str = "8-word_puzzle",
        game_port: int = 8775,
        num_seeds: int = 50,  # 论文使用 50 局
        level: int = 4,  # 论文默认 level 4
    ):
        """
        初始化评估器
        
        Args:
            agent_config_name: Agent 配置名称
            game_name: 游戏名称
            game_port: 游戏服务器端口
            num_seeds: 评估的游戏局数（论文使用 50）
            level: 游戏难度级别
        """
        self.agent_config_name = agent_config_name
        self.game_name = game_name
        self.num_seeds = num_seeds
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
    
    async def evaluate_single_game(self, seed: int) -> Dict:
        """
        评估单个游戏实例
        
        Args:
            seed: 游戏种子
            
        Returns:
            游戏结果字典
        """
        try:
            result = await self.adapter.play_game(self.agent, seed)
            
            return {
                'seed': seed,
                'score': result.get('score', 0),  # 这是关键指标
                'success': result.get('success', False),
                'response_time': result.get('response_time', 0),
                'action': result.get('action', ''),
                'response': result.get('response', ''),
            }
        
        except Exception as e:
            logger.error(f"Game seed {seed} failed: {e}")
            return {
                'seed': seed,
                'score': 0,
                'success': False,
                'response_time': 0,
                'error': str(e)
            }
    
    async def evaluate_all(self) -> Dict:
        """
        评估所有游戏实例
        
        Returns:
            完整的评估结果
        """
        logger.info("=" * 70)
        logger.info("  KORGym Word Puzzle - Paper Aligned Evaluation")
        logger.info("=" * 70)
        logger.info(f"Game: {self.game_name}")
        logger.info(f"Agent: {self.agent_config_name}")
        logger.info(f"Number of games: {self.num_seeds}")
        logger.info(f"Level: {self.level}")
        logger.info("")
        
        results = []
        start_time = time.time()
        
        # 使用 tqdm 显示进度
        for seed in tqdm(range(self.num_seeds), desc="Evaluating"):
            result = await self.evaluate_single_game(seed)
            results.append(result)
            
            # 显示当前进度
            if (seed + 1) % 10 == 0:
                current_scores = [r['score'] for r in results]
                current_avg = np.mean(current_scores)
                tqdm.write(f"  Progress: {seed + 1}/{self.num_seeds}, "
                          f"Current avg score: {current_avg:.4f}")
        
        total_time = time.time() - start_time
        
        # 计算统计数据
        scores = [r['score'] for r in results]
        avg_score = np.mean(scores)
        std_score = np.std(scores)
        max_score = np.max(scores)
        min_score = np.min(scores)
        
        # 计算不同分数区间的分布
        score_distribution = {
            '0.0': sum(1 for s in scores if s == 0),
            '0.0-0.2': sum(1 for s in scores if 0 < s <= 0.2),
            '0.2-0.4': sum(1 for s in scores if 0.2 < s <= 0.4),
            '0.4-0.6': sum(1 for s in scores if 0.4 < s <= 0.6),
            '0.6-0.8': sum(1 for s in scores if 0.6 < s <= 0.8),
            '0.8-1.0': sum(1 for s in scores if 0.8 < s <= 1.0),
        }
        
        summary = {
            'agent_config': self.agent_config_name,
            'game_name': self.game_name,
            'num_games': self.num_seeds,
            'level': self.level,
            'avg_score': float(avg_score),  # 这是论文表格中的数值
            'std_score': float(std_score),
            'max_score': float(max_score),
            'min_score': float(min_score),
            'score_distribution': score_distribution,
            'total_time': total_time,
            'avg_time_per_game': total_time / self.num_seeds,
            'results': results,
        }
        
        return summary
    
    def print_results(self, summary: Dict):
        """
        打印评估结果（论文格式）
        
        Args:
            summary: 评估结果摘要
        """
        logger.info("")
        logger.info("=" * 70)
        logger.info("  Evaluation Results (Paper Format)")
        logger.info("=" * 70)
        logger.info("")
        
        # 关键指标（与论文表格对应）
        logger.info("📊 Paper Table Metrics:")
        logger.info(f"  Average Score: {summary['avg_score']:.3f}")
        logger.info(f"  → This is the value shown in the paper table!")
        logger.info("")
        
        # 详细统计
        logger.info("📈 Detailed Statistics:")
        logger.info(f"  Number of games: {summary['num_games']}")
        logger.info(f"  Average score: {summary['avg_score']:.4f}")
        logger.info(f"  Std deviation: {summary['std_score']:.4f}")
        logger.info(f"  Max score: {summary['max_score']:.4f}")
        logger.info(f"  Min score: {summary['min_score']:.4f}")
        logger.info("")
        
        # 分数分布
        logger.info("📊 Score Distribution:")
        for range_str, count in summary['score_distribution'].items():
            percentage = count / summary['num_games'] * 100
            bar = "█" * int(percentage / 2)
            logger.info(f"  {range_str:8s}: {bar} {count:3d} ({percentage:5.1f}%)")
        logger.info("")
        
        # 时间统计
        logger.info("⏱️  Time Statistics:")
        logger.info(f"  Total time: {summary['total_time']:.2f}s")
        logger.info(f"  Avg time per game: {summary['avg_time_per_game']:.2f}s")
        logger.info("")
        
        # 与论文对比
        logger.info("📖 Comparison with Paper (Table 7):")
        paper_scores = {
            'O1-2024-12-17': 0.960,
            'Gemini-2.5-pro-03-25': 0.900,
            'Claude-3.7-thinking': 0.820,
            'DeepSeek-R1': 0.820,
            'O3-mini': 0.880,
            'Claude-3.7': 0.580,
            'DeepSeek-v3-0324': 0.460,
            'GPT-4o': 0.420,
            'Doubao-1.5-thinking-pro': 0.600,
            'Doubao-1.5-pro': 0.120,
        }
        
        logger.info(f"  Your score: {summary['avg_score']:.3f}")
        logger.info("")
        
        # 找到最接近的模型
        closest_model = min(
            paper_scores.items(),
            key=lambda x: abs(x[1] - summary['avg_score'])
        )
        logger.info(f"  Closest to: {closest_model[0]} ({closest_model[1]:.3f})")
        
        # 排名
        better_than = sum(1 for score in paper_scores.values() 
                         if summary['avg_score'] > score)
        logger.info(f"  Better than {better_than}/{len(paper_scores)} models in the paper")
        logger.info("")
        
        logger.info("=" * 70)
    
    def save_results(self, summary: Dict, output_path: str):
        """
        保存结果到文件
        
        Args:
            summary: 评估结果摘要
            output_path: 输出文件路径
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ Results saved to: {output_file}")
        
        # 同时保存一个简单的分数文件（模仿论文）
        score_file = output_file.parent / "score.txt"
        with open(score_file, 'a', encoding='utf-8') as f:
            f.write(f"{summary['agent_config']}: {summary['avg_score']:.4f}\n")
        
        logger.info(f"✓ Score appended to: {score_file}")


async def main():
    parser = argparse.ArgumentParser(
        description="Word Puzzle evaluation aligned with KORGym paper"
    )
    parser.add_argument(
        '--agent_config',
        type=str,
        default='practice/logic_agent_hierarchical_learning_clean',
        help='Agent config name'
    )
    parser.add_argument(
        '--exp_id',
        type=str,
        required=True,
        help='Experiment ID (for output filename)'
    )
    parser.add_argument(
        '--num_seeds',
        type=int,
        default=50,
        help='Number of games to evaluate (paper uses 50)'
    )
    parser.add_argument(
        '--level',
        type=int,
        default=4,
        help='Game difficulty level (1-5)'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default='workspace/korgym_paper_aligned',
        help='Output directory'
    )
    
    args = parser.parse_args()
    
    # 创建评估器
    evaluator = PaperAlignedEvaluator(
        agent_config_name=args.agent_config,
        game_name="8-word_puzzle",
        num_seeds=args.num_seeds,
        level=args.level,
    )
    
    # 运行评估
    summary = await evaluator.evaluate_all()
    
    # 打印结果
    evaluator.print_results(summary)
    
    # 保存结果
    output_path = f"{args.output_dir}/{args.exp_id}_word_puzzle.json"
    evaluator.save_results(summary, output_path)
    
    logger.info("")
    logger.info("✅ Evaluation completed!")
    logger.info("")
    logger.info(f"📊 Your score for the paper table: {summary['avg_score']:.3f}")


if __name__ == "__main__":
    asyncio.run(main())











