# KORGym 常见问题排查指南

本文档汇总了 KORGym 实验中的常见问题和解决方案。

## 🚨 常见错误分类

### 1. API 和网络错误

#### Error 429: API Rate Limiting

**错误信息**:
```
Error code: 429 - {'message': 'Request was rejected due to rate limiting. Details: TPM limit reached.'}
```

**影响游戏**: 主要是 Alphabetical Sorting（因为任务简单，请求频繁）

**解决方案**:

1. **降低并发数**:
```yaml
# configs/practice/korgym/*_practice.yaml
practice:
  rollout_concurrency: 4  # 从 16/32 降到 4
```

2. **使用较小模型**:
```yaml
# configs/agents/practice/*_agent.yaml
model:
  model: Qwen/Qwen2.5-7B-Instruct  # 从 72B 降到 7B
```

3. **增加重试延迟**:
```yaml
model:
  model_settings:
    timeout: 120  # 增加超时时间
```

**相关文档**: [ALPHABETICAL_SORTING_CACHE_ISSUE.md](../../ALPHABETICAL_SORTING_CACHE_ISSUE.md)

---

#### 500 Server Error: Game Server Crash

**错误信息**:
```
Failed to generate game instance: 500 Server Error: Internal Server Error for url: http://localhost:8775/generate
```

**原因**:
- 游戏服务器崩溃
- 特定 seed 导致服务器内部错误
- 端口被占用

**解决方案**:

1. **重启游戏服务器**:
```bash
# 找到正在运行的服务器进程
lsof -i :8775  # Linux/WSL
netstat -ano | findstr :8775  # Windows

# 杀死进程后重启
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

2. **跳过问题 seed**:
```bash
# 调整数据集生成的 seed 范围
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "8-word_puzzle" \
    --train_seeds_start 0 \
    --train_seeds_end 50 \
    --eval_seeds_start 100 \
    --eval_seeds_end 150
```

**相关文档**: [KORGYM_SERVER_500_ERROR_FIX.md](../../KORGYM_SERVER_500_ERROR_FIX.md)

---

#### Connection Refused

**错误信息**:
```
Connection refused
Failed to connect to game server at localhost:8775
```

**原因**: 游戏服务器未启动或端口错误

**解决方案**:

1. **确认服务器运行**:
```bash
# 检查进程
ps aux | grep game_lib  # Linux/WSL
tasklist | findstr python  # Windows

# 启动服务器
cd KORGym/game_lib/[game_directory]
python game_lib.py -p [port]
```

2. **检查端口配置**:
```yaml
# 确保配置文件中的端口与服务器一致
data:
  game_port: 8775  # 必须匹配服务器端口
```

**端口参考**:
- Word Puzzle: 8775
- Wordle: 8765
- Alphabetical Sorting: 8780

---

### 2. 配置错误

#### Hierarchical Learning Not Enabled

**现象**: 训练后只生成了单层经验，而不是预期的 L0/L1/L2 三层

**原因**: `hierarchical_learning` 配置块位置错误

**错误示例**:
```yaml
# ❌ 错误：在顶层
hierarchical_learning:
  enabled: true
  
practice:
  epochs: 2
```

**正确示例**:
```yaml
# ✅ 正确：在 practice 块内
practice:
  epochs: 2
  hierarchical_learning:
    enabled: true
    levels:
      - name: "L0"
        description: "案例级别"
      - name: "L1"
        description: "模式级别"
      - name: "L2"
        description: "元认知级别"
```

**相关文档**: [HIERARCHICAL_LEARNING_FIX.md](../../HIERARCHICAL_LEARNING_FIX.md)

---

#### Level Mismatch

**现象**: 评估准确率为 0% 或异常低

**原因**: 训练和评估使用了不同的难度级别

**检查方法**:
```bash
# 检查训练配置
cat configs/practice/korgym/word_puzzle_practice.yaml | grep "level:"

# 检查评估配置
cat configs/eval/korgym/word_puzzle_eval.yaml | grep "level:"
cat configs/eval/korgym/word_puzzle_practice_eval.yaml | grep "level:"
```

**解决方案**:
确保所有相关配置文件使用相同的 `level`:
```yaml
data:
  level: 3  # 必须在所有配置文件中一致
```

**相关文档**: [WORD_PUZZLE_ZERO_ACCURACY_FIX.md](../../WORD_PUZZLE_ZERO_ACCURACY_FIX.md)

---

### 3. 数据和数据库错误

#### No game_seed found in meta

**错误信息**:
```
KeyError: 'game_seed'
No game_seed found in meta
```

**原因**: 数据准备脚本使用了错误的字段名（`metadata` vs `meta`）

**解决方案**:

1. **检查数据准备脚本版本**:
```bash
# 确保使用修复后的版本
cat scripts/data/prepare_korgym_data.py | grep "meta="
```

2. **重新生成数据集**:
```bash
# 清理旧数据集
uv run python scripts/clean_and_recreate_datasets.py

# 重新生成
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "8-word_puzzle" \
    --train_count 100 \
    --eval_count 50
```

**相关文档**: [PREPARE_KORGYM_DATA_FIX.md](../../PREPARE_KORGYM_DATA_FIX.md)

---

#### Dataset Already Exists

**错误信息**:
```
Dataset already exists: KORGym-Wordle-Train-100
```

**解决方案**:

**选项 1**: 删除旧数据集
```bash
uv run python scripts/clean_and_recreate_datasets.py
```

**选项 2**: 使用不同名称
```bash
uv run python scripts/data/prepare_korgym_data.py \
    --game_name "33-wordle" \
    --train_count 100 \
    --eval_count 50 \
    --dataset_suffix "v2"  # 生成 KORGym-Wordle-Train-100-v2
```

---

#### Cached Evaluation Results

**现象**: 修改配置或重新训练后，评估结果没有变化

**原因**: 评估结果被缓存在数据库中

**解决方案**:

1. **删除特定实验结果**:
```bash
uv run python scripts/clean_experiment_data.py \
    --exp_id word_puzzle_baseline_eval word_puzzle_practice_eval
```

2. **验证清理**:
```bash
uv run python scripts/verify_clean.py \
    --exp_id word_puzzle_baseline_eval
```

3. **重新运行评估**:
```bash
uv run python scripts/run_eval.py \
    --config_name korgym/word_puzzle_practice_eval
```

**相关文档**: [WORD_PUZZLE_CACHE_CLEANUP.md](../../WORD_PUZZLE_CACHE_CLEANUP.md)

---

### 4. 训练和经验学习错误

#### TypeError: object of type 'NoneType' has no len()

**错误信息**:
```
TypeError: object of type 'NoneType' has no len()
  File "utu/practice/experience_updater.py", line 84
    if len(rollout.trajectories) > 0:
```

**影响游戏**: 主要是 Wordle（多轮交互游戏）

**原因**: `rollout.trajectories` 为 `None` 时未检查

**解决方案**:

确保使用修复后的 `experience_updater.py`:
```python
# 应包含 None 检查
if rollout.trajectories is not None and len(rollout.trajectories) > 0:
    # 处理 trajectories
```

**相关文档**: [WORDLE_TRAJECTORIES_FIX.md](../../WORDLE_TRAJECTORIES_FIX.md)

---

#### Low Experience Count

**现象**: 训练后只生成了很少的经验（如 3 条而不是 6-7 条）

**原因**:
1. 大部分 rollouts 失败（API 限流）
2. 层次经验学习配置错误
3. Batch size 太小

**解决方案**:

1. **检查训练日志**:
```bash
# 查看有多少 rollouts 成功
cat logs/utu.log | grep "Num of candidate experiences"
cat logs/utu.log | grep "success_rate"
```

2. **降低并发避免 API 限流**:
```yaml
practice:
  rollout_concurrency: 4
```

3. **确保层次学习配置正确**:
```yaml
practice:
  hierarchical_learning:
    enabled: true
    # ...
```

4. **增加 batch size**:
```yaml
practice:
  batch_size: 30  # 增加批次大小
```

---

### 5. Python 环境错误

#### AttributeError: module 'jedi' has no attribute 'settings'

**错误信息**:
```
AttributeError: module 'jedi' has no attribute 'settings'
```

**原因**: IPython 和 jedi 版本不兼容

**解决方案**:

```bash
# 升级相关包
uv pip install --upgrade ipython jedi

# 或使用提供的修复脚本
python fix_ipython_jedi.py
```

---

## 🔍 诊断流程

当遇到问题时，按以下顺序检查：

### 1. 检查游戏服务器

```bash
# 检查服务器是否运行
lsof -i :[port]  # Linux/WSL
netstat -ano | findstr :[port]  # Windows

# 检查服务器日志
# 服务器终端应有正常输出，无错误信息
```

### 2. 检查配置文件

```bash
# 检查关键配置
cat configs/practice/korgym/[game]_practice.yaml | grep -E "level:|port:|concurrency:"
cat configs/eval/korgym/[game]_eval.yaml | grep -E "level:|port:"
```

### 3. 检查数据集

```bash
# 列出数据集
uv run python scripts/list_datasets.py | grep KORGym

# 查看数据集样本
uv run python scripts/view_dataset.py \
    --dataset_name "KORGym-Wordle-Eval-50" \
    --limit 3
```

### 4. 检查日志

```bash
# 查看最新日志
tail -100 logs/utu.log

# 搜索错误
cat logs/utu.log | grep -i "error\|exception\|failed"

# 查看特定实验的日志
cat logs/utu.log | grep "exp_id=wordle_practice"
```

### 5. 测试连接

```bash
# 测试游戏服务器连接
curl http://localhost:8775/generate -X POST \
    -H "Content-Type: application/json" \
    -d '{"seed": 1}'

# 应返回游戏实例 JSON
```

---

## 📋 配置检查清单

在运行实验前，确保：

### General
- [ ] `.env` 文件已配置，包含必要的 API keys
- [ ] 虚拟环境已激活：`source .venv/bin/activate`
- [ ] 依赖已安装：`uv sync --all-extras`

### Game Server
- [ ] 游戏服务器正在运行
- [ ] 端口配置正确且未被占用
- [ ] 服务器无错误日志

### Configuration Files
- [ ] 训练和评估的 `level` 参数一致
- [ ] 游戏端口（`game_port`）与服务器匹配
- [ ] `hierarchical_learning` 在 `practice:` 块内（如需要）
- [ ] `rollout_concurrency` 设置合理（建议 4）
- [ ] 模型配置正确（建议 7B 而非 72B）

### Datasets
- [ ] 数据集已创建且名称正确
- [ ] 数据集中有足够的样本
- [ ] 数据集 metadata 包含必要字段（`game_seed`, `game_name`）

### Before Re-running
- [ ] 已清理旧的评估结果（如需要）
- [ ] 已删除旧的 practice agent 配置（如需要）
- [ ] 已确认无缓存数据干扰

---

## 🔗 相关文档索引

### 问题修复文档
- [ALPHABETICAL_SORTING_CACHE_ISSUE.md](../../ALPHABETICAL_SORTING_CACHE_ISSUE.md) - API 限流问题
- [HIERARCHICAL_LEARNING_FIX.md](../../HIERARCHICAL_LEARNING_FIX.md) - 层次学习配置
- [WORD_PUZZLE_ZERO_ACCURACY_FIX.md](../../WORD_PUZZLE_ZERO_ACCURACY_FIX.md) - 准确率为0
- [PREPARE_KORGYM_DATA_FIX.md](../../PREPARE_KORGYM_DATA_FIX.md) - 数据准备问题
- [WORDLE_TRAJECTORIES_FIX.md](../../WORDLE_TRAJECTORIES_FIX.md) - Trajectories 为 None
- [THREE_GAMES_CONFIG_FIX_SUMMARY.md](../../THREE_GAMES_CONFIG_FIX_SUMMARY.md) - 配置修复总结

### 操作指南
- [KORGYM_THREE_GAMES_COMMANDS.md](../../KORGYM_THREE_GAMES_COMMANDS.md) - 完整命令参考
- [PRACTICE_RETRY_MECHANISM_GUIDE.md](../../PRACTICE_RETRY_MECHANISM_GUIDE.md) - 重试机制详解

### 游戏指南
- [wordle_guide.md](wordle_guide.md) - Wordle 实验指南
- [word_puzzle_guide.md](word_puzzle_guide.md) - Word Puzzle 实验指南
- [alphabetical_sorting_guide.md](alphabetical_sorting_guide.md) - Alphabetical Sorting 实验指南

---

## 🆘 寻求帮助

如果上述方法都无法解决问题：

1. **收集信息**:
   ```bash
   # 保存完整日志
   cp logs/utu.log debug_$(date +%Y%m%d_%H%M%S).log
   
   # 导出配置
   cat configs/practice/korgym/*_practice.yaml > debug_configs.txt
   ```

2. **检查 GitHub Issues**: 搜索类似问题

3. **创建详细的问题报告**，包括：
   - 错误信息（完整堆栈跟踪）
   - 配置文件内容
   - 运行的命令
   - 环境信息（OS、Python 版本、依赖版本）
   - 重现步骤











