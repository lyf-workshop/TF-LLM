#!/bin/bash
# 修复IPython和jedi版本冲突问题

cd /mnt/f/youtu-agent

echo "修复IPython和jedi版本冲突..."

# 方案1: 升级IPython和jedi到最新兼容版本
uv pip install --upgrade ipython jedi

# 如果方案1失败，使用方案2：重新同步依赖
if [ $? -ne 0 ]; then
    echo "尝试重新同步依赖..."
    uv sync --all-extras
fi

echo "✓ 修复完成！"

# 测试
echo "测试修复..."
uv run python -c "from utu.db import DatasetSample, DBService; print('✓ 导入成功')"




















