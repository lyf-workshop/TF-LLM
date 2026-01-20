# KORGym 快速使用指南 🚀

## 📋 前提条件

- ✅ WSL 环境（或 Linux）
- ✅ Python >= 3.12
- ✅ 已安装 uv 工具

---

## ⚡ 快速开始（三步走）

### 第一步：配置环境

```bash
cd /mnt/f/youtu-agent
bash setup_korgym_wsl.sh
```

### 第二步：检查环境

```bash
# 激活环境
source .venv/bin/activate

# 运行环境检查
python scripts/check_korgym_env.py
```

**如果看到 "✅ 所有检查通过"，则可以继续下一步！**

### 第三步：运行测试

```bash
# 测试 KORGym 适配器
uv run python scripts/test_korgym_adapter.py

# 查看结果
cat workspace/korgym_test/test_results.json
```

---

## 🎮 使用 KORGym

### 方法 1：自动测试（推荐）

测试脚本会自动启动游戏服务器并运行测试：

```bash
source .venv/bin/activate
uv run python scripts/test_korgym_adapter.py
```

**输出示例：**
```
🎮 KORGym Adapter Test
========================================

1. Initializing KORGym Adapter...
   Game: 3-2048
   Game Category: 3-Reasoning
   Game Type: Computational Puzzle
   Is Multimodal: True

2. Loading Agent...
   Agent loaded: logic_agent_zebralogic

3. Initializing Experience Extractor...
   ✓ Experience extractor ready

4. Playing Game Rounds...
   Playing game with seed 0...
   ✓ Game completed (won: True, score: 2048)
   ...

✓ Test completed successfully!
```

### 方法 2：手动启动游戏服务器

在一个终端启动服务器：

```bash
source .venv/bin/activate

# 启动 2048 游戏
python scripts/start_korgym_server.py 3-2048

# 或启动其他游戏
python scripts/start_korgym_server.py 4-SudoKu --port 8776
```

在另一个终端与游戏交互：

```python
from utu.practice.korgym_adapter import KORGymAdapter
from utu.config import ConfigLoader
from utu.agents import get_agent

# 初始化适配器
adapter = KORGymAdapter(
    game_name="3-2048",
    base_url="http://localhost:8775"
)

# 加载 Agent
config = ConfigLoader.load_agent_config("practice/logic_agent_hierarchical_learning_clean")
agent = get_agent(config)

# 玩游戏
result = await adapter.play_game(agent, seed=42)
print(f"游戏结果: {result}")
```

---

## 🔍 诊断和故障排查

### 问题 1：环境检查失败

**运行诊断：**
```bash
python scripts/check_korgym_env.py
```

**常见问题及解决：**

| 问题 | 解决方案 |
|------|---------|
| Python 版本过低 | `sudo apt install python3.12` |
| 包未安装 | `bash setup_korgym_wsl.sh` |
| KORGym 目录不存在 | 确保 KORGym 在项目根目录 |
| 配置文件缺失 | 检查 git 状态，可能需要 pull |

### 问题 2：测试脚本报错

**错误：`AttributeError: 'AgentConfig' object has no attribute 'name'`**

✅ **已修复！** 重新拉取代码或运行：

```bash
cd /mnt/f/youtu-agent
git pull
```

**错误：`Connection refused`**

原因：游戏服务器未启动

解决：测试脚本会自动启动服务器，如果失败，手动启动：

```bash
python scripts/start_korgym_server.py 3-2048
```

**错误：`Address already in use`**

原因：端口被占用

解决：
```bash
# 找到占用进程
lsof -i :8775

# 杀掉进程
kill -9 <PID>

# 或使用不同端口
python scripts/start_korgym_server.py 3-2048 --port 8776
```

### 问题 3：游戏服务器启动失败

**检查依赖：**
```bash
python -c "import fastapi, uvicorn, gymnasium; print('✓ 依赖正常')"
```

**检查端口：**
```bash
# 测试端口是否可用
nc -zv localhost 8775
```

**查看日志：**
```bash
# 使用详细模式启动
cd KORGym/game_lib/3-2048
python game_lib.py -p 8775 -H 0.0.0.0 --reload
```

---

## 📊 可用游戏列表

查看所有可用游戏：

```bash
ls KORGym/game_lib/
```

**常见游戏：**

| 游戏名称 | 分类 | 难度 | 描述 |
|---------|------|------|------|
| `3-2048` | Reasoning | 中等 | 经典 2048 游戏 |
| `4-SudoKu` | Reasoning | 中等 | 数独谜题 |
| `5-Nonogram` | Reasoning | 困难 | 数织游戏 |
| `1-Graph-Coloring` | Graph | 困难 | 图着色问题 |
| `2-24-Point` | Math | 简单 | 24 点游戏 |

---

## 🎯 完整工作流程

### 场景：首次使用

```bash
# 1. 配置环境
cd /mnt/f/youtu-agent
bash setup_korgym_wsl.sh

# 2. 激活环境
source .venv/bin/activate

# 3. 检查环境
python scripts/check_korgym_env.py

# 4. 运行测试
uv run python scripts/test_korgym_adapter.py

# 5. 查看结果
cat workspace/korgym_test/test_results.json
```

### 场景：开发和调试

```bash
# 激活环境
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 终端 1：启动游戏服务器
python scripts/start_korgym_server.py 3-2048

# 终端 2：运行测试或开发
python -c "
from utu.practice.korgym_adapter import KORGymAdapter

adapter = KORGymAdapter('3-2048')
print(f'Game info: {adapter.get_game_info()}')
"
```

### 场景：训练 Agent

```bash
# 激活环境
source .venv/bin/activate

# 使用 KORGym 配置训练
uv run python scripts/run_training_free_GRPO.py \
    --config_name korgym_hierarchical_test

# 查看生成的经验
cat workspace/hierarchical_experiences/korgym_2048.json
```

---

## 📚 相关命令速查

### 环境管理

```bash
# 激活环境
source .venv/bin/activate

# 退出环境
deactivate

# 查看已安装包
uv pip list

# 更新包
uv pip install --upgrade package_name
```

### 游戏管理

```bash
# 启动游戏
python scripts/start_korgym_server.py <game_name>

# 查看游戏列表
ls KORGym/game_lib/

# 查看游戏信息
python -c "
from utu.practice.korgym_adapter import KORGymAdapter
adapter = KORGymAdapter('3-2048')
print(adapter.get_game_info())
"
```

### 测试和验证

```bash
# 环境检查
python scripts/check_korgym_env.py

# 适配器测试
uv run python scripts/test_korgym_adapter.py

# 单元测试
pytest tests/practice/test_korgym_adapter.py -v
```

---

## 🐛 常见错误及解决

### 错误 1：ModuleNotFoundError

```
ModuleNotFoundError: No module named 'fastapi'
```

**解决：**
```bash
source .venv/bin/activate
uv pip install fastapi uvicorn gymnasium pygame
```

### 错误 2：Permission Denied

```
bash: setup_korgym_wsl.sh: Permission denied
```

**解决：**
```bash
chmod +x setup_korgym_wsl.sh
bash setup_korgym_wsl.sh
```

### 错误 3：WSL 路径问题

```
cd: /mnt/f/youtu-agent: No such file or directory
```

**解决：**
```bash
# 检查挂载点
mount | grep mnt

# 或使用绝对路径
cd "$(wslpath 'F:\youtu-agent')"
```

### 错误 4：Virtual Environment 未激活

```
uv: command not found
```

**解决：**
```bash
# 确保 uv 在 PATH 中
export PATH="$HOME/.cargo/bin:$PATH"

# 或重新安装
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

---

## ✅ 验证成功的标志

运行 `python scripts/check_korgym_env.py` 应该看到：

```
======================================================================
  检查总结
======================================================================
  ✓ Python 版本
  ✓ youtu-agent 包
  ✓ KORGym 包
  ✓ 项目结构
  ✓ KORGym 目录
  ✓ 配置文件
======================================================================

✅ 所有检查通过！环境配置正确。
```

---

## 🎊 完成！

环境配置成功后，你可以：

- ✅ 玩任何 KORGym 游戏
- ✅ 训练 Agent 获得游戏经验
- ✅ 提取和聚合分层经验（L0/L1/L2）
- ✅ 生成增强的 Agent 配置

**开始探索：**

```bash
source .venv/bin/activate
uv run python scripts/test_korgym_adapter.py
```

🎮 享受游戏和学习的乐趣！

---

## 📖 更多文档

- [详细配置指南](KORGym_WSL环境配置指南.md)
- [快速命令列表](快速配置命令-WSL.md)
- [集成架构](KORGym集成指南.md)
- [完成总结](KORGym集成-完成总结.md)











