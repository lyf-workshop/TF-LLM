@echo off
chcp 65001 >nul
echo ========================================
echo 测试对话历史修复的效果
echo ========================================
echo.
echo 🔧 修复内容:
echo   - 在多轮交互中启用 save=True
echo   - Agent 现在能记住之前的推理过程
echo   - 预期：更高的推理连贯性和准确率
echo.
pause

echo.
echo ========================================
echo [1/4] 清理旧评估结果
echo ========================================
call uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_history_test --force
echo.

echo ========================================
echo [2/4] 运行评估（修复后）
echo ========================================
echo 这将需要几分钟...
call uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval
echo.

echo ========================================
echo [3/4] 查看结果
echo ========================================
call uv run python scripts/korgym/view_korgym_results.py wordle_practice_20_eval
echo.

echo ========================================
echo [4/4] 分析前20题
echo ========================================
call uv run python scripts/korgym/analyze_wordle_top20.py --exp_id wordle_practice_20_eval --count 20
echo.

echo ========================================
echo 测试完成！
echo ========================================
echo.
echo 📊 预期改进:
echo   - 准确率: +5-10%%
echo   - 平均轮数: 减少 1-2 轮
echo   - 推理连贯性: 显著提升
echo   - 约束违反: 显著减少
echo.
echo 💡 如果你有修复前的基线，可以运行对比:
echo    uv run python scripts/korgym/compare_korgym_results.py --baseline [旧实验ID] --enhanced wordle_practice_20_eval
echo.
pause

