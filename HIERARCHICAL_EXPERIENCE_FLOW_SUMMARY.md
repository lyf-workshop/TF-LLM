# 分层经验生成流程 - 快速总结

## 🎯 核心问题

### 1. 分层经验在哪个阶段得到？

✅ **在 Training-Free GRPO 训练阶段，每个 epoch 的经验更新后**

```
训练流程：
┌──────────────┐
│ Rollout      │ 生成候选答案
└──────┬───────┘
       ↓
┌──────────────┐
│ Experience   │ 提取传统经验
│ Update       │ {G0: "...", G1: "...", ...}
└──────┬───────┘
       ↓
┌──────────────┐ ⭐ 这里！
│ Hierarchical │ L0 → L1 → L2
│ Processing   │ 分层抽象
└──────┬───────┘
       ↓
┌──────────────┐
│ Save         │ 保存到 JSON
└──────────────┘
```

### 2. 通过什么总结出来的？

✅ **通过 LLM 的多层抽象（L0 转换 → L1 抽象 → L2 提炼）**

---

## 📊 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│ L2 - 元策略级 (Meta-Strategy)                                │
│                                                             │
│ "Principle: 在搜索空间不确定时，优先投资于信息获取          │
│ 和结构化表示..."                                             │
│                                                             │
│ 输入: 3个L1 + 约15个源L0                                     │
│ 方法: LLM提炼跨任务原则                                      │
└─────────────────────────────────────────────────────────────┘
                          ↑ 每3个L1聚合
┌─────────────────────────────────────────────────────────────┐
│ L1 - 模式级 (Pattern-Level)                                 │
│                                                             │
│ "使用高熵起始词（crane, soare）最大化第一轮信息增益"        │
│                                                             │
│ 输入: 5个L0                                                 │
│ 方法: LLM抽象通用策略                                        │
└─────────────────────────────────────────────────────────────┘
                          ↑ 每5个L0聚合
┌─────────────────────────────────────────────────────────────┐
│ L0 - 案例级 (Case-Specific)                                 │
│                                                             │
│ "第一次猜测用 crane 覆盖常见元音和辅音"                     │
│                                                             │
│ 输入: 传统经验（从rollout中提取）                            │
│ 方法: 直接转换 + 谨慎去重                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 详细生成逻辑

### L0 生成（转换 + 去重）

**输入**：传统经验 `{G0: "...", G1: "...", G2: "..."}`

**处理**：
```python
for exp_id, content in step_experiences.items():
    # 1. 提取 scope（游戏名称/任务标识）
    scope_key = self._extract_scope_key(content)
    # 例如: "33-wordle"
    
    # 2. 谨慎去重
    if self._is_too_similar_to_recent_l0(content, scope_key, threshold=0.95):
        continue  # 跳过几乎完全相同的经验
    
    # 3. 创建 L0
    l0_exp = {
        'id': f"L0_{len(self.l0_experiences)}",
        'content': content,
        'scope_key': scope_key,
        'step': step
    }
    self.l0_experiences.append(l0_exp)
```

**去重规则**：
- ✅ 同一 scope 内才去重
- ✅ 高阈值 0.95（Jaccard 相似度）
- ✅ 无 scope 时不去重

---

### L1 生成（LLM 抽象）

**触发**：`未聚合的 L0 数量 >= 5`

**输入**：5 个 L0 案例

**LLM Prompt**：
```
System: 从多个具体案例中提取通用策略模式

User:
L0_0: "第一次用 crane 覆盖常见字母"
L0_1: "起始词用 soare 测试高频元音"
L0_2: "开局选择 audio 包含多个元音"
L0_3: "首次猜测 stare 平衡元音辅音"
L0_4: "使用 arise 最大化信息量"

提取一个通用的 L1 策略。
```

**LLM 输出**：
```
"使用预定义的高熵起始词（crane, soare, audio, stare, arise）
来最大化第一轮信息增益，快速缩小解空间。"
```

**保存**：
```python
l1_exp = {
    'id': 'L1_0',
    'content': "使用预定义的高熵起始词...",
    'source_l0_ids': ['L0_0', 'L0_1', 'L0_2', 'L0_3', 'L0_4'],
    'step': 1
}
```

---

### L2 生成（LLM 提炼 + 源 L0）

**触发**：`未聚合的 L1 数量 >= 3`

**输入**：
- 3 个 L1 模式
- 约 15 个源 L0（3×5）

**LLM Prompt**：
```
System: 从多个模式和源案例中提炼跨任务元策略

User:
【L1 模式】:
L1_0: "使用高熵起始词最大化信息增益"
L1_1: "根据颜色反馈系统性缩小搜索空间"
L1_2: "构建约束列表排除不可能的组合"

【源 L0 案例】（15 个）:
L0_0: "第一次用 crane..."
L0_1: "起始词用 soare..."
...
L0_14: "排除包含灰色字母的候选词..."

提取一个跨任务的 L2 元策略原则。
```

**LLM 输出**：
```
"Principle: 在搜索空间不确定的问题中，优先投资于信息获取
和结构化表示。早期的结构投资（高熵探索、约束建模）能够
指数级降低后续搜索成本，将问题从试错驱动转化为约束驱动
的系统推理。"
```

**关键设计**：
- ✅ **基于 L1 + 源 L0 双重输入**（不是只基于 L1）
- ✅ 避免过度抽象，保持实用性
- ✅ 源 L0 提供具体上下文

---

## 🔄 调用时序

### 完整时序图

```
training_free_grpo.py (主流程)
│
├─ Epoch 1
│   ├─ rollout_manager.rollout_epoch()
│   │   └─ 生成 60 个 rollout 结果
│   │
│   ├─ experience_updater.run()
│   │   └─ 提取 10 个传统经验 {G0-G9}
│   │
│   └─ hierarchical_experience_manager.process_step_experiences()
│       ├─ [3.1] 转换为 L0（10个）
│       ├─ [3.2] _try_generate_l1()
│       │   ├─ 检查: 未聚合 L0 >= 5? ✅
│       │   └─ 生成 L1_0, L1_1
│       ├─ [3.3] _try_generate_l2()
│       │   ├─ 检查: 未聚合 L1 >= 3? ❌
│       │   └─ 等待...
│       └─ save_experiences()
│
├─ Epoch 2
│   ├─ rollout_epoch() → 60 个 rollout
│   ├─ experience_updater.run() → 10 个经验 {G10-G19}
│   └─ process_step_experiences()
│       ├─ 转换为 L0（+10个，总计20）
│       ├─ _try_generate_l1()
│       │   └─ 生成 L1_2, L1_3（总计4个）
│       └─ _try_generate_l2()
│           ├─ 检查: 未聚合 L1 >= 3? ✅
│           └─ 生成 L2_0
│
└─ Epoch 3
    ├─ rollout_epoch() → 60 个 rollout
    ├─ experience_updater.run() → 10 个经验 {G20-G29}
    └─ process_step_experiences()
        ├─ 转换为 L0（+10个，总计30）
        ├─ _try_generate_l1() → L1_4, L1_5（总计6个）
        └─ _try_generate_l2() → L2_1（总计2个）

最终结果:
- L0: 30 个
- L1: 6 个
- L2: 2 个
```

---

## 💡 关键设计点

### 1. **增量生成**

- ✅ 每个 epoch 后自动检查是否满足聚合条件
- ✅ 满足条件立即生成，无需等待训练结束
- ✅ 允许在训练中期就开始使用 L1/L2 经验

### 2. **L2 双重输入**

- ✅ 传统方法：`L2 = LLM(L1_batch)` → 过度抽象
- ✅ 本系统：`L2 = LLM(L1_batch + source_L0)` → 保持实用性

### 3. **谨慎去重**

- ✅ L0 去重：同 scope + Jaccard >= 0.95
- ✅ 避免跨任务误杀
- ✅ 保留经验的多样性

### 4. **自动聚合**

```python
# 配置示例
l1_aggregation_threshold: 5  # 5 个 L0 → 1 个 L1
l2_aggregation_threshold: 3  # 3 个 L1 → 1 个 L2

# 如果 20 个问题，每个生成 1 个 L0:
# Epoch 1: 10 个 L0 → 生成 2 个 L1
# Epoch 2: 20 个 L0 → 生成 4 个 L1 → 生成 1 个 L2
# Epoch 3: 30 个 L0 → 生成 6 个 L1 → 生成 2 个 L2
```

---

## 🧪 验证方法

### 查看生成的经验

```bash
# 运行训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice_20

# 查看生成的分层经验
cat workspace/hierarchical_experiences/wordle_practice_20.json

# 或者用 Python 脚本
uv run python -c "
import json
with open('workspace/hierarchical_experiences/wordle_practice_20.json') as f:
    data = json.load(f)
print(f'L0: {len(data[\"l0_experiences\"])}')
print(f'L1: {len(data[\"l1_experiences\"])}')
print(f'L2: {len(data[\"l2_experiences\"])}')
"
```

### 查看训练日志

```bash
# 查看日志中的分层经验生成信息
grep -i "hierarchical\|L0\|L1\|L2" [训练日志文件]

# 预期输出：
# Processing hierarchical experiences for step 1...
# Added 10 L0 experiences from step 1
# Generating L1 from 10 L0 experiences...
# Generated L1_0
# Generated L1_1
# Hierarchical processing complete. L0=10, L1=2, L2=0
```

---

## 📚 相关文档

- **详细流程**：`docs/HIERARCHICAL_EXPERIENCE_GENERATION_FLOW.md`
- **配置指南**：`分层经验学习-完整运行指南.md`
- **核心代码**：`utu/practice/hierarchical_experience_manager.py`

---

## 🎉 总结

### 回答你的问题

#### Q1: 分层经验在哪个阶段得到？

**A**: ✅ **在训练阶段，每个 epoch 的经验更新后**

```
具体位置：training_free_grpo.py (Line 222-234)

await self.hierarchical_experience_manager.process_step_experiences(
    step_experiences=new_experiences,  # 传统经验
    step=step,                         # 当前 epoch
    problem_count=problem_count        # 问题数量
)
```

#### Q2: 通过什么总结出来的？

**A**: ✅ **通过 LLM 的分层抽象**

| 层级 | 输入 | 方法 | LLM 调用 |
|------|------|------|---------|
| **L0** | 传统经验 | 直接转换 + 去重 | ❌ 不需要 |
| **L1** | 5个L0 | LLM 抽象模式 | ✅ 需要 |
| **L2** | 3个L1 + 源L0 | LLM 提炼原则 | ✅ 需要 |

**Prompt 模板**：`configs/prompts/hierarchical_critique.yaml`

---

**文档创建时间**：2026-01-22
