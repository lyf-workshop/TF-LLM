# Word Puzzle 评估0%准确率诊断指南

## 当前状态

```
准确率: 0.00%
Level配置: 训练=3, 评估=3 ✓一致
```

## 诊断步骤

### 1. 检查数据集是否存在

在WSL中运行：
```bash
cd /mnt/f/youtu-agent

# 检查数据集
uv run python -c "
from utu.utils import SQLModelUtils
from utu.db import DatasetSample
from sqlmodel import select, func

with SQLModelUtils.create_session() as session:
    count = session.exec(
        select(func.count()).select_from(DatasetSample).where(
            DatasetSample.dataset == 'KORGym-WordPuzzle-Eval-50'
        )
    ).one()
    print(f'数据集样本数: {count}')
    
    if count == 0:
        print('❌ 数据集不存在，需要创建！')
    else:
        # 查看第一个样本
        sample = session.exec(
            select(DatasetSample).where(
                DatasetSample.dataset == 'KORGym-WordPuzzle-Eval-50'
            ).limit(1)
        ).first()
        print(f'样本meta: {sample.meta}')
        print(f'样本问题: {sample.question}')
"
```

### 2. 如果数据集不存在，创建它

```bash
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
```

### 3. 检查游戏服务器

```bash
# 测试游戏服务器
curl http://localhost:8775/docs

# 如果失败，启动服务器
cd /mnt/f/youtu-agent/KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

### 4. 查看评估样本详情

```bash
uv run python scripts/simple_debug.py
```

### 5. 重新运行评估

```bash
# 确保游戏服务器运行后
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
```

## 常见问题

### 问题1: 数据集名称不匹配

症状: 找不到数据集
解决: 
- 检查配置中的 `dataset: "KORGym-WordPuzzle-Eval-50"`
- 确保数据集已用正确名称创建

### 问题2: 游戏服务器未运行

症状: preprocess阶段就失败
解决: 启动游戏服务器在8775端口

### 问题3: Level不匹配

症状: 准确率异常低
解决: 确保训练和评估使用相同level

### 问题4: Agent响应格式错误

症状: 有响应但reward=0
解决: 检查Agent是否正确输出答案格式

## 快速诊断命令

一键检查所有配置：
```bash
cd /mnt/f/youtu-agent

# 检查配置一致性
echo "=== 训练配置 ==="
grep "level:" configs/practice/word_puzzle_practice.yaml

echo "=== 评估配置 ==="
grep "level:" configs/eval/korgym/word_puzzle_eval.yaml
grep "level:" configs/eval/korgym/word_puzzle_practice_eval.yaml

echo "=== 数据集名称 ==="
grep "dataset:" configs/eval/korgym/word_puzzle_eval.yaml
grep "practice_dataset_name:" configs/practice/word_puzzle_practice.yaml
```

请在WSL中运行这些命令，然后告诉我结果！

















