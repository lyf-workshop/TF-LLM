@echo off
chcp 65001 >nul
echo ========================================
echo 测试手动优化经验的效果
echo ========================================
echo.
echo 📋 实验设置:
echo   - Agent: wordle_practice_20_l4_agent (手动优化经验)
echo   - 评估集: KORGym-Wordle-Eval-50 (seeds 1-50)
echo   - 经验数量: 9条 (3xL0 + 4xL1 + 2xL2)
echo.
pause

echo.
echo ========================================
echo [1/4] 清理旧评估结果
echo ========================================
call uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_20_eval --force
echo.

echo ========================================
echo [2/4] 运行评估（使用优化版 Agent）
echo ========================================
echo 这将需要几分钟...
call uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval
echo.

echo ========================================
echo [3/4] 查看整体结果
echo ========================================
call uv run python scripts/korgym/view_korgym_results.py wordle_practice_20_eval
echo.

echo ========================================
echo [4/4] 分析前20题详情
echo ========================================
call uv run python scripts/korgym/analyze_wordle_top20.py --exp_id wordle_practice_20_eval --count 20
echo.

echo ========================================
echo 测试完成！
echo ========================================
echo.
echo 💡 如果你有基线评估结果，可以运行对比:
echo    uv run python scripts/korgym/compare_korgym_results.py --baseline wordle_eval --enhanced wordle_practice_20_eval
echo.
pause


