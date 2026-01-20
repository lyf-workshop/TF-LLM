#!/usr/bin/env python
"""测试 practice 配置文件加载是否正常"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utu.config import ConfigLoader

def test_config_loading():
    """测试各类配置加载"""
    
    test_configs = [
        # KORGym configs
        ("korgym/alphabetical_sorting_practice", "KORGym - Alphabetical Sorting"),
        ("korgym/word_puzzle_practice", "KORGym - Word Puzzle"),
        ("korgym/wordle_practice", "KORGym - Wordle"),
        ("korgym/korgym_practice", "KORGym - General"),
        
        # Logic configs
        ("logic/logic_reasoning_zebralogic", "Logic - ZebraLogic"),
        ("logic/qwen_reasoning_easy", "Logic - Qwen Easy"),
        ("logic/medium_reasoning_hierarchical_num1", "Logic - Medium Hierarchical"),
        
        # Math configs
        ("math/math_reasoning", "Math - Basic"),
        ("math/math_reasoning_paper_exp", "Math - Paper Exp"),
        
        # Web configs
        ("web/web_search", "Web - Search"),
    ]
    
    print("=" * 70)
    print("Testing Practice Configuration Loading")
    print("=" * 70)
    
    success_count = 0
    fail_count = 0
    
    for config_name, description in test_configs:
        try:
            cfg = ConfigLoader.load_training_free_grpo_config(config_name)
            print(f"✓ {description:40} | exp_id: {cfg.exp_id}")
            success_count += 1
        except Exception as e:
            print(f"✗ {description:40} | Error: {str(e)[:40]}")
            fail_count += 1
    
    print("=" * 70)
    print(f"Results: {success_count} succeeded, {fail_count} failed")
    print("=" * 70)
    
    if fail_count > 0:
        print("\n⚠ Some configurations failed to load!")
        return False
    else:
        print("\n✓ All configurations loaded successfully!")
        return True

if __name__ == "__main__":
    success = test_config_loading()
    sys.exit(0 if success else 1)















