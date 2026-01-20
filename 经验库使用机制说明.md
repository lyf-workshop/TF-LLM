# 经验库使用机制说明 📚

本文档详细说明 Training-Free GRPO 训练出的经验库是如何在测试时传递给大模型的。

## 🔄 完整流程概览

```
训练阶段 (Training)
├── 在 DAPO-100 上运行 Training-Free GRPO
├── 提取经验 (Experiences/Guidelines)
└── 保存到 enhanced agent 配置文件
    └── math_practice_paper_exp_agent.yaml

测试阶段 (Evaluation)
├── 加载 enhanced agent 配置
├── 读取 instructions 字段（包含所有经验）
├── 每次做题时，完整地传递给大模型
└── 作为 system message 或 instructions
```

## 📝 经验库的存储方式

### 1. 训练后自动生成的配置文件

训练完成后，系统会自动生成增强的 agent 配置文件：

```yaml
# configs/agents/practice/math_practice_paper_exp_agent.yaml
agent:
  name: math_agent_paper_exp
  instructions: |
    Solve the following math problem step by step...
    
    When solving problems, you MUST first carefully read and understand 
    the helpful instructions and experiences:
    
    [G0]. Diagram interpretation: ...
    [G1]. Constraint handling: ...
    [G2]. Periodic functions: ...
    ...
    [G63]. Pattern validation: ...
```

### 2. 经验的格式

每条经验都是一个简洁的指导原则：

```
[G标号]. 经验标题: 具体的指导内容
```

例如：
```
[G0]. Diagram interpretation: Prioritize labeled numerical values over 
coordinate measurements in geometric diagrams as they represent actual 
problem constraints and diagrams are often schematic and not to scale.
```

## 🎯 测试时的使用方式

### 方式一：**每次做题都完整传递所有经验**

**是的！每次做题时，所有的经验（[G0]到[G63]）都会完整地发送给大模型。**

### 具体实现流程

```python
# 1. 评估配置引用增强的 agent
# configs/eval/math/math_practice_paper_exp_AIME24.yaml
defaults:
  - /agents/practice/math_practice_paper_exp_agent@agent  # 引用增强 agent

# 2. 加载配置时读取 instructions
config = ConfigLoader.load_eval_config("math/math_practice_paper_exp_AIME24")
# config.agent.instructions 包含所有经验

# 3. 创建 SimpleAgent 时设置 instructions
agent = SimpleAgent(config=config)
await agent.build()

# 4. 在 SimpleAgent.build() 中
self.current_agent = Agent(
    name=self.config.agent.name,
    instructions=self.config.agent.instructions,  # 包含所有经验
    model=self.model,
    ...
)

# 5. 每次做题时
# instructions 作为 system message 或者在 prompt 的最开始
# 完整地发送给大模型
```

## 📨 实际发送给 LLM 的消息

每次做题时，LLM 收到的消息结构大致如下：

```
System Message / Instructions:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Solve the following math problem step by step using pure reasoning.
Think through the problem carefully and show your work.

The last part of your final response should be in the following format:
<answer>
\boxed{{'The final answer goes here.'}}
</answer>

When solving problems, you MUST first carefully read and understand 
the helpful instructions and experiences:

[G0]. Diagram interpretation: Prioritize labeled numerical values...
[G1]. Constraint handling: Validate solutions by adjusting formulas...
[G2]. Periodic functions: Map values to fundamental period...
...
[G63]. Pattern validation: Always validate identified patterns...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

User Message:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[具体的数学题目]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 🔍 代码实现细节

### 1. Agent 初始化

```python
# utu/agents/simple_agent.py
async def build(self, trace_id: str = None):
    """Build the agent"""
    # ...
    self.current_agent = Agent(
        name=self.config.agent.name,
        instructions=self.config.agent.instructions,  # 这里包含所有经验
        model=self.model,
        model_settings=self.model_settings,
        tools=await self.get_tools(),
        output_type=self.output_type,
        tool_use_behavior=self.tool_use_behavior,
        mcp_servers=self._mcp_servers,
    )
```

### 2. Instructions 如何工作

`instructions` 参数在底层 `agents` 库中会被处理为：
- 对于支持 system message 的模型（如 OpenAI, DeepSeek）：作为 system message
- 对于不支持的模型：插入到第一条 user message 之前

### 3. 每次调用都包含

```python
# 每次做题
await agent.run(question)

# 内部会构造类似这样的消息列表
messages = [
    {"role": "system", "content": instructions},  # 包含所有经验
    {"role": "user", "content": question}         # 具体题目
]
```

## ❓ 常见问题

### Q1: 经验库会不会太长，超过 token 限制？

**A**: 在论文实验中，64 条经验大约占用 **1000-1500 tokens**。对于现代 LLM（如 DeepSeek V3.1 支持 64K context），这只占很小一部分，完全可以接受。

### Q2: 每次都发送所有经验，会不会影响性能？

**A**: 
- **Token 成本**: 增加约 1000-1500 input tokens/问题
- **延迟**: 影响很小，因为 input tokens 处理速度快
- **好处**: 模型可以根据题目需要选择相关经验

### Q3: 能否只发送相关的经验？

**可以，但目前没有实现**。理论上可以：
1. 用 embedding 计算题目和经验的相似度
2. 只选择 top-k 最相关的经验发送

但论文实验表明，发送所有经验的效果已经很好，且实现更简单。

### Q4: 经验库在哪里存储？

**存储位置**：
- **主要位置**: Agent 配置文件的 `instructions` 字段
  - 例如：`configs/agents/practice/math_practice_paper_exp_agent.yaml`
- **数据库**: 训练过程中的经验也存储在数据库中（用于记录和分析）
  - 但评估时不从数据库读取，直接从配置文件读取

### Q5: 如何查看某条经验是否真的被使用了？

可以在 Phoenix 中查看详细的 trace：
1. 启动 Phoenix: `phoenix serve`
2. 访问 http://127.0.0.1:6006
3. 查看 trace 详情，可以看到完整的 system message

或者在代码中添加日志：
```python
# 在 SimpleAgent.build() 后
print(agent.current_agent.instructions[:500])  # 打印前 500 字符
```

## 📊 性能影响分析

### Token 使用对比

| 阶段 | Baseline | Enhanced (with experiences) | 增加 |
|-----|----------|----------------------------|------|
| System/Instructions | ~200 tokens | ~1500 tokens | +1300 |
| Question | ~100 tokens | ~100 tokens | 0 |
| Response | ~500 tokens | ~500 tokens | 0 |
| **总计** | ~800 tokens | ~2100 tokens | +1300 |

### 成本影响

以 DeepSeek V3.1 为例（¥1/M input tokens）：
- 每个问题增加约 1300 input tokens
- 成本增加: ¥0.0013/问题
- AIME24 (30题): 增加约 ¥0.04
- **几乎可以忽略不计**

## 🎯 总结

1. **传递方式**: 每次做题时，**所有经验都完整地**作为 instructions 发送给大模型

2. **为什么这样设计**:
   - ✅ 简单直接，无需检索或选择
   - ✅ 模型可以自主决定使用哪些经验
   - ✅ Token 成本可接受
   - ✅ 不需要额外的检索系统

3. **实现机制**:
   ```
   配置文件 (YAML) 
   → ConfigLoader 
   → AgentConfig.agent.instructions 
   → Agent(instructions=...) 
   → System Message / Prompt 前缀
   → 发送给 LLM
   ```

4. **优化空间**:
   - 可以实现经验检索（根据题目相似度选择）
   - 可以实现经验分层（高频/低频经验）
   - 可以实现动态经验（根据性能调整）

## 🔗 相关文件

| 文件 | 作用 |
|-----|------|
| `configs/agents/practice/math_practice_paper_exp_agent.yaml` | 存储经验库的配置文件 |
| `utu/agents/simple_agent.py` | Agent 初始化，读取 instructions |
| `utu/practice/training_free_grpo.py` | 训练时生成经验库 |
| `scripts/run_eval.py` | 评估时加载和使用经验库 |

## 💡 验证经验是否生效

### 方法 1: 查看配置文件

```bash
# 查看经验库内容
cat configs/agents/practice/math_practice_paper_exp_agent.yaml | grep "\[G"

# 应该看到 [G0] 到 [G63] 所有经验
```

### 方法 2: 在评估时打印

在 `utu/agents/simple_agent.py` 中添加：

```python
async def build(self, trace_id: str = None):
    # ...
    self.current_agent = Agent(...)
    
    # 添加这行打印
    print(f"Agent instructions length: {len(self.config.agent.instructions)} chars")
    print(f"First 200 chars: {self.config.agent.instructions[:200]}")
```

### 方法 3: 通过 Phoenix 查看

在 Phoenix UI 中查看任意一个 trace 的详细信息，可以看到完整的 system message 包含所有经验。

---

**关键要点**: 经验库是在**每次做题时**都**完整地**发送给大模型的，作为 instructions 或 system message 的一部分，让模型在解题时可以参考这些积累的经验。这是 Training-Free GRPO 的核心机制 - 通过 **in-context learning** 而不是参数更新来提升性能。




