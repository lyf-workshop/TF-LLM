# 两个经验库对比分析

## 配置文件对比

### 文件 1: `zebralogic_grpo_hard20_3epochs_agent.yaml`
- 来源：可能是使用 `logic_with_error_analysis.py` (V1) 生成的
- 经验数量：5个 (G0-G4)

### 文件 2: `logic_practice_zebralogic_optimized_normalverify_agent.yaml`
- 来源：可能是使用基本验证器 (`logic.py`) 生成的
- 经验数量：5个 (G0-G4)

---

## 详细对比

### G0: 约束处理策略

#### 文件1: Constraint Prioritization
```
[G0]. Constraint prioritization: When solving logic puzzles with spatial 
and relational constraints, prioritize applying ordering clues simultaneously 
with equivalence grouping early in the reasoning process to reduce solution 
space proactively and minimize backtracking.
```

**特点**:
- ✅ 强调"早期应用"（early in the reasoning process）
- ✅ 同时处理排序线索和等价分组
- ✅ 目标明确：减少解空间，最小化回溯
- ⚠️ 稍微抽象，但可操作

#### 文件2: Constraint Propagation
```
[G0]. Constraint propagation: Maintain dynamic possibility tables that track 
all remaining valid attributes per house, updating and propagating constraints 
simultaneously across all categories after each assignment to enable immediate 
validation, early pruning, and prevent cascading errors.
```

**特点**:
- ✅ **更具体**：明确提到"possibility tables"（可能性表）
- ✅ **更可操作**：具体说明如何维护和更新
- ✅ **更系统化**：强调"after each assignment"（每次赋值后）
- ✅ **更全面**：涵盖验证、剪枝、错误预防

**对比**:
- 文件2 **更优**：更具体、更可操作、更系统化

---

### G1: 等价/分组策略

#### 文件1: Equivalence Grouping
```
[G1]. Equivalence grouping: Systematically create composite attribute blocks 
by chaining equivalent clues across categories to minimize variables, enable 
efficient constraint propagation, and reduce cognitive load while validating 
against all constraints.
```

**特点**:
- ✅ 强调"系统化创建"（Systematically create）
- ✅ 跨类别链接等价线索
- ✅ 目标：最小化变量、减少认知负担
- ⚠️ "composite attribute blocks"概念较抽象

#### 文件2: Incremental Validation
```
[G1]. Incremental validation: Perform immediate cross-category consistency 
checks after each assignment using dynamic possibility tracking to detect 
uniqueness violations and constraint satisfiability across all attributes, 
preventing error propagation and deep backtracking.
```

**特点**:
- ✅ **更实用**：强调"immediate"（立即）和"after each assignment"（每次赋值后）
- ✅ **更具体**：明确说明检查什么（uniqueness violations, constraint satisfiability）
- ✅ **更防错**：明确提到"preventing error propagation"（防止错误传播）
- ✅ **更系统化**：使用"dynamic possibility tracking"（动态可能性跟踪）

**对比**:
- 文件2 **更优**：更注重实际执行和错误预防

---

### G2: 约束整合/传递推理

#### 文件1: Attribute and Constraint Integration
```
[G2]. Attribute and constraint integration: Maintain a dynamic constraint map 
that combines transitive attribute chains with constraint propagation, validating 
uniqueness and all related constraints immediately after each assignment to detect 
contradictions early and minimize backtracking.
```

**特点**:
- ✅ 维护"dynamic constraint map"（动态约束映射）
- ✅ 结合传递属性链和约束传播
- ✅ 立即验证唯一性和相关约束
- ✅ 早期检测矛盾

#### 文件2: Transitive Reasoning
```
[G2]. Transitive reasoning: Bundle strongly-linked attribute relationships into 
composite entities and propagate transitive constraint chains before hypothesis 
testing to reduce combinatorial complexity and maintain constraint coherence.
```

**特点**:
- ✅ 强调"before hypothesis testing"（假设测试前）
- ✅ 减少组合复杂度
- ✅ 维护约束一致性
- ⚠️ 稍微抽象

**对比**:
- **平手**：文件1更注重验证，文件2更注重传递推理
- 文件1在**错误预防**方面更优（立即验证）

---

### G3: 空间约束/唯一性验证

#### 文件1: Spatial Constraint Priority
```
[G3]. Spatial constraint priority: Prioritize constraints that combine spatial 
relationships with fixed identities early in reasoning to prune invalid branches 
before deep analysis, applying deductions immediately to maximize solution space 
reduction.
```

**特点**:
- ✅ 针对空间约束（spatial relationships）
- ✅ 早期剪枝无效分支
- ✅ 立即应用推理
- ✅ 最大化解空间减少

#### 文件2: Uniqueness Verification
```
[G3]. Uniqueness verification: Perform incremental uniqueness checks after each 
assignment to detect constraint violations early, minimizing backtracking and 
ensuring consistent reasoning paths.
```

**特点**:
- ✅ **更基础但重要**：唯一性验证是逻辑谜题的核心
- ✅ **更系统化**：每次赋值后检查
- ✅ **更防错**：早期检测约束违反
- ✅ **更可靠**：确保推理路径一致

**对比**:
- 文件2 **更优**：唯一性验证是更基础、更关键的技能
- 文件1的空间约束优先级是高级策略，但唯一性验证更重要

---

### G4: 回溯/假设测试

#### 文件1: Systematic Backtracking
```
[G4]. Systematic backtracking and constraint reevaluation: After any assignment, 
systematically re-validate all constraints to catch inconsistencies immediately 
and backtrack to the last decision point while re-evaluating dynamic constraints 
to prevent false contradictions.
```

**特点**:
- ✅ 系统化重新验证所有约束
- ✅ 立即捕获不一致
- ✅ 回溯到最后一个决策点
- ✅ 防止假矛盾
- ✅ **非常全面**

#### 文件2: Hypothesis Testing
```
[G4]. Hypothesis testing: Systematically explore variable reassignments within 
hypothesis frameworks before rejecting core assumptions, with immediate consistency 
checking after each assignment.
```

**特点**:
- ✅ 系统化探索变量重新赋值
- ✅ 在拒绝核心假设前测试
- ✅ 立即一致性检查
- ⚠️ 稍微抽象

**对比**:
- 文件1 **更优**：更全面、更注重错误预防（防止假矛盾）

---

## 综合评分

### 文件1: `zebralogic_grpo_hard20_3epochs_agent.yaml`

**优势**:
- ✅ G4 非常全面（系统化回溯和约束重新评估）
- ✅ G3 针对空间约束（高级策略）
- ✅ G2 强调立即验证

**劣势**:
- ⚠️ G0 和 G1 稍微抽象
- ⚠️ 缺少"可能性表"等具体工具
- ⚠️ 可能受V1误报影响（如果使用V1生成）

**总分**: 7.5/10

---

### 文件2: `logic_practice_zebralogic_optimized_normalverify_agent.yaml`

**优势**:
- ✅ **G0 非常具体**（可能性表、动态更新）
- ✅ **G1 非常实用**（增量验证、错误预防）
- ✅ **G3 基础且重要**（唯一性验证）
- ✅ **更可操作**：每个经验都有具体的执行步骤
- ✅ **更系统化**：强调"after each assignment"

**劣势**:
- ⚠️ G2 和 G4 稍微抽象
- ⚠️ 缺少空间约束优先级（高级策略）

**总分**: 8.5/10

---

## 详细对比表

| 维度 | 文件1 | 文件2 | 胜者 |
|------|-------|-------|------|
| **具体性** | 中等 | 高 | 文件2 |
| **可操作性** | 中等 | 高 | 文件2 |
| **系统化程度** | 高 | 高 | 平手 |
| **错误预防** | 高 | 非常高 | 文件2 |
| **基础技能覆盖** | 中等 | 高 | 文件2 |
| **高级策略** | 高 | 中等 | 文件1 |
| **完整性** | 高 | 高 | 平手 |

---

## 关键差异

### 1. 执行方式

**文件1**: 更注重策略和优先级
- "prioritize"（优先）
- "early in reasoning"（早期）
- "systematically"（系统化）

**文件2**: 更注重具体操作和时机
- "after each assignment"（每次赋值后）
- "immediate"（立即）
- "dynamic possibility tables"（动态可能性表）

### 2. 错误预防

**文件1**: 
- 防止假矛盾
- 早期检测矛盾
- 最小化回溯

**文件2**: 
- **更全面**：防止错误传播、防止深度回溯
- **更具体**：检测唯一性违反、约束可满足性
- **更系统化**：每次赋值后立即检查

### 3. 工具和方法

**文件1**: 
- 动态约束映射
- 复合属性块
- 空间约束优先级

**文件2**: 
- **可能性表**（更具体、更实用）
- 动态可能性跟踪
- 增量验证

---

## 结论

### 文件2 更好！

**原因**:

1. ✅ **更具体可操作**
   - 明确说明"after each assignment"（每次赋值后）
   - 提供具体工具（可能性表）
   - 更容易执行

2. ✅ **更注重错误预防**
   - 增量验证
   - 立即一致性检查
   - 防止错误传播

3. ✅ **更系统化**
   - 每个经验都有明确的执行时机
   - 强调"immediate"和"incremental"
   - 更符合逻辑推理的实际需求

4. ✅ **基础技能更扎实**
   - 唯一性验证（G3）是核心技能
   - 可能性表（G0）是实用工具
   - 增量验证（G1）是防错关键

5. ✅ **可能不受V1误报影响**
   - 如果使用基本验证器生成，可能更准确
   - 经验更聚焦于实际推理改进

---

## 建议

### 推荐使用文件2

**理由**:
- 更具体、更可操作
- 更注重错误预防
- 更系统化
- 基础技能更扎实

### 可以结合两者

**最佳实践**:
- 以文件2为基础（G0, G1, G3）
- 从文件1补充高级策略（G3的空间约束优先级，G4的系统化回溯）

**组合版本**:
```
[G0]. Constraint propagation: Maintain dynamic possibility tables... (文件2)
[G1]. Incremental validation: Perform immediate cross-category... (文件2)
[G2]. Attribute and constraint integration: Maintain a dynamic constraint map... (文件1)
[G3]. Uniqueness verification: Perform incremental uniqueness checks... (文件2)
[G4]. Systematic backtracking: After any assignment, systematically re-validate... (文件1)
```

---

## 验证方法

### 方法1: 查看训练效果

```bash
# 查看使用文件1的训练效果
python scripts/view_problem_details.py <exp_id_1> [1,2,3,4,5]

# 查看使用文件2的训练效果
python scripts/view_problem_details.py <exp_id_2> [1,2,3,4,5]

# 对比
python scripts/compare_training_changes.py <exp_id_1> <exp_id_2>
```

### 方法2: 分析推理质量

检查实际推理过程：
- 是否使用了可能性表？
- 是否在每次赋值后验证？
- 是否检测到唯一性违反？

---

## 总结

**文件2 (`logic_practice_zebralogic_optimized_normalverify_agent.yaml`) 更好！**

**关键优势**:
1. ✅ 更具体可操作（可能性表、增量验证）
2. ✅ 更注重错误预防（立即检查、防止传播）
3. ✅ 更系统化（明确的执行时机）
4. ✅ 基础技能更扎实（唯一性验证）

**建议**: 使用文件2，或结合两者的优势创建最佳版本。






































































