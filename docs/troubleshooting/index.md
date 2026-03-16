# 故障排除指南

本文档汇总了所有已知问题、报错及其解决方案。建议使用 Ctrl+F 搜索错误关键词。

**快速跳转**：
- [API和网络错误](#api和网络错误)
- [游戏服务器错误](#游戏服务器错误)
- [配置错误](#配置错误)
- [数据和数据库问题](#数据和数据库问题)
- [训练和经验学习错误](#训练和经验学习错误)
- [评估结果异常](#评估结果异常)

---

## API和网络错误

### 问题：API Rate Limit (429错误)

**现象**：
```
Error: 429 Too Many Requests
Rate limit exceeded
Request was rejected due to rate limiting
```

**根因**：
并发请求过多，触发API提供商的速率限制（如 DeepSeek/OpenAI）。

**特别注意**：Wordle等多轮游戏会产生10倍的API调用量！
- 单轮游戏：每样本1次API调用
- Wordle（10轮）：每样本10次API调用
- `concurrency: 8` = 最多80次并发调用 → 极易触发429

**修复方案**：

**方案1**：降低并发数（最有效）
```yaml
# configs/eval/korgym/wordle_eval.yaml
concurrency: 2  # 多轮游戏必须用2，从8/32降低

# configs/practice/korgym/wordle_practice.yaml
practice:
  rollout_concurrency: 4  # 训练时更保守
```

**方案2**：使用更小的模型
```yaml
agent:
  model:
    model_settings:
      model: "Qwen2.5-7B-Instruct"  # 从72B降级到7B
```

**方案3**：增加超时和重试延迟
```yaml
practice:
  task_timeout: 900  # 增加超时时间
  rollout_concurrency: 2  # 进一步降低并发
```

**并发数对比表**：

| 并发数 | 最大API调用（Wordle 10轮） | 429风险 | 推荐度 |
|-------|---------------------------|---------|--------|
| 32 | 320 | 🔴 极高 | ❌ 禁止 |
| 8 | 80 | 🔴 高 | ❌ 不推荐 |
| 4 | 40 | 🟡 中 | ⚠️ 可能有风险 |
| **2** | **20** | **🟢 低** | **✅ 推荐** |
| 1 | 10 | 🟢 极低 | ✅ 最保险但慢 |

**验证方式**：
重新运行评估/训练，观察日志中是否还有429错误。

**相关文件**：
- 配置：`configs/eval/korgym/*.yaml`, `configs/practice/*.yaml`
- 代码：`utu/practice/rollout_manager.py`

---

### 问题：Connection Refused (连接被拒绝)

**现象**：
```
Error: Connection refused to http://localhost:8777
Failed to connect to game server
```

**根因**：
游戏服务器未启动或端口不匹配。

**修复方案**：

**Step 1**：检查服务器是否运行
```bash
# Windows
netstat -an | findstr 8777

# Linux/WSL
netstat -tuln | grep 8777
lsof -i :8777
```

**Step 2**：启动游戏服务器
```bash
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

**Step 3**：检查端口冲突
```bash
# 如果端口被占用，更换端口
python game_lib.py -p 8778

# 同时修改配置文件
# configs/eval/korgym/wordle_eval.yaml
korgym:
  game_port: 8778  # 改为新端口
```

**验证方式**：
在浏览器访问 `http://localhost:8777`，应该看到游戏服务器响应。

---

## 游戏服务器错误

### 问题：500 Internal Server Error

**现象**：
```
HTTPError: 500 Server Error: Internal Server Error
Game server crashed
```

**根因**：
游戏实例生成时的内部错误，通常是参数配置问题。

**修复方案**：

**Step 1**：检查level参数是否合法
```yaml
# configs/eval/korgym/wordle_eval.yaml
korgym:
  level: 5  # 必须在4-12范围内（Wordle单词长度）
```

**常见错误值**：
- Word Puzzle: level应该是1-5（难度等级）
- Wordle: level应该是4-12（单词长度）
- Alphabetical Sorting: level应该是1-5（难度等级）

**Step 2**：重启游戏服务器
```bash
# Ctrl+C 停止服务器
cd KORGym/game_lib/33-wordle
python game_lib.py -p 8777
```

**Step 3**：查看服务器日志
观察终端输出的错误信息，通常会指出具体问题。

**验证方式**：
运行测试命令：
```bash
python scripts/korgym/test_korgym_server.py
```

**相关文件**：
- 游戏代码：`KORGym/game_lib/*/game_lib.py`
- 适配器：`utu/practice/korgym_adapter.py`

---

## 配置错误

### 问题：Hierarchical Learning 未启用

**现象**：
训练完成后没有生成L1/L2经验，只有L0经验或完全没有经验。

**根因**：
`hierarchical_learning` 配置位置错误或参数缺失。

**常见错误配置**：
```yaml
# ❌ 错误：hierarchical_learning在顶层
exp_id: "wordle_practice"
hierarchical_learning:
  enabled: true

practice:
  epochs: 2
```

**正确配置**：
```yaml
# ✅ 正确：hierarchical_learning在practice下
exp_id: "wordle_practice"

practice:
  epochs: 2
  hierarchical_learning:  # 必须在practice块内！
    enabled: true
    l1_aggregation_threshold: 5
    l2_aggregation_threshold: 3
    max_l0_per_game: 1
    max_l0_recent: 50
    include_l0_in_prompt: true
    experience_save_path: workspace/hierarchical_experiences/wordle_practice.json
    agent_save_path: configs/agents/practice/wordle_practice_agent.yaml
```

**验证方式**：
```bash
# 检查生成的经验文件
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.L0 | length'
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.L1 | length'
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.L2 | length'
```

**预期数量**（100题训练）：
- L0: 45-50个
- L1: 9-10个
- L2: 3个

**相关文件**：
- 配置：`configs/practice/*.yaml`
- 代码：`utu/practice/hierarchical_experience_manager.py`

---

### 问题：Level 不匹配导致准确率为0%

**现象**：
训练后评估的准确率始终为0%或很低。

**根因**：
训练和评估使用了不同的`level`参数，导致模型在不同难度下训练和测试。

**诊断**：
```bash
# 检查训练配置
grep -A5 "level:" configs/practice/korgym/word_puzzle_practice.yaml

# 检查评估配置
grep -A5 "level:" configs/eval/korgym/word_puzzle_practice_eval.yaml
```

**修复方案**：
确保训练和评估的level完全一致：
```yaml
# configs/practice/korgym/word_puzzle_practice.yaml
korgym:
  level: 3  # 训练用level 3

# configs/eval/korgym/word_puzzle_practice_eval.yaml
korgym:
  level: 3  # 评估也必须用level 3
```

**验证方式**：
清理缓存后重新评估：
```bash
# 删除旧的评估结果
uv run python scripts/utils/clean_experiment_data.py --exp_id word_puzzle_practice_eval

# 重新评估
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

---

### 问题：Max_rounds 不匹配

**现象**：
多轮游戏（如Wordle）评估时出现轨迹错误或提前结束。

**根因**：
配置文件中的`max_rounds`与`game_lib.py`中的`attempts`不一致。

**诊断**：
```bash
# 查看game_lib.py中的attempts设置
grep "attempts" KORGym/game_lib/33-wordle/game_lib.py
# 输出: "attempts": 10

# 查看配置文件中的max_rounds
grep "max_rounds" configs/eval/korgym/wordle_eval.yaml
```

**修复方案**：
```yaml
# configs/eval/korgym/wordle_eval.yaml
korgym:
  max_rounds: 10  # 必须与game_lib.py中的attempts一致
```

**常见游戏的attempts**：
- Wordle: 10次
- 2048: 100次
- Minesweeper: 根据地图大小

**验证方式**：
观察评估日志中的轮数信息，应该完整执行10轮。

---

## 数据和数据库问题

### 问题：Dataset Already Exists

**现象**：
```
Error: Dataset already exists: KORGym-Wordle-Train-100
```

**根因**：
数据库中已存在同名数据集。

**修复方案**：

**方案1**：删除旧数据集（推荐）
```bash
uv run python -c "
from utu.db import DBService, DatasetSample
from sqlmodel import select
db = DBService()
with db.session() as session:
    stmt = select(DatasetSample).where(
        DatasetSample.dataset == 'KORGym-Wordle-Train-100'
    )
    for sample in session.exec(stmt):
        session.delete(sample)
    session.commit()
print('✓ 删除成功')
"
```

**方案2**：使用不同名称
```bash
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --dataset_suffix "_v2"  # 生成 KORGym-Wordle-Train-100_v2
```

**方案3**：使用清理脚本
```bash
bash scripts/cleanup_and_rerun_wordle.sh
```

**验证方式**：
```bash
# 查看所有数据集
uv run python scripts/data/list_datasets.py | grep Wordle
```

---

### 问题：DatasetSample.index 为 None 导致崩溃

**现象**：
```
TypeError: '<' not supported between instances of 'NoneType' and 'int'
File "utu/eval/data/data_manager.py", line 123, in get_dataset
    samples.sort(key=lambda x: x.index)
```

**根因**：
数据库中的`DatasetSample`对象缺少`index`字段。

**修复方案**：

**方案1**：修复数据准备脚本（已修复）
```python
# scripts/data/prepare_korgym_data.py
DatasetSample(
    dataset=dataset_name,
    source="KORGym",
    question=json.dumps(question_data),
    answer=None,
    index=i,  # ✅ 添加index字段
    metadata={}
)
```

**方案2**：重新生成数据集
```bash
# 删除旧数据集
uv run python scripts/utils/clean_dataset.py --dataset_name "KORGym-Wordle-Train-100"

# 重新生成（使用修复后的脚本）
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
```

**验证方式**：
查看数据库中的样本是否有index字段：
```bash
sqlite3 test.db "SELECT id, dataset, \"index\" FROM dataset_samples WHERE dataset LIKE 'KORGym%' LIMIT 5"
```

**相关文件**：
- 修复文件：`scripts/data/prepare_korgym_data.py`
- 数据管理：`utu/eval/data/data_manager.py`

---

### 问题：Processer 匹配失败

**现象**：
```
Warning: Processer for dataset='8-word_puzzle' not found. Using default processer.
```

**根因**：
数据集的`source`字段设置错误，无法匹配到`KORGymProcesser`。

**修复方案**：

确保数据准备脚本中`source`设置为`"KORGym"`：
```python
# scripts/data/prepare_korgym_data.py
DatasetSample(
    source="KORGym",  # ✅ 必须是"KORGym"才能匹配到KORGymProcesser
    dataset=dataset_name,
    ...
)
```

**错误配置示例**：
```python
# ❌ 错误
source="training_free_grpo"  # 找不到对应Processer
source="korgym"  # 大小写错误
source="8-word_puzzle"  # 游戏名不是source
```

**Processer匹配规则**：
```python
# utu/eval/processer/__init__.py
PROCESSER_REGISTRY = {
    "KORGym": KORGymProcesser,
    "training_free_grpo": TrainingFreeGRPOProcesser,
    ...
}
```

**验证方式**：
观察评估日志，应该看到：
```
✓ Using KORGymProcesser for dataset: KORGym-Wordle-Eval-50
```

**相关文件**：
- 数据准备：`scripts/data/prepare_korgym_data.py`
- Processer注册：`utu/eval/processer/__init__.py`
- KORGym Processer：`utu/eval/processer/korgym_processor.py`

---

### 问题：评估结果缓存（重复结果）

**现象**：
多次运行评估，但结果完全相同，包括响应内容和时间戳。

**根因**：
数据库缓存了之前的评估结果，新运行直接返回缓存。

**修复方案**：

**方案1**：清理特定实验的缓存
```bash
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id wordle_baseline_eval
```

**方案2**：清理所有匹配的实验
```bash
uv run python scripts/utils/clean_experiment_data.py \
  --exp_id_pattern "wordle%"
```

**方案3**：使用不同的exp_id
```yaml
# configs/eval/korgym/wordle_eval.yaml
exp_id: "wordle_baseline_eval_v2"  # 使用新的ID
```

**方案4**：直接删除数据库（终极方案）
```bash
# 备份
cp test.db test.db.backup

# 删除
rm test.db

# 重新创建数据集
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
```

**验证方式**：
查看评估日志的时间戳，应该是新的时间。

---

## 训练和经验学习错误

### 问题：Wordle 完全不生成经验（0个L0）

**现象**：
训练完成后，经验文件为空或只有极少L0经验（<5个）。

**根因**：
Wordle的0/1二值评分机制 + 经验提取器的"部分正确"筛选逻辑导致样本被过滤。

**详细分析**：

**Wordle评分机制**：
- 猜中 = 1.0
- 失败 = 0.0
- 无部分分数

**经验提取器筛选逻辑**：
```python
# utu/practice/experience_updater.py
avg_score = sum(scores) / len(scores)
if avg_score > 0 and avg_score < 1:  # 只处理部分正确的
    all_rollouts_to_process.extend(rollouts)
```

**问题**：
- 如果3个rollout全部成功 [1,1,1] → avg=1.0 → **不提取**
- 如果3个rollout全部失败 [0,0,0] → avg=0.0 → **不提取**
- 只有部分成功 [1,0,0] → avg=0.33 → **提取**

**修复方案**：

**方案1**：修改经验提取器（已实现）
```python
# utu/practice/korgym_experience_extractor.py
# 专门为KORGym设计的经验提取器
# 不再严格要求"部分正确"，只要有得分差异即可
if max(scores) > min(scores):  # 只要有差异就提取
    all_rollouts_to_process.extend(rollouts)
```

**方案2**：增加rollout数量
```yaml
# configs/practice/korgym/wordle_practice.yaml
practice:
  grpo_n: 5  # 从3增加到5，提高"部分成功"概率
```

**方案3**：调整游戏难度
```yaml
korgym:
  level: 5  # 使用5字母单词（中等难度）
  # 避免level太高（难度太大，全失败）
  # 避免level太低（难度太小，全成功）
```

**验证方式**：
```bash
# 查看生成的经验数量
cat workspace/hierarchical_experiences/wordle_practice.json | jq '.L0 | length'

# 预期：100题训练应该有45-50个L0经验
```

**相关文件**：
- 通用提取器：`utu/practice/experience_updater.py`
- KORGym提取器：`utu/practice/korgym_experience_extractor.py`
- 配置：`configs/practice/korgym/*.yaml`

---

### 问题：L1/L2 经验数量太少

**现象**：
训练完成后，L0经验正常（40-50个），但L1只有1-2个，L2为0。

**根因**：
分层聚合阈值过高，L0数量不足以聚合成足够的L1/L2。

**诊断**：
```bash
# 查看当前配置的阈值
grep -A3 "hierarchical_learning:" configs/practice/korgym/wordle_practice.yaml
```

**修复方案**：

**方案1**：降低聚合阈值
```yaml
# configs/practice/korgym/wordle_practice.yaml
practice:
  hierarchical_learning:
    l1_aggregation_threshold: 4  # 从5降到4
    l2_aggregation_threshold: 2  # 从3降到2
```

**方案2**：增加训练数据
```bash
# 使用100题代替20题
uv run python scripts/data/prepare_korgym_data.py \
  --game_name "33-wordle" \
  --train_seeds_start 51 \
  --train_seeds_end 150  # 100题
```

**方案3**：增加每题的经验提取数
```yaml
practice:
  num_experiences_per_query: 2  # 从1改为2（每题提取2个L0）
```

**不同数据集规模的预期经验数**：

| 训练题数 | L0数量 | L1数量 | L2数量 |
|---------|--------|--------|--------|
| 20题 | 15-18 | 3-4 | 1-2 |
| 50题 | 30-40 | 6-8 | 2-3 |
| 100题 | 45-50 | 9-10 | 3 |

**验证方式**：
```bash
cat workspace/hierarchical_experiences/wordle_practice.json | jq '{L0: (.L0|length), L1: (.L1|length), L2: (.L2|length)}'
```

---

### 问题：Circular Import Error (循环导入)

**现象**：
```
ImportError: cannot import name 'BaseBenchmark' from 'utu.eval.benchmarks.base'
(most likely due to a circular import)
```

**根因**：
模块级导入造成循环依赖：`korgym_processor.py` ↔ `korgym_adapter.py` ↔ `base.py`

**修复方案**（已修复）：

使用延迟导入（Lazy Import）：
```python
# utu/eval/processer/korgym_processor.py

# ❌ 错误：模块级导入
from ...practice.korgym_adapter import KORGymAdapter

class KORGymProcesser:
    def __init__(self, config):
        self.adapter = KORGymAdapter(...)

# ✅ 正确：延迟导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...practice.korgym_adapter import KORGymAdapter

class KORGymProcesser:
    def __init__(self, config):
        from ...practice.korgym_adapter import KORGymAdapter  # 运行时才导入
        self.adapter = KORGymAdapter(...)
```

**验证方式**：
成功运行评估或训练命令，不再出现循环导入错误。

**相关文件**：
- `utu/eval/processer/korgym_processor.py`
- `utu/practice/korgym_adapter.py`
- `utu/eval/benchmarks/base.py`

---

## 评估结果异常

### 问题：准确率始终为0%

**现象**：
评估完成，所有样本都显示失败，准确率0%。

**可能原因及排查**：

**原因1**：Level不匹配（最常见）
```bash
# 检查训练和评估的level是否一致
grep "level:" configs/practice/korgym/word_puzzle_practice.yaml
grep "level:" configs/eval/korgym/word_puzzle_practice_eval.yaml
```
→ 参考 [Level不匹配](#问题level-不匹配导致准确率为0)

**原因2**：答案格式不正确
```bash
# 查看失败样本的响应
sqlite3 test.db "SELECT response, correct_answer FROM evaluation_data WHERE exp_id='word_puzzle_practice_eval' LIMIT 3"
```

检查：
- 响应是否包含有效的JSON
- 是否包含`answers`字段
- 答案格式是否符合游戏要求

**原因3**：游戏服务器返回错误
```bash
# 查看评估日志中的错误信息
tail -100 logs/eval_wordle_practice_eval.log
```

**原因4**：Prompt问题（Wordle特有）
- 未使用简洁历史格式 → prompt过长导致LLM理解困难
- 未强调单词有效性 → LLM猜无效单词

→ 参考 [Wordle使用指南](../guides/korgym/wordle.md) 的优化章节

**通用诊断流程**：
1. 检查配置一致性（level, max_rounds等）
2. 检查游戏服务器日志
3. 查看数据库中的具体样本
4. 对比基线版和训练版配置差异

---

### 问题：准确率异常高（>95%）或异常低（<5%）

**现象**：
评估结果不符合预期，准确率极端。

**可能原因**：

**准确率>95%（异常高）**：
1. **使用了缓存结果** → 清理缓存重新评估
2. **评估集太简单** → 检查`level`参数
3. **数据泄露** → 评估集和训练集重叠

**准确率<5%（异常低）**：
1. **配置错误** → level不匹配
2. **API限流导致大量失败** → 降低并发数
3. **Prompt问题** → LLM无法理解任务

**诊断方法**：
```bash
# 查看前5个成功和失败的样本
sqlite3 test.db "SELECT question, response, correct_answer FROM evaluation_data WHERE exp_id='xxx' AND correct=1 LIMIT 5"
sqlite3 test.db "SELECT question, response, correct_answer FROM evaluation_data WHERE exp_id='xxx' AND correct=0 LIMIT 5"
```

---

### 问题：Wordle Trajectories 为 None

**现象**：
```
TypeError: object of type 'NoneType' has no len()
File "utu/practice/korgym_adapter.py", line XX
    if len(trajectories) > 0:
```

**根因**：
多轮游戏的`trajectories`字段未正确保存。

**修复方案**（已修复）：

```python
# utu/practice/korgym_adapter.py
async def play_multiple_rounds(...):
    # ...
    return {
        "final_score": final_score,
        "trajectories": trajectory,  # ✅ 确保保存轨迹
        "total_time": total_time,
        "responses": responses,
    }
```

**验证方式**：
查看数据库中的multiround_result字段：
```bash
sqlite3 test.db "SELECT id, multiround_result FROM evaluation_data WHERE exp_id='wordle_practice_eval' LIMIT 3"
```

应该包含`trajectories`数组。

---

## 快速诊断流程

当遇到问题时，按以下顺序排查：

### 1. 确认基础环境
```bash
# 检查Python版本
python --version  # 需要3.12+

# 检查虚拟环境
which python  # 应该指向.venv/bin/python

# 检查游戏服务器
netstat -an | findstr 8777  # Windows
netstat -tuln | grep 8777  # Linux
```

### 2. 检查配置文件
```bash
# 检查配置语法
python -c "import yaml; yaml.safe_load(open('configs/eval/korgym/wordle_eval.yaml'))"

# 检查关键参数
grep -E "level:|max_rounds:|concurrency:" configs/eval/korgym/wordle_eval.yaml
```

### 3. 查看日志
```bash
# 最新的评估日志
ls -lt logs/*.log | head -1 | xargs tail -100

# 搜索错误
grep -i "error\|exception\|failed" logs/*.log | tail -20
```

### 4. 检查数据库
```bash
# 查看数据集
sqlite3 test.db "SELECT dataset, COUNT(*) FROM dataset_samples GROUP BY dataset"

# 查看评估结果
sqlite3 test.db "SELECT exp_id, COUNT(*), AVG(correct) FROM evaluation_data GROUP BY exp_id"
```

### 5. 清理并重试
```bash
# 清理缓存
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_baseline_eval

# 重新运行
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

---

## 获取帮助

如果以上方法都无法解决问题：

1. **查看详细文档**：
   - [Wordle指南](../guides/korgym/wordle.md)
   - [Word Puzzle指南](../guides/korgym/word_puzzle.md)
   - [Alphabetical Sorting指南](../guides/korgym/alphabetical_sorting.md)

2. **查看日志文件**：
   - `logs/` 目录下的最新日志
   - 游戏服务器终端输出

3. **检查数据库**：
   ```bash
   sqlite3 test.db ".schema"
   sqlite3 test.db "SELECT * FROM evaluation_data WHERE exp_id='xxx' LIMIT 3"
   ```

4. **提交Issue**：
   - 包含完整错误信息
   - 配置文件内容
   - 重现步骤
   - 环境信息（OS, Python版本等）

---

*最后更新：2026-03-16*  
*文档版本：v2.0（整合版）*
