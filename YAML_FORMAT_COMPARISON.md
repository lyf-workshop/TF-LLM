# YAML 格式对比：单引号 vs 双引号 + 转义

## 📊 格式差异总结

### 格式 A：单引号 + 自然换行（转换前）

```yaml
instructions: 'You are an expert Wordle player.

  CRITICAL: First read "Word length: X" and always match that length.
  
  Feedback Meaning:
  - GREEN = correct letter, correct position (lock it)'
```

**特点**：
- 单引号：`'...'`
- 自然空行（真实的空行）
- 不需要转义
- 文件行数多（包含空行）
- **易于人类阅读和编辑**

---

### 格式 B：双引号 + 转义符（转换后）

```yaml
instructions: "You are an expert Wordle player.\n\nCRITICAL: First read \"Word length:\
  \ X\" and always match that length.\n\nFeedback Meaning:\n- GREEN = correct letter,\
  \ correct position (lock it)"
```

**特点**：
- 双引号：`"..."`
- 使用 `\n` 表示换行
- 使用 `\` 行继续符
- 使用 `\ ` 保留空格
- 文件更紧凑
- **适合程序生成和处理**

---

## 🔑 关键转义符号

### 1. `\` - 行继续符

**含义**：当前行在下一行继续（物理换行，但逻辑不换行）

```yaml
# 示例
text: "Hello\
  \ world"

# 解析结果：
"Hello world"  # 中间有一个空格，无换行
```

### 2. `\n` - 显式换行

**含义**：插入一个换行符（逻辑换行）

```yaml
# 示例
text: "Line 1\nLine 2\n\nLine 4"

# 解析结果：
Line 1
Line 2

Line 4
```

### 3. `\ ` - 保留前导空格

**含义**：在行继续时保留空格

```yaml
# 示例 1（有空格）
text: "Word\
  \ continuation"
# 结果: "Word continuation"

# 示例 2（无空格）
text: "Word\
  continuation"
# 结果: "Wordcontinuation"
```

### 4. `\"` - 转义引号

**含义**：在双引号字符串中使用字面双引号

```yaml
# 示例
text: "Check \"Word length: X\" here"

# 解析结果：
Check "Word length: X" here
```

---

## 📋 转换规则详解

### 规则 1：引号类型

```yaml
# 转换前
instructions: 'Text...'

# 转换后
instructions: "Text..."
```

### 规则 2：空行处理

```yaml
# 转换前（真实空行）
instructions: 'Line 1

  Line 2'

# 转换后（\n\n）
instructions: "Line 1\n\nLine 2"
```

### 规则 3：长行续行

```yaml
# 转换前（YAML 自动续行）
instructions: 'Very long text that wraps
  to next line automatically'

# 转换后（显式 \）
instructions: "Very long text that wraps\
  \ to next line automatically"
```

### 规则 4：缩进保留

```yaml
# 转换前（4 空格缩进）
instructions: 'Text
    indented by 4 spaces'

# 转换后（保留空格）
instructions: "Text\n    indented by 4 spaces"
```

---

## ✅ 验证结果

### 转换后的文件

**文件**：`configs/agents/practice/wordle_practice_20_l4_2_agent.yaml`

**验证**：
- ✅ YAML 格式有效
- ✅ Instructions 长度：7179 字符
- ✅ 换行符数量：61 个
- ✅ 配置可正常加载
- ✅ Lint 检查通过

---

## 🎯 何时使用哪种格式？

### 使用单引号 + 自然换行（格式 A）

**适用场景**：
- ✅ 手动编写配置
- ✅ 需要频繁修改
- ✅ 优先考虑可读性
- ✅ 简单文本（少特殊字符）

**示例**：初始 agent 配置

### 使用双引号 + 转义（格式 B）

**适用场景**：
- ✅ 程序自动生成
- ✅ 需要精确控制格式
- ✅ 包含特殊字符（如引号、emoji）
- ✅ 需要紧凑格式

**示例**：训练后保存的 agent 配置（包含经验）

---

## 📚 YAML 最佳实践

### 1. 简单文本：使用字面块

```yaml
# 推荐（最清晰）
instructions: |
  Line 1
  Line 2
  
  Line 4
```

### 2. 复杂格式：使用双引号 + 转义

```yaml
# 推荐（最精确）
instructions: "Line 1\n\nLine 2 with \"quotes\"\
  \ and emoji \U0001F3AF"
```

### 3. 避免：混合格式

```yaml
# 不推荐
instructions: 'Line 1\nLine 2'  # 单引号不支持 \n
```

---

## 🎉 总结

### 转换完成

- ✅ 格式已统一为**双引号 + 转义符**格式
- ✅ 与 `wordle_practice_20_l4_agent.yaml` 格式一致
- ✅ 所有经验内容完整保留
- ✅ YAML 解析正确

### 关键差异

| 特性 | 格式 A（转换前） | 格式 B（转换后） |
|------|----------------|----------------|
| **引号** | 单引号 `'...'` | 双引号 `"..."` |
| **换行** | 自然空行 | `\n` |
| **续行** | 自动 | `\` |
| **空格** | 自动 | `\ ` |
| **可读性** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **紧凑性** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **精确性** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**推荐**：
- 手动编辑：使用格式 A
- 程序生成：使用格式 B

---

**转换完成时间**：2026-01-22  
**验证状态**：✅ 通过
