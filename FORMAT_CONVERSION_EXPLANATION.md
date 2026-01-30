# YAML 格式转换说明

## 🎯 转换目标

将 `wordle_practice_20_l4_2_agent.yaml` 的格式统一为 `wordle_practice_20_l4_agent.yaml` 的格式。

---

## 📊 格式差异对比

### 格式 A（转换前）- 自然多行格式

```yaml
agent:
  name: wordle_agent
  instructions: 'You are an expert Wordle player. Guess the hidden word within 10
    attempts using feedback.


    CRITICAL: First read "Word length: X" and always match that length.

    Feedback Meaning:

    - GREEN = correct letter, correct position (lock it)
    ...'
```

**特点**：
- ✅ 单引号包裹：`'...'`
- ✅ 保留自然换行（空行）
- ❌ 没有转义符
- ❌ 文件较大（更多空行）

---

### 格式 B（转换后）- 紧凑转义格式

```yaml
agent:
  name: wordle_agent
  instructions: "You are an expert Wordle player. Guess the hidden word within 10\
    \ attempts using feedback.\n\nCRITICAL: First read \"Word length: X\" and always\
    \ match that length.\n\nFeedback Meaning:\n- GREEN = correct letter, correct position\
    \ (lock it)\n..."
```

**特点**：
- ✅ 双引号包裹：`"..."`
- ✅ 使用 `\n` 表示换行
- ✅ 使用 `\` 行继续符（在行尾）
- ✅ 使用 `\ ` 保留前导空格
- ✅ 文件更紧凑

---

## 🔧 关键转义符号

### 1. `\` - 行继续符

**作用**：表示当前行在下一行继续（不换行）

```yaml
# 在 YAML 中，这两种写法等价：

# 方式 A（不使用 \）
text: "Hello
  world"
# 结果: "Hello world" (中间有换行)

# 方式 B（使用 \）
text: "Hello\
  \ world"
# 结果: "Hello world" (中间无换行，连续)
```

### 2. `\ ` - 保留空格

**作用**：在行继续时保留前导空格

```yaml
instructions: "Line 1\
  \ Line 2"
# 结果: "Line 1 Line 2" (中间有一个空格)

instructions: "Line 1\
  Line 2"
# 结果: "Line 1Line 2" (中间没有空格)
```

### 3. `\n` - 显式换行

**作用**：插入一个换行符

```yaml
instructions: "Paragraph 1\n\nParagraph 2"
# 结果:
# Paragraph 1
# 
# Paragraph 2
# (两段之间有一个空行)
```

### 4. `\"` - 转义引号

**作用**：在双引号字符串中插入字面的双引号

```yaml
instructions: "Check \"Word length: X\" in the prompt"
# 结果: Check "Word length: X" in the prompt
```

---

## 📋 转换规则

### 规则 1：引号类型

```yaml
# 转换前（单引号）
instructions: 'Text here'

# 转换后（双引号）
instructions: "Text here"
```

### 规则 2：空行 → `\n\n`

```yaml
# 转换前（自然空行）
instructions: 'Line 1

  Line 2'

# 转换后（显式换行）
instructions: "Line 1\n\nLine 2"
```

### 规则 3：续行 → `\`

```yaml
# 转换前（YAML 自动续行）
instructions: 'Very long text that
  continues on next line'

# 转换后（显式续行符）
instructions: "Very long text that\
  \ continues on next line"
```

### 规则 4：保留缩进 → `\ `

```yaml
# 转换前（4 空格缩进）
instructions: 'Text
    indented text'

# 转换后（显式空格）
instructions: "Text\n    indented text"
# 或
instructions: "Text\
  \  indented text"  # \ 后面跟空格
```

---

## 🎯 为什么要用格式 B？

### 优点

1. ✅ **紧凑性**：减少文件大小（少空行）
2. ✅ **显式性**：明确显示换行和空格
3. ✅ **兼容性**：更好的跨平台一致性
4. ✅ **可控性**：精确控制格式细节

### 缺点

1. ❌ **可读性**：不如自然格式直观
2. ❌ **编辑难度**：手动编辑较困难
3. ❌ **调试难度**：需要理解转义规则

---

## 🧪 验证转换正确性

### 测试 1：加载配置文件

```bash
# 加载转换后的配置
uv run python -c "
from utu.utils import FileUtils
config = FileUtils.load_agent_config('practice/wordle_practice_20_l4_2_agent.yaml')
print('✅ 配置加载成功')
print(f'Instructions 长度: {len(config.agent.instructions)}')
"
```

### 测试 2：检查换行符

```bash
# 检查换行符是否正确
uv run python -c "
from utu.utils import FileUtils
config = FileUtils.load_agent_config('practice/wordle_practice_20_l4_2_agent.yaml')
lines = config.agent.instructions.split('\n')
print(f'总行数: {len(lines)}')
print(f'空行数: {sum(1 for line in lines if not line.strip())}')
"
```

---

## 📚 YAML 字符串格式完整指南

### 1. 字面块（Literal Block）`|`

```yaml
text: |
  Line 1
  Line 2
  
  Line 4
# 保留所有换行和空行
```

### 2. 折叠块（Folded Block）`>`

```yaml
text: >
  This is a very
  long paragraph
  that will be folded.
# 折叠为单行（除非有空行）
```

### 3. 单引号字符串

```yaml
text: 'Simple text
  continues here'
# 自动续行，不需要转义
```

### 4. 双引号字符串（推荐用于复杂格式）

```yaml
text: "Complex text\n\
  with explicit\n\
  control"
# 需要转义，但更精确
```

---

## 🎉 转换完成总结

### 已完成

1. ✅ **单引号 → 双引号**
2. ✅ **空行 → `\n\n`**
3. ✅ **续行 → `\` + `\ `**
4. ✅ **保留所有经验内容**
5. ✅ **Lint 检查通过**

### 效果

- ✅ 格式与 `wordle_practice_20_l4_agent.yaml` 一致
- ✅ 配置可正常加载
- ✅ 经验内容完整保留
- ✅ 文件更紧凑

---

**转换完成时间**：2026-01-22  
**转换文件**：`configs/agents/practice/wordle_practice_20_l4_2_agent.yaml`  
**参考文件**：`configs/agents/practice/wordle_practice_20_l4_agent.yaml`  
**状态**：✅ 完成
