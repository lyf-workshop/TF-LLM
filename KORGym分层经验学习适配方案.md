# KORGym 分层经验学习适配方案 🎮

## 📋 概述

本文档详细说明如何将**分层经验学习系统（L0/L1/L2）**应用到 **KORGym** 游戏平台，帮助大模型在50+种游戏中总结经验并提升正确率。

---

## 🎯 一、KORGym 任务特点分析

### 1.1 任务类型

根据论文，KORGym 包含：

- **6个推理维度**：
  1. 数学与逻辑推理（Math & Logic）
  2. 控制交互推理（Control & Interaction）
  3. 谜题推理（Puzzle）
  4. 空间与几何推理（Spatial & Geometric）
  5. 战略推理（Strategic）
  6. 多模态推理（Multimodal）

- **50+ 种游戏**：每种游戏都有独特的规则和挑战

- **多轮交互**：支持多轮对话和状态追踪

- **强化学习支持**：可以与环境交互并接收反馈

### 1.2 与现有系统的对比

| 维度 | ZebraLogic（当前） | KORGym（目标） |
|------|-------------------|----------------|
| **任务类型** | 单一逻辑推理 | 6类50+游戏 |
| **交互方式** | 单轮问答 | 多轮交互 |
| **状态管理** | 无状态 | 有状态（游戏状态） |
| **反馈机制** | 最终答案验证 | 每轮动作反馈 |
| **难度控制** | 固定难度 | 可配置难度等级 |

---

## 🏗️ 二、适配方案设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│              KORGym 分层经验学习系统                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐      ┌──────────────┐                │
│  │  KORGym      │      │  分层经验     │                │
│  │  游戏环境    │◄────►│  管理器       │                │
│  │  (Gymnasium) │      │  (Hierarchical│                │
│  └──────────────┘      │   Experience)│                │
│         │               └──────────────┘                │
│         │                       ▲                       │
│         ▼                       │                       │
│  ┌──────────────┐      ┌──────────────┐                │
│  │  Agent       │      │  经验聚合     │                │
│  │  执行器      │─────►│  (L0→L1→L2)  │                │
│  └──────────────┘      └──────────────┘                │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### 2.2 分层经验映射

#### **L0 层：游戏回合级经验**

**触发时机**：每个游戏回合结束后

**经验来源**：
- 单次游戏回合的完整轨迹
- 动作序列和反馈
- 错误分析和失败原因

**示例**：
```
游戏：2048
回合ID：game_2048_round_1
L0经验：
"在2048游戏中，优先合并角落的数字块，避免将大数字块移动到中间位置，
这会导致后续无法继续合并。在移动前先观察所有可能的合并路径。"
```

#### **L1 层：游戏类型级策略**

**触发时机**：每积累 5 个同一游戏类型的 L0 经验

**经验来源**：
- 同一游戏（如 2048）的多个回合
- 或同一推理维度（如战略推理）的多个游戏

**示例**：
```
游戏类型：战略推理类（2048, Trust Evolution, N point）
L1经验：
"在需要长期规划的战略游戏中，应该：
1. 优先考虑未来3-5步的后果
2. 避免短视的局部最优解
3. 保持资源/状态的灵活性
4. 建立预测模型评估不同策略的长期收益"
```

#### **L2 层：跨游戏元策略**

**触发时机**：每积累 3 个不同游戏类型的 L1 经验

**经验来源**：
- 跨推理维度的 L1 策略
- 对应的所有源 L0 案例

**示例**：
```
L2经验：
"Principle: 在复杂推理任务中，建立显式的状态表示和预测模型
Why: 显式表示减少认知负载，预测模型帮助评估长期后果
When: 适用于需要多步推理、状态依赖、长期规划的任务
Benefits: 
  - 提高决策质量
  - 减少短视错误
  - 增强策略可解释性
Examples: 2048（状态=棋盘布局），Trust Evolution（状态=信任网络），
          N point（状态=当前得分和剩余机会）"
```

---

## 🔧 三、技术实现方案

### 3.1 新增组件

#### **1. KORGym 游戏适配器**

```python
# utu/practice/korgym_adapter.py

class KORGymAdapter:
    """适配 KORGym 游戏环境到分层经验学习系统"""
    
    def __init__(self, game_name: str, difficulty: str):
        self.game_name = game_name
        self.difficulty = difficulty
        self.game_env = None  # Gymnasium 环境
        self.game_state = None
        
    async def play_one_round(self, agent) -> Dict:
        """执行一轮游戏，返回轨迹和经验"""
        trajectory = []
        actions = []
        rewards = []
        
        # 初始化游戏
        obs = self.game_env.reset()
        
        while not self.game_env.is_done():
            # Agent 选择动作
            action = await agent.choose_action(obs, self.game_state)
            actions.append(action)
            
            # 执行动作
            next_obs, reward, done, info = self.game_env.step(action)
            rewards.append(reward)
            trajectory.append({
                'observation': obs,
                'action': action,
                'reward': reward,
                'next_observation': next_obs,
                'info': info
            })
            
            obs = next_obs
            self.game_state = info.get('state', None)
        
        # 计算最终结果
        final_score = self.game_env.get_final_score()
        success = self.game_env.is_success()
        
        return {
            'game_name': self.game_name,
            'trajectory': trajectory,
            'actions': actions,
            'rewards': rewards,
            'final_score': final_score,
            'success': success,
            'round_id': f"{self.game_name}_{self.difficulty}_{int(time.time())}"
        }
    
    def extract_l0_experience(self, round_result: Dict) -> str:
        """从游戏回合结果中提取 L0 经验"""
        if round_result['success']:
            # 成功案例：总结成功策略
            return self._extract_success_experience(round_result)
        else:
            # 失败案例：分析失败原因
            return self._extract_failure_experience(round_result)
```

#### **2. 游戏类型分类器**

```python
# utu/practice/korgym_game_classifier.py

GAME_CATEGORIES = {
    'math_logic': ['2048', 'Sudoku', 'Kakuro', ...],
    'control_interaction': ['Trust Evolution', 'Circle the cat', ...],
    'puzzle': ['Spider Solitaire', 'N point', ...],
    'spatial_geometric': ['Spatial Puzzle', ...],
    'strategic': ['2048', 'Trust Evolution', 'N point', ...],
    'multimodal': ['Visual Puzzle', ...]
}

class KORGymGameClassifier:
    """将游戏分类到推理维度"""
    
    @staticmethod
    def get_category(game_name: str) -> str:
        """返回游戏所属的推理维度"""
        for category, games in GAME_CATEGORIES.items():
            if game_name in games:
                return category
        return 'unknown'
    
    @staticmethod
    def get_primary_category(game_name: str) -> str:
        """返回游戏的主要推理维度（一个游戏可能属于多个维度）"""
        # 实现优先级逻辑
        ...
```

#### **3. 多轮交互经验提取器**

```python
# utu/practice/korgym_experience_extractor.py

class KORGymExperienceExtractor:
    """从多轮游戏交互中提取经验"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
        
    async def extract_l0_from_round(
        self, 
        round_result: Dict,
        game_category: str
    ) -> str:
        """从单轮游戏结果提取 L0 经验"""
        
        prompt = f"""
分析以下游戏回合，提取关键经验教训：

游戏：{round_result['game_name']}
类型：{game_category}
成功：{round_result['success']}
最终得分：{round_result['final_score']}

动作序列：
{self._format_actions(round_result['actions'])}

奖励序列：
{self._format_rewards(round_result['rewards'])}

请提取一条具体的经验教训，包括：
1. 关键错误或成功策略
2. 具体的改进建议
3. 适用的游戏状态

格式：
[L0-Case] 经验标题: 具体内容...
"""
        
        response = await self.llm.generate(prompt)
        return response.strip()
    
    def _format_actions(self, actions: List) -> str:
        """格式化动作序列"""
        return "\n".join([f"Step {i+1}: {action}" for i, action in enumerate(actions)])
    
    def _format_rewards(self, rewards: List) -> str:
        """格式化奖励序列"""
        return "\n".join([f"Step {i+1}: {reward}" for i, reward in enumerate(rewards)])
```

### 3.2 修改现有组件

#### **修改 HierarchicalExperienceManager**

```python
# utu/practice/hierarchical_experience_manager.py

class HierarchicalExperienceManager:
    # ... 现有代码 ...
    
    async def add_korgym_l0_experience(
        self,
        game_name: str,
        game_category: str,
        round_result: Dict,
        experience_content: str
    ):
        """添加来自 KORGym 游戏的 L0 经验"""
        l0_exp = {
            'id': f"L0-{len(self.l0_experiences)}",
            'game_name': game_name,
            'game_category': game_category,
            'round_id': round_result['round_id'],
            'content': experience_content,
            'level': 'L0-Case',
            'success': round_result['success'],
            'final_score': round_result['final_score'],
            'timestamp': datetime.now().isoformat()
        }
        
        self.l0_experiences.append(l0_exp)
        
        # 检查是否触发 L1 聚合（按游戏类型）
        self._check_l1_aggregation_by_category(game_category)
    
    def _check_l1_aggregation_by_category(self, category: str):
        """检查同一游戏类型是否达到 L1 聚合阈值"""
        category_l0s = [
            exp for exp in self.l0_experiences
            if exp.get('game_category') == category
        ]
        
        if len(category_l0s) >= self.h_config.l1_aggregation_threshold:
            # 触发该游戏类型的 L1 聚合
            asyncio.create_task(self._aggregate_l1_for_category(category))
    
    async def _aggregate_l1_for_category(self, category: str):
        """为特定游戏类型聚合 L1 经验"""
        category_l0s = [
            exp for exp in self.l0_experiences
            if exp.get('game_category') == category
        ][-self.h_config.l1_aggregation_threshold:]
        
        # 使用 LLM 聚合
        l1_content = await self._generate_l1_from_l0(category_l0s, category)
        
        l1_exp = {
            'id': f"L1-{len(self.l1_experiences)}",
            'content': l1_content,
            'level': 'L1-Pattern',
            'game_category': category,
            'source_l0_ids': [exp['id'] for exp in category_l0s],
            'timestamp': datetime.now().isoformat()
        }
        
        self.l1_experiences.append(l1_exp)
        
        # 检查是否触发 L2 聚合
        if len(self.l1_experiences) % self.h_config.l2_aggregation_threshold == 0:
            await self._aggregate_l1_to_l2()
```

### 3.3 配置文件

#### **KORGym 训练配置**

```yaml
# configs/practice/korgym_hierarchical_num1.yaml

defaults:
  - practice: base
  - agent: practice/logic_agent_hierarchical_learning_clean
  - eval: logic/easy_base_hierarchical_clean

exp_id: korgym_hierarchical_num1

data:
  practice_dataset_name: KORGym-Strategic-20  # 战略推理类20个游戏
  eval_dataset_name: KORGym-Strategic-10

evaluation:
  data:
    dataset: KORGym-Strategic-10

hierarchical_learning:
  enabled: true
  l1_aggregation_threshold: 5  # 每5个L0聚合一个L1
  l2_aggregation_threshold: 3   # 每3个L1聚合一个L2
  max_l0_per_game: 3          # 每个游戏最多3个L0
  max_l0_recent: 50           # 保留最近50个L0
  
  # KORGym 特定配置
  korgym:
    enabled: true
    game_categories:
      - strategic
      - math_logic
      - puzzle
    difficulty_levels:
      - easy
      - medium
    multi_turn: true           # 支持多轮交互
    state_tracking: true       # 追踪游戏状态
    
  experience_save_path: workspace/hierarchical_experiences/korgym_hierarchical_num1.json
  agent_save_path: configs/agents/practice/korgym_hierarchical_num1_agent.yaml
```

---

## 📊 四、经验生成流程

### 4.1 完整训练流程

```
阶段1：游戏回合执行
├── 选择游戏（如 2048）
├── 初始化游戏环境
├── Agent 执行多轮动作
├── 收集轨迹和反馈
└── 生成 L0 经验

阶段2：L1 聚合（每5个L0）
├── 识别同一游戏类型
├── LLM 抽象通用策略
└── 保存 L1 经验

阶段3：L2 聚合（每3个L1）
├── 收集跨游戏类型的 L1
├── 收集对应的所有 L0
├── LLM 提炼元策略
└── 保存 L2 经验

阶段4：经验库生成
├── 整合 L0/L1/L2
├── 按层次排序
├── 添加游戏类型标签
└── 生成最终配置文件
```

### 4.2 经验格式示例

```yaml
agent:
  instructions: |
    You are an expert game-playing agent. When solving KORGym games, 
    you MUST first read and understand the following experiences:
    
    [G0]. [L2-Meta] Cross-game strategic planning: In games requiring 
    long-term planning (2048, Trust Evolution, N point), establish 
    explicit state representations and prediction models. This reduces 
    cognitive load and helps evaluate long-term consequences...
    
    [G1]. [L2-Meta] Resource management principle: In games with limited 
    resources or moves, prioritize flexibility over immediate gains...
    
    [G2]. [L1-Pattern] Strategic reasoning games: When playing strategic 
    games, consider 3-5 steps ahead, avoid local optima, maintain state 
    flexibility, and build prediction models...
    
    [G3]. [L1-Pattern] Math logic games: In mathematical reasoning games, 
    systematically break down problems, verify each step, and check 
    constraints...
    
    [G4]. [L0-Case] 2048 corner strategy: In 2048, prioritize merging 
    tiles in corners, avoid moving large tiles to the center, and observe 
    all possible merge paths before moving...
    
    [G5]. [L0-Case] Trust Evolution network building: In Trust Evolution, 
    gradually build trust networks, avoid early aggressive moves, and 
    maintain balanced relationships...
    
    ...
```

---

## 🎯 五、预期效果

### 5.1 性能提升预测

基于论文中的实验结果和我们的分层经验学习系统：

| 模型类型 | Baseline | 扁平经验 | 分层经验（预测） |
|---------|----------|---------|-----------------|
| **闭源模型** | 60-70% | 65-75% | **70-80%** ⬆️ |
| **开源模型** | 40-50% | 45-55% | **50-65%** ⬆️ |
| **思维模型** | 65-75% | 70-80% | **75-85%** ⬆️ |

### 5.2 关键优势

1. **跨游戏泛化**：L2 元策略可应用于多个游戏类型
2. **快速适应**：L0 经验帮助快速学习新游戏
3. **策略可解释**：分层结构便于理解和调试
4. **持续改进**：随着游戏数量增加，经验库不断优化

---

## 🚀 六、实施步骤

### 步骤 1：环境准备

```bash
# 1. 安装 KORGym
pip install korgym  # 假设有官方包，或从 GitHub 安装

# 2. 准备游戏数据集
python scripts/data/load_korgym_dataset.py \
  --categories strategic math_logic puzzle \
  --difficulty easy medium \
  --output KORGym-Strategic-20
```

### 步骤 2：实现适配器

```bash
# 创建适配器文件
touch utu/practice/korgym_adapter.py
touch utu/practice/korgym_game_classifier.py
touch utu/practice/korgym_experience_extractor.py

# 实现核心逻辑（参考上面的代码示例）
```

### 步骤 3：修改配置

```bash
# 创建 KORGym 训练配置
cp configs/practice/medium_reasoning_hierarchical_num1.yaml \
   configs/practice/korgym_hierarchical_num1.yaml

# 修改配置（参考上面的配置示例）
```

### 步骤 4：运行训练

```bash
# 运行分层经验学习训练
uv run python scripts/run_training_free_GRPO.py \
  --config_name korgym_hierarchical_num1
```

### 步骤 5：评估效果

```bash
# 评估训练后的 agent
uv run python scripts/run_eval.py \
  --config_name korgym/korgym_hierarchical_num1_eval
```

---

## 📝 七、注意事项

### 7.1 游戏状态管理

- **状态持久化**：多轮游戏需要保存中间状态
- **状态表示**：不同游戏的状态格式可能不同，需要统一接口

### 7.2 经验去重

- **游戏特定去重**：同一游戏的相似回合可能产生重复经验
- **跨游戏去重**：不同游戏但策略相似的经验需要合并

### 7.3 计算资源

- **多轮交互成本**：每个游戏回合需要多次 LLM 调用
- **批量处理**：考虑批量执行多个游戏回合以提高效率

### 7.4 评估指标

- **游戏特定指标**：每个游戏的成功标准不同
- **跨游戏指标**：需要统一的评估框架

---

## 🔗 八、相关资源

- **KORGym 论文**：https://github.com/multimodal-art-projection/KORGym
- **分层经验学习文档**：`分层经验学习-完整运行指南.md`
- **GRPO 训练文档**：`Training-Free_GRPO完整流程详解.md`

---

## ✅ 总结

通过将**分层经验学习系统**应用到 **KORGym**，我们可以：

1. ✅ **从具体游戏回合中提取 L0 经验**
2. ✅ **从同一游戏类型中抽象 L1 策略**
3. ✅ **从跨游戏类型中提炼 L2 元策略**
4. ✅ **持续提升模型在多种游戏上的表现**

这个方案充分利用了分层经验学习的优势，同时适配了 KORGym 的多轮交互和多样化游戏特点。预期可以显著提升模型在 KORGym 平台上的正确率！🎯












