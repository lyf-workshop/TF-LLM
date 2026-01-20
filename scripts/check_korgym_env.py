#!/usr/bin/env python3
"""
快速检查 KORGym 环境是否正确配置

Usage:
    python scripts/check_korgym_env.py
"""

import sys
from pathlib import Path


def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    print(f"Python 版本: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 12):
        print("  ❌ Python 版本过低，需要 >= 3.12")
        return False
    else:
        print("  ✓ Python 版本符合要求")
        return True


def check_package(name, desc, optional=False):
    """检查单个包"""
    try:
        mod = __import__(name)
        version = getattr(mod, '__version__', 'N/A')
        print(f"  ✓ {name:20s} ({version:15s}) - {desc}")
        return True
    except ImportError:
        if optional:
            print(f"  ○ {name:20s} (未安装)        - {desc} [可选]")
        else:
            print(f"  ❌ {name:20s} (未安装)        - {desc} [必需]")
        return False


def check_korgym_directory():
    """检查 KORGym 目录"""
    korgym_path = Path(__file__).parent.parent / "KORGym"
    game_lib_path = korgym_path / "game_lib"
    
    print(f"\nKORGym 目录: {korgym_path}")
    
    if not korgym_path.exists():
        print("  ❌ KORGym 目录不存在")
        return False
    
    print("  ✓ KORGym 目录存在")
    
    if not game_lib_path.exists():
        print("  ❌ game_lib 目录不存在")
        return False
    
    print("  ✓ game_lib 目录存在")
    
    # 列出可用游戏
    games = [d.name for d in game_lib_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
    print(f"  ✓ 找到 {len(games)} 个游戏:")
    for game in sorted(games)[:5]:  # 只显示前 5 个
        print(f"    - {game}")
    if len(games) > 5:
        print(f"    ... 还有 {len(games) - 5} 个游戏")
    
    return True


def check_project_structure():
    """检查项目结构"""
    project_root = Path(__file__).parent.parent
    
    required_dirs = [
        ("utu", "核心包"),
        ("configs", "配置目录"),
        ("scripts", "脚本目录"),
        ("KORGym", "KORGym 代码"),
    ]
    
    print("\n项目结构:")
    all_ok = True
    
    for dir_name, desc in required_dirs:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"  ✓ {dir_name:15s} - {desc}")
        else:
            print(f"  ❌ {dir_name:15s} - {desc} (不存在)")
            all_ok = False
    
    return all_ok


def check_config_files():
    """检查配置文件"""
    project_root = Path(__file__).parent.parent
    
    config_files = [
        ("configs/agents/practice/logic_agent_hierarchical_learning_clean.yaml", "Agent 配置"),
        ("configs/practice/korgym/korgym_hierarchical_test.yaml", "KORGym 测试配置"),
    ]
    
    print("\n配置文件:")
    all_ok = True
    
    for config_path, desc in config_files:
        full_path = project_root / config_path
        if full_path.exists():
            print(f"  ✓ {config_path}")
        else:
            print(f"  ⚠ {config_path} (不存在)")
            all_ok = False
    
    return all_ok


def main():
    print("="*70)
    print("  KORGym 环境检查")
    print("="*70)
    
    # 检查 Python 版本
    print("\n1. Python 环境:")
    python_ok = check_python_version()
    
    # 检查 youtu-agent 核心包
    print("\n2. youtu-agent 核心包:")
    youtu_packages = {
        'utu': 'youtu-agent 核心',
        'openai': 'OpenAI API',
        'tiktoken': 'Token 计数',
        'pydantic': '数据验证',
        'requests': 'HTTP 请求',
        'numpy': '数值计算',
        'pandas': '数据处理',
    }
    
    youtu_ok = all(check_package(pkg, desc) for pkg, desc in youtu_packages.items())
    
    # 检查 KORGym 核心包
    print("\n3. KORGym 核心包:")
    korgym_packages = {
        'fastapi': 'FastAPI 框架',
        'uvicorn': 'ASGI 服务器',
        'gymnasium': '游戏环境',
        'pygame': '游戏开发',
        'PIL': '图像处理 (Pillow)',
    }
    
    korgym_ok = all(check_package(pkg, desc) for pkg, desc in korgym_packages.items())
    
    # 检查可选包
    print("\n4. 可选包:")
    optional_packages = {
        'torch': 'PyTorch',
        'vllm': '本地模型服务',
        'matplotlib': '可视化',
    }
    
    for pkg, desc in optional_packages.items():
        check_package(pkg, desc, optional=True)
    
    # 检查目录结构
    print("\n5. 项目结构:")
    structure_ok = check_project_structure()
    
    # 检查 KORGym 目录
    print("\n6. KORGym 游戏:")
    korgym_dir_ok = check_korgym_directory()
    
    # 检查配置文件
    print("\n7. 配置文件:")
    config_ok = check_config_files()
    
    # 总结
    print("\n" + "="*70)
    print("  检查总结")
    print("="*70)
    
    checks = [
        ("Python 版本", python_ok),
        ("youtu-agent 包", youtu_ok),
        ("KORGym 包", korgym_ok),
        ("项目结构", structure_ok),
        ("KORGym 目录", korgym_dir_ok),
        ("配置文件", config_ok),
    ]
    
    all_passed = True
    for name, status in checks:
        if status:
            print(f"  ✓ {name}")
        else:
            print(f"  ❌ {name}")
            all_passed = False
    
    print("="*70)
    
    if all_passed:
        print("\n✅ 所有检查通过！环境配置正确。")
        print("\n下一步:")
        print("  1. 运行测试: uv run python scripts/test_korgym_adapter.py")
        print("  2. 启动游戏: python scripts/start_korgym_server.py 3-2048")
        return 0
    else:
        print("\n❌ 部分检查失败，请先完成环境配置。")
        print("\n推荐操作:")
        print("  1. 运行配置脚本: bash setup_korgym_wsl.sh")
        print("  2. 或查看文档: cat KORGym_WSL环境配置指南.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())











