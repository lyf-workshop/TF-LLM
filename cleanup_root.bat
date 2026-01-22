@echo off
chcp 65001 > nul
echo.
echo ========================================
echo 清理根目录临时文件
echo ========================================
echo.

echo 移动重组文档到归档...
move /Y "DOCS_ORGANIZATION_COMPLETE.md" "docs\archive\docs_organization_complete.md"
move /Y "DOCS_REORGANIZATION_GUIDE.md" "docs\archive\docs_reorganization_guide.md"
move /Y "DOCS_REORGANIZATION_PLAN.md" "docs\archive\docs_reorganization_plan.md"
move /Y "FINAL_CLEANUP_INSTRUCTIONS.md" "docs\archive\final_cleanup_instructions.md"
move /Y "FINAL_DOCS_REORGANIZATION_REPORT.md" "docs\archive\final_reorganization_report.md"

echo.
echo 删除重组脚本...
del /Q reorganize_docs.bat
del /Q reorganize_docs.py
del /Q execute_reorganization.py
del /Q finish_reorganization.py
del /Q finish_remaining_moves.bat
del /Q move_remaining_docs.bat

echo.
echo 删除已复制的PDF（已在 docs/advanced/papers/ 中）...
del /Q "Training-Free Group Relative Policy Optimization.pdf"

echo.
echo ========================================
echo 清理完成！
echo ========================================
echo.
echo 根目录剩余的 .md 文件:
dir /B *.md
echo.
echo 这些是应该保留的项目文档：
echo - README.md
echo - README_JA.md
echo - README_KORGYM_FORK.md
echo - CONTRIBUTING.md
echo - CHANGELOG.md
echo.
pause






