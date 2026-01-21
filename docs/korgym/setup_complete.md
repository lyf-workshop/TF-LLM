# ✅ KORGym分层经验学习配置完成！

恭喜！所有必要的配置文件和脚本已经创建完成。

---

## 📦 已创建的文件清单

### ✅ 核心配置文件（7个）

1. **验证函数**
   - `utu/practice/verify/korgym.py` - KORGym游戏结果验证

2. **Agent配置**
   - `configs/agents/practice/korgym_agent.yaml ` - 基础Agent配置

3. **评估配置**
   - `configs/eval/korgym/korgym_eval.yaml` - 基线评估（训练前）
   - `configs/eval/korgym/korgym_practice_eval.yaml` - 训练后评估

4. **训练配置**
   - `configs/practice/korgym_practice.yaml` - 分层经验学习训练配置

5. **数据准备**
   - `scripts/data/prepare_korgym_data.py` - 数据集创建脚本

6. **便捷脚本**
   - `scripts/start_korgym_server.sh` - 游戏服务器启动脚本
   - `scripts/run_korgym_full_pipeline.sh` - 完整流程一键运行脚本

### ✅ 文档文件（5个）

1. `KORGym_Usage_Guide.md` - 完整使用指南（最详细）
2. `KORGYM_QUICK_START.md` - 快速开始指南（最快上手）
3. `KORGYM_WSL_SETUP.md` - WSL环境设置（你的环境）
4. `KORGYM_COMMANDS_SUMMARY.md` - 命令速查表（最实用）
5. `KORGYM_INTEGRATION_README.md` - 文件清单和架构说明

---

## 🚀 现在开始运行（WSL环境）

### 第一步：设置权限（只需执行一次）

打开WSL终端，执行：

```bash
cd /mnt/f/youtu-agent
chmod +x scripts/start_korgym_server.sh
chmod +x scripts/run_korgym_full_pipeline.sh
```

### 第二步：启动游戏服务器

**打开第一个WSL终端**，执行：

```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

保持这个终端运行，不要关闭！

### 第三步：运行完整流程

**打开第二个WSL终端**，执行：

```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate
./scripts/run_korgym_full_pipeline.sh
```

这个脚本会自动执行：
1. ✅ 准备数据集（50题评估 + 100题训练）
2. ✅ 基线评估（使用seeds 1-50）
3. ✅ 训练并提取经验（使用seeds 51-150）
4. ✅ 评估训练后的模型（再次使用seeds 1-50）
5. ✅ 对比结果

---

## 📊 关键特性

### ✅ 数据集设计（已配置好）

| 数据集 | 用途 | 种子范围 | 数量 | 目的 |
|--------|------|---------|------|------|
| **KORGym-Eval-50** | 评估 | 1-50 | 50题 | 基线和训练后都用这个，保证公平对比 |
| **KORGym-Train-100** | 训练 | 51-150 | 100题 | 用于学习经验，不与评估集重叠 |

### ✅ 分层经验学习（已配置好）

```
游戏对局（100题）
    ↓
L0经验（案例级）：~100个
每个游戏回合提取1个具体策略
    ↓ 每5个L0聚合
L1经验（模式级）：~20个
总结通用的游戏策略模式
    ↓ 每3个L1聚合
L2经验（元策略级）：~6-7个
提炼跨游戏的通用原则
    ↓
增强的Agent配置
```

### ✅ 评估一致性（已保证）

- 基线评估和训练后评估使用**完全相同的50题**（seeds 1-50）
- 通过固定种子确保每次评估的题目内容一致
- 可以公平对比训练前后的性能提升

---

## 📖 建议的阅读顺序

如果这是你第一次使用：

1. **先看**: `KORGYM_QUICK_START.md`（5分钟快速了解）
2. **再看**: `KORGYM_WSL_SETUP.md`（WSL特定设置）
3. **参考**: `KORGYM_COMMANDS_SUMMARY.md`（命令速查）
4. **详细**: `KORGym_Usage_Guide.md`（完整文档，需要时查看）

---

## 🎯 预期效果

根据分层经验学习的设计：

- **基线准确率**: 30-50%
- **训练后准确率**: 40-65%
- **提升幅度**: +10-15%

*注：实际效果取决于游戏类型、模型能力和参数设置*

---

## 🎮 当前配置

### 游戏设置
- **默认游戏**: 8-word_puzzle（文字谜题）
- **游戏端口**: 8775
- **难度等级**: 3（中等）

### 训练设置
- **训练样本**: 100题（seeds 51-150）
- **评估样本**: 50题（seeds 1-50）
- **训练轮数**: 2 epochs
- **批大小**: 50
- **经验提取**: L0→L1→L2 自动聚合

---

## 🔄 如何切换到其他游戏

比如想改用2048游戏：

1. **编辑训练配置**（`configs/practice/korgym_practice.yaml`）:
   ```yaml
   korgym:
     game_name: "3-2048"  # 改这里
     game_port: 8776      # 改端口避免冲突
   ```

2. **创建新数据集**:
   ```bash
   uv run python scripts/data/prepare_korgym_data.py --game_name "3-2048"
   ```

3. **启动2048游戏服务器**:
   ```bash
   cd /mnt/f/youtu-agent/KORGym/game_lib/3-2048
   python game_lib.py -p 8776
   ```

4. **运行训练**（和之前一样）

---

## 🐛 遇到问题？

### 问题1: 找不到游戏服务器
```bash
# 检查服务器是否运行
curl http://localhost:8775/docs
```

### 问题2: Python环境问题
```bash
cd /mnt/f/youtu-agent
source .venv/bin/activate
which python  # 应该显示 .venv 路径
```

### 问题3: 权限错误
```bash
chmod +x scripts/*.sh
```

更多问题请查看 `KORGYM_WSL_SETUP.md` 的故障排查部分。

---

## 📁 重要文件位置（供查看）

```bash
# 查看基线评估结果
cat workspace/korgym_baseline_eval/score.txt

# 查看训练后评估结果
cat workspace/korgym_practice_eval/score.txt

# 查看提取的经验
cat workspace/hierarchical_experiences/korgym_practice.json

# 查看生成的增强Agent配置
cat configs/agents/practice/korgym_practice_agent.yaml
```

---

## ✅ 准备清单

在开始运行前，请确认：

- [x] 所有配置文件已创建
- [ ] WSL环境可以访问（`/mnt/f/youtu-agent`）
- [ ] 虚拟环境可以激活（`source .venv/bin/activate`）
- [ ] KORGym目录存在（`KORGym/game_lib/8-word_puzzle/`）
- [ ] 环境变量已配置（`.env`文件，包含LLM API密钥）
- [ ] 脚本有执行权限（`chmod +x scripts/*.sh`）

---

## 🎉 下一步

1. **按照上面"现在开始运行"部分执行命令**
2. **等待训练完成**（可能需要1-3小时，取决于硬件和LLM速度）
3. **查看结果对比**
4. **查看提取的分层经验**

---

## 💡 小提示

- 使用 `tmux` 可以方便管理多个终端（参考`KORGYM_WSL_SETUP.md`）
- 训练过程中可以在另一个终端查看经验文件的实时更新
- 如果启用Phoenix，可以在浏览器查看详细的trace（`http://localhost:6006`）

---

## 📞 需要帮助？

查看对应的文档：
- 💻 **命令不会用**: `KORGYM_COMMANDS_SUMMARY.md`
- 🐧 **WSL环境问题**: `KORGYM_WSL_SETUP.md`
- 📖 **详细说明**: `KORGym_Usage_Guide.md`
- ⚡ **快速上手**: `KORGYM_QUICK_START.md`

---

**🎮 祝你的Agent学习顺利！期待看到分层经验学习带来的性能提升！**

---

*创建时间: 2026-01-15*  
*项目: youtu-agent KORGym集成*  
*配置版本: v1.0*

