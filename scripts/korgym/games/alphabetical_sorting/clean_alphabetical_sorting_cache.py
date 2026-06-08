#!/usr/bin/env python3
"""清理 Alphabetical Sorting 的经验缓存

这个脚本会删除数据库中的经验缓存，让训练可以重新提取经验。

用法:
    uv run python scripts/clean_alphabetical_sorting_cache.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utu.utils.experience_cache import ExperienceCache
from utu.utils import get_logger

logger = get_logger(__name__)


def main():
    exp_id = "wordle_practice_l4"
    
    print("\n" + "=" * 80)
    print("🧹 清理 Alphabetical Sorting 经验缓存")
    print("=" * 80)
    print()
    print(f"实验ID: {exp_id}")
    print()
    
    # 确认删除
    response = input("确认删除经验缓存？这将允许重新提取经验。输入 'yes' 继续: ")
    if response.lower() != 'yes':
        print("❌ 取消操作")
        return
    
    # 删除经验缓存
    print(f"\n📦 正在删除 {exp_id} 的经验缓存...")
    success = ExperienceCache.delete_experiment_cache(exp_id)
    
    if success:
        print("✅ 经验缓存已成功删除！")
        print()
        print("现在可以重新运行训练:")
        print(f"  uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice")
        print()
        print("新的训练将重新提取和聚合经验，生成完整的分层经验（L0→L1→L2）")
    else:
        print("❌ 删除失败，请检查日志")
    
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()













