#!/bin/bash
# 测试 KORGym 环境
source .venv/bin/activate

echo "测试 Python 环境..."
python3 << 'PYTHON_TEST'
import sys
print(f"Python: {sys.version}")

# 测试关键包
packages = [
    'requests', 'fastapi', 'uvicorn', 'gymnasium', 
    'openai', 'tiktoken', 'torch', 'numpy', 'pandas',
    'utu'  # youtu-agent 包
]

print("\n检查包:")
for pkg in packages:
    try:
        mod = __import__(pkg)
        version = getattr(mod, '__version__', 'N/A')
        print(f"  ✓ {pkg} ({version})")
    except ImportError as e:
        print(f"  ✗ {pkg} (未找到)")

print("\n✓ 环境测试完成")
PYTHON_TEST
