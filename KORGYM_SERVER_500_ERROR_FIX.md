# KORGym服务器500错误修复指南 🔧

## 🐛 问题描述

运行评估时出现：
```
500 Server Error: Internal Server Error for url: http://localhost:8775/generate
```

说明：
- ✅ 服务器正在运行（能连接上）
- ❌ 生成游戏实例时发生内部错误

---

## 🔍 诊断步骤

### 步骤1: 测试服务器

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 运行诊断脚本
uv run python scripts/test_korgym_server.py \
  --port 8775 \
  --game_name "8-word_puzzle"
```

这会测试：
1. 服务器是否运行
2. /generate端点是否正常
3. /verify端点是否正常

---

## 🔧 常见原因和解决方案

### 原因1: 游戏服务器启动目录错误

**问题**: 服务器找不到依赖文件（如`high_quality_word_clues.csv`）

**解决**: 必须在游戏目录中启动服务器

```bash
# ❌ 错误的启动方式
cd /mnt/f/youtu-agent
python KORGym/game_lib/8-word_puzzle/game_lib.py -p 8775

# ✅ 正确的启动方式
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

---

### 原因2: 缺少依赖文件

**检查**:
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle

# 检查必需的文件
ls -lh high_quality_word_clues.csv
ls -lh cache/  # 图片缓存目录
```

**解决**: 确保所有依赖文件存在

---

### 原因3: Python依赖问题

**检查**:
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle

# 测试直接运行generate函数
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from game_lib import generate

try:
    result = generate(seed=42)
    print("✅ Generate成功")
    print(f"答案数量: {len(result.get('answer', []))}")
except Exception as e:
    print(f"❌ Generate失败: {e}")
    import traceback
    traceback.print_exc()
EOF
```

---

### 原因4: 服务器需要重启

**解决**:
```bash
# 1. 停止当前服务器（Ctrl+C）

# 2. 确保在正确目录
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle

# 3. 重新启动
python game_lib.py -p 8775

# 4. 查看启动日志，确保没有错误
```

---

## 🚀 推荐的完整重启流程

### 终端1: 重启游戏服务器

```bash
# 1. 停止旧服务器
# 按 Ctrl+C 停止，或者
pkill -f "game_lib.py"

# 2. 进入游戏目录（重要！）
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle

# 3. 检查依赖文件
ls -lh high_quality_word_clues.csv
# 应该显示CSV文件存在

# 4. 启动服务器
python game_lib.py -p 8775

# 5. 确认启动成功
# 应该看到: INFO:     Uvicorn running on http://0.0.0.0:8775
```

### 终端2: 测试服务器

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate

# 测试服务器
uv run python scripts/test_korgym_server.py --port 8775 --game_name "8-word_puzzle"

# 应该看到：
# ✅ 服务器正在运行
# ✅ 游戏实例生成成功
# ✅ 验证成功
```

### 终端2: 重新运行评估

```bash
# 如果测试成功，重新运行评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

---

## 🔍 查看服务器日志

游戏服务器的终端会显示详细的错误信息。如果出现500错误，检查服务器终端的输出：

```
可能的错误信息：
- FileNotFoundError: 找不到 high_quality_word_clues.csv
- ValueError: 可用单词不足
- RuntimeError: 生成填字游戏尝试次数过多
- PIL相关错误: 图片生成失败
```

---

## 🐛 其他可能的问题

### 问题1: 端口被占用

```bash
# 检查端口
netstat -tuln | grep 8775

# 或
lsof -i :8775

# 杀死占用进程
kill -9 <PID>
```

### 问题2: 权限问题

```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle

# 检查文件权限
ls -la high_quality_word_clues.csv
ls -la game_lib.py

# 如果需要，添加执行权限
chmod +x game_lib.py
```

### 问题3: Python环境问题

```bash
# 检查游戏服务器的Python环境
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle

# 检查依赖
python3 -c "import fastapi, uvicorn, pandas, PIL; print('✅ 所有依赖已安装')"

# 如果失败，安装依赖
pip install -r ../../requirements.txt
```

---

## ✅ 验证清单

在运行评估前，确保：

- [ ] 在游戏目录中启动服务器 (`cd KORGym/game_lib/8-word_puzzle`)
- [ ] 服务器启动成功（看到uvicorn日志）
- [ ] `high_quality_word_clues.csv` 文件存在
- [ ] 测试脚本通过（`scripts/test_korgym_server.py`）
- [ ] 浏览器可以访问 `http://localhost:8775/docs`

---

## 💡 快速修复方案

```bash
# === 终端1 ===
# 1. 停止旧服务器
pkill -f "game_lib.py"

# 2. 进入正确目录并启动
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# === 终端2 ===
# 3. 测试服务器
cd /mnt/f/youtu-agent
source .venv/bin/activate
uv run python scripts/test_korgym_server.py

# 4. 如果测试通过，重新运行评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

---

## 📞 获取详细错误信息

如果问题持续，在游戏服务器终端查看详细错误堆栈：

```python
# 服务器可能显示的错误：
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  ...
  FileNotFoundError: [Errno 2] No such file or directory: 'high_quality_word_clues.csv'
```

根据具体错误信息进行修复。

---

**现在重启游戏服务器并测试！** 🔧🚀

