#!/bin/bash
# ============================================
# 安装所有项目依赖脚本 (Linux/WSL/macOS)
# ============================================

set -e  # 遇到错误立即退出

echo ""
echo "============================================"
echo "安装 Youtu-Agent 和 KORGym 所有依赖"
echo "============================================"
echo ""

# 检查 Python 版本
echo "[1/6] 检查 Python 版本..."
if ! command -v python3 &> /dev/null; then
    echo "[错误] Python3 未安装"
    echo "请安装 Python 3.12 或更高版本"
    exit 1
fi

python3 --version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Python $PYTHON_VERSION 已安装"
echo ""

# 检查 uv 是否安装
echo "[2/6] 检查 uv 包管理器..."
if ! command -v uv &> /dev/null; then
    echo "[警告] uv 未安装，正在安装..."
    pip3 install uv
    if [ $? -ne 0 ]; then
        echo "[错误] uv 安装失败"
        exit 1
    fi
fi
echo "✓ uv 已安装"
echo ""

# 安装主项目依赖
echo "[3/6] 安装主项目依赖..."
echo "使用 uv sync 安装依赖（这可能需要几分钟）..."
uv sync
if [ $? -ne 0 ]; then
    echo "[错误] 主项目依赖安装失败"
    exit 1
fi
echo "✓ 主项目依赖安装完成"
echo ""

# 激活虚拟环境并安装 KORGym 依赖
echo "[4/6] 安装 KORGym 依赖..."
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    echo "✓ 虚拟环境已激活"
    
    echo "安装 KORGym 游戏环境依赖..."
    pip install -r KORGym/requirements.txt
    if [ $? -ne 0 ]; then
        echo "[错误] KORGym 依赖安装失败"
        exit 1
    fi
    echo "✓ KORGym 依赖安装完成"
else
    echo "[警告] 虚拟环境未找到，使用全局 Python 环境"
    pip3 install -r KORGym/requirements.txt
    if [ $? -ne 0 ]; then
        echo "[错误] KORGym 依赖安装失败"
        exit 1
    fi
fi
echo ""

# 配置环境文件
echo "[5/6] 配置环境文件..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "创建 .env 文件..."
        cp .env.example .env
        echo "✓ .env 文件已创建"
        echo "[重要] 请编辑 .env 文件，填入你的 API Keys"
    else
        echo "[警告] .env.example 不存在，跳过环境文件创建"
    fi
else
    echo "✓ .env 文件已存在"
fi
echo ""

# 验证安装
echo "[6/6] 验证安装..."
echo "检查关键包..."

if python3 -c "import utu" &> /dev/null; then
    echo "✓ utu 包可用"
else
    echo "✗ utu 包未找到"
fi

if python3 -c "import flask" &> /dev/null; then
    echo "✓ flask 可用 (KORGym 游戏服务器)"
else
    echo "✗ flask 未找到 (KORGym 可能无法运行)"
fi

if python3 -c "import openai" &> /dev/null; then
    echo "✓ openai 包可用"
else
    echo "✗ openai 包未找到"
fi

echo ""
echo "============================================"
echo "安装完成！"
echo "============================================"
echo ""
echo "下一步操作："
echo "1. 编辑 .env 文件，配置 API Keys:"
echo "   - UTU_LLM_API_KEY (必需)"
echo "   - SERPER_API_KEY (可选，用于搜索)"
echo "   - JINA_API_KEY (可选，用于网页读取)"
echo ""
echo "2. 测试安装:"
echo "   python scripts/korgym/check_korgym_env.py"
echo ""
echo "3. 启动 KORGym 游戏服务器:"
echo "   cd KORGym/game_lib/33-wordle"
echo "   python game_lib.py -p 8777"
echo ""
echo "4. 运行第一个实验:"
echo "   uv run python scripts/run_eval.py --config_name korgym/wordle_eval"
echo ""

