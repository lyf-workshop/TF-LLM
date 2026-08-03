#!/bin/bash
# KORGym WSL 环境配置脚本
# 兼容现有 youtu-agent 项目

set -e  # 遇到错误立即退出

echo "=================================================="
echo "  KORGym + youtu-agent WSL 环境配置"
echo "=================================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查是否在 WSL 环境
if ! grep -qi microsoft /proc/version; then
    echo -e "${RED}警告: 当前可能不在 WSL 环境中${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 项目根目录
PROJECT_ROOT=$(pwd)
echo -e "${GREEN}✓${NC} 项目根目录: ${PROJECT_ROOT}"

# 步骤 1: 检查 Python 版本
echo ""
echo "步骤 1/6: 检查 Python 版本..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
REQUIRED_VERSION="3.12"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}✗ Python 版本过低: ${PYTHON_VERSION} (需要 >= ${REQUIRED_VERSION})${NC}"
    echo "请先升级 Python:"
    echo "  sudo apt update"
    echo "  sudo apt install python3.12 python3.12-venv python3.12-dev"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python 版本: ${PYTHON_VERSION}"

# 步骤 2: 检查 uv 工具
echo ""
echo "步骤 2/6: 检查 uv 工具..."
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}→${NC} 安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
    echo -e "${GREEN}✓${NC} uv 已安装"
else
    echo -e "${GREEN}✓${NC} uv 已存在"
fi

# 步骤 3: 创建/更新虚拟环境
echo ""
echo "步骤 3/6: 配置虚拟环境..."

if [ -d ".venv" ]; then
    echo -e "${YELLOW}→${NC} 虚拟环境已存在，将更新依赖..."
else
    echo -e "${YELLOW}→${NC} 创建新的虚拟环境..."
    uv venv
fi

# 激活虚拟环境
source .venv/bin/activate
echo -e "${GREEN}✓${NC} 虚拟环境已激活"

# 步骤 4: 安装 youtu-agent 依赖
echo ""
echo "步骤 4/6: 安装 youtu-agent 依赖..."
if [ -f "pyproject.toml" ]; then
    uv sync
    echo -e "${GREEN}✓${NC} youtu-agent 依赖已安装"
else
    echo -e "${RED}✗ 找不到 pyproject.toml${NC}"
    exit 1
fi

# 步骤 5: 安装 KORGym 依赖
echo ""
echo "步骤 5/6: 安装 KORGym 依赖..."

if [ ! -d "KORGym" ]; then
    echo -e "${RED}✗ 找不到 KORGym 目录${NC}"
    echo "请确保 KORGym 在项目根目录下"
    exit 1
fi

if [ -f "KORGym/requirements.txt" ]; then
    echo -e "${YELLOW}→${NC} 安装 KORGym 依赖..."
    
    # 合并安装，避免版本冲突
    cat KORGym/requirements.txt | while read package; do
        # 跳过空行和注释
        [[ -z "$package" || "$package" =~ ^#.* ]] && continue
        
        # 检查是否已安装
        package_name=$(echo $package | cut -d'=' -f1 | cut -d'>' -f1 | cut -d'<' -f1)
        if ! uv pip list | grep -qi "^${package_name} "; then
            echo "  安装: $package"
            uv pip install "$package" || echo "  警告: $package 安装失败，可能已有兼容版本"
        else
            echo "  跳过: $package (已安装)"
        fi
    done
    
    echo -e "${GREEN}✓${NC} KORGym 依赖已安装"
else
    echo -e "${RED}✗ 找不到 KORGym/requirements.txt${NC}"
    exit 1
fi

# 步骤 6: 验证安装
echo ""
echo "步骤 6/6: 验证安装..."

echo -e "${YELLOW}→${NC} 检查关键包..."
REQUIRED_PACKAGES=("requests" "fastapi" "uvicorn" "gymnasium" "openai" "tiktoken" "torch" "numpy" "pandas")
ALL_OK=true

for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if uv pip list | grep -qi "^${pkg} "; then
        version=$(uv pip list | grep -i "^${pkg} " | awk '{print $2}')
        echo -e "  ${GREEN}✓${NC} $pkg ($version)"
    else
        echo -e "  ${RED}✗${NC} $pkg (未安装)"
        ALL_OK=false
    fi
done

if [ "$ALL_OK" = false ]; then
    echo -e "${RED}✗ 部分依赖缺失，请检查错误信息${NC}"
    exit 1
fi

# 创建快捷脚本
echo ""
echo "创建快捷脚本..."

# 创建激活脚本
cat > activate_korgym.sh << 'EOF'
#!/bin/bash
# 激活 KORGym 环境
source .venv/bin/activate
echo "✓ KORGym 环境已激活"
echo "Python: $(python --version)"
echo "位置: $(which python)"
EOF
chmod +x activate_korgym.sh

# 创建测试脚本
cat > test_korgym_env.sh << 'EOF'
#!/bin/bash
# 测试 KORGym 环境
source .venv/bin/activate

echo "测试 Python 环境..."
python3 << 'PYTHON_TEST'
import sys
print(f"Python: {sys.version}")

# 测试关键包
packages = [
    'requests', 'fastapi', 'uvicorn', 'gymnasium', 
    'openai', 'tiktoken', 'torch', 'numpy', 'pandas',
    'utu'  # youtu-agent 包
]

print("\n检查包:")
for pkg in packages:
    try:
        mod = __import__(pkg)
        version = getattr(mod, '__version__', 'N/A')
        print(f"  ✓ {pkg} ({version})")
    except ImportError as e:
        print(f"  ✗ {pkg} (未找到)")

print("\n✓ 环境测试完成")
PYTHON_TEST
EOF
chmod +x test_korgym_env.sh

echo -e "${GREEN}✓${NC} 快捷脚本已创建:"
echo "  - activate_korgym.sh  (激活环境)"
echo "  - test_korgym_env.sh  (测试环境)"

# 最终总结
echo ""
echo "=================================================="
echo -e "${GREEN}✓ 环境配置完成！${NC}"
echo "=================================================="
echo ""
echo "下一步操作:"
echo ""
echo "1. 激活环境 (每次新终端需要运行):"
echo "   source .venv/bin/activate"
echo "   或使用: source activate_korgym.sh"
echo ""
echo "2. 测试环境:"
echo "   bash test_korgym_env.sh"
echo ""
echo "3. 运行 KORGym 测试:"
echo "   uv run python scripts/test_korgym_adapter.py"
echo ""
echo "4. 手动启动游戏服务器:"
echo "   python scripts/start_korgym_server.py 3-2048"
echo ""
echo "=================================================="

# 自动测试
echo ""
read -p "是否立即测试环境? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    bash test_korgym_env.sh
fi

echo ""
echo -e "${GREEN}完成！${NC}"












