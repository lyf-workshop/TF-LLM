# 🔥 Wordle 评估 Rate Limiting 问题分析与解决

## 📊 调试结果总结

### ✅ 好消息

**多轮交互是正常的！**
- 5 个样本中，3 个成功执行了完整的 10 轮交互
- `multiround_result` 正确保存
- `final_score` 和 `reward` 一致
- **你的最初怀疑是错的（这是好事！）** - 评估脚本读取的确实是 10 轮交互后的最终结果

### ❌ 新问题

**2/5 样本因 429 错误失败**
```
样本 2, 3: 
Multi-round game failed: Error code: 429 - 
{'message': 'Request was rejected due to rate limiting...'}
```

---

## 🔍 问题根源

### Rate Limiting 计算

**当前配置**：
```yaml
# configs/eval/korgym/wordle_practice_20_eval.yaml
concurrency: 8          # 并发 8 个样本
korgym:
  max_rounds: 10        # 每个样本最多 10 轮
```

**API 调用量**：
```
并发样本数: 8
每样本轮数: 10
理论最大并发调用: 8 × 10 = 80 次 API 调用
```

**API 限流**：
- 大多数 LLM API 都有速率限制（例如：每分钟 60-100 次请求）
- 当并发过高时，会触发 429 错误
- Wordle 多轮游戏的 API 调用量是单轮游戏的 10 倍

---

## 📈 实际影响

### 成功率分析

根据你的调试结果：
```
总样本: 5
成功: 3 (60%)
失败: 2 (40%) - 因 429 错误
```

如果这个比例在整个 50 题评估中保持，那么：
```
总样本: 50
预期成功: ~30 (60%)
预期失败: ~20 (40%) - 因 API 限流
```

**影响**：
- ⚠️  准确率统计可能不准确（样本数减少）
- ⚠️  评估时间延长（需要重试失败的样本）
- ⚠️  资源浪费（失败的样本也消耗了部分 API 调用）

---

## 🛠️ 解决方案

### 方案 1：降低并发数 ✅ **推荐**

**修改配置**：

```yaml
# configs/eval/korgym/wordle_practice_20_eval.yaml

# 原配置
concurrency: 8  # ← 太高

# 建议修改为
concurrency: 2  # ← 降低到 2-4
```

**效果**：
```
并发样本数: 2
每样本轮数: 10
理论最大并发调用: 2 × 10 = 20 次
```

**优点**：
- ✅ 大幅降低 API 并发压力（80 → 20）
- ✅ 几乎消除 429 错误
- ✅ 无需修改代码

**缺点**：
- ⚠️  评估时间延长（但 Wordle 本来就慢）

### 方案 2：增加重试机制（已有）

查看现有重试机制：

**文件**：`utu/practice/korgym_adapter.py`

当前没有针对 429 错误的特殊处理。需要添加：

```python
async def play_multiple_rounds(self, agent, seed: int) -> Dict:
    game_state = self.generate_game_instance(seed)
    trajectory = []
    responses = []
    total_time = 0
    
    for round_num in range(1, self.max_rounds + 1):
        prompt = self.get_game_prompt(game_state)
        
        # ✅ 添加重试逻辑
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                agent_result = await agent.run(prompt, save=True)
                response_time = time.time() - start_time
                total_time += response_time
                break  # 成功，跳出重试循环
                
            except Exception as e:
                if "429" in str(e) or "rate limit" in str(e).lower():
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # 指数退避
                        logger.warning(f"Rate limit hit, retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Max retries reached for round {round_num}")
                        raise
                else:
                    raise
        
        # 继续原有逻辑
        action = self._extract_action(agent_result.final_output)
        ...
```

### 方案 3：使用更高级的 API 套餐

如果使用的是付费 API：
- 升级到更高的速率限制套餐
- 例如：从 60 RPM → 600 RPM

---

## 🎯 推荐实施步骤

### Step 1: 降低并发数（立即实施）✅

```bash
# 编辑配置文件
code configs/eval/korgym/wordle_practice_20_eval.yaml

# 修改第 14 行
concurrency: 8  # 改为 2 或 4
```

```yaml
# 修改后
concurrency: 2  # ← 多轮游戏推荐 2-4
```

### Step 2: 清理失败的样本

```bash
# 删除有 429 错误的评估结果
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_eval_20_3 --force
```

### Step 3: 重新评估

```bash
# 使用降低后的并发重新评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval
```

### Step 4: 验证结果

```bash
# 再次检查是否还有 429 错误
uv run python scripts/debug_wordle_multiround.py --exp_id wordle_practice_eval_20_3 --limit 10
```

**预期结果**：
```
✅ 所有样本都正常执行
✅ 没有 429 错误
✅ 所有样本都有 multiround_result
```

---

## 📊 不同并发数的对比

| 并发数 | 最大并发调用 | 429 风险 | 评估时间（50题） | 推荐度 |
|-------|-------------|---------|----------------|--------|
| **8** | 80 | 🔴 高 | ~10 分钟 | ❌ 不推荐 |
| **4** | 40 | 🟡 中 | ~20 分钟 | ⚠️ 可能有风险 |
| **2** | 20 | 🟢 低 | ~40 分钟 | ✅ **推荐** |
| **1** | 10 | 🟢 极低 | ~80 分钟 | ⚠️ 太慢 |

**建议**：
- 开发/测试：使用 `concurrency: 2`
- 如果还有 429：降低到 `concurrency: 1`
- 如果 API 配额高：可以试 `concurrency: 4`

---

## 📝 其他配置文件的建议

### 查看所有 Wordle 评估配置

```bash
# configs/eval/korgym/wordle_eval.yaml
concurrency: 2  # ✅ 已经是 2，正确

# configs/eval/korgym/wordle_practice_eval.yaml
concurrency: 2  # ✅ 已经是 2，正确

# configs/eval/korgym/wordle_practice_20_eval.yaml
concurrency: 8  # ❌ 需要改为 2
```

### 对比其他游戏

```bash
# Word Puzzle (单轮游戏)
concurrency: 32  # ✅ 可以高并发

# Alphabetical Sorting (单轮游戏)
concurrency: 32  # ✅ 可以高并发

# Wordle (多轮游戏，10 轮)
concurrency: 2   # ✅ 必须低并发
```

**规律**：
- **单轮游戏**：可以用高并发（32）
- **多轮游戏**：必须用低并发（2-4）

---

## 💡 为什么之前的配置是 8？

可能的原因：
1. 配置是从单轮游戏模板复制的
2. 没有考虑到 Wordle 的多轮特性（10 轮 = 10x API 调用）
3. 测试时使用的 API 配额更高

---

## 🔧 修改配置文件

立即修改配置：

```yaml
# configs/eval/korgym/wordle_practice_20_eval.yaml

# @package _global_
defaults:
  - /agents/practice/wordle_practice_20_l4_agent@agent
  - _self_

exp_id: "wordle_practice_eval_20_3"

# Evaluation dataset configuration (same as baseline)
data:
  dataset: "KORGym-Wordle-Eval-50"
  type: "single"

# Evaluation settings
concurrency: 2  # ← 修改这里！从 8 改为 2

pass_k: 1

# Verification function settings
verify_filename: "korgym.py"
verify_func_name: "verify_func"

# KORGym specific settings
korgym:
  enabled: true
  game_name: "33-wordle"
  game_host: "localhost"
  game_port: 8777
  level: 4
  max_rounds: 10
  timeout_per_game: 600
```

---

## 🧪 测试流程

### 测试脚本

```bash
# 1. 修改配置（并发 8 → 2）
code configs/eval/korgym/wordle_practice_20_eval.yaml

# 2. 清理旧结果
uv run python scripts/utils/clean_experiment_data.py --exp_id wordle_practice_eval_20_3 --force

# 3. 重新评估（使用修复后的配置）
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_20_eval

# 4. 检查结果（应该没有 429 错误）
uv run python scripts/debug_wordle_multiround.py --exp_id wordle_practice_eval_20_3 --limit 10

# 5. 查看整体统计
uv run python scripts/korgym/view_korgym_results.py wordle_practice_eval_20_3
```

---

## 📊 预期改进

### 修复前（并发 8）

```
总样本: 50
成功完成: ~30 (60%)
429 失败: ~20 (40%)
实际准确率: 无法准确统计
```

### 修复后（并发 2）

```
总样本: 50
成功完成: ~50 (100%)
429 失败: 0 (0%)
实际准确率: 可准确统计
```

---

## 🎉 总结

### 关键发现

1. ✅ **多轮交互逻辑完全正常**
   - 成功的样本都执行了完整的 10 轮
   - `final_score` 是最终结果，不是第一轮
   - 评估脚本读取的是正确的数据

2. ❌ **并发配置不当导致 API 限流**
   - 当前 `concurrency: 8` 对于多轮游戏太高
   - 导致 40% 的样本因 429 错误失败
   - 需要降低到 `concurrency: 2`

3. 🔧 **简单修改即可解决**
   - 只需修改一行配置
   - 无需修改代码
   - 立即生效

### 下一步行动

1. **立即修改配置**：`concurrency: 8` → `2`
2. **重新评估**：清除旧数据，重新运行
3. **验证结果**：确认没有 429 错误
4. **继续测试**：测试对话历史修复和手动优化经验的效果

---

**🚀 修改配置后，Wordle 评估应该就能稳定运行了！**

