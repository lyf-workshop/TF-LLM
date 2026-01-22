@echo off
chcp 65001 >nul
echo ========================================
echo 测试数据集查看脚本
echo ========================================
echo.

echo [1/5] 列出所有数据集...
echo ----------------------------------------
call uv run python scripts/utils/view_datasets.py --list
echo.

echo [2/5] 过滤 Wordle 数据集...
echo ----------------------------------------
call uv run python scripts/utils/view_datasets.py --list --filter Wordle
echo.

echo [3/5] 搜索 Wordle 游戏的所有数据集...
echo ----------------------------------------
call uv run python scripts/utils/view_datasets.py --game "33-wordle"
echo.

echo [4/5] 查看 KORGym-Wordle-Train-20 详情（如果存在）...
echo ----------------------------------------
call uv run python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20"
echo.

echo [5/5] 查看 KORGym-Wordle-Train-20 前3个样本（如果存在）...
echo ----------------------------------------
call uv run python scripts/utils/view_datasets.py --dataset "KORGym-Wordle-Train-20" --samples 3
echo.

echo ========================================
echo 测试完成！
echo ========================================
pause


