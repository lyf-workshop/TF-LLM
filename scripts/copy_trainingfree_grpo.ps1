# 复制 Training-Free GRPO 文件到独立文件夹
# PowerShell 脚本

param(
    [string]$TargetDir = "F:\trainingfree-grpo-standalone"
)

# 创建目标目录
Write-Host "=========================================================================="  -ForegroundColor Cyan
Write-Host "Copying Training-Free GRPO files" -ForegroundColor Cyan
Write-Host "Target directory: $TargetDir" -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Creating target directory..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

# 复制核心代码
Write-Host "`n📦 Copying core code files..." -ForegroundColor Yellow
$corePaths = @(
    "utu\practice",
    "utu\eval",
    "utu\db",
    "utu\agents",
    "utu\config",
    "utu\prompts\practice",
    "utu\utils"
)

foreach ($path in $corePaths) {
    if (Test-Path $path) {
        $dest = Join-Path $TargetDir $path
        Write-Host "  ✓ Copying $path" -ForegroundColor Green
        Copy-Item -Path $path -Destination $dest -Recurse -Force
    } else {
        Write-Host "  ⚠ Skipping $path (not found)" -ForegroundColor DarkYellow
    }
}

# 复制配置文件
Write-Host "`n⚙️  Copying configuration files..." -ForegroundColor Yellow
$configPaths = @(
    "configs\agents\practice",
    "configs\practice",
    "configs\eval\math",
    "configs\model"
)

foreach ($path in $configPaths) {
    if (Test-Path $path) {
        $dest = Join-Path $TargetDir $path
        Write-Host "  ✓ Copying $path" -ForegroundColor Green
        Copy-Item -Path $path -Destination $dest -Recurse -Force
    } else {
        Write-Host "  ⚠ Skipping $path (not found)" -ForegroundColor DarkYellow
    }
}

# 复制脚本文件
Write-Host "`n📜 Copying script files..." -ForegroundColor Yellow
$scriptFiles = @(
    "scripts\run_training_free_GRPO.py",
    "scripts\run_eval.py",
    "scripts\run_paper_experiment_wsl_v2.sh",
    "scripts\clean_experiment_data.py",
    "scripts\view_training_results.py",
    "scripts\data\create_dapo_100.py",
    "scripts\data\process_training_free_GRPO_data.py"
)

foreach ($file in $scriptFiles) {
    if (Test-Path $file) {
        $dest = Join-Path $TargetDir $file
        $destDir = Split-Path $dest -Parent
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        Write-Host "  ✓ Copying $file" -ForegroundColor Green
        Copy-Item -Path $file -Destination $dest -Force
    } else {
        Write-Host "  ⚠ Skipping $file (not found)" -ForegroundColor DarkYellow
    }
}

# 复制文档文件
Write-Host "`n📚 Copying documentation files..." -ForegroundColor Yellow
$docFiles = @(
    "utu\practice\README.md",
    "论文实验复现指南_DeepSeekV3.1.md",
    "WSL论文实验复现完整指南.md",
    "Training-Free_GRPO文件清单.md",
    "经验库使用机制说明.md",
    "查看训练结果指南.md",
    "数据库清理指南.md",
    "WSL快速开始卡片.md",
    "WSL使用说明.md",
    "复制Training-Free_GRPO文件指南.md"
)

foreach ($file in $docFiles) {
    if (Test-Path $file) {
        $dest = Join-Path $TargetDir $file
        $destDir = Split-Path $dest -Parent
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        Write-Host "  ✓ Copying $file" -ForegroundColor Green
        Copy-Item -Path $file -Destination $dest -Force
    } else {
        Write-Host "  ⚠ Skipping $file (not found)" -ForegroundColor DarkYellow
    }
}

# 复制依赖文件
Write-Host "`n📦 Copying dependency files..." -ForegroundColor Yellow
$depFiles = @(
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    "README.md"
)

foreach ($file in $depFiles) {
    if (Test-Path $file) {
        $dest = Join-Path $TargetDir $file
        Write-Host "  ✓ Copying $file" -ForegroundColor Green
        Copy-Item -Path $file -Destination $dest -Force
    } else {
        Write-Host "  ⚠ Skipping $file (not found)" -ForegroundColor DarkYellow
    }
}

# 创建说明文件
Write-Host "`n📝 Creating README..." -ForegroundColor Yellow
$readmeContent = @"
# Training-Free GRPO Standalone Package

This is a standalone package containing all files needed to run Training-Free GRPO experiments.

## Setup

1. Install dependencies:
   ``````powershell
   uv sync --all-extras
   ``````

2. Configure API keys in ``.env``:
   ``````powershell
   Copy-Item .env.example .env
   # Edit .env and add your API keys
   notepad .env
   ``````

3. Activate virtual environment:
   ``````powershell
   .\.venv\Scripts\Activate.ps1
   ``````

4. Install math-verify:
   ``````powershell
   uv pip install math-verify
   ``````

## Quick Start

See the documentation files for detailed instructions:
- 论文实验复现指南_DeepSeekV3.1.md
- WSL论文实验复现完整指南.md
- Training-Free_GRPO文件清单.md

## Run Experiment

``````powershell
# Prepare data
uv run python scripts/data/process_training_free_GRPO_data.py
uv run python scripts/data/create_dapo_100.py

# Run training
uv run python scripts/run_training_free_GRPO.py --config_name math_reasoning_paper_exp

# Run evaluation
uv run python scripts/run_eval.py --config_name math/math_practice_paper_exp_AIME24
uv run python scripts/run_eval.py --config_name math/math_practice_paper_exp_AIME25
``````

## Documentation

- Training-Free_GRPO文件清单.md - Complete file listing
- 经验库使用机制说明.md - How experience library works
- 查看训练结果指南.md - View training results
- 复制Training-Free_GRPO文件指南.md - File copy guide

---
Package created on: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@

$readmeContent | Out-File -FilePath (Join-Path $TargetDir "README_STANDALONE.md") -Encoding UTF8

Write-Host "`n=========================================================================="  -ForegroundColor Green
Write-Host "✓ Copy completed successfully!" -ForegroundColor Green
Write-Host "==========================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Target directory: " -NoNewline
Write-Host "$TargetDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. cd $TargetDir"
Write-Host "  2. uv sync --all-extras"
Write-Host "  3. Copy-Item .env.example .env  # Then edit .env"
Write-Host "  4. .\.venv\Scripts\Activate.ps1"
Write-Host "  5. Follow README_STANDALONE.md for usage"
Write-Host ""




