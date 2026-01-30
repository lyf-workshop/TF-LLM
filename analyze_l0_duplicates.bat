@echo off
chcp 65001 > nul
echo.
echo ======================================================================
echo L0 经验重复分析
echo ======================================================================
echo.

cd /d F:\youtu-agent

if "%1"=="" (
    echo 分析最新的分层经验文件...
    uv run python scripts/analyze_l0_duplicates.py
) else if "%1"=="--all" (
    echo 分析所有分层经验文件...
    uv run python scripts/analyze_l0_duplicates.py --all
) else (
    echo 分析指定的实验: %1
    uv run python scripts/analyze_l0_duplicates.py --exp_id %1
)

echo.
echo ======================================================================
echo 使用方法:
echo   analyze_l0_duplicates.bat                    # 分析最新文件
echo   analyze_l0_duplicates.bat --all              # 分析所有文件
echo   analyze_l0_duplicates.bat wordle_practice_20 # 分析指定实验
echo ======================================================================
echo.
pause
