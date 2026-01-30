@echo off
chcp 65001 > nul
echo.
echo ======================================================================
echo Wordle 简洁历史格式测试
echo ======================================================================
echo.
echo 此脚本将测试新的简洁历史格式，对比 token 消耗和 prompt 长度。
echo.
echo 要求：
echo   1. Wordle 游戏服务器已启动（端口 8777）
echo   2. .env 文件已配置 API Key
echo.
echo 按任意键继续，或 Ctrl+C 取消...
pause > nul

cd /d F:\youtu-agent

echo.
echo 1. 检查 Wordle 游戏服务器...
curl -s http://localhost:8777/ > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo    ❌ Wordle 服务器未启动！
    echo.
    echo    请先启动服务器：
    echo    cd KORGym\game_lib\33-wordle
    echo    python game_lib.py -p 8777
    echo.
    pause
    exit /b 1
)
echo    ✅ 服务器运行中

echo.
echo 2. 运行测试脚本...
echo.

uv run python scripts/test_wordle_compact_history.py

echo.
echo ======================================================================
echo 测试完成！
echo ======================================================================
echo.
pause
