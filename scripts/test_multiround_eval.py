#!/usr/bin/env python3
"""
测试多轮游戏评估功能

用于验证Wordle等多轮游戏的评估流程是否正确工作。

用法:
    # 测试2个Wordle样本
    uv run python scripts/test_multiround_eval.py --game_name "33-wordle" --seeds 1 2
    
    # 测试5个样本并显示详细信息
    uv run python scripts/test_multiround_eval.py --game_name "33-wordle" --seeds 1 2 3 4 5 --verbose
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.config import ConfigLoader
from utu.eval.benchmarks import BaseBenchmark
from utu.db import DatasetSample, EvaluationSample
from utu.utils import SQLModelUtils, get_logger
from sqlmodel import select, delete

logger = get_logger(__name__)


def create_test_samples(game_name: str, seeds: list[int], dataset_name: str):
    """创建测试样本"""
    print(f"\n{'='*80}")
    print(f"创建测试样本: {game_name}")
    print(f"{'='*80}")
    
    with SQLModelUtils.create_session() as session:
        # 清理旧的测试数据
        session.exec(delete(DatasetSample).where(DatasetSample.dataset == dataset_name))
        session.exec(delete(EvaluationSample).where(EvaluationSample.exp_id == "test_multiround"))
        session.commit()
        
        # 创建新样本
        samples = []
        for seed in seeds:
            sample = DatasetSample(
                dataset=dataset_name,
                source="KORGym",
                question=f"Play KORGym game '{game_name}' with seed {seed}",
                answer="success",
                meta={
                    "seed": seed,
                    "game_name": game_name,
                    "dataset_type": "test"
                }
            )
            samples.append(sample)
        
        for sample in samples:
            session.add(sample)
        session.commit()
        
        print(f"✓ 创建了 {len(samples)} 个测试样本")
        print(f"  Seeds: {seeds}")
        print(f"  Dataset: {dataset_name}")


async def run_test_evaluation(config_name: str, verbose: bool = False):
    """运行测试评估"""
    print(f"\n{'='*80}")
    print(f"运行测试评估: {config_name}")
    print(f"{'='*80}\n")
    
    # 加载配置
    config = ConfigLoader.load_eval_config(name=config_name)
    config.exp_id = "test_multiround"  # 使用测试exp_id
    
    # 创建benchmark
    benchmark = BaseBenchmark(config)
    
    # 执行评估
    print("阶段1: Preprocessing...")
    benchmark.preprocess()
    
    print("\n阶段2: Rollout (多轮交互)...")
    await benchmark.rollout()
    
    print("\n阶段3: Judging...")
    await benchmark.judge()
    
    print("\n阶段4: Statistics...")
    results = await benchmark.stat()
    
    # 显示结果
    print(f"\n{'='*80}")
    print("测试结果")
    print(f"{'='*80}")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # 详细信息
    if verbose:
        print(f"\n{'='*80}")
        print("详细样本信息")
        print(f"{'='*80}")
        
        with SQLModelUtils.create_session() as session:
            samples = session.exec(
                select(EvaluationSample).where(
                    EvaluationSample.exp_id == "test_multiround"
                ).order_by(EvaluationSample.id)
            ).all()
            
            for i, sample in enumerate(samples, 1):
                print(f"\n样本 {i}:")
                print(f"  Seed: {sample.meta.get('seed') if sample.meta else 'N/A'}")
                print(f"  Correct: {sample.correct}")
                print(f"  Reward: {sample.reward}")
                print(f"  Time: {sample.time_cost:.2f}s" if sample.time_cost else "  Time: N/A")
                
                if sample.meta and 'multiround_result' in sample.meta:
                    mr = sample.meta['multiround_result']
                    print(f"  Rounds: {mr.get('rounds', 'N/A')}")
                    print(f"  Final Score: {mr.get('final_score', 'N/A')}")
                    print(f"  Success: {mr.get('success', 'N/A')}")
                    
                    # 显示trajectory
                    if 'trajectory' in mr and mr['trajectory']:
                        print(f"  Trajectory length: {len(mr['trajectory'])}")
                        if verbose:
                            print("  Trajectory:")
                            for j, step in enumerate(mr['trajectory'][:3], 1):  # 只显示前3轮
                                action = step.get('action', 'N/A')
                                score = step.get('score', 0)
                                print(f"    Round {j}: action={action}, score={score}")
    
    return results


def cleanup_test_data():
    """清理测试数据"""
    print(f"\n{'='*80}")
    print("清理测试数据")
    print(f"{'='*80}")
    
    with SQLModelUtils.create_session() as session:
        # 删除测试样本
        dataset_count = len(session.exec(
            select(DatasetSample).where(DatasetSample.dataset.like("Test-%"))
        ).all())
        
        eval_count = len(session.exec(
            select(EvaluationSample).where(EvaluationSample.exp_id == "test_multiround")
        ).all())
        
        session.exec(delete(DatasetSample).where(DatasetSample.dataset.like("Test-%")))
        session.exec(delete(EvaluationSample).where(EvaluationSample.exp_id == "test_multiround"))
        session.commit()
        
        print(f"✓ 删除了 {dataset_count} 个数据集样本")
        print(f"✓ 删除了 {eval_count} 个评估样本")


async def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser(
        description="测试多轮游戏评估功能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--game_name",
        type=str,
        default="33-wordle",
        help="游戏名称 (例如: 33-wordle, 3-2048)"
    )
    
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[1, 2],
        help="测试的种子列表 (例如: 1 2 3)"
    )
    
    parser.add_argument(
        "--config_name",
        type=str,
        default="korgym/wordle_eval",
        help="评估配置名称"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细信息"
    )
    
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="不清理测试数据（用于调试）"
    )
    
    args = parser.parse_args()
    
    # 生成数据集名称
    game_short_name = args.game_name.split('-')[-1].capitalize()
    dataset_name = f"Test-{game_short_name}"
    
    try:
        # 1. 创建测试样本
        create_test_samples(args.game_name, args.seeds, dataset_name)
        
        # 2. 临时修改配置使用测试数据集
        print(f"\n{'='*80}")
        print("注意: 使用测试数据集")
        print(f"{'='*80}")
        print(f"配置文件: {args.config_name}")
        print(f"测试数据集: {dataset_name}")
        print(f"实际评估请使用正式数据集")
        
        # 加载配置并修改dataset
        config = ConfigLoader.load_eval_config(name=args.config_name)
        original_dataset = config.data.dataset
        config.data.dataset = dataset_name
        config.exp_id = "test_multiround"
        
        print(f"原数据集: {original_dataset}")
        print(f"测试数据集: {dataset_name}")
        
        # 3. 运行评估
        benchmark = BaseBenchmark(config)
        await benchmark.main()
        
        # 4. 显示详细结果
        if args.verbose:
            with SQLModelUtils.create_session() as session:
                samples = session.exec(
                    select(EvaluationSample).where(
                        EvaluationSample.exp_id == "test_multiround"
                    )
                ).all()
                
                print(f"\n{'='*80}")
                print(f"详细结果 ({len(samples)} 个样本)")
                print(f"{'='*80}")
                
                for i, sample in enumerate(samples, 1):
                    print(f"\n样本 {i}:")
                    print(f"  Seed: {sample.meta.get('seed') if sample.meta else 'N/A'}")
                    print(f"  Correct: {sample.correct}")
                    print(f"  Reward: {sample.reward}")
                    print(f"  Response: {sample.response[:100]}..." if sample.response else "  Response: None")
                    
                    if sample.meta and 'multiround_result' in sample.meta:
                        mr = sample.meta['multiround_result']
                        print(f"  Multi-round info:")
                        print(f"    Rounds: {mr.get('rounds', 'N/A')}")
                        print(f"    Final Score: {mr.get('final_score', 'N/A')}")
                        print(f"    Success: {mr.get('success', 'N/A')}")
        
        print(f"\n{'='*80}")
        print("✅ 测试完成！")
        print(f"{'='*80}\n")
        
    finally:
        # 5. 清理测试数据
        if not args.no_cleanup:
            cleanup_test_data()
        else:
            print("\n⚠️  测试数据未清理（使用了 --no-cleanup）")


if __name__ == "__main__":
    asyncio.run(main())
