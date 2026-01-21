# ✅ KORGym数据集准备脚本修复

## 🔍 问题

原脚本生成的数据集名称是**固定的**，不匹配配置文件中的期望名称：

### ❌ **修复前**

```python
# 脚本生成（固定名称）
dataset="KORGym-Eval-50"
dataset="KORGym-Train-100"
```

### ✅ **配置文件期望**

| 游戏 | 评估数据集 | 训练数据集 |
|------|-----------|-----------|
| Word Puzzle | `KORGym-WordPuzzle-Eval-50` | `KORGym-WordPuzzle-Train-100` |
| Alphabetical Sorting | `KORGym-AlphabeticalSorting-Eval-50` | `KORGym-AlphabeticalSorting-Train-100` |
| Wordle | `KORGym-Wordle-Eval-50` | `KORGym-Wordle-Train-100` |

**结果**: 数据集名称不匹配，训练/评估无法找到数据集！

---

## ✅ 修复内容

### **1. 添加游戏名称转换函数**

```python
def game_name_to_dataset_name(game_name: str) -> str:
    """
    Convert KORGym game ID to dataset name format.
    
    Examples:
        "8-word_puzzle" -> "WordPuzzle"
        "22-alphabetical_sorting" -> "AlphabeticalSorting"
        "33-wordle" -> "Wordle"
    """
    # Remove number prefix (e.g., "8-", "22-", "33-")
    parts = game_name.split("-", 1)
    if len(parts) > 1:
        game_part = parts[1]
    else:
        game_part = parts[0]
    
    # Convert underscore-separated words to CamelCase
    words = game_part.split("_")
    camel_case = "".join(word.capitalize() for word in words)
    
    return camel_case
```

### **2. 动态生成数据集名称**

```python
# Generate dataset names based on game name
game_dataset_name = game_name_to_dataset_name(game_name)
eval_dataset_name = f"KORGym-{game_dataset_name}-Eval-{eval_count}"
train_dataset_name = f"KORGym-{game_dataset_name}-Train-{train_count}"
```

### **3. 使用动态名称创建数据集**

```python
# Evaluation dataset
sample = DatasetSample(
    dataset=eval_dataset_name,  # ✅ 动态名称
    ...
)

# Training dataset
sample = DatasetSample(
    dataset=train_dataset_name,  # ✅ 动态名称
    ...
)
```

---

## 📊 转换规则

| 游戏ID | 转换步骤 | 数据集名称组件 | 完整数据集名称 |
|--------|---------|--------------|--------------|
| `8-word_puzzle` | 去掉 `8-` → `word_puzzle` → 驼峰命名 | `WordPuzzle` | `KORGym-WordPuzzle-Eval-50` |
| `22-alphabetical_sorting` | 去掉 `22-` → `alphabetical_sorting` → 驼峰命名 | `AlphabeticalSorting` | `KORGym-AlphabeticalSorting-Eval-50` |
| `33-wordle` | 去掉 `33-` → `wordle` → 驼峰命名 | `Wordle` | `KORGym-Wordle-Eval-50` |

---

## 🚀 使用方法

### **Word Puzzle**

```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "8-word_puzzle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 150
```

**生成的数据集**:
- `KORGym-WordPuzzle-Eval-50`
- `KORGym-WordPuzzle-Train-100`

### **Alphabetical Sorting**

```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "22-alphabetical_sorting" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 150
```

**生成的数据集**:
- `KORGym-AlphabeticalSorting-Eval-50`
- `KORGym-AlphabeticalSorting-Train-100`

### **Wordle**

```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --eval_seeds_start 1 \
  --eval_seeds_end 50 \
  --train_seeds_start 51 \
  --train_seeds_end 150
```

**生成的数据集**:
- `KORGym-Wordle-Eval-50`
- `KORGym-Wordle-Train-100`

---

## ✅ 验证

### **1. 检查生成的数据集名称**

运行脚本后，日志会显示：

```
Creating KORGym datasets for game: 8-word_puzzle
  - Evaluation dataset: KORGym-WordPuzzle-Eval-50
    Samples: 50 (seeds 1-50)
  - Training dataset: KORGym-WordPuzzle-Train-100
    Samples: 100 (seeds 51-150)
```

### **2. 检查配置文件匹配**

```yaml
# configs/practice/word_puzzle_practice.yaml
data:
  practice_dataset_name: "KORGym-WordPuzzle-Train-100"  # ✅ 匹配

# configs/eval/korgym/word_puzzle_eval.yaml
data:
  dataset: "KORGym-WordPuzzle-Eval-50"  # ✅ 匹配
```

---

## 📝 完整示例

### **为三个游戏创建数据集**

```bash
# Word Puzzle
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"

# Alphabetical Sorting
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"

# Wordle
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
```

---

## 🎯 修复效果

### **之前（错误）**

```python
# 所有游戏都生成相同的名称
dataset="KORGym-Eval-50"      # ❌ 不匹配
dataset="KORGym-Train-100"    # ❌ 不匹配
```

### **之后（正确）**

```python
# 根据游戏动态生成
"8-word_puzzle" → "KORGym-WordPuzzle-Eval-50"      # ✅ 匹配
"22-alphabetical_sorting" → "KORGym-AlphabeticalSorting-Eval-50"  # ✅ 匹配
"33-wordle" → "KORGym-Wordle-Eval-50"              # ✅ 匹配
```

---

## ✅ 检查清单

修复后确认：

- [x] 添加了 `game_name_to_dataset_name()` 函数
- [x] 数据集名称根据游戏动态生成
- [x] 生成的名称与配置文件匹配
- [x] 支持所有三个游戏
- [x] 日志输出清晰显示数据集名称

---

## 🚀 下一步

1. **运行脚本为每个游戏创建数据集**
2. **验证数据集名称与配置文件匹配**
3. **开始训练和评估**

**现在脚本生成的数据集名称与配置文件完全匹配了！** 🎉

---

**创建时间**: 2026-01-16  
**修复内容**: 动态生成数据集名称，匹配配置文件  
**影响范围**: 所有KORGym游戏的数据集准备























