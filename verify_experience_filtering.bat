@echo off
chcp 65001 > nul
echo.
echo ======================================================================
echo 验证经验提取筛选问题
echo ======================================================================
echo.
echo 检查 Wordle 训练中有多少问题因为 0/1 评分而被过滤掉
echo.

cd /d F:\youtu-agent

echo 分析 Wordle Practice 实验...
echo.
uv run python scripts/debug_experience_filtering.py --exp_id wordle_practice_20_3 --grpo_n 3

echo.
echo ======================================================================
echo 完成！
echo ======================================================================
echo.
pause
