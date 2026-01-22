# 📦 完整安装指南

## 🚀 快速安装

### Windows

```cmd
install_all_dependencies.bat
```

### Linux / WSL / macOS

```bash
chmod +x install_all_dependencies.sh
./install_all_dependencies.sh
```

---

## 📋 安装内容

脚本将自动安装以下依赖：

### 1. 主项目依赖
- **Agent 框架**: openai-agents, pydantic, hydra-core
- **LLM 客户端**: openai, anthropic
- **数据库**: sqlmodel, alembic
- **Web 工具**: requests, beautifulsoup4, playwright
- **其他核心依赖**: 详见 `pyproject.toml`

### 2. KORGym 游戏环境
- **游戏服务器**: flask, flask-cors
- **游戏依赖**: numpy, scipy
- **其他**: 详见 `KORGym/requirements.txt`

### 3. 开发工具（可选）
使用 `uv sync --all-extras` 安装额外的开发工具：
- 测试工具: pytest, pytest-asyncio
- 代码质量: ruff, mypy
- 文档: mkdocs, mkdocs-material

---

## 🔧 安装步骤详解

### 步骤 1: 检查 Python 版本
**要求**: Python 3.12 或更高版本

```bash
python --version  # Windows
python3 --version  # Linux/macOS
```

如果版本不符合要求：
- **Windows**: 从 [python.org](https://www.python.org/downloads/) 下载安装
- **Linux**: `sudo apt install python3.12` (Ubuntu/Debian)
- **macOS**: `brew install python@3.12`

### 步骤 2: 安装 uv 包管理器
uv 是一个快速的 Python 包管理器，脚本会自动安装。

手动安装：
```bash
pip install uv
```

### 步骤 3: 安装主项目依赖
使用 uv 安装所有依赖（自动创建虚拟环境）：
```bash
uv sync
```

包含开发工具：
```bash
uv sync --all-extras
```

### 步骤 4: 安装 KORGym 依赖
激活虚拟环境后安装：
```bash
# Windows
.venv\Scripts\activate
pip install -r KORGym\requirements.txt

# Linux/macOS
source .venv/bin/activate
pip install -r KORGym/requirements.txt
```

### 步骤 5: 配置环境变量
复制环境变量模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API Keys：
```bash
# LLM API (必需)
UTU_LLM_TYPE=chat.completions
UTU_LLM_MODEL=deepseek-chat
UTU_LLM_BASE_URL=https://api.deepseek.com/v1
UTU_LLM_API_KEY=your-api-key-here

# 搜索工具 (可选)
SERPER_API_KEY=your-serper-key
JINA_API_KEY=your-jina-key

# 数据库 (可选，默认使用 SQLite)
UTU_DB_URL=sqlite:///test.db
```

### 步骤 6: 验证安装
运行环境检查脚本：
```bash
python scripts/korgym/check_korgym_env.py
```

---

## ✅ 验证安装

### 测试主框架
```bash
# 测试 Agent 框架
python -c "import utu; print('✓ UTU 框架已安装')"

# 测试配置加载
python -c "from utu.config import ConfigLoader; print('✓ 配置系统正常')"
```

### 测试 KORGym
```bash
# 测试 Flask (游戏服务器)
python -c "import flask; print('✓ Flask 已安装')"

# 启动测试服务器
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
# 按 Ctrl+C 停止
```

### 运行完整测试
```bash
# 运行单元测试（如果有）
pytest tests/

# 运行快速评估测试
uv run python scripts/utils/test_multiround_eval.py
```

---

## 🔍 常见问题

### Q1: uv sync 失败，显示 "No such file or directory"
**原因**: uv 可能未正确安装或未添加到 PATH

**解决**:
```bash
# 重新安装 uv
pip install --upgrade uv

# 或使用 pipx 安装
pipx install uv
```

### Q2: KORGym 依赖安装失败
**原因**: 可能是 Python 版本不兼容或缺少系统依赖

**解决**:
```bash
# Linux: 安装必要的系统包
sudo apt-get install python3-dev build-essential

# 尝试单独安装失败的包
pip install flask numpy scipy
```

### Q3: 虚拟环境激活失败
**原因**: 执行策略限制（Windows）或权限问题（Linux）

**解决**:
```powershell
# Windows: 以管理员身份运行 PowerShell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser

# Linux: 检查文件权限
chmod +x .venv/bin/activate
```

### Q4: ImportError: cannot import name 'XXX'
**原因**: 包版本冲突或安装不完整

**解决**:
```bash
# 清理并重新安装
rm -rf .venv
uv sync
pip install -r KORGym/requirements.txt
```

### Q5: API Key 错误
**原因**: .env 文件未正确配置

**解决**:
1. 确认 .env 文件存在于项目根目录
2. 检查 API Key 格式是否正确（无多余空格）
3. 确认 API Key 有效且有足够配额

---

## 🎯 安装后的快速开始

### 1. 运行第一个 KORGym 实验

```bash
# 终端 1: 启动 Wordle 游戏服务器
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777

# 终端 2: 准备数据集
cd /path/to/youtu-agent
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"

# 终端 2: 运行评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

### 2. 查看结果

```bash
# 查看 KORGym 结果
python scripts/korgym/view_korgym_results.py

# 查看详细评估结果
python scripts/utils/view_eval_results.py --exp_id wordle_baseline_eval
```

### 3. 运行 Training-Free GRPO

```bash
# 训练（生成经验）
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 评估训练后的性能
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
```

---

## 📚 相关文档

- **[KORGym 游戏指南](docs/korgym/index.md)** - 详细的游戏实验教程
- **[环境配置](docs/setup/index.md)** - WSL、Docker 等环境设置
- **[故障排除](docs/troubleshooting/index.md)** - 常见问题解决方案
- **[Training-Free GRPO](docs/practice.md)** - 训练框架文档

---

## 🆘 需要帮助？

1. **查看文档**: 先检查 `docs/` 目录下的相关文档
2. **运行诊断**: `python scripts/korgym/check_korgym_env.py`
3. **查看日志**: 检查 `logs/` 目录下的错误日志
4. **GitHub Issues**: 搜索或创建新的 Issue

---

## 📝 卸载

如果需要完全卸载：

```bash
# 删除虚拟环境
rm -rf .venv

# 删除数据库（可选）
rm test.db*

# 删除缓存
rm -rf __pycache__ **/__pycache__

# 删除日志（可选）
rm -rf logs/
```

---

*安装指南版本: 1.0*  
*更新日期: 2026-01-21*  
*适用于: Youtu-Agent + KORGym*






