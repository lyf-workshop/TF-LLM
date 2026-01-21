#!/usr/bin/env python3
"""
一键运行论文实验的脚本
Quick script to run the paper experiment reproduction
"""

import subprocess
import sys
import os

def run_command(cmd, description, check=True, shell=True):
    """运行命令并打印状态"""
    print(f"\n{'='*80}")
    print(f"执行: {description}")
    print(f"命令: {cmd}")
    print(f"{'='*80}\n")
    
    try:
        result = subprocess.run(cmd, shell=shell, check=check)
        if result.returncode == 0:
            print(f"\n✓ {description} - 成功完成\n")
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n✗ {description} - 失败: {e}\n")
        return False

def check_env_file():
    """检查.env文件是否存在"""
    if not os.path.exists('.env'):
        print("\n" + "="*80)
        print("警告: 未找到.env文件！")
        print("="*80)
        print("\n请创建.env文件并配置以下环境变量：")
        print("""
LLM_TYPE=deepseek
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your-api-key-here

# 可选：Phoenix tracing
# PHOENIX_ENDPOINT=http://127.0.0.1:6006/v1/traces
# PHOENIX_PROJECT_NAME=Youtu-Agent
        """)
        response = input("\n已经配置好.env文件了吗？(y/n): ")
        if response.lower() != 'y':
            print("请先配置.env文件后再运行此脚本。")
            sys.exit(1)

def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║   论文实验复现脚本                                                          ║
║   Paper Experiment Reproduction Script                                   ║
║                                                                           ║
║   Training-Free Group Relative Policy Optimization                       ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查环境文件
    check_env_file()
    
    print("\n实验配置:")
    print("- 数据集: DAPO-100 (从DAPO-Math-17K采样100个问题)")
    print("- 轮次: 3 epochs")
    print("- 群体大小: 5")
    print("- 学习温度: 0.7")
    print("- 评估温度: 0.3")
    print("- Agent: 无工具的纯文本推理\n")
    
    # 询问是否开始
    response = input("是否开始实验？(y/n): ")
    if response.lower() != 'y':
        print("实验取消。")
        sys.exit(0)
    
    # 步骤1: 准备数据
    print("\n" + "█"*80)
    print("步骤 1/4: 准备数据集")
    print("█"*80)
    if not run_command(
        "uv run python scripts/data/process_training_free_GRPO_data.py",
        "下载并准备AIME24, AIME25, DAPO-Math-17k数据集"
    ):
        print("数据准备失败，请检查网络连接或HuggingFace访问。")
        sys.exit(1)
    
    # 步骤2: Baseline评估
    print("\n" + "█"*80)
    print("步骤 2/4: Baseline评估（训练前）")
    print("█"*80)
    print("\n注意: 如果此步骤在Windows上失败，请在WSL中运行。\n")
    
    baseline_success = True
    baseline_success &= run_command(
        "uv run python scripts/run_eval.py --config_name math/math_AIME24_no_tools",
        "评估AIME24 baseline",
        check=False
    )
    print("\n跳过AIME25 baseline评估（根据用户要求）...\n")
    
    if not baseline_success:
        print("\n警告: Baseline评估可能失败。建议在WSL中重新运行评估命令。")
        response = input("是否继续训练？(y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # 步骤3: Training-Free GRPO
    print("\n" + "█"*80)
    print("步骤 3/4: 运行Training-Free GRPO")
    print("█"*80)
    if not run_command(
        "uv run python scripts/run_training_free_GRPO.py --config_name math_reasoning_paper_exp",
        "训练3个epochs，每个epoch包含100个样本"
    ):
        print("训练失败，请检查日志。")
        sys.exit(1)
    
    # 步骤4: 训练后评估
    print("\n" + "█"*80)
    print("步骤 4/4: 评估增强Agent（训练后）")
    print("█"*80)
    print("\n注意: 建议在WSL中运行此步骤。\n")
    
    practice_success = True
    practice_success &= run_command(
        "uv run python scripts/run_eval.py --config_name math/math_AIME24_no_tools_practice",
        "评估AIME24 (训练后)",
        check=False
    )
    print("\n跳过AIME25训练后评估（根据用户要求）...\n")
    
    print("\n" + "="*80)
    print("实验完成！")
    print("="*80)
    
    if practice_success:
        print("\n✓ 所有步骤成功完成")
    else:
        print("\n! 某些评估步骤可能失败，请在WSL中重新运行评估命令")
    
    print("\n查看结果:")
    print("- 训练后的agent配置: configs/agents/practice/math_agent_no_tools_practice.yaml")
    print("- 如果启用了Phoenix: http://127.0.0.1:6006")
    print("- 日志文件: logs/")

if __name__ == "__main__":
    main()

