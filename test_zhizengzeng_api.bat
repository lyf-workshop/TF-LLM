@echo off
chcp 65001 > nul
echo.
echo ======================================================================
echo 智增增 API 配置测试
echo ======================================================================
echo.

cd /d F:\youtu-agent

uv run python test_zhizengzeng_api.py

echo.
pause
