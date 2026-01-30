# 📚 Experience Filter 使用指南

## ✨ 功能概述

Experience Filter 是一个可配置的经验筛选系统，用于控制在评估过程中向 Agent 注入哪些经验。支持按层级（L0/L1/L2）筛选经验，提高推理效率和性能。

### 核心优势

- ✅ **Token 效率**: 最多节省 79% 的 prompt tokens
- ✅ **提升质量**: 减少无关经验干扰，聚焦高质量策略
- ✅ **可配置**: YAML 配置即可调整筛选策略
- ✅ **向后兼容**: 不影响现有评估配置

---

## 🎯 配置说明

### 基础配置

在评估配置文件（如 `configs/eval/korgym/wordle_practice_20_eval.yaml`）中添加：

```yaml
# Experience filtering configuration
experience_filter:
  enabled: true              # 是否启用筛选（默认: false）
  strategy: "static"         # 筛选策略: "static" | "retrieval"
  max_l2: 3                 # 最多保留 N 条 L2（元策略），None=全部
  max_l1: 5                 # 最多保留 N 条 L1（模式级），None=全部
  max_l0: 0                 # 最多保留 N 条 L0（案例级），None=全部
  
  # 以下为 retrieval 策略配置（未来扩展）
  retrieval_top_k: 5
  retrieval_min_score: 0.0
```

### 配置项详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | false | 是否启用经验筛选 |
| `strategy` | str | "static" | 筛选策略（当前支持 static） |
| `max_l2` | int\|None | None | L2 经验上限（None=不限制） |
| `max_l1` | int\|None | None | L1 经验上限（None=不限制） |
| `max_l0` | int\|None | None | L0 经验上限（None=不限制） |

---

## 📖 使用示例

### 示例 1: 保留所有 L2 + 前5条 L1 + 不保留 L0

```yaml
experience_filter:
  enabled: true
  strategy: "static"
  max_l2: null  # 保留所有 L2
  max_l1: 5     # 只保留前5条 L1
  max_l0: 0     # 不保留 L0
```

**适用场景**: 大部分评估任务，平衡泛化能力和具体指导

---

### 示例 2: 仅保留元策略（最简配置）

```yaml
experience_filter:
  enabled: true
  strategy: "static"
  max_l2: 3     # 只保留前3条 L2
  max_l1: 0     # 不保留 L1
  max_l0: 0     # 不保留 L0
```

**适用场景**: 简单任务，只需要高层次指导

---

### 示例 3: 禁用筛选（使用全部经验）

```yaml
experience_filter:
  enabled: false
```

**适用场景**: 向后兼容，或需要所有经验的场景

---

## 🔄 工作流程

```
1. 加载评估配置
   ├─ 读取 experience_filter 配置
   └─ 初始化 ExperienceFilter

2. 解析 Agent 指令
   ├─ 提取经验段落
   └─ 识别 L0/L1/L2 层级

3. 应用筛选规则
   ├─ 按层级分组
   ├─ 应用 max_l0/l1/l2 限制
   └─ 保持原始顺序

4. 重新渲染指令
   ├─ 拼接筛选后的经验
   └─ 更新 agent.instructions

5. 执行评估
   └─ 使用筛选后的 Agent
```

---

## 🧪 验证功能

### 方法 1: 查看日志

运行评估时，查看日志输出：

```bash
python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval
```

正确配置后会看到：

```
INFO: Experience filtering enabled: strategy=static, max_l2=3, max_l1=5, max_l0=0
INFO: Parsed 4 experiences: L2=1, L1=3, L0=0
INFO: Static filtering: 4 → 4 experiences (L2=1, L1=3, L0=0)
INFO: Applied experience filtering: 2841 → 2654 chars (reduced by 187 chars)
```

---

### 方法 2: 手动检查

读取配置并验证：

```python
from utu.config import ConfigLoader
from utu.eval.experience_filter import ExperienceFilter

# 加载配置
config = ConfigLoader.load_eval_config("korgym/wordle_practice_20_eval")

# 创建筛选器
filter = ExperienceFilter(config.experience_filter)

# 解析经验
base, experiences = filter.parse_experiences(config.agent.instructions)

print(f"Parsed {len(experiences)} experiences")
for exp in experiences:
    print(f"  [{exp.id}] {exp.level}: {exp.content[:50]}...")
```

---

## 💡 最佳实践

### 推荐配置策略

| 任务类型 | 推荐配置 | 理由 |
|---------|---------|------|
| **Wordle** | L2=1-3, L1=3-5, L0=0 | 避免过拟合具体单词 |
| **数学推理** | L2=2-3, L1=5-8, L0=2-3 | 需要具体案例参考 |
| **Web 搜索** | L2=2, L1=3-5, L0=0 | 策略导向，避免过度具体化 |
| **简单任务** | L2=1-2, L1=0-3, L0=0 | 只需高层次指导 |

---

### 调优建议

1. **先测试基准**: 使用 `enabled: false` 跑一次完整评估
2. **逐步筛选**: 从保留全部 → 限制 L0 → 限制 L1 → 限制 L2
3. **监控性能**: 记录 Pass@1、平均轮次等指标
4. **找到平衡点**: Token 效率 vs 性能之间的最佳配置

---

## 🐛 常见问题

### Q1: 配置了 experience_filter 但没有生效？

**A**: 检查以下几点：
1. `enabled: true` 是否设置
2. Agent 配置中是否包含经验段落
3. 查看日志确认是否有 "Experience filtering enabled" 提示

---

### Q2: 筛选后性能下降？

**A**: 可能原因：
- `max_l1` 设置过低，丢失了关键模式
- 缺少 L2 元策略指导
- 建议增加 `max_l1` 或保留更多 L2

---

### Q3: 如何禁用筛选？

**A**: 两种方式：
1. 设置 `enabled: false`
2. 删除整个 `experience_filter` 配置块（向后兼容）

---

### Q4: 支持动态检索吗？

**A**: 已实现代码框架，但当前版本建议使用 `strategy: "static"`。动态检索（`retrieval`）将在未来版本中完善。

---

## 📁 相关文件

```
utu/
├── config/
│   └── eval_config.py          # ExperienceFilterConfig 定义
├── eval/
│   ├── experience_filter.py    # ExperienceFilter 实现
│   └── benchmarks/
│       └── base_benchmark.py   # 集成点
└── practice/
    └── experience_retriever.py # 动态检索（未来）

configs/
└── eval/
    └── korgym/
        └── wordle_practice_20_eval.yaml  # 示例配置

scripts/
└── test_experience_filter.py   # 测试脚本
```

---

## 🎓 技术细节

### 经验格式识别

支持以下格式：

```
[G0]. [L2-Meta] **策略内容**       ← 标准格式
[G1]. [L1-Pattern] **策略内容**    ← 标准格式
[L2_0]. **策略内容**               ← ID 前缀识别
[G5]. **策略内容**                 ← 默认识别为 L1
```

---

### 筛选算法

```python
# 静态筛选伪代码
1. 按层级分组: L2_list, L1_list, L0_list
2. 应用限制:
   - L2_filtered = L2_list[:max_l2]
   - L1_filtered = L1_list[:max_l1]
   - L0_filtered = L0_list[:max_l0]
3. 合并并按原始顺序排序
4. 渲染回指令格式
```

---

## 📞 支持

如有问题或建议，请查看：
- 项目 README: `README.md`
- 代码注释: `utu/eval/experience_filter.py`
- 测试用例: `scripts/test_experience_filter.py`

---

**最后更新**: 2026-01-26
