# ✅ Alphabetical Sorting 缓存问题解决方案

## 🔍 问题诊断

你遇到的问题：**重复训练多次，每次结果都一样，只有1个经验**

### 根本原因

从日志中发现：

```
🔄 Using cached experiences for alphabetical_sorting_practice step 2 from database
Experiences for step 2 already exist in database, skipping experience update.
Extracted 1 experiences
```

**问题**：
1. ✅ 训练实际上执行了（388个样本，Pass@5 = 36.67%，33/90成功）
2. ❌ **从数据库读取了旧的缓存经验**
3. ❌ **跳过了新的经验提取和聚合**
4. ❌ 每次都用旧的1个经验，所以结果完全一样

### 为什么没有分层经验？

经验聚合需要：
```
100个游戏 → 100个L0经验
100个L0 ÷ 5 → 20个L1经验  
20个L1 ÷ 3 → 6-7个L2经验（G级）
```

但因为用了缓存，一直停在第1次训练的1个经验上，没有继续聚合。

---

## 🛠️ 解决方案

### **方案1：使用清理脚本（推荐）** ⭐

我已经为你创建了两个清理脚本：

#### 选项A：只清理经验缓存（快速）

```bash
cd /mnt/f/youtu-agent
uv run python scripts/clean_alphabetical_sorting_cache.py
```

这会删除经验缓存，让下次训练重新提取经验。

#### 选项B：完整重启（彻底）

```bash
cd /mnt/f/youtu-agent
uv run python scripts/restart_alphabetical_sorting_training.py
```

这会清理：
- ✅ 经验缓存
- ✅ 训练rollout数据
- ✅ 训练后评估数据

但保留：
- ✅ 数据集（避免重新创建）
- ✅ 基线评估

---

### **方案2：更改实验ID（不清理数据库）**

如果不想清理，可以修改配置文件：

```yaml
# configs/practice/alphabetical_sorting_practice.yaml
exp_id: "alphabetical_sorting_practice_v2"  # 改个新名字

# 同时修改保存路径
hierarchical_learning:
  experience_save_path: workspace/hierarchical_experiences/alphabetical_sorting_practice_v2.json
  agent_save_path: configs/agents/practice/alphabetical_sorting_practice_v2_agent.yaml
```

这样会创建一个新的实验，不会使用旧缓存。

---

## 🚀 完整重启流程

### Step 1: 清理缓存

```bash
cd /mnt/f/youtu-agent
uv run python scripts/restart_alphabetical_sorting_training.py
```

输入 `yes` 确认删除。

### Step 2: 确保游戏服务器运行

**终端1（WSL或Git Bash）**:
```bash
cd /mnt/f/youtu-agent/KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8776
```

保持运行！

### Step 3: 重新训练

**终端2（PowerShell）**:
```powershell
cd F:\youtu-agent
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice
```

### Step 4: 查看经验文件

训练完成后：
```powershell
# 查看经验文件
Get-Content workspace\hierarchical_experiences\alphabetical_sorting_practice.json

# 查看生成的Agent配置
Get-Content configs\agents\practice\alphabetical_sorting_practice_agent.yaml
```

### Step 5: 训练后评估

```powershell
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
```

---

## 📊 预期结果

### 之前（有缓存问题）
```yaml
agent:
  instructions: |
    ...
    [G0]. Systematic lexicographic search: ...
```
只有1个经验 ❌

### 之后（清理缓存）
```yaml
agent:
  instructions: |
    ...
    [G0]. First experience about letter counting...
    [G1]. Second experience about candidate generation...
    [G2]. Third experience about path verification...
    [G3]. Fourth experience about common patterns...
    [G4]. Fifth experience about...
    [G5]. Sixth experience about...
    [G6]. Seventh experience about...
```
预计6-7个分层经验 ✅

---

## 🎯 关键配置检查

确保这些配置正确：

```yaml
# configs/practice/alphabetical_sorting_practice.yaml
practice:
  epochs: 3              # 训练3轮
  batch_size: 100        # 每批100题
  
hierarchical_learning:
  enabled: true          # ✅ 必须启用
  l1_aggregation_threshold: 5   # 每5个L0聚合成1个L1
  l2_aggregation_threshold: 3   # 每3个L1聚合成1个L2
  max_l0_per_game: 1     # 每个游戏最多1个L0
```

---

## 🐛 其他可能的问题

### 问题1：训练成功率很低

从日志看到：
- **训练**: Pass@5 = 36.67% (33/90成功)
- **评估**: Pass@1 = 0% (0/50成功)

**可能原因**：
1. 策略还在优化中（已更新为词路径谜题策略）
2. 温度设置影响探索vs利用

**解决方案**：
- ✅ 已更新Agent策略（字母统计+候选生成+路径验证）
- ✅ 温度已调整为0.3（更确定的答案）
- ✅ 使用更大模型（Qwen2.5-72B）

### 问题2：数据集是否正确

检查数据集是否存在：
```powershell
uv run python scripts/check_experiments.py
```

如果需要重新创建：
```bash
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
```

---

## 📝 脚本说明

### 1. `scripts/clean_alphabetical_sorting_cache.py`
- **用途**: 只清理经验缓存
- **适用**: 快速重新训练
- **保留**: 所有其他数据

### 2. `scripts/restart_alphabetical_sorting_training.py`
- **用途**: 完整重启训练流程
- **清理**: 经验缓存 + 训练数据 + 评估数据
- **保留**: 数据集 + 基线评估

### 3. `scripts/clean_experiment_data.py`
- **用途**: 通用清理工具
- **功能**: 可以清理任何实验的数据

---

## 💡 最佳实践

1. **第一次遇到缓存问题**：使用 `restart_alphabetical_sorting_training.py`
2. **后续调试**：使用 `clean_alphabetical_sorting_cache.py`（更快）
3. **完全重来**：使用 `clean_and_restart_alphabetical_sorting.sh`（重建数据集）

---

## ✅ 检查清单

执行前确认：

- [ ] 已创建清理脚本
- [ ] 游戏服务器在8776端口运行
- [ ] 虚拟环境已激活
- [ ] 数据集已创建（或准备重建）
- [ ] 有足够的时间等待训练（1-2小时）

---

## 🎉 下一步

1. **运行清理脚本**
2. **重新训练**
3. **查看分层经验文件**
4. **对比训练前后的性能**

期待看到完整的分层经验（L0→L1→L2）！🚀

---

**创建时间**: 2026-01-16  
**问题**: 经验缓存导致重复训练结果相同  
**解决**: 清理数据库缓存，重新提取经验













