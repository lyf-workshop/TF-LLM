# Training-Free GRPO 完整流程详解 📚

本文档面向新手，详细讲解 Training-Free GRPO 的完整流程，包括数学求解和网页搜索两个典型场景，并解释每个代码文件的作用。

---

## 🎯 什么是 Training-Free GRPO？

**Training-Free GRPO (Group Relative Policy Optimization)** 是一种**无需训练模型参数**就能提升 AI 智能体性能的方法。

### 核心思想

想象你在学习数学题：
1. **多次尝试**：对同一道题，尝试不同的解题方法
2. **对比分析**：看看哪些方法成功了，哪些失败了
3. **总结经验**：从成功和失败中提取通用的解题技巧
4. **应用经验**：下次遇到类似问题时，直接使用这些经验

Training-Free GRPO 就是这样工作的，但它是在**代码层面**自动完成的！

---

## 📋 完整流程概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Training-Free GRPO 流程                    │
└─────────────────────────────────────────────────────────────┘

阶段 0: 初始化 (Build)
├── 加载数据集
├── 创建 Rollout 管理器
├── 创建经验更新器
└── 准备验证函数

阶段 1: 训练循环 (Practice)
│
├── 对于每个 Epoch（轮次）:
│   │
│   ├── 对于每个 Batch（批次）:
│   │   │
│   │   ├── 步骤 1: Rollout（生成多个解答）
│   │   │   └── 对每个问题生成 N 个不同的解答
│   │   │
│   │   ├── 步骤 2: 验证（判断对错）
│   │   │   └── 使用验证函数给每个解答打分
│   │   │
│   │   ├── 步骤 3: 经验提取
│   │   │   ├── 3.1 单 Rollout 摘要
│   │   │   ├── 3.2 组优势分析
│   │   │   ├── 3.3 组更新
│   │   │   └── 3.4 批量更新
│   │   │
│   │   └── 步骤 4: 评估（可选）
│   │       └── 在评估集上测试当前性能
│   │
│   └── 继续下一个 Batch
│
阶段 2: 生成最终配置
└── 将提取的经验整合到 Agent 配置文件中
```

---

## 🔢 场景一：数学求解

### 问题示例

假设我们有一个数学问题：

```
问题：求所有正整数 n，使得 sqrt(n² + 85n + 2017) 是整数。
正确答案：42
```

### 详细流程

#### 步骤 1: Rollout（生成多个解答）

系统会为这个问题生成 **N 个不同的解答**（例如 N=3，即 `grpo_n=3`）。

**Rollout 1**：
```
思考过程：
- 设 k = sqrt(n² + 85n + 2017)
- k² = n² + 85n + 2017
- 尝试 n = 1, 2, 3... 代入计算
- 当 n = 42 时，k = 65，是整数
- 答案：42
```
**验证结果**：✅ 正确 (reward = 1.0)

**Rollout 2**：
```
思考过程：
- 直接尝试 n = 1, 2, 3...
- 计算到 n = 20 时停止，没有找到答案
- 答案：无解
```
**验证结果**：❌ 错误 (reward = 0.0)

**Rollout 3**：
```
思考过程：
- 使用完全平方公式
- (n + 42.5)² = n² + 85n + 1806.25
- 需要 2017 - 1806.25 = 210.75
- 调整：n² + 85n + 2017 = (n + 42)² + 85
- 当 85 是完全平方数时...（推理错误）
- 答案：无解
```
**验证结果**：❌ 错误 (reward = 0.0)

#### 步骤 2: 验证（使用数学验证函数）

验证函数 (`utu/practice/verify/math.py`) 的工作方式：

```python
def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    # 1. 从模型输出中提取数学表达式
    model_output = sample.response  # 例如："答案是 42"
    
    # 2. 使用 math_verify 库进行符号验证
    #    - 提取 LaTeX 格式的答案
    #    - 与正确答案比较
    verify_func = math_metric(
        gold_extraction_target=(LatexExtractionConfig(),),
        pred_extraction_target=(ExprExtractionConfig(), LatexExtractionConfig()),
    )
    
    # 3. 返回分数和推理过程
    ret_score, _ = verify_func([ground_truth_boxed], [model_output])
    return {"reward": float(ret_score), "reasoning": None}
```

**验证结果汇总**：
- Rollout 1: reward = 1.0 ✅
- Rollout 2: reward = 0.0 ❌
- Rollout 3: reward = 0.0 ❌
- **平均分数** = (1.0 + 0.0 + 0.0) / 3 = 0.33

**筛选条件**：平均分数在 0 和 1 之间（部分正确），**会被用于经验提取** ✅

#### 步骤 3: 经验提取

##### 3.1 单 Rollout 摘要 (Single Rollout Summary)

为每个 Rollout 生成详细摘要：

**Rollout 1 的摘要**：
```
成功原因：
- 正确使用了完全平方公式
- 系统地尝试了不同的 n 值
- 找到了关键点：n = 42 时满足条件
- 推理过程清晰，步骤完整
```

**Rollout 2 的摘要**：
```
失败原因：
- 尝试范围不够广，过早停止
- 没有使用数学技巧（完全平方公式）
- 缺乏系统性的解题方法
```

**Rollout 3 的摘要**：
```
失败原因：
- 完全平方公式应用错误
- 计算过程中出现数值错误
- 没有验证结果的正确性
```

##### 3.2 组优势分析 (Group Advantage)

对比所有 Rollout，提取成功的关键因素：

**生成的初步经验**：
```
<Experiences>
1. 对于涉及完全平方的问题，应该系统地应用完全平方公式 (a+b)² = a² + 2ab + b²
2. 当需要找到满足条件的整数时，应该扩大搜索范围，不要过早停止
3. 在应用公式后，应该验证结果的正确性，确保满足原始条件
</Experiences>
```

##### 3.3 组更新 (Group Update)

将新经验与已有经验库合并，避免重复：

**已有经验库**：
```
[G0]. 对于几何问题，优先使用坐标和角度关系
[G1]. 对于代数问题，注意因式分解
```

**新经验**：
```
1. 对于涉及完全平方的问题，应该系统地应用完全平方公式
2. 当需要找到满足条件的整数时，应该扩大搜索范围
3. 在应用公式后，应该验证结果的正确性
```

**更新操作**：
- 检查是否有重复或相似的经验
- 合并相似的经验
- 添加新的经验

**更新后的经验库**：
```
[G0]. 对于几何问题，优先使用坐标和角度关系
[G1]. 对于代数问题，注意因式分解
[G2]. 对于涉及完全平方的问题，应该系统地应用完全平方公式 (a+b)² = a² + 2ab + b²，并验证结果的正确性
[G3]. 当需要找到满足条件的整数时，应该扩大搜索范围，不要过早停止
```

##### 3.4 批量更新 (Batch Update)

处理整个 Batch 的所有问题，统一更新经验库：

- 收集所有问题的经验提取结果
- 去重和合并相似经验
- 生成最终的经验库

---

## 🌐 场景二：网页搜索

### 问题示例

假设我们有一个网页搜索任务：

```
问题：2024年东京的人口是多少？
正确答案：约 1400 万人
```

### 详细流程

#### 步骤 1: Rollout（生成多个搜索策略）

系统会为这个问题生成 **N 个不同的搜索和回答过程**。

**Rollout 1**：
```
搜索过程：
1. 使用搜索工具查询 "Tokyo population 2024"
2. 从搜索结果中提取：东京都人口约 1400 万人（2024年数据）
3. 验证数据来源：来自东京都政府官网
4. 回答：2024年东京的人口约为 1400 万人
```
**验证结果**：✅ 正确 (reward = 1.0)

**Rollout 2**：
```
搜索过程：
1. 使用搜索工具查询 "Tokyo"
2. 从搜索结果中提取：东京是日本的首都
3. 没有进一步搜索人口信息
4. 回答：东京是日本的首都（未回答问题）
```
**验证结果**：❌ 错误 (reward = 0.0)

**Rollout 3**：
```
搜索过程：
1. 使用搜索工具查询 "Japan capital population"
2. 从搜索结果中提取：日本首都东京人口约 1300 万人（2020年数据）
3. 直接使用旧数据，没有确认最新数据
4. 回答：2024年东京的人口约为 1300 万人
```
**验证结果**：❌ 错误 (reward = 0.0) - 数据过时

#### 步骤 2: 验证（使用 LLM 判断）

验证函数 (`utu/practice/verify/webwalker.py`) 的工作方式：

```python
async def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    # 1. 使用 LLM 作为"裁判"来判断答案是否正确
    llm = kwargs.get("llm", SimplifiedAsyncOpenAI())
    
    # 2. 构建判断提示
    template = """
    问题：{problem}
    正确答案：{answer}
    模型回答：{response}
    
    请判断模型回答是否正确。
    输出格式：
    GRADE: CORRECT 或 INCORRECT
    EXPLANATION: 判断理由
    """
    
    # 3. LLM 判断
    response = await llm.query_one(messages=up)
    
    # 4. 解析结果
    correct = "CORRECT" in response
    return {"reward": float(correct), "reasoning": None}
```

**验证结果汇总**：
- Rollout 1: reward = 1.0 ✅
- Rollout 2: reward = 0.0 ❌
- Rollout 3: reward = 0.0 ❌
- **平均分数** = 0.33（部分正确，会被用于经验提取）

#### 步骤 3: 经验提取

##### 3.1 单 Rollout 摘要

**Rollout 1 的摘要**：
```
成功原因：
- 使用了精确的搜索关键词 "Tokyo population 2024"
- 验证了数据来源的可靠性（政府官网）
- 直接回答了问题，信息准确
```

**Rollout 2 的摘要**：
```
失败原因：
- 搜索关键词过于宽泛（"Tokyo"）
- 没有针对具体问题（人口）进行搜索
- 提取的信息不相关，未回答问题
```

**Rollout 3 的摘要**：
```
失败原因：
- 搜索关键词不够精确（"Japan capital population"）
- 使用了过时的数据（2020年而非2024年）
- 没有验证数据的时间戳
```

##### 3.2 组优势分析

**生成的初步经验**：
```
<Experiences>
1. 对于需要特定年份数据的问题，应该在搜索关键词中包含年份信息
2. 验证数据来源的可靠性，优先使用官方或权威来源
3. 检查数据的时间戳，确保使用最新数据
4. 搜索关键词应该精确匹配问题的核心信息
</Experiences>
```

##### 3.3 组更新

**更新后的经验库**：
```
[G0]. 对于需要特定年份数据的问题，应该在搜索关键词中包含年份信息（如 "Tokyo population 2024"）
[G1]. 验证数据来源的可靠性，优先使用官方或权威来源
[G2]. 检查数据的时间戳，确保使用最新数据，避免使用过时信息
[G3]. 搜索关键词应该精确匹配问题的核心信息，避免过于宽泛的查询
```

---

## 📁 代码文件详解

### 1. `training_free_grpo.py` - 主控制器

**作用**：整个流程的"总指挥"，协调所有组件

**主要功能**：
- `__init__()`: 初始化配置和记录器
- `build()`: 构建所有需要的组件（数据管理器、Rollout 管理器、经验更新器）
- `practice()`: 执行训练循环（Epoch → Batch → Rollout → 经验提取）
- `run()`: 运行完整流程并生成最终的 Agent 配置文件

**关键代码片段**：
```python
async def practice(self):
    for epoch in range(self.config.practice.epochs):
        # 1. 加载当前 Epoch 的数据
        epoch_data = self.practice_rollout_manager.load_epoch_data(epoch)
        
        # 2. 对每个 Batch 进行处理
        for batch_idx in range(num_batches):
            # 2.1 Rollout：生成多个解答
            rollouts, stat = await self.practice_rollout_manager.main(
                batch_idx=batch_idx,
                recorder=self.recorder,
            )
            
            # 2.2 经验提取和更新
            new_experiences = await self.experience_updater.run(
                rollouts=rollouts,
                recorder=self.recorder,
            )
            
            # 2.3 评估（可选）
            if self._should_evaluate(step, batch_idx, num_batches):
                await self.eval_rollout_manager.main(...)
```

---

### 2. `rollout_manager.py` - Rollout 执行器

**作用**：管理"生成多个解答"的过程

**主要功能**：
- `load_epoch_data()`: 加载当前 Epoch 的数据
- `preprocess_batch()`: 预处理批次数据（将经验添加到问题中）
- `rollout_batch()`: 对批次中的每个问题生成多个解答
- `judge_batch()`: 使用验证函数判断每个解答的对错
- `stat_batch()`: 统计批次的性能指标

**工作流程**：
```
问题 → 预处理（添加经验） → Rollout（生成解答） → 验证（判断对错） → 统计
```

**关键代码片段**：
```python
async def rollout_batch(self, batch_idx: int | None = None):
    # 获取需要处理的问题
    samples_to_process = self._get_batch_samples(batch_idx=batch_idx, stage="init")
    
    # 并发处理每个问题
    async def rollout_with_semaphore(item: EvaluationSample):
        # 调用 Agent 生成解答
        result = await self.rollout_one(item)
        return result
    
    # 并行执行所有 Rollout
    tasks = [rollout_with_semaphore(item) for item in samples_to_process]
    results = await asyncio.gather(*tasks)
```

---

### 3. `experience_updater.py` - 经验提取和更新器

**作用**：从 Rollout 结果中提取经验，并更新经验库

**主要功能**：
- `run()`: 执行完整的经验提取流程
- `_single_rollout_summary()`: 为每个 Rollout 生成摘要
- `_group_advantage()`: 对比多个 Rollout，提取组优势
- `_group_update()`: 将新经验与已有经验合并
- `_batch_update()`: 批量处理所有问题的经验

**工作流程**：
```
Rollout 结果 → 单 Rollout 摘要 → 组优势分析 → 组更新 → 批量更新 → 最终经验库
```

**关键代码片段**：
```python
async def _group_advantage(self, problem_to_summarized_rollouts, ...):
    # 对每个问题，对比其所有 Rollout
    for rollouts_per_problem in all_rollouts:
        # 格式化所有 Rollout 的摘要
        formatted_trajectories = "\n\n".join([
            f"Attempt {i+1} (Reward {each['reward']}):\n{each['trajectory_summary']}"
            for i, each in enumerate(rollouts_per_problem)
        ])
        
        # 使用 LLM 分析成功和失败的原因
        response = await self.llm.query_one(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        
        # 提取经验
        experiences = extract_experiences(response)
```

---

### 4. `data_manager.py` - 数据管理器

**作用**：管理训练和评估数据的加载、存储和查询

**主要功能**：
- `load_epoch_data()`: 加载指定 Epoch 的数据，并为每个问题创建 N 个副本（用于 GRPO）
- `get_batch_samples()`: 获取指定批次的问题
- `check_dataset()`: 检查数据集是否存在
- `save()`: 保存数据到数据库

**关键特性**：
- **数据复制**：为每个问题创建 `pass_k` 个副本（例如 pass_k=3，则每个问题有 3 个副本）
- **数据打乱**：每个 Epoch 可以打乱数据顺序
- **数据截断**：可以只使用数据集的前 N 个问题

**关键代码片段**：
```python
def load_epoch_data(self, epoch: int, shuffle: bool = True, truncate: int = None):
    # 1. 从数据库加载原始数据
    datapoints = session.exec(
        select(DatasetSample).where(DatasetSample.dataset == self.config.data.dataset)
    ).all()
    
    # 2. 打乱数据（如果需要）
    if shuffle:
        random.shuffle(datapoints)
    
    # 3. 截断数据（如果需要）
    if truncate:
        datapoints = datapoints[:truncate]
    
    # 4. 为每个问题创建 N 个副本（用于 GRPO）
    samples = []
    for dp in datapoints:
        for _ in range(self.config.pass_k):  # 例如 pass_k=3
            sample = EvaluationSample(
                dataset=dp.dataset,
                raw_question=dp.question,
                correct_answer=dp.answer,
                exp_id=f"{self.config.exp_id}_epoch_{epoch}",
            )
            samples.append(sample)
    
    return samples
```

---

### 5. `utils.py` - 工具函数

**作用**：提供配置解析和任务记录功能

**主要功能**：
- `TaskRecorder`: 记录训练过程中的经验、统计信息等
- `parse_training_free_grpo_config()`: 解析命令行参数和配置文件

**TaskRecorder 的作用**：
```python
@dataclass
class TaskRecorder:
    experiment_name: str          # 实验名称
    experiences: dict[str, str]   # 经验库 {经验ID: 经验内容}
    stats: dict[str, Any]         # 统计信息
    
    def experiences_update(self, experiences):
        # 更新经验库
        self.experiences = experiences
    
    def stat_update(self, stat):
        # 更新统计信息
        self.stats.update(stat)
```

---

### 6. `verify/` 目录 - 验证函数

**作用**：判断 Agent 的解答是否正确

#### `math.py` - 数学验证函数

**工作方式**：
1. 从模型输出中提取数学表达式（LaTeX 格式）
2. 使用 `math_verify` 库进行符号验证
3. 与正确答案比较
4. 返回分数（0.0 或 1.0）

**适用场景**：数学问题、需要精确答案的问题

#### `webwalker.py` - 网页搜索验证函数

**工作方式**：
1. 使用 LLM 作为"裁判"
2. 将问题、正确答案、模型回答一起发送给 LLM
3. LLM 判断模型回答是否正确
4. 返回分数（0.0 或 1.0）

**适用场景**：网页搜索、需要语义理解的任务

---

## 🔄 完整流程示例

### 数学问题完整流程

```
问题：求所有正整数 n，使得 sqrt(n² + 85n + 2017) 是整数。

┌─────────────────────────────────────────────────────────┐
│ 步骤 1: Rollout（生成 3 个解答）                          │
└─────────────────────────────────────────────────────────┘
Rollout 1: 使用完全平方公式，找到 n=42 ✅
Rollout 2: 直接尝试，范围不够 ❌
Rollout 3: 公式应用错误 ❌

┌─────────────────────────────────────────────────────────┐
│ 步骤 2: 验证（使用 math.py）                              │
└─────────────────────────────────────────────────────────┘
Rollout 1: reward = 1.0
Rollout 2: reward = 0.0
Rollout 3: reward = 0.0
平均分数 = 0.33（部分正确，用于经验提取）

┌─────────────────────────────────────────────────────────┐
│ 步骤 3: 经验提取                                          │
└─────────────────────────────────────────────────────────┘
3.1 单 Rollout 摘要：
  - Rollout 1: 成功使用完全平方公式
  - Rollout 2: 尝试范围不够
  - Rollout 3: 公式应用错误

3.2 组优势分析：
  提取经验：对于完全平方问题，应该系统应用公式并验证

3.3 组更新：
  将新经验合并到经验库

3.4 批量更新：
  处理整个 Batch，生成最终经验库

┌─────────────────────────────────────────────────────────┐
│ 步骤 4: 应用到 Agent 配置                                │
└─────────────────────────────────────────────────────────┘
将经验添加到 Agent 的 instructions 中：
"When solving problems, you MUST first carefully read and understand 
the helpful instructions and experiences:

[G0]. 对于涉及完全平方的问题，应该系统地应用完全平方公式...
[G1]. 当需要找到满足条件的整数时，应该扩大搜索范围..."
```

---

### 网页搜索完整流程

```
问题：2024年东京的人口是多少？

┌─────────────────────────────────────────────────────────┐
│ 步骤 1: Rollout（生成 3 个搜索过程）                      │
└─────────────────────────────────────────────────────────┘
Rollout 1: 搜索 "Tokyo population 2024"，找到准确数据 ✅
Rollout 2: 搜索 "Tokyo"，信息不相关 ❌
Rollout 3: 搜索 "Japan capital population"，数据过时 ❌

┌─────────────────────────────────────────────────────────┐
│ 步骤 2: 验证（使用 webwalker.py + LLM 判断）              │
└─────────────────────────────────────────────────────────┘
Rollout 1: reward = 1.0
Rollout 2: reward = 0.0
Rollout 3: reward = 0.0
平均分数 = 0.33（部分正确，用于经验提取）

┌─────────────────────────────────────────────────────────┐
│ 步骤 3: 经验提取                                          │
└─────────────────────────────────────────────────────────┘
3.1 单 Rollout 摘要：
  - Rollout 1: 使用精确关键词，验证数据来源
  - Rollout 2: 关键词过于宽泛
  - Rollout 3: 数据过时

3.2 组优势分析：
  提取经验：搜索关键词应包含年份，验证数据时间戳

3.3 组更新：
  将新经验合并到经验库

3.4 批量更新：
  处理整个 Batch，生成最终经验库

┌─────────────────────────────────────────────────────────┐
│ 步骤 4: 应用到 Agent 配置                                │
└─────────────────────────────────────────────────────────┘
将经验添加到 Agent 的 instructions 中：
"When solving problems, you MUST first carefully read and understand 
the helpful instructions and experiences:

[G0]. 对于需要特定年份数据的问题，应该在搜索关键词中包含年份信息
[G1]. 验证数据来源的可靠性，优先使用官方或权威来源
[G2]. 检查数据的时间戳，确保使用最新数据..."
```

---

## 🎓 关键概念总结

### 1. GRPO (Group Relative Policy Optimization)

- **Group**：对每个问题生成多个解答（Rollout）
- **Relative**：通过对比成功和失败的解答，提取相对优势
- **Policy Optimization**：优化策略（通过经验指导）

### 2. Training-Free

- **无需训练模型参数**：不修改 LLM 的权重
- **通过经验指导**：将提取的经验添加到 Agent 的 instructions 中
- **成本低**：只需要 API 调用，不需要 GPU 训练

### 3. 经验（Experiences）

- **格式**：`[G编号]. 经验标题: 具体指导内容`
- **来源**：从成功和失败的 Rollout 对比中提取
- **应用**：添加到 Agent 配置的 instructions 中，每次推理时都会使用

### 4. 验证函数（Verify Function）

- **数学问题**：使用符号验证（`math_verify` 库）
- **网页搜索**：使用 LLM 判断（语义理解）
- **返回**：`{"reward": 0.0 或 1.0, "reasoning": 可选}`

---

## 📊 数据流图

```
┌──────────────┐
│  原始数据集   │
└──────┬───────┘
       │
       ▼
┌──────────────┐      ┌──────────────┐
│ 数据管理器    │─────▶│ 创建 N 个副本 │
│ data_manager │      │ (用于 GRPO)   │
└──────┬───────┘      └──────────────┘
       │
       ▼
┌──────────────┐
│ Rollout 管理器│
│rollout_manager│
└──────┬───────┘
       │
       ├──▶ 预处理（添加经验） ──▶ Rollout（生成解答） ──▶ 验证（判断对错）
       │
       ▼
┌──────────────┐
│ 经验更新器    │
│experience_   │
│updater       │
└──────┬───────┘
       │
       ├──▶ 单 Rollout 摘要
       ├──▶ 组优势分析
       ├──▶ 组更新
       └──▶ 批量更新
       │
       ▼
┌──────────────┐
│  经验库      │
│ (Experiences)│
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Agent 配置    │
│ (带经验的)    │
└──────────────┘
```

---

## 🚀 快速开始

### 1. 准备数据

```bash
# 加载内置数据集
python scripts/data/process_training_free_GRPO_data.py
```

### 2. 运行 Training-Free GRPO

```bash
# 数学问题
python scripts/run_training_free_GRPO.py --config_name math_reasoning

# 网页搜索
python scripts/run_training_free_GRPO.py --config_name web_search
```

### 3. 评估结果

```bash
# 评估增强后的 Agent
python scripts/run_eval.py --config_name math/math_practice_AIME24
```

---

## 📚 相关文档

- [README.md](utu/practice/README.md) - 官方文档
- [经验生成机制详解.md](经验生成机制详解.md) - 经验生成详细说明
- [经验库使用机制说明.md](经验库使用机制说明.md) - 经验如何应用

---

## ❓ 常见问题

### Q1: 为什么需要生成多个 Rollout？

**A**: 通过对比成功和失败的解答，可以更准确地提取出成功的关键因素。单个解答可能只是偶然成功，多个解答的对比更能反映真正的优势。

### Q2: 经验是如何应用的？

**A**: 经验会被添加到 Agent 配置的 `instructions` 字段中。每次 Agent 处理问题时，这些经验会作为系统提示的一部分发送给 LLM。

### Q3: Training-Free 是什么意思？

**A**: 不需要训练（fine-tuning）模型的参数。只需要通过 API 调用 LLM，提取经验，然后将经验添加到配置中。这样成本更低，速度更快。

### Q4: 数学和网页搜索的验证方式为什么不同？

**A**: 
- **数学问题**：答案通常是精确的（如数字、公式），可以用符号验证
- **网页搜索**：答案可能是文本描述，需要语义理解，所以用 LLM 判断

---

## 🎯 总结

Training-Free GRPO 的核心流程：

1. **Rollout**：为每个问题生成多个解答
2. **验证**：判断每个解答的对错
3. **经验提取**：从成功和失败的对比中提取经验
4. **经验应用**：将经验添加到 Agent 配置中

这种方法**无需训练模型参数**，只需要通过 API 调用和配置更新，就能显著提升 Agent 的性能！

---

*本文档面向新手，如有疑问请参考官方文档或提交 Issue。*

















































































