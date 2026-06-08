#!/usr/bin/env bash
# =============================================================================
# TF-LLM Linux 部署脚本
#
# 用法:
#   # 全新部署（交互式配置 API Key）
#   bash scripts/setup/deploy.sh
#
#   # 指定 API Key 非交互部署
#   bash scripts/setup/deploy.sh --api-key sk-xxxx
#
#   # 指定模型和 API 地址（适配国产模型）
#   bash scripts/setup/deploy.sh --api-key sk-xxxx --model qwen-plus \
#       --base-url https://dashscope.aliyuncs.com/compatible-mode/v1
#
#   # 仅更新依赖（已部署后）
#   bash scripts/setup/deploy.sh --update-only
#
#   # 跳过 KORGym 安装（只用 SkillsBench/LiveCodeBench）
#   bash scripts/setup/deploy.sh --api-key sk-xxxx --no-korgym
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 颜色定义
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "  ${RED}✗${NC} $*" >&2; }
info() { echo -e "  ${CYAN}→${NC} $*"; }
step() { echo -e "\n${BOLD}${BLUE}[$1]${NC} ${BOLD}$2${NC}"; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
API_KEY=""
MODEL="deepseek-chat"
BASE_URL="https://api.deepseek.com/v1"
UPDATE_ONLY=false
NO_KORGYM=false
REPO_URL="https://github.com/TencentCloudADP/youtu-agent.git"  # 按需修改
INSTALL_DIR="${INSTALL_DIR:-$(pwd)}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-key)     API_KEY="$2";    shift 2 ;;
    --model)       MODEL="$2";      shift 2 ;;
    --base-url)    BASE_URL="$2";   shift 2 ;;
    --repo)        REPO_URL="$2";   shift 2 ;;
    --dir)         INSTALL_DIR="$2"; shift 2 ;;
    --update-only) UPDATE_ONLY=true; shift ;;
    --no-korgym)   NO_KORGYM=true;  shift ;;
    -h|--help)
      sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) die "未知参数: $1  (使用 --help 查看帮助)" ;;
  esac
done

# ---------------------------------------------------------------------------
# 标题
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${BLUE}=================================================${NC}"
echo -e "${BOLD}${BLUE}   TF-LLM  Linux 部署脚本                       ${NC}"
echo -e "${BOLD}${BLUE}   Training-Free GRPO + 分层经验学习系统         ${NC}"
echo -e "${BOLD}${BLUE}=================================================${NC}"
echo ""

# ---------------------------------------------------------------------------
# STEP 1: 检查先决条件
# ---------------------------------------------------------------------------
step "1/6" "检查先决条件"

# Python
if ! command -v python3 &>/dev/null; then
  die "Python3 未安装。请安装 Python 3.10+：\n    sudo apt install python3.10 python3.10-venv"
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [[ $PY_MAJOR -lt 3 || ($PY_MAJOR -eq 3 && $PY_MINOR -lt 10) ]]; then
  die "Python $PY_VER 版本过低，需要 3.10+。当前版本: $PY_VER"
fi
ok "Python $PY_VER"

# git
command -v git &>/dev/null || die "git 未安装：sudo apt install git"
ok "git $(git --version | awk '{print $3}')"

# uv
if ! command -v uv &>/dev/null; then
  warn "uv 未安装，正在安装..."
  pip3 install uv --quiet || die "uv 安装失败，请手动执行：pip3 install uv"
fi
ok "uv $(uv --version | awk '{print $2}')"

# curl（API 连通性测试用）
command -v curl &>/dev/null && ok "curl" || warn "curl 未安装，将跳过 API 连通性测试"

# ---------------------------------------------------------------------------
# STEP 2: 获取代码
# ---------------------------------------------------------------------------
step "2/6" "获取代码"

if [[ "$UPDATE_ONLY" == true ]]; then
  info "更新模式：只拉取最新代码"
  if [[ ! -f pyproject.toml ]]; then
    die "当前目录不是项目根目录，请先 cd 到项目目录，或去掉 --update-only"
  fi
  git pull --ff-only
  ok "代码已更新到最新版本"
else
  if [[ -f pyproject.toml ]]; then
    ok "已在项目目录中，跳过 clone（如需更新请加 --update-only）"
  else
    info "克隆仓库到 $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ok "仓库克隆完成"
  fi
fi

# 确认项目根目录
[[ -f pyproject.toml ]] || die "pyproject.toml 不存在，请确认当前目录为项目根目录"

# ---------------------------------------------------------------------------
# STEP 3: 安装主项目依赖
# ---------------------------------------------------------------------------
step "3/6" "安装主项目依赖"

info "运行 uv sync（首次可能需要几分钟）..."
uv sync --quiet
ok "主项目依赖安装完成"

# 激活虚拟环境（后续命令使用）
VENV_PYTHON=".venv/bin/python"
VENV_PIP=".venv/bin/pip"
[[ -f "$VENV_PYTHON" ]] || die ".venv 未创建，请检查 uv sync 输出"

# ---------------------------------------------------------------------------
# STEP 4: 安装 KORGym 依赖（可跳过）
# ---------------------------------------------------------------------------
step "4/6" "安装 KORGym 游戏环境依赖"

if [[ "$NO_KORGYM" == true ]]; then
  warn "已跳过 KORGym 安装（--no-korgym）"
  warn "若需使用 KORGym 游戏，请后续手动执行："
  warn "  .venv/bin/pip install -r KORGym/requirements.txt"
elif [[ -f "KORGym/requirements.txt" ]]; then
  info "安装 KORGym 依赖..."
  "$VENV_PIP" install -r KORGym/requirements.txt --quiet
  ok "KORGym 依赖安装完成"
else
  warn "KORGym/requirements.txt 不存在，跳过"
fi

# ---------------------------------------------------------------------------
# STEP 5: 配置 .env
# ---------------------------------------------------------------------------
step "5/6" "配置环境变量 (.env)"

if [[ -f .env ]]; then
  ok ".env 文件已存在"
  # 检查 API Key 是否已填写
  EXISTING_KEY=$(grep -E '^UTU_LLM_API_KEY=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
  if [[ -n "$EXISTING_KEY" ]]; then
    ok "API Key 已配置"
    if [[ -n "$API_KEY" && "$API_KEY" != "$EXISTING_KEY" ]]; then
      warn "检测到 --api-key 参数与现有 .env 不同，将更新..."
      sed -i "s|^UTU_LLM_API_KEY=.*|UTU_LLM_API_KEY=${API_KEY}|" .env
      ok "API Key 已更新"
    fi
  else
    # API Key 为空
    if [[ -z "$API_KEY" ]]; then
      echo ""
      echo -e "  ${YELLOW}请输入 LLM API Key（回车跳过，之后手动编辑 .env）：${NC}"
      echo -e "  支持：DeepSeek (https://platform.deepseek.com/)"
      echo -e "         阿里云百炼 (https://dashscope.aliyuncs.com/)"
      echo -e "         硅基流动、OpenAI 等兼容 OpenAI 格式的服务"
      read -rp "  API Key: " API_KEY
    fi
    if [[ -n "$API_KEY" ]]; then
      sed -i "s|^UTU_LLM_API_KEY=.*|UTU_LLM_API_KEY=${API_KEY}|" .env
      ok "API Key 已写入 .env"
    else
      warn "API Key 未填写，请之后手动编辑 .env：  UTU_LLM_API_KEY=your-key"
    fi
  fi
else
  # 从模板创建 .env
  if [[ -f .env.example ]]; then
    cp .env.example .env
    ok ".env 已从 .env.example 创建"
  else
    cat > .env << 'ENVEOF'
UTU_LLM_TYPE=chat.completions
UTU_LLM_MODEL=deepseek-chat
UTU_LLM_BASE_URL=https://api.deepseek.com/v1
UTU_LLM_API_KEY=
UTU_DB_URL=sqlite:///test.db
UTU_LOG_LEVEL=WARNING
ENVEOF
    ok ".env 已从内置模板创建"
  fi

  # 写入 API Key / Model / Base URL
  if [[ -z "$API_KEY" ]]; then
    echo ""
    echo -e "  ${YELLOW}请输入 LLM API Key（回车跳过，之后手动编辑 .env）：${NC}"
    read -rp "  API Key: " API_KEY
  fi
  [[ -n "$API_KEY" ]]    && sed -i "s|^UTU_LLM_API_KEY=.*|UTU_LLM_API_KEY=${API_KEY}|" .env
  sed -i "s|^UTU_LLM_MODEL=.*|UTU_LLM_MODEL=${MODEL}|" .env
  sed -i "s|^UTU_LLM_BASE_URL=.*|UTU_LLM_BASE_URL=${BASE_URL}|" .env
  [[ -n "$API_KEY" ]] && ok "API Key / Model / Base URL 已写入 .env" || warn "API Key 未填写，请手动编辑 .env"
fi

# ---------------------------------------------------------------------------
# STEP 6: 验证安装
# ---------------------------------------------------------------------------
step "6/6" "验证安装"

PASS=0; FAIL=0

check_import() {
  local pkg="$1" label="${2:-$1}"
  if "$VENV_PYTHON" -c "import $pkg" &>/dev/null; then
    ok "$label"
    PASS=$((PASS+1))
  else
    err "$label 导入失败"
    FAIL=$((FAIL+1))
  fi
}

check_import utu          "utu 核心包"
check_import openai       "openai"
check_import sqlmodel     "sqlmodel (数据库)"
check_import hydra        "hydra (配置管理)"
check_import jinja2       "jinja2 (模板引擎)"

if [[ "$NO_KORGYM" == false && -f "KORGym/requirements.txt" ]]; then
  check_import flask  "flask (KORGym 服务器)"
  check_import numpy  "numpy"
fi

# API 连通性测试
if [[ -n "$API_KEY" ]] && command -v curl &>/dev/null; then
  info "测试 API 连通性..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    "${BASE_URL%/v1}/v1/models" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" == "200" ]]; then
    ok "LLM API 连通正常 (HTTP $HTTP_CODE)"
  elif [[ "$HTTP_CODE" == "401" ]]; then
    warn "API Key 认证失败 (HTTP 401)，请检查 .env 中的 UTU_LLM_API_KEY"
  else
    warn "API 连通性测试返回 HTTP $HTTP_CODE（可能是防火墙限制，不影响部署）"
  fi
fi

# 汇总
echo ""
if [[ $FAIL -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}  ✓ 验证通过（$PASS 项全部正常）${NC}"
else
  echo -e "${YELLOW}${BOLD}  ⚠ 验证完成：$PASS 项正常，$FAIL 项失败${NC}"
fi

# ---------------------------------------------------------------------------
# 完成：打印下一步
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}${GREEN}=================================================${NC}"
echo -e "${BOLD}${GREEN}  部署完成！                                     ${NC}"
echo -e "${BOLD}${GREEN}=================================================${NC}"
echo ""

# 检查 API Key 是否已配置
FINAL_KEY=$(grep -E '^UTU_LLM_API_KEY=' .env | cut -d= -f2- | tr -d '"' | tr -d "'" || true)
if [[ -z "$FINAL_KEY" ]]; then
  echo -e "${YELLOW}  ⚠ 提醒：UTU_LLM_API_KEY 尚未填写，运行实验前请先编辑 .env${NC}"
  echo ""
fi

echo -e "${BOLD}  下一步操作：${NC}"
echo ""
echo -e "  ${CYAN}1. 运行 SkillsBench 评估（无需游戏服务器）${NC}"
echo "     uv run python scripts/run_eval.py --config_name skillsbench/skillsbench_baseline_eval"
echo ""
echo -e "  ${CYAN}2. 启动 KORGym 游戏服务器（以 Wordle 为例）${NC}"
echo "     # 在单独终端中运行："
echo "     cd KORGym/game_lib/33-wordle && python game_lib.py -p 8777"
echo "     # 然后在项目根目录运行评估："
echo "     uv run python scripts/run_eval.py --config_name korgym/wordle_eval"
echo ""
echo -e "  ${CYAN}3. 运行 Training-Free GRPO 训练${NC}"
echo "     uv run python scripts/run_training_free_GRPO.py --config_name skillsbench/skillsbench_practice"
echo ""
echo -e "  ${CYAN}4. 查看评估结果${NC}"
echo "     uv run python scripts/utils/view_benchmark_results.py -e skillsbench_baseline_eval"
echo "     uv run python scripts/utils/view_results.py -e exp_id --compare"
echo ""
echo -e "  ${CYAN}5. 完整脚本使用说明${NC}"
echo "     cat scripts/README.md"
echo ""
echo -e "  ${CYAN}6. 更新项目${NC}"
echo "     bash scripts/setup/deploy.sh --update-only"
echo ""
