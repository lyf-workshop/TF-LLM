# KORGym WSL环境设置指南 🐧

由于你在Windows系统上使用WSL，这里提供特别的设置说明。

## 📦 前置准备

### 1. 确保WSL环境正常
```bash
# 在PowerShell中检查WSL版本
wsl --list --verbose

# 进入WSL
wsl
```

### 2. 在WSL中进入项目目录
```bash
# 从Windows路径映射到WSL路径
cd /mnt/f/youtu-agent
```

### 3. 设置脚本权限（在WSL中执行）
```bash
chmod +x scripts/start_korgym_server.sh
chmod +x scripts/run_korgym_full_pipeline.sh
```

---

## 🚀 运行方式

### 方式1: 使用提供的Shell脚本（推荐）

#### 终端1 - 启动游戏服务器（在WSL中）
```bash
cd /mnt/f/youtu-agent
./scripts/start_korgym_server.sh 8-word_puzzle 8775
```

#### 终端2 - 运行训练流程（在WSL中）
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate
./scripts/run_korgym_full_pipeline.sh
```

### 方式2: 手动执行命令（更灵活）

参考 `KORGYM_QUICK_START.md` 中的分步运行命令。

---

## 🔧 WSL特定配置

### 网络端口映射

如果你想从Windows访问WSL中的游戏服务器，需要配置端口转发：

```powershell
# 在PowerShell（管理员）中执行
netsh interface portproxy add v4tov4 listenport=8775 listenaddress=0.0.0.0 connectport=8775 connectaddress=localhost
```

检查端口映射：
```powershell
netsh interface portproxy show all
```

删除端口映射：
```powershell
netsh interface portproxy delete v4tov4 listenport=8775 listenaddress=0.0.0.0
```

### 文件路径说明

| Windows路径 | WSL路径 |
|------------|---------|
| `F:\youtu-agent` | `/mnt/f/youtu-agent` |
| `F:\youtu-agent\KORGym` | `/mnt/f/youtu-agent/KORGym` |

---

## ⚡ 快速启动（所有命令在WSL中执行）

```bash
# 0. 进入项目目录
cd /mnt/f/youtu-agent

# 1. 激活虚拟环境
source .venv/bin/activate

# 2. 启动游戏服务器（在单独的终端）
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# 3. 回到项目根目录（在另一个终端）
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 4. 准备数据集
uv run python scripts/data/prepare_korgym_data.py

# 5. 基线评估
uv run python scripts/run_eval.py --config_name korgym/korgym_eval

# 6. 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym_practice

# 7. 评估训练后的模型
uv run python scripts/run_eval.py --config_name korgym/korgym_practice_eval
```

---

## 📊 查看结果（在WSL中）

```bash
cd /mnt/f/youtu-agent

# 基线结果
cat workspace/korgym_baseline_eval/score.txt

# 训练后结果
cat workspace/korgym_practice_eval/score.txt

# 经验统计
cat workspace/hierarchical_experiences/korgym_practice.json | python -m json.tool | grep -A 3 '"stats"'
```

---

## 🐛 常见WSL问题

### 问题1: Python虚拟环境激活失败

```bash
# 重新创建虚拟环境
cd /mnt/f/youtu-agent
rm -rf .venv
uv sync --all-extras
source .venv/bin/activate
```

### 问题2: 端口被占用

```bash
# 查找占用端口的进程
lsof -i :8775

# 或者使用netstat
netstat -tuln | grep 8775

# 杀死进程
kill -9 <PID>
```

### 问题3: 文件权限问题

```bash
# 修复脚本权限
chmod +x scripts/*.sh

# 修复Python文件权限
chmod +x scripts/data/*.py
```

### 问题4: WSL访问速度慢

建议将项目克隆到WSL原生文件系统：
```bash
# 在WSL中
cd ~
git clone <your-repo> youtu-agent
cd youtu-agent
# 然后按正常流程操作
```

---

## 💡 使用tmux管理多终端（推荐）

安装tmux：
```bash
sudo apt-get update
sudo apt-get install tmux
```

使用tmux运行：
```bash
# 创建新会话
tmux new -s korgym

# 分割窗口（Ctrl+b然后按"）
# 上方窗口运行游戏服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# 切换到下方窗口（Ctrl+b然后按↓）
# 运行训练流程
cd /mnt/f/youtu-agent
source .venv/bin/activate
./scripts/run_korgym_full_pipeline.sh

# 退出tmux但保持运行: Ctrl+b然后按d
# 重新连接: tmux attach -t korgym
```

---

## ✅ 验证环境

运行以下命令验证环境设置正确：

```bash
cd /mnt/f/youtu-agent

# 检查Python环境
python --version

# 检查uv
uv --version

# 检查虚拟环境
source .venv/bin/activate
which python

# 检查KORGym
ls KORGym/game_lib/ | head -10

# 测试游戏服务器启动
cd KORGym/game_lib/8-word_puzzle
timeout 5 python game_lib.py -p 8775 || echo "Game server can start"
```

---

## 📝 建议的工作流

1. **打开两个WSL终端**（或使用tmux）
2. **终端1**: 保持游戏服务器运行
3. **终端2**: 执行训练和评估命令
4. 使用VS Code的WSL扩展可以更方便地编辑文件

---

✅ 现在你可以在WSL环境中运行KORGym分层经验学习了！

有问题请参考完整文档: `KORGym_Usage_Guide.md`

