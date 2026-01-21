# Practice 重试机制快速参考 ⚡

---

## 🎯 一句话总结

Practice 模块使用 **指数退避（Exponential Backoff）+ Jitter** 算法处理 API 速率限制，在 4 个关键位置实现了智能重试。

---

## 📍 重试位置速查

| # | 位置 | 文件 | 重试次数 | 延迟策略 | 触发条件 |
|---|------|------|---------|---------|---------|
| 1 | **Rollout** | `rollout_manager.py:133-152` | 3次 | 无延迟 | 超时/异常 |
| 2 | **单轮总结** | `experience_updater.py:102-157` | 5次 | 指数退避 | 速率限制 |
| 3 | **组优势分析** | `experience_updater.py:190-242` | 5次 | 指数退避 | 速率限制 |
| 4 | **经验更新** | `experience_updater.py:265-317` | 5次 | 指数退避 | 速率限制 |

---

## 🔧 关键代码片段

### 1. Rollout 重试（简单重试）

```python
# utu/practice/rollout_manager.py:133-152
for attempt in range(self.max_retries):  # max_retries=3
    try:
        result = await asyncio.wait_for(
            self.rollout_one(item), 
            timeout=self.task_timeout  # 3600秒
        )
        return result
    except TimeoutError:
        logger.warning(f"Timeout on attempt {attempt + 1}")
    except Exception as e:
        logger.warning(f"Error on attempt {attempt + 1}: {e}")
# 失败后返回 None
return None
```

### 2. 经验生成重试（智能重试）

```python
# utu/practice/experience_updater.py （3个地方相同逻辑）
max_retries = 5
base_delay = 2.0

for attempt in range(max_retries):
    try:
        response = await self.llm.query_one(...)
        return response
    except Exception as e:
        # 检测是否为速率限制错误
        is_rate_limit = (
            "429" in str(e) or 
            "rate limit" in str(e).lower() or 
            "TPM limit" in str(e)
        )
        
        if is_rate_limit and attempt < max_retries - 1:
            # 指数退避 + Jitter
            delay = base_delay * (2 ** attempt) + (attempt * 0.5)
            # 延迟序列: 2.0s, 4.5s, 9.0s, 18.5s, 38.0s
            
            logger.warning(f"Rate limit, retry after {delay:.1f}s")
            await asyncio.sleep(delay)
            continue
        else:
            return None  # 失败
```

---

## 📊 延迟时间表

### 指数退避计算公式
```
delay = 2.0 * (2 ^ attempt) + (attempt * 0.5)
```

### 延迟序列
```
第1次重试: 2.0秒
第2次重试: 4.5秒
第3次重试: 9.0秒
第4次重试: 18.5秒
第5次重试: 38.0秒
────────────────
总等待时间: ~72秒
```

---

## ⚙️ 快速配置

### 调整 Rollout 重试次数

```python
# 方法1: 修改代码 (utu/practice/rollout_manager.py:36)
def __init__(self, config, batch_size, task_timeout=3600, max_retries=5):
    #                                                      ^^^^^^^^^ 改为5

# 方法2: 初始化时传入
rollout_manager = RolloutManager(
    config=config,
    batch_size=100,
    max_retries=5  # 自定义重试次数
)
```

### 调整经验生成重试

```python
# 修改 utu/practice/experience_updater.py
# 3个位置需要同时修改:
# - 行104: _single_rollout_summary
# - 行192: _group_advantage  
# - 行262: _group_update

max_retries = 10  # 从5改为10
base_delay = 3.0  # 从2.0改为3.0
```

### 降低并发（推荐方式）

```yaml
# configs/practice/korgym/wordle_practice.yaml
practice:
  rollout_concurrency: 4  # 从32降到4

# configs/eval/korgym/wordle_eval.yaml
concurrency: 4  # 从32降到4
```

---

## 🚨 常见速率限制错误

```
Error code: 429 - {'message': 'Request was rejected due to rate limiting. 
Details: TPM limit reached.', 'data': None}
```

```
Rate limit hit in summary (attempt 1/5), retrying after 2.0s
```

---

## 📝 监控命令

### 实时监控重试

```bash
# 监控所有重试
tail -f logs/utu.log | grep -i "attempt\|retry"

# 仅监控速率限制
tail -f logs/utu.log | grep -i "rate limit"

# 监控失败情况
tail -f logs/utu.log | grep -i "failed after"
```

### 统计重试次数

```bash
# Rollout重试
grep "Rollout error on attempt" logs/utu.log | wc -l

# 经验生成重试
grep "Rate limit hit" logs/utu.log | wc -l

# 最终失败
grep "failed after.*attempts" logs/utu.log | wc -l
```

---

## 💡 快速诊断

### 问题：大量速率限制错误

```bash
# 检查日志
grep -c "Rate limit hit" logs/utu.log

# 解决方案（按优先级）：
# 1. 降低并发: rollout_concurrency: 2
# 2. 换小模型: Qwen2.5-7B (替代 72B)
# 3. 增加延迟: base_delay = 5.0
# 4. 减少批次: batch_size: 25
```

### 问题：重试过慢

```bash
# 解决方案：
# 1. 减少重试: max_retries = 3
# 2. 减少延迟: base_delay = 1.0
# 3. 提高并发: concurrency: 8 (风险：更多速率限制)
```

### 问题：仍有大量失败

```bash
# 检查非速率限制错误
grep "failed in" logs/utu.log | grep -v "Rate limit"

# 常见原因：
# - trajectories为None → 已修复 ✅
# - JSON解析错误 → 检查prompt格式
# - 游戏服务器错误 → 重启游戏服务器
```

---

## 🎯 推荐配置

### 保守配置（高成功率，慢）

```python
# rollout_manager.py
max_retries = 5

# experience_updater.py
max_retries = 10
base_delay = 3.0

# config.yaml
rollout_concurrency: 2
concurrency: 2
```

### 平衡配置（推荐）⭐

```python
# rollout_manager.py
max_retries = 3  # 默认

# experience_updater.py
max_retries = 5  # 默认
base_delay = 2.0  # 默认

# config.yaml
rollout_concurrency: 4
concurrency: 4
```

### 激进配置（快速，失败率高）

```python
# rollout_manager.py
max_retries = 1

# experience_updater.py
max_retries = 3
base_delay = 1.0

# config.yaml
rollout_concurrency: 16
concurrency: 16
```

---

## 📚 相关文档

- 详细分析：`PRACTICE_RETRY_MECHANISM_GUIDE.md`
- Wordle修复：`WORDLE_TRAJECTORIES_FIX.md`
- 完整命令：`KORGYM_THREE_GAMES_COMMANDS.md`

---

**快速参考卡片 - 打印或保存备用** 📋











