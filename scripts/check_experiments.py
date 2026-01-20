#!/usr/bin/env python3
"""检查数据库中存储的所有实验"""

import sys
from pathlib import Path
from sqlmodel import select, func
from collections import defaultdict
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.db.eval_datapoint import EvaluationSample
from utu.db.experience_cache_model import ExperienceCacheModel
from utu.utils.sqlmodel_utils import SQLModelUtils


def format_datetime(dt):
    """格式化日期时间"""
    if dt is None:
        return "N/A"
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def check_evaluation_experiments():
    """检查评估实验"""
    print("\n" + "=" * 80)
    print("📊 评估实验 (Evaluation Experiments)")
    print("=" * 80)
    
    with SQLModelUtils.create_session() as session:
        # 获取所有不同的 exp_id
        exp_ids = session.exec(
            select(EvaluationSample.exp_id).distinct()
        ).all()
        
        if not exp_ids:
            print("\n❌ 未找到任何评估实验")
            return
        
        print(f"\n找到 {len(exp_ids)} 个实验:\n")
        
        # 为每个实验计算统计信息
        experiments_info = []
        
        for exp_id in sorted(exp_ids):
            samples = list(session.exec(
                select(EvaluationSample).where(EvaluationSample.exp_id == exp_id)
            ))
            
            if not samples:
                continue
            
            # 计算统计信息
            total = len(samples)
            correct = sum(1 for s in samples if s.reward and s.reward > 0.5)
            accuracy = (correct / total * 100) if total > 0 else 0.0
            
            # 计算平均 reward
            rewards = [s.reward for s in samples if s.reward is not None]
            avg_reward = sum(rewards) / len(rewards) if rewards else 0.0
            
            # 计算平均时间成本
            time_costs = [s.time_cost for s in samples if s.time_cost is not None]
            avg_time = sum(time_costs) / len(time_costs) if time_costs else 0.0
            
            # 获取时间范围
            created_dates = [s.created_at for s in samples if s.created_at]
            if created_dates:
                earliest = min(created_dates)
                latest = max(created_dates)
            else:
                earliest = latest = None
            
            # 统计不同 stage
            stages = defaultdict(int)
            for s in samples:
                stages[s.stage] += 1
            
            # 统计数据集
            datasets = set(s.dataset for s in samples if s.dataset)
            
            # 统计问题数（去重）
            problems = set()
            for s in samples:
                key = s.raw_question or s.question or ""
                if key:
                    problems.add(key)
            total_problems = len(problems)
            
            experiments_info.append({
                'exp_id': exp_id,
                'total': total,
                'correct': correct,
                'accuracy': accuracy,
                'avg_reward': avg_reward,
                'avg_time': avg_time,
                'earliest': earliest,
                'latest': latest,
                'stages': dict(stages),
                'datasets': datasets,
                'total_problems': total_problems,
            })
        
        # 显示详细信息
        for i, info in enumerate(experiments_info, 1):
            print(f"{i}. 实验ID: {info['exp_id']}")
            print(f"   📈 样本统计:")
            print(f"      - 总样本数: {info['total']}")
            print(f"      - 总问题数: {info['total_problems']}")
            print(f"      - 每题平均样本数: {info['total'] / info['total_problems']:.1f}" if info['total_problems'] > 0 else "      - 每题平均样本数: N/A")
            print(f"   ✅ 正确性:")
            print(f"      - 正确样本: {info['correct']}/{info['total']}")
            print(f"      - 准确率: {info['accuracy']:.2f}%")
            print(f"      - 平均 Reward: {info['avg_reward']:.4f}")
            print(f"   ⏱️  时间:")
            print(f"      - 平均耗时: {info['avg_time']:.2f}秒" if info['avg_time'] > 0 else "      - 平均耗时: N/A")
            print(f"      - 最早记录: {format_datetime(info['earliest'])}")
            print(f"      - 最新记录: {format_datetime(info['latest'])}")
            print(f"   📋 其他信息:")
            print(f"      - 数据集: {', '.join(info['datasets']) if info['datasets'] else 'N/A'}")
            print(f"      - 阶段分布: {', '.join(f'{k}:{v}' for k, v in info['stages'].items())}")
            print()
        
        print("=" * 80)


def check_experience_cache_experiments():
    """检查经验缓存实验"""
    print("\n" + "=" * 80)
    print("💾 经验缓存实验 (Experience Cache Experiments)")
    print("=" * 80)
    
    with SQLModelUtils.create_session() as session:
        # 获取所有不同的 experiment_name
        experiment_names = session.exec(
            select(ExperienceCacheModel.experiment_name).distinct()
        ).all()
        
        if not experiment_names:
            print("\n❌ 未找到任何经验缓存实验")
            return
        
        print(f"\n找到 {len(experiment_names)} 个经验缓存实验:\n")
        
        for exp_name in sorted(experiment_names):
            caches = list(session.exec(
                select(ExperienceCacheModel).where(
                    ExperienceCacheModel.experiment_name == exp_name
                )
            ))
            
            if not caches:
                continue
            
            # 计算统计信息
            total = len(caches)
            steps = sorted(set(c.step for c in caches))
            epochs = sorted(set(c.epoch for c in caches if c.epoch is not None))
            batches = sorted(set(c.batch for c in caches if c.batch is not None))
            
            # 时间范围
            timestamps = [c.timestamp for c in caches if c.timestamp]
            if timestamps:
                earliest_ts = min(timestamps)
                latest_ts = max(timestamps)
                earliest = datetime.fromtimestamp(earliest_ts) if earliest_ts else None
                latest = datetime.fromtimestamp(latest_ts) if latest_ts else None
            else:
                earliest = latest = None
            
            print(f"实验名称: {exp_name}")
            print(f"   📊 统计:")
            print(f"      - 缓存记录数: {total}")
            print(f"      - Step 范围: {min(steps)} - {max(steps)}" if steps else "      - Step 范围: N/A")
            print(f"      - Epoch 范围: {min(epochs)} - {max(epochs)}" if epochs else "      - Epoch 范围: N/A")
            print(f"      - Batch 范围: {min(batches)} - {max(batches)}" if batches else "      - Batch 范围: N/A")
            print(f"   ⏱️  时间:")
            print(f"      - 最早记录: {format_datetime(earliest)}")
            print(f"      - 最新记录: {format_datetime(latest)}")
            print()


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("🔍 数据库实验检查工具")
    print("=" * 80)
    
    # 检查数据库连接
    if not SQLModelUtils.check_db_available():
        print("\n❌ 数据库连接失败！")
        print("请检查环境变量 UTU_DB_URL 是否正确设置")
        return
    
    print("\n✅ 数据库连接成功")
    
    # 检查评估实验
    try:
        check_evaluation_experiments()
    except Exception as e:
        print(f"\n⚠️  检查评估实验时出错: {e}")
    
    # 检查经验缓存实验
    try:
        check_experience_cache_experiments()
    except Exception as e:
        print(f"\n⚠️  检查经验缓存实验时出错: {e}")
    
    print("\n" + "=" * 80)
    print("✅ 检查完成")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

