"""
分析数据库中的ZebraLogic数据集
统计每个题目的信息，并将详细内容写入文本文件
"""
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from sqlmodel import select
from tqdm import tqdm

from utu.db import DatasetSample, EvaluationSample
from utu.utils import SQLModelUtils, get_logger

logger = get_logger(__name__)


def analyze_dataset_samples():
    """分析DatasetSample表中的ZebraLogic数据"""
    
    print("\n" + "="*80)
    print("📊 分析 DatasetSample 表中的 ZebraLogic 数据集")
    print("="*80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        # 查询所有包含 ZebraLogic 的数据
        query = select(DatasetSample).where(
            DatasetSample.dataset.like("%ZebraLogic%")
        )
        samples = session.exec(query).all()
        
        if not samples:
            print("❌ 没有找到 ZebraLogic 相关的数据")
            return None
        
        print(f"✅ 找到 {len(samples)} 条 ZebraLogic 数据\n")
        
        # 统计信息
        stats = {
            "total_count": len(samples),
            "dataset_names": Counter(),
            "source_names": Counter(),
            "level_distribution": Counter(),
            "has_meta": 0,
            "has_topic": 0,
        }
        
        # 按数据集名称分组
        dataset_groups = defaultdict(list)
        
        for sample in samples:
            # 统计数据集名称
            stats["dataset_names"][sample.dataset] += 1
            dataset_groups[sample.dataset].append(sample)
            
            # 统计source
            if sample.source:
                stats["source_names"][sample.source] += 1
            
            # 统计难度分布
            if sample.level is not None:
                stats["level_distribution"][sample.level] += 1
            
            # 统计meta和topic
            if sample.meta:
                stats["has_meta"] += 1
            if sample.topic:
                stats["has_topic"] += 1
        
        # 打印统计信息
        print_statistics(stats)
        
        return {
            "samples": samples,
            "stats": stats,
            "dataset_groups": dataset_groups
        }


def analyze_evaluation_samples():
    """分析EvaluationSample表中的ZebraLogic数据"""
    
    print("\n" + "="*80)
    print("📊 分析 EvaluationSample 表中的 ZebraLogic 评估数据")
    print("="*80 + "\n")
    
    with SQLModelUtils.create_session() as session:
        # 查询所有包含 ZebraLogic 的评估数据
        query = select(EvaluationSample).where(
            EvaluationSample.dataset.like("%ZebraLogic%")
        )
        samples = session.exec(query).all()
        
        if not samples:
            print("ℹ️  没有找到 ZebraLogic 相关的评估数据")
            return None
        
        print(f"✅ 找到 {len(samples)} 条 ZebraLogic 评估数据\n")
        
        # 统计信息
        stats = {
            "total_count": len(samples),
            "exp_ids": Counter(),
            "stage_distribution": Counter(),
            "level_distribution": Counter(),
            "correct_count": 0,
            "incorrect_count": 0,
            "not_judged": 0,
        }
        
        # 按实验ID分组
        exp_groups = defaultdict(list)
        
        for sample in samples:
            stats["exp_ids"][sample.exp_id] += 1
            exp_groups[sample.exp_id].append(sample)
            
            stats["stage_distribution"][sample.stage] += 1
            
            if sample.level is not None:
                stats["level_distribution"][sample.level] += 1
            
            if sample.correct is not None:
                if sample.correct:
                    stats["correct_count"] += 1
                else:
                    stats["incorrect_count"] += 1
            else:
                stats["not_judged"] += 1
        
        # 打印统计信息
        print_evaluation_statistics(stats)
        
        return {
            "samples": samples,
            "stats": stats,
            "exp_groups": exp_groups
        }


def print_statistics(stats):
    """打印DatasetSample统计信息"""
    
    print(f"📈 总题目数: {stats['total_count']}\n")
    
    print("📚 数据集分布:")
    for dataset_name, count in stats["dataset_names"].most_common():
        print(f"  • {dataset_name}: {count} 题")
    print()
    
    if stats["source_names"]:
        print("🔗 Source 分布:")
        for source_name, count in stats["source_names"].most_common():
            print(f"  • {source_name}: {count} 题")
        print()
    
    if stats["level_distribution"]:
        print("📊 难度分布:")
        for level, count in sorted(stats["level_distribution"].items()):
            level_name = get_level_name(level)
            print(f"  • Level {level} ({level_name}): {count} 题")
        print()
    
    print(f"🏷️  包含 meta 信息: {stats['has_meta']} 题")
    print(f"🏷️  包含 topic 信息: {stats['has_topic']} 题")
    print()


def print_evaluation_statistics(stats):
    """打印EvaluationSample统计信息"""
    
    print(f"📈 总评估样本数: {stats['total_count']}\n")
    
    print("🔬 实验ID分布:")
    for exp_id, count in stats["exp_ids"].most_common(10):  # 只显示前10个
        print(f"  • {exp_id}: {count} 样本")
    if len(stats["exp_ids"]) > 10:
        print(f"  ... 还有 {len(stats['exp_ids']) - 10} 个实验")
    print()
    
    print("🚦 Stage 分布:")
    for stage, count in stats["stage_distribution"].items():
        print(f"  • {stage}: {count} 样本")
    print()
    
    if stats["level_distribution"]:
        print("📊 难度分布:")
        for level, count in sorted(stats["level_distribution"].items()):
            level_name = get_level_name(level)
            print(f"  • Level {level} ({level_name}): {count} 样本")
        print()
    
    # 计算准确率
    judged_count = stats["correct_count"] + stats["incorrect_count"]
    if judged_count > 0:
        accuracy = (stats["correct_count"] / judged_count) * 100
        print("✅ 评估结果:")
        print(f"  • 正确: {stats['correct_count']} 题")
        print(f"  • 错误: {stats['incorrect_count']} 题")
        print(f"  • 未判定: {stats['not_judged']} 题")
        print(f"  • 准确率: {accuracy:.2f}% ({stats['correct_count']}/{judged_count})")
    else:
        print(f"ℹ️  未判定: {stats['not_judged']} 题")
    print()


def get_level_name(level):
    """获取难度级别名称"""
    level_names = {
        1: "Easy",
        2: "Medium",
        3: "Hard",
    }
    return level_names.get(level, "Unknown")


def write_samples_to_file(dataset_groups, output_file):
    """将题目详细内容写入文本文件"""
    
    print(f"📝 正在写入题目详细内容到文件: {output_file}")
    
    with open(output_file, "w", encoding="utf-8") as f:
        # 写入文件头
        f.write("="*100 + "\n")
        f.write("ZebraLogic 数据集题目详细内容\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*100 + "\n\n")
        
        # 按数据集分组写入
        for dataset_name, samples in sorted(dataset_groups.items()):
            f.write("\n" + "="*100 + "\n")
            f.write(f"数据集: {dataset_name}\n")
            f.write(f"题目数量: {len(samples)}\n")
            f.write("="*100 + "\n\n")
            
            # 按index排序
            samples_sorted = sorted(samples, key=lambda x: x.index or 0)
            
            for idx, sample in enumerate(samples_sorted, 1):
                write_sample_detail(f, sample, idx)
    
    print(f"✅ 成功写入 {output_file}")


def write_sample_detail(f, sample: DatasetSample, seq_num: int):
    """写入单个样本的详细信息"""
    
    f.write("-"*100 + "\n")
    f.write(f"题目 #{seq_num}\n")
    f.write("-"*100 + "\n\n")
    
    # 基本信息
    f.write(f"数据库ID: {sample.id}\n")
    f.write(f"数据集: {sample.dataset}\n")
    f.write(f"索引: {sample.index}\n")
    if sample.source:
        f.write(f"Source: {sample.source}\n")
    if sample.source_index is not None:
        f.write(f"Source索引: {sample.source_index}\n")
    if sample.level is not None:
        f.write(f"难度级别: {sample.level} ({get_level_name(sample.level)})\n")
    if sample.topic:
        f.write(f"主题: {sample.topic}\n")
    f.write("\n")
    
    # 题目内容
    f.write("【题目】\n")
    f.write("-"*50 + "\n")
    f.write(sample.question)
    f.write("\n" + "-"*50 + "\n\n")
    
    # 答案
    f.write("【答案】\n")
    f.write("-"*50 + "\n")
    if sample.answer:
        # 尝试格式化JSON答案
        try:
            answer_dict = json.loads(sample.answer)
            f.write(json.dumps(answer_dict, indent=2, ensure_ascii=False))
        except:
            f.write(sample.answer)
    else:
        f.write("(无答案)")
    f.write("\n" + "-"*50 + "\n\n")
    
    # Meta信息
    if sample.meta:
        f.write("【Meta信息】\n")
        f.write("-"*50 + "\n")
        try:
            meta_formatted = json.dumps(sample.meta, indent=2, ensure_ascii=False)
            f.write(meta_formatted)
        except:
            f.write(str(sample.meta))
        f.write("\n" + "-"*50 + "\n\n")
    
    f.write("\n\n")


def write_evaluation_samples_to_file(exp_groups, output_file):
    """将评估样本详细内容写入文本文件"""
    
    print(f"📝 正在写入评估样本详细内容到文件: {output_file}")
    
    with open(output_file, "w", encoding="utf-8") as f:
        # 写入文件头
        f.write("="*100 + "\n")
        f.write("ZebraLogic 评估样本详细内容\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*100 + "\n\n")
        
        # 按实验ID分组写入
        for exp_id, samples in sorted(exp_groups.items()):
            f.write("\n" + "="*100 + "\n")
            f.write(f"实验ID: {exp_id}\n")
            f.write(f"样本数量: {len(samples)}\n")
            f.write("="*100 + "\n\n")
            
            # 按dataset_index排序
            samples_sorted = sorted(samples, key=lambda x: (x.dataset_index or 0, x.id))
            
            for idx, sample in enumerate(samples_sorted, 1):
                write_evaluation_sample_detail(f, sample, idx)
    
    print(f"✅ 成功写入 {output_file}")


def write_evaluation_sample_detail(f, sample: EvaluationSample, seq_num: int):
    """写入单个评估样本的详细信息"""
    
    f.write("-"*100 + "\n")
    f.write(f"评估样本 #{seq_num}\n")
    f.write("-"*100 + "\n\n")
    
    # 基本信息
    f.write(f"数据库ID: {sample.id}\n")
    f.write(f"实验ID: {sample.exp_id}\n")
    f.write(f"数据集: {sample.dataset}\n")
    f.write(f"数据集索引: {sample.dataset_index}\n")
    if sample.source:
        f.write(f"Source: {sample.source}\n")
    if sample.level is not None:
        f.write(f"难度级别: {sample.level} ({get_level_name(sample.level)})\n")
    f.write(f"Stage: {sample.stage}\n")
    
    # 评估结果
    if sample.correct is not None:
        result = "✅ 正确" if sample.correct else "❌ 错误"
        f.write(f"评估结果: {result}\n")
        if sample.reward is not None:
            f.write(f"奖励分数: {sample.reward}\n")
    
    if sample.time_cost is not None:
        f.write(f"耗时: {sample.time_cost:.2f} 秒\n")
    
    if sample.trace_id:
        f.write(f"Trace ID: {sample.trace_id}\n")
    
    f.write("\n")
    
    # 题目内容
    f.write("【原始题目】\n")
    f.write("-"*50 + "\n")
    f.write(sample.raw_question)
    f.write("\n" + "-"*50 + "\n\n")
    
    # 增强题目
    if sample.augmented_question and sample.augmented_question != sample.raw_question:
        f.write("【增强题目】\n")
        f.write("-"*50 + "\n")
        f.write(sample.augmented_question)
        f.write("\n" + "-"*50 + "\n\n")
    
    # 正确答案
    f.write("【正确答案】\n")
    f.write("-"*50 + "\n")
    if sample.correct_answer:
        try:
            answer_dict = json.loads(sample.correct_answer)
            f.write(json.dumps(answer_dict, indent=2, ensure_ascii=False))
        except:
            f.write(sample.correct_answer)
    else:
        f.write("(无答案)")
    f.write("\n" + "-"*50 + "\n\n")
    
    # 模型输出
    if sample.response:
        f.write("【模型输出】\n")
        f.write("-"*50 + "\n")
        # 只显示前1000个字符，避免文件过大
        response_preview = sample.response[:1000]
        if len(sample.response) > 1000:
            response_preview += f"\n\n... (总长度: {len(sample.response)} 字符，已截断)"
        f.write(response_preview)
        f.write("\n" + "-"*50 + "\n\n")
    
    # 提取的答案
    if sample.extracted_final_answer:
        f.write("【提取的答案】\n")
        f.write("-"*50 + "\n")
        try:
            extracted_dict = json.loads(sample.extracted_final_answer)
            f.write(json.dumps(extracted_dict, indent=2, ensure_ascii=False))
        except:
            f.write(sample.extracted_final_answer)
        f.write("\n" + "-"*50 + "\n\n")
    
    # 判定推理
    if sample.reasoning:
        f.write("【判定推理】\n")
        f.write("-"*50 + "\n")
        f.write(sample.reasoning)
        f.write("\n" + "-"*50 + "\n\n")
    
    f.write("\n\n")


def export_statistics_to_json(dataset_result, evaluation_result, output_file):
    """导出统计信息到JSON文件"""
    
    print(f"📊 正在导出统计信息到: {output_file}")
    
    export_data = {
        "generated_at": datetime.now().isoformat(),
        "dataset_samples": None,
        "evaluation_samples": None,
    }
    
    if dataset_result:
        export_data["dataset_samples"] = {
            "total_count": dataset_result["stats"]["total_count"],
            "dataset_names": dict(dataset_result["stats"]["dataset_names"]),
            "source_names": dict(dataset_result["stats"]["source_names"]),
            "level_distribution": dict(dataset_result["stats"]["level_distribution"]),
            "has_meta": dataset_result["stats"]["has_meta"],
            "has_topic": dataset_result["stats"]["has_topic"],
        }
    
    if evaluation_result:
        export_data["evaluation_samples"] = {
            "total_count": evaluation_result["stats"]["total_count"],
            "exp_ids": dict(evaluation_result["stats"]["exp_ids"]),
            "stage_distribution": dict(evaluation_result["stats"]["stage_distribution"]),
            "level_distribution": dict(evaluation_result["stats"]["level_distribution"]),
            "correct_count": evaluation_result["stats"]["correct_count"],
            "incorrect_count": evaluation_result["stats"]["incorrect_count"],
            "not_judged": evaluation_result["stats"]["not_judged"],
        }
        
        # 计算准确率
        judged = export_data["evaluation_samples"]["correct_count"] + \
                 export_data["evaluation_samples"]["incorrect_count"]
        if judged > 0:
            export_data["evaluation_samples"]["accuracy"] = \
                export_data["evaluation_samples"]["correct_count"] / judged
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 成功导出统计信息")


def main():
    """主函数"""
    
    print("\n" + "🦓"*40)
    print("ZebraLogic 数据集分析工具")
    print("🦓"*40 + "\n")
    
    # 检查数据库连接
    if not SQLModelUtils.check_db_available():
        print("❌ 数据库连接失败，请检查配置")
        return
    
    print("✅ 数据库连接成功\n")
    
    # 创建输出目录
    output_dir = Path("analysis/zebra_dataset")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 分析DatasetSample表
    dataset_result = analyze_dataset_samples()
    
    # 分析EvaluationSample表
    evaluation_result = analyze_evaluation_samples()
    
    # 写入文件
    if dataset_result:
        dataset_file = output_dir / f"zebra_dataset_samples_{timestamp}.txt"
        write_samples_to_file(dataset_result["dataset_groups"], dataset_file)
    
    if evaluation_result:
        evaluation_file = output_dir / f"zebra_evaluation_samples_{timestamp}.txt"
        write_evaluation_samples_to_file(evaluation_result["exp_groups"], evaluation_file)
    
    # 导出统计信息到JSON
    stats_file = output_dir / f"zebra_statistics_{timestamp}.json"
    export_statistics_to_json(dataset_result, evaluation_result, stats_file)
    
    print("\n" + "="*80)
    print("✅ 分析完成！")
    print("="*80)
    print(f"\n📁 输出文件位置: {output_dir.absolute()}")
    if dataset_result:
        print(f"  • 数据集样本: zebra_dataset_samples_{timestamp}.txt")
    if evaluation_result:
        print(f"  • 评估样本: zebra_evaluation_samples_{timestamp}.txt")
    print(f"  • 统计信息: zebra_statistics_{timestamp}.json")
    print()


if __name__ == "__main__":
    main()
































