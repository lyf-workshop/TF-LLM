"""
清理实验数据脚本
Clean experiment data from database

用法 / Usage:
1. 删除所有数据 / Delete all data:
   python scripts/clean_experiment_data.py --all

2. 删除特定实验 / Delete specific experiment:
   python scripts/clean_experiment_data.py --exp_id math_paper_exp_AIME24_eval

3. 删除多个实验 / Delete multiple experiments:
   python scripts/clean_experiment_data.py --exp_id math_paper_exp_AIME24_eval math_paper_exp_AIME25_eval

4. 列出所有实验 / List all experiments:
   python scripts/clean_experiment_data.py --list

5. 删除论文实验相关的所有数据 / Delete all paper experiment data:
   python scripts/clean_experiment_data.py --paper_exp
"""

import argparse
from sqlmodel import Session, create_engine, select, delete
from utu.db import EvaluationSample, DatasetSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def list_experiments():
    """列出所有实验"""
    with SQLModelUtils.create_session() as session:
        # 获取所有 evaluation 实验
        eval_exps = session.exec(
            select(EvaluationSample.exp_id).distinct()
        ).all()
        
        print("\n" + "=" * 70)
        print("评估实验列表 (Evaluation Experiments)")
        print("=" * 70)
        
        if eval_exps:
            for exp_id in sorted(eval_exps):
                count = session.exec(
                    select(EvaluationSample)
                    .where(EvaluationSample.exp_id == exp_id)
                ).all()
                print(f"  - {exp_id} ({len(count)} samples)")
        else:
            print("  (无评估实验)")
        
        # 获取所有数据集
        datasets = session.exec(
            select(DatasetSample.dataset).distinct()
        ).all()
        
        print("\n" + "=" * 70)
        print("数据集列表 (Datasets)")
        print("=" * 70)
        
        if datasets:
            for dataset in sorted(datasets):
                count = session.exec(
                    select(DatasetSample)
                    .where(DatasetSample.dataset == dataset)
                ).all()
                print(f"  - {dataset} ({len(count)} samples)")
        else:
            print("  (无数据集)")
        
        print("\n" + "=" * 70 + "\n")


def delete_all_data(confirm: bool = False):
    """删除所有数据"""
    if not confirm:
        print("\n警告：这将删除数据库中的所有数据！")
        print("包括所有评估结果和数据集。")
        response = input("确认删除？输入 'yes' 继续: ")
        if response.lower() != 'yes':
            print("取消删除。")
            return
    
    with SQLModelUtils.create_session() as session:
        # 删除所有评估样本
        eval_count = session.exec(select(EvaluationSample)).all()
        session.exec(delete(EvaluationSample))
        
        # 删除所有数据集样本
        dataset_count = session.exec(select(DatasetSample)).all()
        session.exec(delete(DatasetSample))
        
        session.commit()
        
        print(f"\n✓ 已删除 {len(eval_count)} 条评估记录")
        print(f"✓ 已删除 {len(dataset_count)} 条数据集记录")
        print("✓ 所有数据已清空\n")


def delete_experiment(exp_ids: list[str]):
    """删除特定实验"""
    with SQLModelUtils.create_session() as session:
        total_deleted = 0
        
        for exp_id in exp_ids:
            # 检查实验是否存在
            samples = session.exec(
                select(EvaluationSample)
                .where(EvaluationSample.exp_id == exp_id)
            ).all()
            
            if not samples:
                print(f"⚠ 未找到实验: {exp_id}")
                continue
            
            # 删除实验
            session.exec(
                delete(EvaluationSample)
                .where(EvaluationSample.exp_id == exp_id)
            )
            
            print(f"✓ 已删除实验 {exp_id} ({len(samples)} 条记录)")
            total_deleted += len(samples)
        
        session.commit()
        print(f"\n✓ 总共删除了 {total_deleted} 条记录\n")


def delete_paper_experiments():
    """删除论文实验相关的所有数据"""
    paper_exp_ids = [
        "math_paper_exp_AIME24_eval",
        "math_paper_exp_AIME25_eval",
        "math_practice_paper_exp_AIME24_eval",
        "math_practice_paper_exp_AIME25_eval",
    ]
    
    print("\n将删除以下论文实验的数据:")
    for exp_id in paper_exp_ids:
        print(f"  - {exp_id}")
    
    response = input("\n确认删除？输入 'yes' 继续: ")
    if response.lower() != 'yes':
        print("取消删除。")
        return
    
    delete_experiment(paper_exp_ids)
    
    # 询问是否删除 DAPO-100 数据集
    print("\n是否也删除 DAPO-100 训练数据集？")
    response = input("输入 'yes' 删除，或直接回车保留: ")
    
    if response.lower() == 'yes':
        delete_dataset(["DAPO-100"])


def delete_dataset(dataset_names: list[str]):
    """删除特定数据集"""
    with SQLModelUtils.create_session() as session:
        total_deleted = 0
        
        for dataset_name in dataset_names:
            # 检查数据集是否存在
            samples = session.exec(
                select(DatasetSample)
                .where(DatasetSample.dataset == dataset_name)
            ).all()
            
            if not samples:
                print(f"⚠ 未找到数据集: {dataset_name}")
                continue
            
            # 删除数据集
            session.exec(
                delete(DatasetSample)
                .where(DatasetSample.dataset == dataset_name)
            )
            
            print(f"✓ 已删除数据集 {dataset_name} ({len(samples)} 条记录)")
            total_deleted += len(samples)
        
        session.commit()
        print(f"\n✓ 总共删除了 {total_deleted} 条记录\n")


def main():
    parser = argparse.ArgumentParser(
        description="清理实验数据 / Clean experiment data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有实验和数据集"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="删除所有数据（需要确认）"
    )
    
    parser.add_argument(
        "--exp_id", "-e",
        nargs="+",
        help="删除特定实验（可以指定多个）"
    )
    
    parser.add_argument(
        "--dataset", "-d",
        nargs="+",
        help="删除特定数据集（可以指定多个）"
    )
    
    parser.add_argument(
        "--paper_exp",
        action="store_true",
        help="删除论文实验相关的所有数据"
    )
    
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="跳过确认提示（慎用）"
    )
    
    args = parser.parse_args()
    
    # 如果没有任何参数，显示帮助
    if not any([args.list, args.all, args.exp_id, args.dataset, args.paper_exp]):
        parser.print_help()
        return
    
    # 列出实验
    if args.list:
        list_experiments()
        return
    
    # 删除所有数据
    if args.all:
        delete_all_data(confirm=args.force)
        return
    
    # 删除论文实验
    if args.paper_exp:
        delete_paper_experiments()
        return
    
    # 删除特定实验
    if args.exp_id:
        delete_experiment(args.exp_id)
    
    # 删除特定数据集
    if args.dataset:
        delete_dataset(args.dataset)


if __name__ == "__main__":
    main()





