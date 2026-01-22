"""
查看数据库中的数据集
View datasets in database

用法 / Usage:
1. 列出所有数据集 / List all datasets:
   python scripts/utils/view_datasets.py --list

2. 查看特定数据集详情 / View specific dataset details:
   python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20"

3. 查看数据集样本 / View dataset samples:
   python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20" --samples 5

4. 查看所有 KORGym 数据集 / View all KORGym datasets:
   python scripts/utils/view_datasets.py --filter KORGym

5. 导出数据集信息到 JSON / Export dataset info to JSON:
   python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20" --export dataset_info.json
"""

import argparse
import json
from typing import Optional
from sqlmodel import select
from utu.db import DatasetSample, EvaluationSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def list_all_datasets(filter_pattern: Optional[str] = None):
    """列出所有数据集及其基本信息"""
    with SQLModelUtils.create_session() as session:
        # 获取所有数据集名称
        dataset_names = session.exec(
            select(DatasetSample.dataset_name).distinct()
        ).all()
        
        if not dataset_names:
            print("\n❌ 数据库中没有任何数据集\n")
            return
        
        # 过滤数据集
        if filter_pattern:
            dataset_names = [name for name in dataset_names if filter_pattern.lower() in name.lower()]
            if not dataset_names:
                print(f"\n❌ 没有找到匹配 '{filter_pattern}' 的数据集\n")
                return
        
        print("\n" + "=" * 80)
        print("📊 数据集列表 (Datasets)")
        print("=" * 80)
        
        total_samples = 0
        for dataset_name in sorted(dataset_names):
            samples = session.exec(
                select(DatasetSample)
                .where(DatasetSample.dataset_name == dataset_name)
            ).all()
            
            total_samples += len(samples)
            
            # 获取数据集的基本信息
            if samples:
                first_sample = samples[0]
                meta = first_sample.meta or {}
                
                # 提取关键信息
                game_name = meta.get('game_name', 'N/A')
                dataset_type = meta.get('dataset_type', 'N/A')
                
                print(f"\n📦 {dataset_name}")
                print(f"   样本数量: {len(samples)}")
                print(f"   游戏名称: {game_name}")
                print(f"   数据集类型: {dataset_type}")
                
                # 显示种子范围
                seeds = [s.meta.get('seed', 0) for s in samples if s.meta]
                if seeds:
                    print(f"   种子范围: {min(seeds)} - {max(seeds)}")
        
        print("\n" + "=" * 80)
        print(f"📊 总计: {len(dataset_names)} 个数据集, {total_samples} 个样本")
        print("=" * 80 + "\n")


def view_dataset_details(dataset_name: str, num_samples: int = 0):
    """查看特定数据集的详细信息"""
    with SQLModelUtils.create_session() as session:
        # 获取数据集样本
        samples = session.exec(
            select(DatasetSample)
            .where(DatasetSample.dataset_name == dataset_name)
        ).all()
        
        if not samples:
            print(f"\n❌ 未找到数据集: {dataset_name}\n")
            return None
        
        print("\n" + "=" * 80)
        print(f"📦 数据集详情: {dataset_name}")
        print("=" * 80)
        
        # 基本统计
        print(f"\n📊 基本信息:")
        print(f"   总样本数: {len(samples)}")
        
        # 从第一个样本获取元数据
        first_sample = samples[0]
        meta = first_sample.meta or {}
        
        if meta:
            print(f"\n🎮 游戏信息:")
            if 'game_name' in meta:
                print(f"   游戏名称: {meta['game_name']}")
            if 'dataset_type' in meta:
                print(f"   数据集类型: {meta['dataset_type']}")
            if 'level' in meta:
                print(f"   难度级别: {meta.get('level', 'N/A')}")
        
        # 种子统计
        seeds = [s.meta.get('seed', 0) for s in samples if s.meta]
        if seeds:
            print(f"\n🌱 种子信息:")
            print(f"   种子范围: {min(seeds)} - {max(seeds)}")
            print(f"   种子数量: {len(set(seeds))}")
        
        # 查看是否有关联的评估实验
        eval_exps = session.exec(
            select(EvaluationSample.exp_id).distinct()
            .where(EvaluationSample.dataset == dataset_name)
        ).all()
        
        if eval_exps:
            print(f"\n🔬 关联的评估实验:")
            for exp_id in sorted(eval_exps):
                exp_samples = session.exec(
                    select(EvaluationSample)
                    .where(EvaluationSample.exp_id == exp_id)
                ).all()
                print(f"   - {exp_id} ({len(exp_samples)} 样本)")
        
        # 显示样本示例
        if num_samples > 0:
            print(f"\n📝 样本示例 (前 {min(num_samples, len(samples))} 个):")
            print("-" * 80)
            
            for i, sample in enumerate(samples[:num_samples], 1):
                print(f"\n样本 #{i} (ID: {sample.id})")
                print(f"  数据集索引: {sample.dataset_index}")
                
                if sample.meta:
                    print(f"  元数据:")
                    for key, value in sample.meta.items():
                        # 限制显示长度
                        if isinstance(value, str) and len(value) > 100:
                            value = value[:100] + "..."
                        print(f"    - {key}: {value}")
                
                if sample.question:
                    q_preview = sample.question[:200] + "..." if len(sample.question) > 200 else sample.question
                    print(f"  问题: {q_preview}")
                
                if sample.answer:
                    a_preview = sample.answer[:200] + "..." if len(sample.answer) > 200 else sample.answer
                    print(f"  答案: {a_preview}")
        
        print("\n" + "=" * 80 + "\n")
        
        return {
            "dataset_name": dataset_name,
            "total_samples": len(samples),
            "seeds": sorted(list(set(seeds))) if seeds else [],
            "meta": meta,
            "related_experiments": sorted(eval_exps) if eval_exps else []
        }


def export_dataset_info(dataset_name: str, output_file: str):
    """导出数据集信息到 JSON 文件"""
    info = view_dataset_details(dataset_name, num_samples=0)
    
    if info is None:
        return
    
    with SQLModelUtils.create_session() as session:
        samples = session.exec(
            select(DatasetSample)
            .where(DatasetSample.dataset_name == dataset_name)
        ).all()
        
        # 准备导出数据
        export_data = {
            "dataset_name": dataset_name,
            "total_samples": len(samples),
            "seeds": info["seeds"],
            "meta": info["meta"],
            "related_experiments": info["related_experiments"],
            "samples": []
        }
        
        # 添加所有样本
        for sample in samples:
            sample_data = {
                "id": sample.id,
                "dataset_index": sample.dataset_index,
                "question": sample.question,
                "answer": sample.answer,
                "meta": sample.meta
            }
            export_data["samples"].append(sample_data)
        
        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 数据集信息已导出到: {output_file}")
        print(f"  包含 {len(samples)} 个样本的完整信息\n")


def compare_datasets(dataset_names: list[str]):
    """对比多个数据集"""
    print("\n" + "=" * 80)
    print("📊 数据集对比")
    print("=" * 80)
    
    with SQLModelUtils.create_session() as session:
        for dataset_name in dataset_names:
            samples = session.exec(
                select(DatasetSample)
                .where(DatasetSample.dataset_name == dataset_name)
            ).all()
            
            if not samples:
                print(f"\n❌ {dataset_name}: 未找到")
                continue
            
            seeds = [s.meta.get('seed', 0) for s in samples if s.meta]
            meta = samples[0].meta or {}
            
            print(f"\n📦 {dataset_name}")
            print(f"   样本数: {len(samples)}")
            print(f"   种子范围: {min(seeds) if seeds else 'N/A'} - {max(seeds) if seeds else 'N/A'}")
            print(f"   游戏: {meta.get('game_name', 'N/A')}")
            print(f"   类型: {meta.get('dataset_type', 'N/A')}")
    
    print("\n" + "=" * 80 + "\n")


def search_datasets_by_game(game_name: str):
    """根据游戏名称搜索数据集"""
    with SQLModelUtils.create_session() as session:
        all_samples = session.exec(select(DatasetSample)).all()
        
        matching_datasets = {}
        for sample in all_samples:
            if sample.meta and sample.meta.get('game_name') == game_name:
                dataset_name = sample.dataset_name
                if dataset_name not in matching_datasets:
                    matching_datasets[dataset_name] = []
                matching_datasets[dataset_name].append(sample)
        
        if not matching_datasets:
            print(f"\n❌ 没有找到游戏 '{game_name}' 的数据集\n")
            return
        
        print("\n" + "=" * 80)
        print(f"🎮 游戏 '{game_name}' 的数据集")
        print("=" * 80)
        
        for dataset_name, samples in sorted(matching_datasets.items()):
            seeds = [s.meta.get('seed', 0) for s in samples if s.meta]
            meta = samples[0].meta or {}
            
            print(f"\n📦 {dataset_name}")
            print(f"   样本数: {len(samples)}")
            print(f"   种子范围: {min(seeds)} - {max(seeds)}")
            print(f"   类型: {meta.get('dataset_type', 'N/A')}")
        
        print("\n" + "=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="查看数据库中的数据集 / View datasets in database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有数据集"
    )
    
    parser.add_argument(
        "--dataset", "-d",
        type=str,
        help="查看特定数据集的详细信息"
    )
    
    parser.add_argument(
        "--samples", "-s",
        type=int,
        default=0,
        help="显示的样本数量（默认不显示样本）"
    )
    
    parser.add_argument(
        "--filter", "-f",
        type=str,
        help="过滤数据集名称（支持部分匹配）"
    )
    
    parser.add_argument(
        "--export", "-e",
        type=str,
        help="导出数据集信息到 JSON 文件"
    )
    
    parser.add_argument(
        "--compare", "-c",
        nargs="+",
        help="对比多个数据集"
    )
    
    parser.add_argument(
        "--game", "-g",
        type=str,
        help="根据游戏名称搜索数据集"
    )
    
    args = parser.parse_args()
    
    # 如果没有任何参数，显示帮助
    if not any([args.list, args.dataset, args.compare, args.game]):
        parser.print_help()
        return
    
    # 列出所有数据集
    if args.list:
        list_all_datasets(filter_pattern=args.filter)
        return
    
    # 查看特定数据集
    if args.dataset:
        if args.export:
            export_dataset_info(args.dataset, args.export)
        else:
            view_dataset_details(args.dataset, num_samples=args.samples)
        return
    
    # 对比数据集
    if args.compare:
        compare_datasets(args.compare)
        return
    
    # 根据游戏搜索
    if args.game:
        search_datasets_by_game(args.game)
        return


if __name__ == "__main__":
    main()


