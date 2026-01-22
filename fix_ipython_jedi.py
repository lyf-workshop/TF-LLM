#!/usr/bin/env python3
"""
修复IPython和jedi版本冲突问题

用法:
    uv run python fix_ipython_jedi.py
"""

import subprocess
import sys

def fix_ipython_jedi():
    print("\n" + "="*80)
    print("修复IPython和jedi版本冲突")
    print("="*80 + "\n")
    
    print("方案1: 升级IPython和jedi到兼容版本...")
    try:
        # 升级IPython和jedi
        subprocess.run(
            ["uv", "pip", "install", "--upgrade", "ipython>=8.18.0", "jedi>=0.19.0"],
            check=True
        )
        print("✓ 升级成功\n")
    except subprocess.CalledProcessError:
        print("⚠️  升级失败，尝试方案2...\n")
        
        print("方案2: 重新同步依赖...")
        try:
            subprocess.run(
                ["uv", "sync", "--all-extras"],
                check=True
            )
            print("✓ 同步成功\n")
        except subprocess.CalledProcessError as e:
            print(f"❌ 同步失败: {e}\n")
            return False
    
    # 测试导入
    print("测试修复...")
    try:
        from utu.db import DatasetSample, DBService
        print("✓ 导入成功！\n")
        
        print("="*80)
        print("✅ 修复完成！现在可以运行 prepare_korgym_data.py 了")
        print("="*80 + "\n")
        return True
    except Exception as e:
        print(f"❌ 导入仍然失败: {e}\n")
        print("建议: 尝试重新创建虚拟环境")
        return False

if __name__ == "__main__":
    success = fix_ipython_jedi()
    sys.exit(0 if success else 1)




















