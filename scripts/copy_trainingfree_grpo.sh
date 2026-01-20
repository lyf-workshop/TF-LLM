#!/bin/bash
# 复制 Training-Free GRPO 文件到独立文件夹

set -e

# 设置目标文件夹路径
TARGET_DIR="$HOME/trainingfree-grpo-standalone"

# 如果提供了参数，使用参数作为目标路径
if [ $# -eq 1 ]; then
    TARGET_DIR="$1"
fi

echo "=========================================================================="
echo "Copying Training-Free GRPO files"
echo "Target directory: $TARGET_DIR"
echo "=========================================================================="
echo

# 创建目标目录
echo "Creating target directory..."
mkdir -p "$TARGET_DIR"

# 复制核心代码
echo -e "\n📦 Copying core code files..."
CORE_PATHS=(
    "utu/practice"
    "utu/eval"
    "utu/db"
    "utu/agents"
    "utu/config"
    "utu/prompts/practice"
    "utu/utils"
)

for path in "${CORE_PATHS[@]}"; do
    if [ -e "$path" ]; then
        echo "  ✓ Copying $path"
        mkdir -p "$TARGET_DIR/$(dirname $path)"
        cp -r "$path" "$TARGET_DIR/$path"
    else
        echo "  ⚠ Skipping $path (not found)"
    fi
done

# 复制配置文件
echo -e "\n⚙️  Copying configuration files..."
CONFIG_PATHS=(
    "configs/agents/practice"
    "configs/practice"
    "configs/eval/math"
    "configs/model"
)

for path in "${CONFIG_PATHS[@]}"; do
    if [ -e "$path" ]; then
        echo "  ✓ Copying $path"
        mkdir -p "$TARGET_DIR/$(dirname $path)"
        cp -r "$path" "$TARGET_DIR/$path"
    else
        echo "  ⚠ Skipping $path (not found)"
    fi
done

# 复制脚本文件
echo -e "\n📜 Copying script files..."
SCRIPT_FILES=(
    "scripts/run_training_free_GRPO.py"
    "scripts/run_eval.py"
    "scripts/run_paper_experiment_wsl_v2.sh"
    "scripts/clean_experiment_data.py"
    "scripts/view_training_results.py"
    "scripts/data/create_dapo_100.py"
    "scripts/data/process_training_free_GRPO_data.py"
)

for file in "${SCRIPT_FILES[@]}"; do
    if [ -e "$file" ]; then
        echo "  ✓ Copying $file"
        mkdir -p "$TARGET_DIR/$(dirname $file)"
        cp "$file" "$TARGET_DIR/$file"
    else
        echo "  ⚠ Skipping $file (not found)"
    fi
done

# 复制文档文件
echo -e "\n📚 Copying documentation files..."
DOC_FILES=(
    "utu/practice/README.md"
    "论文实验复现指南_DeepSeekV3.1.md"
    "WSL论文实验复现完整指南.md"
    "Training-Free_GRPO文件清单.md"
    "经验库使用机制说明.md"
    "查看训练结果指南.md"
    "数据库清理指南.md"
    "WSL快速开始卡片.md"
    "WSL使用说明.md"
    "复制Training-Free_GRPO文件指南.md"
)

for file in "${DOC_FILES[@]}"; do
    if [ -e "$file" ]; then
        echo "  ✓ Copying $file"
        mkdir -p "$TARGET_DIR/$(dirname $file)"
        cp "$file" "$TARGET_DIR/$file"
    else
        echo "  ⚠ Skipping $file (not found)"
    fi
done

# 复制依赖文件
echo -e "\n📦 Copying dependency files..."
DEP_FILES=(
    "pyproject.toml"
    "uv.lock"
    ".env.example"
    "README.md"
)

for file in "${DEP_FILES[@]}"; do
    if [ -e "$file" ]; then
        echo "  ✓ Copying $file"
        cp "$file" "$TARGET_DIR/$file"
    else
        echo "  ⚠ Skipping $file (not found)"
    fi
done

# 创建说明文件
echo -e "\n📝 Creating README..."
cat > "$TARGET_DIR/README_STANDALONE.md" << 'EOF'
# Training-Free GRPO Standalone Package

This is a standalone package containing all files needed to run Training-Free GRPO experiments.

## Setup

1. Install dependencies:
   ```bash
   uv sync --all-extras
   ```

2. Configure API keys in `.env`:
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   nano .env
   ```

3. Install math-verify:
   ```bash
   uv pip install math-verify
   ```

## Quick Start

See the documentation files for detailed instructions:
- 论文实验复现指南_DeepSeekV3.1.md
- WSL论文实验复现完整指南.md
- Training-Free_GRPO文件清单.md

## Run Experiment

```bash
# Activate virtual environment
source .venv/bin/activate

# Prepare data
uv run python scripts/data/process_training_free_GRPO_data.py
uv run python scripts/data/create_dapo_100.py

# Run training
uv run python scripts/run_training_free_GRPO.py --config_name math_reasoning_paper_exp

# Run evaluation
uv run python scripts/run_eval.py --config_name math/math_practice_paper_exp_AIME24
uv run python scripts/run_eval.py --config_name math/math_practice_paper_exp_AIME25
```

## Documentation

- Training-Free_GRPO文件清单.md - Complete file listing
- 经验库使用机制说明.md - How experience library works
- 查看训练结果指南.md - View training results
- 复制Training-Free_GRPO文件指南.md - File copy guide

---
Package created on: $(date)
EOF

echo -e "\n=========================================================================="
echo "✓ Copy completed successfully!"
echo "=========================================================================="
echo
echo "Target directory: $TARGET_DIR"
echo
echo "Next steps:"
echo "  1. cd $TARGET_DIR"
echo "  2. uv sync --all-extras"
echo "  3. cp .env.example .env && nano .env  # Configure API keys"
echo "  4. source .venv/bin/activate"
echo "  5. Follow README_STANDALONE.md for usage"
echo




