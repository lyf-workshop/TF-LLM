#!/usr/bin/env python3
"""测试Wordle配置是否正确加载"""
from utu.config import ConfigLoader

try:
    config = ConfigLoader.load_training_free_grpo_config("wordle_qwen_grpo")
    
    print("=" * 60)
    print("配置加载测试")
    print("=" * 60)
    print(f"✓ exp_id: {config.exp_id}")
    print(f"✓ practice_dataset: {config.data.practice_dataset_name}")
    
    # 检查顶层korgym
    if hasattr(config, 'korgym') and config.korgym:
        print(f"✓ 顶层 korgym.game_name: {config.korgym.game_name}")
        print(f"✓ 顶层 korgym.game_port: {config.korgym.game_port}")
    else:
        print("✗ 顶层 korgym 未设置或为None")
    
    # 检查evaluation中的korgym
    if hasattr(config.evaluation, 'korgym') and config.evaluation.korgym:
        print(f"✓ evaluation.korgym.game_name: {config.evaluation.korgym.game_name}")
        print(f"✓ evaluation.korgym.game_port: {config.evaluation.korgym.game_port}")
    else:
        print("✗ evaluation.korgym 未设置或为None")
    
    # 检查evaluation.agent
    if hasattr(config.evaluation, 'agent') and config.evaluation.agent:
        print(f"✓ evaluation.agent 已设置")
        if hasattr(config.evaluation.agent, 'agent') and config.evaluation.agent.agent:
            print(f"✓ evaluation.agent.agent.name: {config.evaluation.agent.agent.name}")
    else:
        print("✗ evaluation.agent 未设置")
    
    print("=" * 60)
    print("✓ 配置加载成功！")
    
except Exception as e:
    print(f"✗ 配置加载失败: {e}")
    import traceback
    traceback.print_exc()



