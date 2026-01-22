@echo off
chcp 65001 > nul
echo.
echo ======================================================================
echo 测试 KORGym 专用经验提取器集成
echo ======================================================================
echo.
echo 此脚本将：
echo 1. 清理旧训练数据
echo 2. 重新运行 Wordle 训练（使用修复后的提取器）
echo 3. 验证所有样本都参与经验生成
echo.
echo 预期结果：
echo - 训练日志显示 "✅ Detected KORGym game"
echo - 所有 20 个问题都生成经验（100%% 覆盖率）
echo - 经验样本量增加 6.7x
echo.

set /p CONTINUE="确认开始测试？(y/n): "
if /i not "%CONTINUE%"=="y" (
    echo 测试已取消
    pause
    exit /b
)

cd /d F:\youtu-agent

echo.
echo ======================================================================
echo 步骤 1/4: 清理旧训练数据
echo ======================================================================
echo.
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_20_3 --force

echo.
echo ======================================================================
echo 步骤 2/4: 重新训练（使用修复后的提取器）
echo ======================================================================
echo.
echo 请注意观察日志中是否出现：
echo "✅ Detected KORGym game - using specialized experience extraction"
echo.
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20

echo.
echo ======================================================================
echo 步骤 3/4: 验证经验生成情况
echo ======================================================================
echo.
uv run python scripts/debug_experience_filtering.py --exp_id wordle_practice_20_3 --grpo_n 3

echo.
echo ======================================================================
echo 步骤 4/4: 运行评估
echo ======================================================================
echo.
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval

echo.
echo ======================================================================
echo 测试完成！
echo ======================================================================
echo.
echo 查看详细分析：
echo uv run python scripts/games/wordle/analyze_wordle_top20.py --exp_id wordle_practice_eval_20_3
echo.
echo 对比修复前后：
echo uv run python scripts/korgym/view_korgym_results.py wordle_baseline_eval wordle_practice_eval_20_3
echo.
pause
