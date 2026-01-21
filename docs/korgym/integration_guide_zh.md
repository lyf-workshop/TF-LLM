# KORGym 集成指南 🎮

## 📋 概述

本指南说明如何将 KORGym 游戏平台集成到 youtu-agent 项目中，使用分层经验学习系统（L0/L1/L2）来提升大模型在游戏中的表现。

---

## 🎯 已完成的工作

### 第一步：核心适配器 ✅

已创建以下核心模块：

1. **`utu/practice/korgym_adapter.py`** - KORGym 游戏适配器
   - 游戏分类器（按6个推理维度分类）
   - 游戏类型识别（单轮/多轮）
   - 游戏服务器通信接口
   - 动作提取和验证

2. **`utu/practice/korgym_experience_extractor.py`** - 经验提取器
   - 从游戏轨迹提取 L0 经验
   - 支持单轮和多轮游戏
   - 批量并发提取
   - LLM 驱动的经验生成

3. **`configs/practice/korgym_hierarchical_test.yaml`** - 测试配置
   - 2048 游戏测试配置
   - 分层学习参数
   - GRPO 设置

4. **`scripts/test_korgym_adapter.py`** - 测试脚本
   - 自动启动游戏服务器
   - 测试游戏执行
   - 验证经验提取
   - 生成测试报告

---

## 🚀 快速开始

### 环境准备

1. **安装 KORGym 依赖**：

```bash
cd KORGym
pip install -r requirements.txt
```

2. **验证 KORGym 结构**：

```bash
# 应该看到这些目录
ls KORGym/
# game_lib/  eval_lib/  results/  ...

# 检查 2048 游戏文件
ls KORGym/game_lib/3-2048/
# game_lib.py  game_server.out
```

### 运行测试

```bash
# 在项目根目录运行
uv run python scripts/test_korgym_adapter.py
```

测试脚本会：
1. ✅ 启动 2048 游戏服务器
2. ✅ 初始化 KORGym 适配器
3. ✅ 加载 Agent
4. ✅ 玩 3 局游戏
5. ✅ 提取 L0 经验
6. ✅ 生成测试报告

### 查看结果

```bash
# 测试结果保存在
cat workspace/korgym_test/test_results.json
```

---

## 🎮 支持的游戏

KORGym 包含 **50+ 种游戏**，分为 **6 个推理维度**：

### 1. 数学与逻辑推理 (Math & Logic)
- `1-DateCount` - 日期计数
- `4-SudoKu` - 数独
- `16-jiafa` - 加法游戏
- `32-numeral_bricks` - 数字积木
- `47-jiafa_multimodal` - 多模态加法
- `50-SudoKu_MultiModal` - 多模态数独

### 2. 控制交互推理 (Control & Interaction)
- `10-minigrid` - 迷你网格
- `11-maze` - 迷宫
- `12-sokoban` - 推箱子
- `41-PVZ` - 植物大战僵尸
- `45-free_the_key` - 解锁钥匙

### 3. 谜题推理 (Puzzle)
- `2-GuessWord` - 猜词
- `5-light_out_game` - 关灯游戏
- `8-word_puzzle` - 文字谜题
- `33-wordle` - Wordle
- `36-CryptoWord` - 密码词
- ...（共16个谜题游戏）

### 4. 空间与几何推理 (Spatial & Geometric)
- `7-black_white_copy` - 黑白复制
- `18-alien` - 外星人
- `30-Tower_of_Hanoi` - 汉诺塔
- `31-ball_arrange` - 球排列
- `48-map_position_simulation_text` - 地图位置模拟

### 5. 战略推理 (Strategic) ⭐
- `3-2048` - 2048 游戏
- `24-snake` - 贪吃蛇
- `25-Tetris` - 俄罗斯方块
- `26-TrustRovolution` - 信任进化
- `27-NpointPlus` - N点增强
- `37-SpiderSolitaire` - 蜘蛛纸牌
- `40-CircleTheCat-Text` - 围住猫（文本）

### 6. 多模态推理 (Multimodal)
- `43-CircleTheCat-Multimodal` - 围住猫（多模态）
- `46-wordle_multimodal` - Wordle（多模态）
- `49_map_position_simulation_multimodal` - 地图（多模态）
- `51-ball_arrange_multimodal` - 球排列（多模态）

---

## 🏗️ 架构说明

### 系统组件

```
┌─────────────────────────────────────────────────────────┐
│         KORGym 分层经验学习集成架构                       │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐      ┌──────────────┐                │
│  │  KORGym      │      │  分层经验     │                │
│  │  游戏环境    │◄────►│  管理器       │                │
│  │  (FastAPI)   │      │  (Hierarchical│                │
│  └──────────────┘      │   Manager)   │                │
│         │               └──────────────┘                │
│         │                       ▲                       │
│         ▼                       │                       │
│  ┌──────────────┐      ┌──────────────┐                │
│  │  KORGym      │      │  经验聚合     │                │
│  │  Adapter     │─────►│  (L0→L1→L2)  │                │
│  └──────────────┘      └──────────────┘                │
│         │                       │                       │
│         ▼                       ▼                       │
│  ┌──────────────┐      ┌──────────────┐                │
│  │  Experience  │      │  Agent Config │                │
│  │  Extractor   │      │  Generator   │                │
│  └──────────────┘      └──────────────┘                │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### 数据流

```
游戏执行 → 轨迹记录 → L0提取 → L1聚合 → L2抽象 → 配置生成
```

1. **游戏执行**：Agent 与 KORGym 游戏环境交互
2. **轨迹记录**：记录动作、状态、奖励序列
3. **L0 提取**：从单局游戏中提取具体经验
4. **L1 聚合**：每 5 个 L0 → 1 个 L1（同类型游戏）
5. **L2 抽象**：每 3 个 L1 → 1 个 L2（跨游戏类型）
6. **配置生成**：生成包含所有经验的 Agent 配置

---

## 📊 分层经验示例

### L0 - 游戏回合级经验

```
[L0-Case] 2048 Corner Strategy: In the 2048 game, prioritize keeping the 
largest tile in one corner (preferably top-left or bottom-right). Moving 
the large tile to the center blocks future merges and reduces available 
space. Always plan 2-3 moves ahead before committing to an action.

Context: Game #42, Seed 7, Score 2048, 47 rounds
```

### L1 - 游戏类型级策略

```
[L1-Pattern] Strategic Planning in Long-term Games: In games requiring 
long-term planning (2048, Trust Evolution, N point), establish clear 
intermediate goals and evaluate each action's impact on future states. 
Avoid myopic decisions that maximize immediate rewards but limit future 
options. Key principles:
1. Maintain state flexibility
2. Plan 3-5 steps ahead
3. Identify and avoid dead-end states
4. Balance exploration and exploitation

Source: L0 experiences from 2048 (#3, #7, #12), Trust Evolution (#8, #15)
```

### L2 - 跨游戏元策略

```
[L2-Meta] Explicit State Representation Principle: In complex reasoning 
tasks across all game types, building an explicit, structured representation 
of the current state significantly improves decision quality.

Why: Reduces cognitive load and working memory demands, making patterns 
and constraints more visible.

When: Applicable to:
- Strategic games (2048, Tetris) - track board state and upcoming pieces
- Puzzle games (Sudoku, Maze) - maintain constraint network
- Control games (Sokoban, Minigrid) - map environment topology

Benefits:
- Fewer reasoning errors
- Better long-term planning
- Easier backtracking and error recovery

Examples: In 2048, explicitly track tile positions and possible merges; 
in Sudoku, maintain candidate sets for each cell; in Maze, build mental 
map of explored areas.

Source: 3 L1 patterns across 15 L0 cases from strategic, puzzle, and 
control game categories
```

---

## 🔧 下一步开发

### 待实现功能

#### 1. 完整 GRPO 训练循环 
- [ ] 集成到 `TrainingFreeGRPO` 主流程
- [ ] 批量游戏执行
- [ ] 经验缓存和持久化

#### 2. 多游戏支持
- [ ] 游戏调度器（轮询不同游戏）
- [ ] 难度自适应（动态调整 level）
- [ ] 跨游戏经验迁移

#### 3. 高级经验管理
- [ ] L0 去重（相似游戏场景）
- [ ] 经验质量评分
- [ ] 动态经验选择（根据当前游戏）

#### 4. 评估和分析
- [ ] 跨游戏性能对比
- [ ] 经验有效性分析
- [ ] 可视化dashboard

---

## 📖 使用示例

### 示例 1：测试单个游戏

```python
import asyncio
from utu.agents import get_agent
from utu.config import ConfigLoader
from utu.practice.korgym_adapter import KORGymAdapter

async def test_game():
    # 加载 agent
    config = ConfigLoader.load_agent_config("practice/logic_agent_hierarchical_learning_clean")
    agent = get_agent(config)
    
    # 初始化适配器
    adapter = KORGymAdapter(
        game_name="3-2048",
        game_host="localhost",
        game_port=8775
    )
    
    # 玩游戏
    result = await adapter.play_game(agent, seed=42)
    
    print(f"Score: {result['final_score']}")
    print(f"Rounds: {result['rounds']}")
    print(f"Success: {result['success']}")

asyncio.run(test_game())
```

### 示例 2：批量提取经验

```python
import asyncio
from utu.practice.korgym_experience_extractor import KORGymExperienceExtractor

async def extract_experiences(game_results):
    # 初始化提取器
    extractor = KORGymExperienceExtractor(llm_config={
        "type": "chat.completions",
        "model": "Qwen/Qwen3-14B"
    })
    
    # 批量提取
    experiences = await extractor.extract_batch_l0(
        game_results,
        game_category="strategic",
        game_type="multiple",
        max_concurrent=5
    )
    
    return experiences
```

---

## 🐛 故障排查

### 问题 1：游戏服务器无法启动

**症状**：`Connection refused` 错误

**解决**：
```bash
# 手动启动游戏服务器
cd KORGym/game_lib/3-2048
python game_lib.py -p 8775

# 确认服务器运行
curl http://localhost:8775/docs
```

### 问题 2：Agent 响应超时

**症状**：游戏卡住不动

**解决**：
- 增加 `task_timeout` 配置
- 检查 LLM API 是否正常
- 降低游戏难度（`level=1`）

### 问题 3：经验提取失败

**症状**：生成 fallback 经验

**解决**：
- 检查 LLM 配置
- 查看日志中的 LLM 调用详情
- 尝试不同的 prompt 模板

---

## 📚 相关文档

- [KORGym 原始论文](https://arxiv.org/abs/2505.14552)
- [分层经验学习指南](分层经验学习-完整运行指南.md)
- [KORGym 适配方案](KORGym分层经验学习适配方案.md)
- [Training-Free GRPO 流程](Training-Free_GRPO完整流程详解.md)

---

## ✅ 总结

已完成的核心功能：
- ✅ KORGym 游戏适配器
- ✅ 经验提取器
- ✅ 游戏分类系统
- ✅ 测试脚本
- ✅ 基础配置

下一步：
1. 运行测试脚本验证集成
2. 根据测试结果调整参数
3. 实现完整的 GRPO 训练循环
4. 扩展到更多游戏类型

🎮 准备开始使用 KORGym 训练你的 Agent！












