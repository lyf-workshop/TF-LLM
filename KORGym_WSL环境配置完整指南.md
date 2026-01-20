# KORGym WSL 环境配置完整指南 🐧

## 📋 概述

本指南帮助你在 WSL (Windows Subsystem for Linux) 上配置 KORGym 环境，确保与现有 youtu-agent 项目完全兼容。

---

## 🚀 快速开始（一键配置）

### 方法 1：使用自动化脚本（推荐）

```bash
# 1. 在 WSL 中进入项目目录
cd /mnt/f/youtu-agent

# 2. 运行配置脚本
bash setup_korgym_wsl.sh
```

脚本会自动：
- ✅ 检查 Python 版本
- ✅ 安装/更新 uv 工具
- ✅ 创建/更新虚拟环境
- ✅ 安装 youtu-agent 依赖
- ✅ 安装 KORGym 依赖（兼容处理）
- ✅ 验证所有包
- ✅ 创建快捷脚本

---

## 📝 方法 2：手动配置（详细步骤）

如果你想了解每一步在做什么，或者自动脚本遇到问题：

### 步骤 1：检查 WSL 和 Python

```bash
# 确认在 WSL 环境中
uname -a
# 应该看到包含 "Microsoft" 或 "WSL"

# 检查 Python 版本（需要 >= 3.12）
python3 --version

# 如果版本过低，升级 Python
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev
```

### 步骤 2：安装 uv 工具

```bash
# 安装 uv（如果还没安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 添加到 PATH
export PATH="$HOME/.cargo/bin:$PATH"
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 验证安装
uv --version
```

### 步骤 3：进入项目目录

```bash
# 从 Windows 挂载点进入项目
cd /mnt/f/youtu-agent
```

### 步骤 4：创建虚拟环境

```bash
# 创建新的虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate

# 确认激活成功
which python
# 应该显示: /mnt/f/youtu-agent/.venv/bin/python
```

### 步骤 5：安装 youtu-agent 依赖

```bash
# 确保在虚拟环境中
source .venv/bin/activate

# 使用 uv sync 安装所有依赖（从 pyproject.toml）
uv sync

# 验证安装
uv pip list | grep utu
```

### 步骤 6：安装 KORGym 依赖

```bash
# 核心依赖（优先安装）
uv pip install fastapi==0.115.12
uv pip install uvicorn
uv pip install gymnasium==1.1.1
uv pip install pygame
uv pip install Pillow
uv pip install matplotlib
uv pip install imageio==2.37.0
uv pip install networkx
uv pip install nltk
uv pip install func_timeout==4.3.5
uv pip install datasets==3.0.2
uv pip install pytest pytest_mock
uv pip install ipdb==0.13.13
uv pip install jsonlines==4.0.0
uv pip install hilbertcurve==2.0.5
```

### 步骤 7：验证安装

```bash
# 运行环境检查脚本
python scripts/check_korgym_env.py
```

应该看到所有检查都是 ✓

---

## 🎮 测试 KORGym 集成

### 测试 1：启动游戏服务器

```bash
# 激活环境
source .venv/bin/activate

# 使用快捷脚本启动游戏
python scripts/start_korgym_server.py 3-2048
# 按 Ctrl+C 停止
```

### 测试 2：完整集成测试

```bash
# 激活环境
source .venv/bin/activate

# 运行完整测试
uv run python scripts/test_korgym_adapter.py

# 查看结果
cat workspace/korgym_test/test_results.json
```

---

## 🔧 常见问题解决

### 问题 1：Python 版本不兼容

**症状**：
```
ERROR: Python 3.10 is not supported
```

**解决**：
```bash
# 安装 Python 3.12
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev

# 指定使用 Python 3.12
python3.12 -m venv .venv
source .venv/bin/activate
```

### 问题 2：uv 命令找不到

**症状**：
```
bash: uv: command not found
```

**解决**：
```bash
# 重新安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 添加到 PATH
export PATH="$HOME/.cargo/bin:$PATH"
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 问题 3：包版本冲突

**症状**：
```
ERROR: Package 'xxx' has conflicting dependencies
```

**解决**：
```bash
# 方法 1：使用 uv 的依赖解析
uv pip install --upgrade package_name

# 方法 2：重建虚拟环境
rm -rf .venv
uv venv
source .venv/bin/activate
uv sync
# 然后重新安装 KORGym 依赖
```

### 问题 4：游戏服务器启动失败

**症状**：
```
Address already in use
```

**解决**：
```bash
# 查找占用端口的进程
lsof -i :8775

# 杀掉进程
kill -9 <PID>

# 或使用不同端口
python scripts/start_korgym_server.py 3-2048 --port 8776
```

### 问题 5：pygame 安装失败

**解决**：
```bash
# 安装 pygame 依赖
sudo apt install python3-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libfreetype6-dev libportmidi-dev

# 然后重新安装
uv pip install pygame
```

---

## 📊 完整命令速查表

### 环境管理

```bash
# 激活虚拟环境
source .venv/bin/activate

# 退出虚拟环境
deactivate

# 查看已安装的包
uv pip list

# 查看特定包
uv pip show package_name

# 更新包
uv pip install --upgrade package_name
```

### 游戏服务器管理

```bash
# 启动 2048
python scripts/start_korgym_server.py 3-2048

# 启动 Sudoku（不同端口）
python scripts/start_korgym_server.py 4-SudoKu --port 8776

# 后台启动
python scripts/start_korgym_server.py 3-2048 &

# 查看所有游戏
ls KORGym/game_lib/
```

---

## ✅ 验证清单

配置完成后，检查以下项目：

- [ ] Python 版本 >= 3.12
- [ ] uv 工具已安装
- [ ] 虚拟环境已创建并激活
- [ ] youtu-agent 依赖已安装（`uv pip list | grep utu`）
- [ ] KORGym 核心依赖已安装（fastapi, gymnasium, pygame 等）
- [ ] 没有包版本冲突
- [ ] 可以启动游戏服务器
- [ ] 可以运行测试脚本
- [ ] 测试结果文件已生成

---

## 📚 相关文档

- [KORGym 集成指南](KORGym集成指南.md)
- [KORGym 快速使用指南](KORGym快速使用指南.md)
- [Word Puzzle 完整指南](Word_Puzzle完整指南.md)

---

## 🎊 完成！

环境配置完成后，你可以：

1. ✅ 运行任何 KORGym 游戏
2. ✅ 使用分层经验学习系统
3. ✅ 训练 Agent 在多个游戏上
4. ✅ 提取和聚合经验（L0/L1/L2）
5. ✅ 生成增强的 Agent 配置

**开始使用：**

```bash
# 激活环境
source .venv/bin/activate

# 运行测试
uv run python scripts/test_korgym_adapter.py
```

🚀 准备好获得游戏经验了！








