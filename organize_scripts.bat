@echo off
chcp 65001 > nul
echo.
echo ========================================
echo Scripts 文件夹重组
echo ========================================
echo.

cd scripts

echo 创建目录结构...
mkdir korgym 2>nul
mkdir games 2>nul
mkdir games\zebralogic 2>nul
mkdir games\wordle 2>nul
mkdir games\word_puzzle 2>nul
mkdir games\alphabetical_sorting 2>nul
mkdir error_analysis 2>nul
mkdir experiments 2>nul
mkdir utils 2>nul

echo.
echo 移动 KORGym 通用脚本...
move /Y view_korgym_results.py korgym\ 2>nul
move /Y check_korgym_env.py korgym\ 2>nul
move /Y test_korgym_server.py korgym\ 2>nul
move /Y run_korgym_full_pipeline.sh korgym\ 2>nul
move /Y start_korgym_server.sh korgym\ 2>nul
move /Y compare_korgym_scores.py korgym\ 2>nul
move /Y eval_with_dataset.sh korgym\ 2>nul
move /Y preview_korgym_game.py korgym\ 2>nul
move /Y cleanup_korgym_temp_data.py korgym\ 2>nul
move /Y eval_korgym_with_dataset.py korgym\ 2>nul
move /Y init_korgym_dataset.py korgym\ 2>nul
move /Y init_korgym_eval_dataset.py korgym\ 2>nul
move /Y restart_korgym_training.sh korgym\ 2>nul
move /Y run_korgym_eval.py korgym\ 2>nul
move /Y compare_korgym_results.py korgym\ 2>nul
move /Y debug_game_server.py korgym\ 2>nul
move /Y start_korgym_server.py korgym\ 2>nul
move /Y test_korgym_adapter.py korgym\ 2>nul

echo.
echo 移动 ZebraLogic 脚本...
move /Y view_zebralogic_results.py games\zebralogic\ 2>nul
move /Y run_zebralogic_experiment.sh games\zebralogic\ 2>nul
move /Y diagnose_zebralogic_eval.py games\zebralogic\ 2>nul
move /Y compare_zebralogic_results.py games\zebralogic\ 2>nul
move /Y clean_zebralogic_training_data.py games\zebralogic\ 2>nul
move /Y check_zebralogic_data.py games\zebralogic\ 2>nul
move /Y analyze_zebra_dataset.py games\zebralogic\ 2>nul

echo.
echo 移动 Wordle 脚本...
move /Y analyze_wordle_top20.py games\wordle\ 2>nul
move /Y test_wordle_config.py games\wordle\ 2>nul
move /Y run_wordle_full_experiment.sh games\wordle\ 2>nul
move /Y diagnose_wordle_training.py games\wordle\ 2>nul
move /Y clean_wordle_data.sh games\wordle\ 2>nul
move /Y check_wordle_eval_samples.py games\wordle\ 2>nul
move /Y check_wordle_dataset.py games\wordle\ 2>nul

echo.
echo 移动 Word Puzzle 脚本...
move /Y analyze_word_puzzle_results.py games\word_puzzle\ 2>nul
move /Y debug_word_puzzle_results.py games\word_puzzle\ 2>nul
move /Y run_complete_word_puzzle_experiment.sh games\word_puzzle\ 2>nul
move /Y run_word_puzzle_experiment.sh games\word_puzzle\ 2>nul
move /Y run_word_puzzle_72b_full_experiment.sh games\word_puzzle\ 2>nul
move /Y eval_word_puzzle_paper_aligned.py games\word_puzzle\ 2>nul
move /Y clean_word_puzzle_data.sh games\word_puzzle\ 2>nul

echo.
echo 移动 Alphabetical Sorting 脚本...
move /Y clean_alphabetical_sorting_cache.py games\alphabetical_sorting\ 2>nul
move /Y restart_alphabetical_sorting_training.py games\alphabetical_sorting\ 2>nul
move /Y run_alphabetical_sorting_full_experiment.sh games\alphabetical_sorting\ 2>nul
move /Y run_alphabetical_sorting_experiment.sh games\alphabetical_sorting\ 2>nul
move /Y quick_test_alphabetical_prompts.sh games\alphabetical_sorting\ 2>nul
move /Y clean_and_restart_alphabetical_sorting.sh games\alphabetical_sorting\ 2>nul

echo.
echo 移动错误分析脚本...
move /Y inspect_error_analysis_output.py error_analysis\ 2>nul
move /Y logic_conflict_detector.py error_analysis\ 2>nul
move /Y logic_conflict_detector_example.py error_analysis\ 2>nul
move /Y test_error_analysis_v2.py error_analysis\ 2>nul
move /Y test_logic_verify.py error_analysis\ 2>nul
move /Y view_actual_error_analysis.py error_analysis\ 2>nul
move /Y view_problem_details.py error_analysis\ 2>nul
move /Y test_error_extractor.py error_analysis\ 2>nul
move /Y test_agent_answers_verification.py error_analysis\ 2>nul
move /Y logic_error_analyzer.py error_analysis\ 2>nul
move /Y simple_test_logic_error_analyzer.py error_analysis\ 2>nul
move /Y test_logic_error_analyzer.py error_analysis\ 2>nul
move /Y detailed_debug_verifier.py error_analysis\ 2>nul
move /Y debug_logic_verifier.py error_analysis\ 2>nul
move /Y test_improved_verifier.py error_analysis\ 2>nul
move /Y test_logic_verifier.py error_analysis\ 2>nul

echo.
echo 移动实验脚本...
move /Y compare_paper_scores.py experiments\ 2>nul
move /Y run_paper_experiment_wsl_v2.sh experiments\ 2>nul
move /Y run_paper_experiment_wsl.sh experiments\ 2>nul
move /Y run_paper_experiment.py experiments\ 2>nul
move /Y get_per_problem_stats.py experiments\ 2>nul
move /Y generate_per_problem_report.py experiments\ 2>nul
move /Y extract_specific_problems.py experiments\ 2>nul
move /Y compare_training_changes.py experiments\ 2>nul
move /Y compare_specific_problems.py experiments\ 2>nul
move /Y analyze_report_statistics.py experiments\ 2>nul
move /Y analyze_problem_commonality.py experiments\ 2>nul
move /Y analyze_per_problem_correctness.py experiments\ 2>nul
move /Y analyze_incomplete_reasoning_detection.py experiments\ 2>nul
move /Y analyze_difficulty_distribution.py experiments\ 2>nul
move /Y analyze_clues_difficulty.py experiments\ 2>nul
move /Y analyze_baseline_failures.py experiments\ 2>nul
move /Y analyze_answer_format.py experiments\ 2>nul

echo.
echo 移动通用工具...
move /Y view_eval_results.py utils\ 2>nul
move /Y view_dataset.py utils\ 2>nul
move /Y clean_and_recreate_datasets.py utils\ 2>nul
move /Y get_training_statistics.py utils\ 2>nul
move /Y analyze_training_statistics.py utils\ 2>nul
move /Y view_training_results.py utils\ 2>nul
move /Y check_experiments.py utils\ 2>nul
move /Y clean_experiment_data.py utils\ 2>nul
move /Y quick_view_results.py utils\ 2>nul
move /Y view_evaluation_details.py utils\ 2>nul
move /Y check_model_config.py utils\ 2>nul
move /Y check_siliconflow_models.py utils\ 2>nul
move /Y simple_debug.py utils\ 2>nul
move /Y verify_clean.py utils\ 2>nul
move /Y test_multiround_eval.py utils\ 2>nul
move /Y analyze_hierarchical_experiences.py utils\ 2>nul
move /Y test_hierarchical_experience.py utils\ 2>nul

cd ..

echo.
echo ========================================
echo 重组完成！
echo ========================================
echo.
echo 新的目录结构：
echo   scripts/
echo     ├── korgym/              (18 files)
echo     ├── games/
echo     │   ├── zebralogic/      (7 files)
echo     │   ├── wordle/          (7 files)
echo     │   ├── word_puzzle/     (7 files)
echo     │   └── alphabetical_sorting/ (6 files)
echo     ├── error_analysis/      (16 files)
echo     ├── experiments/         (17 files)
echo     └── utils/               (17 files)
echo.
pause






