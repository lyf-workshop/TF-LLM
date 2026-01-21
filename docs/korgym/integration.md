# KORGym分层经验学习集成 - 文件清单 📚

本文档列出为KORGym游戏集成创建的所有配置文件和文档。

## 📦 创建的文件概览

### 1. 核心配置文件 ⚙️

#### Verification Function（验证函数）
- **文件**: `utu/practice/verify/korgym.py`
- **作用**: 验证KORGym游戏的执行结果（成功/失败）
- **说明**: 解析游戏结果JSON，返回reward和reasoning

#### Agent Configurations（Agent配置）
- **文件**: `configs/agents/practice/korgym_agent.yaml`
- **作用**: 基础Agent配置，用于游戏执行
- **说明**: 包含游戏策略的基本指令

#### Evaluation Configurations（评估配置）
- **文件1**: `configs/eval/korgym/korgym_eval.yaml`
  - **作用**: 基线评估配置（训练前）
  - **数据集**: KORGym-Eval-50（seeds 1-50）

- **文件2**: `configs/eval/korgym/korgym_practice_eval.yaml`
  - **作用**: 训练后评估配置
  - **数据集**: 同样使用KORGym-Eval-50（保证公平对比）

#### Practice Configuration（训练配置）
- **文件**: `configs/practice/korgym_practice.yaml`
- **作用**: 分层经验学习训练配置
- **数据集**: KORGym-Train-100（seeds 51-150）
- **特点**: 
  - 配置L0/L1/L2经验提取阈值
  - GRPO参数设置
  - 游戏相关参数

---

### 2. 脚本文件 🔧

#### 数据准备脚本
- **文件**: `scripts/data/prepare_korgym_data.py`
- **作用**: 创建训练和评估数据集
- **功能**:
  - 创建50个评估样本（seeds 1-50）
  - 创建100个训练样本（seeds 51-150）
  - 支持自定义游戏和种子范围

#### 游戏服务器启动脚本
- **文件**: `scripts/start_korgym_server.sh`
- **作用**: 便捷启动KORGym游戏服务器
- **用法**: `./scripts/start_korgym_server.sh 8-word_puzzle 8775`

#### 完整流程脚本
- **文件**: `scripts/run_korgym_full_pipeline.sh`
- **作用**: 一键运行完整训练和评估流程
- **包含步骤**:
  1. 检查游戏服务器
  2. 准备数据集
  3. 基线评估
  4. 训练
  5. 训练后评估
  6. 结果对比

---

### 3. 文档文件 📖

#### 主要使用指南
- **文件**: `KORGym_Usage_Guide.md`
- **内容**: 完整的使用指南
- **包含**:
  - 环境准备
  - 完整运行流程（6个步骤）
  - 游戏切换说明
  - 故障排查
  - 配置详解

#### 快速启动指南
- **文件**: `KORGYM_QUICK_START.md`
- **内容**: 快速上手指南
- **包含**:
  - 一键运行命令
  - 分步执行命令
  - 游戏切换方法
  - 常见问题解答

#### WSL环境设置
- **文件**: `KORGYM_WSL_SETUP.md`
- **内容**: Windows WSL环境特定设置
- **包含**:
  - WSL路径映射
  - 权限设置
  - 端口转发配置
  - WSL特定问题解决

#### 命令速查表
- **文件**: `KORGYM_COMMANDS_SUMMARY.md`
- **内容**: 所有命令的快速参考
- **包含**:
  - 核心命令列表
  - 结果查看命令
  - 故障排查命令
  - 重要文件位置

#### 本文件
- **文件**: `KORGYM_INTEGRATION_README.md`
- **内容**: 文件清单和集成说明

---

## 🎯 使用流程

```
1. 阅读文档
   └── 推荐顺序: QUICK_START → COMMANDS_SUMMARY → Usage_Guide

2. 环境准备
   └── 参考: WSL_SETUP.md（如果使用WSL）

3. 执行训练
   └── 方式1: 使用 run_korgym_full_pipeline.sh（一键运行）
   └── 方式2: 手动执行（参考COMMANDS_SUMMARY.md）

4. 查看结果
   └── 参考: COMMANDS_SUMMARY.md 中的"查看结果"部分
```

---

## 📊 数据集设计

| 数据集 | 用途 | 种子范围 | 样本数 |
|--------|------|---------|--------|
| KORGym-Eval-50 | 评估（基线+训练后） | 1-50 | 50 |
| KORGym-Train-100 | 训练 | 51-150 | 100 |

**设计理由**:
- 评估集固定（seeds 1-50），确保baseline和practice使用相同数据，可公平对比
- 训练集不重叠（seeds 51-150），避免数据泄露

---

## 🎮 支持的游戏

当前配置默认使用 **8-word_puzzle**，可通过修改配置切换到其他游戏：

### 推荐游戏列表

| 类别 | 游戏示例 | 游戏ID | 推荐端口 |
|------|---------|--------|----------|
| Puzzle | Word Puzzle | 8-word_puzzle | 8775 |
| Strategic | 2048 | 3-2048 | 8776 |
| Puzzle | Wordle | 33-wordle | 8777 |
| Math-Logic | Sudoku | 4-SudoKu | 8778 |
| Spatial | Tower of Hanoi | 30-Tower_of_Hanoi | 8779 |

---

## 🔄 分层经验学习架构

```
游戏对局 (seeds 51-150)
    ↓
L0经验提取 (每个游戏1个案例级经验)
    ↓ (每5个L0聚合)
L1经验生成 (模式级策略)
    ↓ (每3个L1聚合)
L2经验生成 (元策略级原则)
    ↓
增强Agent配置
    ↓
评估 (seeds 1-50, 与baseline对比)
```

**预期生成经验数量**（100个游戏）:
- L0: ~100个（案例级）
- L1: ~20个（模式级）
- L2: ~6-7个（元策略级）

---

## 📁 生成的文件结构

```
youtu-agent/
├── configs/
│   ├── agents/practice/
│   │   ├── korgym_agent.yaml                    # [创建] 基础Agent
│   │   └── korgym_practice_agent.yaml           # [生成] 增强Agent
│   ├── eval/korgym/
│   │   ├── korgym_eval.yaml                     # [创建] 基线评估
│   │   └── korgym_practice_eval.yaml            # [创建] 训练后评估
│   └── practice/
│       └── korgym_practice.yaml                 # [创建] 训练配置
├── scripts/
│   ├── data/
│   │   └── prepare_korgym_data.py               # [创建] 数据准备
│   ├── start_korgym_server.sh                   # [创建] 服务器启动
│   └── run_korgym_full_pipeline.sh              # [创建] 完整流程
├── utu/practice/verify/
│   └── korgym.py                                # [创建] 验证函数
├── workspace/
│   ├── korgym_baseline_eval/                    # [生成] 基线结果
│   ├── korgym_practice_eval/                    # [生成] 训练后结果
│   └── hierarchical_experiences/
│       └── korgym_practice.json                 # [生成] 经验库
└── [文档]
    ├── KORGym_Usage_Guide.md                    # [创建] 使用指南
    ├── KORGYM_QUICK_START.md                    # [创建] 快速开始
    ├── KORGYM_WSL_SETUP.md                      # [创建] WSL设置
    ├── KORGYM_COMMANDS_SUMMARY.md               # [创建] 命令速查
    └── KORGYM_INTEGRATION_README.md             # [创建] 本文件
```

**图例**:
- `[创建]`: 手动创建的配置/脚本/文档
- `[生成]`: 训练过程自动生成的文件

---

## ✅ 验证清单

使用前请确认：

- [ ] 所有配置文件已创建
- [ ] 数据准备脚本可执行
- [ ] Shell脚本有执行权限（WSL中运行`chmod +x`）
- [ ] KORGym仓库在项目根目录
- [ ] 环境变量已配置（.env文件）
- [ ] 虚拟环境可以激活
- [ ] 游戏服务器可以启动

---

## 🚀 快速开始

1. **阅读快速开始指南**
   ```bash
   cat KORGYM_QUICK_START.md
   ```

2. **启动游戏服务器**（终端1）
   ```bash
   cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
   python game_lib.py -p 8775
   ```

3. **运行完整流程**（终端2）
   ```bash
   cd /mnt/f/youtu-agent
   source .venv/bin/activate
   ./scripts/run_korgym_full_pipeline.sh
   ```

---

## 📞 获取帮助

- **详细文档**: 参考 `KORGym_Usage_Guide.md`
- **命令查询**: 参考 `KORGYM_COMMANDS_SUMMARY.md`
- **WSL问题**: 参考 `KORGYM_WSL_SETUP.md`
- **快速开始**: 参考 `KORGYM_QUICK_START.md`

---

## 📈 预期效果

根据分层经验学习的设计：

- **基线准确率**: 30-50%（取决于游戏和模型）
- **训练后准确率**: 40-65%
- **预期提升**: +10-15%

实际效果可能因游戏类型、模型能力和超参数设置而异。

---

## 🎓 技术要点

### 关键配置参数

```yaml
# 分层经验学习
l1_aggregation_threshold: 5  # L0→L1聚合阈值
l2_aggregation_threshold: 3  # L1→L2聚合阈值
max_l0_recent: 50           # Prompt中保留的L0数量

# GRPO训练
epochs: 2                   # 训练轮数
batch_size: 50              # 批大小
grpo_n: 3                   # 每题rollout数量

# 数据集
eval_seeds: 1-50            # 评估种子范围
train_seeds: 51-150         # 训练种子范围
```

### 经验提取流程

1. **L0提取**: 从每个游戏回合的轨迹中提取具体策略
2. **L1聚合**: 每5个同类L0经验总结为1个通用模式
3. **L2聚合**: 每3个L1经验提炼为1个元策略原则
4. **Agent增强**: 将L0/L1/L2注入到Agent instructions中

---

✅ **所有配置和文档已完成，可以开始使用了！**

建议从 `KORGYM_QUICK_START.md` 开始阅读。

