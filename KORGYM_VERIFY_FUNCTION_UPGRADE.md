# KORGym验证函数升级说明 🔧

## 📋 概述

已将 `utu/practice/verify/korgym.py` 重写为**完全兼容KORGym官方验证机制**的版本。

---

## ✅ 主要改进

### 1. **与KORGym官方验证机制对齐**

**之前**：简单的JSON解析和success检查
```python
# 旧版本：假设response是JSON格式，手动判断success
result = json.loads(sample.response)
success = result.get("success", False)
reward = 1.0 if success else 0.0
```

**现在**：调用KORGym游戏服务器的 `/verify` API
```python
# 新版本：调用游戏服务器API，与KORGym eval_lib保持一致
verified_state = call_korgym_verify_api(game_server_url, game_state)
score = verified_state.get('score', 0)
reward = calculate_reward_from_score(score)
```

---

### 2. **实现了标准的答案提取逻辑**

新增 `extract_action_from_response()` 函数，从Agent的文本响应中提取答案：

```python
def extract_action_from_response(response: str) -> str:
    """
    提取最后一个 'Answer:' 后面的内容
    支持各种格式：
    - Answer: LEFT
    - Answer: ["happy", "sad"]
    - answer: 42
    """
```

**处理示例**：
```
Agent响应:
"Let me think... the best move is to go left.
Answer: LEFT"

提取结果: "LEFT"
```

---

### 3. **支持单轮和多轮游戏**

#### 单轮游戏（如 8-word_puzzle）
- `score`: 0-1之间（正确率）
- `reward`: 直接使用score
- 示例：答对5个单词中的3个，score=0.6，reward=0.6

#### 多轮游戏（如 3-2048）
- `score`: 累积得分（如256, 512等）
- `reward`: 1.0 if score > 0 else 0.0
- 检查 `is_end` 状态判断游戏是否结束

---

### 4. **正确处理游戏状态**

新版本需要从 `sample.metadata` 中获取游戏状态：

```python
# 从metadata获取游戏状态
game_state = sample.metadata.get('game_state', {})
game_server_url = sample.metadata.get('game_server_url', 'http://localhost:8775')

# 更新action
game_state['action'] = extracted_action

# 调用服务器验证
verified_state = call_korgym_verify_api(game_server_url, game_state)
```

---

## 🔧 技术细节

### KORGym验证流程

```
Agent Response
    ↓
提取 Action (extract_action_from_response)
    ↓
构建 Game State
    {
      "board": [...],
      "score": 0,
      "is_end": false,
      "action": "LEFT",  # 提取的动作
      "epoch": 1,
      ...
    }
    ↓
POST /verify API (call_korgym_verify_api)
    ↓
验证结果
    {
      "score": 8,        # 更新后的分数
      "is_end": false,   # 是否结束
      "board": [...],    # 更新后的棋盘
      "epoch": 2,        # 下一回合
      ...
    }
    ↓
计算 Reward (0-1)
```

---

## 📝 函数接口

### 主函数：`verify_func()`

```python
def verify_func(sample: EvaluationSample, timeout_score: float = 0, **kwargs) -> dict:
    """
    Args:
        sample: EvaluationSample包含:
            - response: Agent的文本响应
            - metadata: 包含game_state和game_server_url
        timeout_score: 超时时返回的分数
        **kwargs: 额外参数
            - game_server_url: 游戏服务器URL
            - verify_timeout: 验证API超时时间（秒）
    
    Returns:
        {
            "reward": float,      # 0.0-1.0
            "reasoning": str      # 详细说明
        }
    """
```

### 辅助函数

1. **`normalize_response()`**
   - 清理LaTeX格式和特殊字符
   - 与KORGym eval_lib保持一致

2. **`extract_action_from_response()`**
   - 从响应中提取"Answer:"后的内容
   - 支持多种格式

3. **`call_korgym_verify_api()`**
   - 调用游戏服务器的 `/verify` 端点
   - 处理网络错误和超时

---

## 🎮 使用示例

### 示例1: Word Puzzle游戏

```python
# Game state (from metadata)
game_state = {
    'answer': ['happy', 'person', 'water'],  # 正确答案
    'clues': [...],
    'image_path': '...',
    'score': 0,
    'is_end': False
}

# Agent response
agent_response = '''
Based on the clues:
1. "happy" - feeling of joy
2. "person" - human being
3. "ocean" - large body of water

Answer: ["happy", "person", "ocean"]
'''

# Verification
# 提取action: ["happy", "person", "ocean"]
# 调用/verify API
# 结果: score = 2/3 = 0.667 (2个正确)
# reward = 0.667
```

### 示例2: 2048游戏

```python
# Game state
game_state = {
    'board': [[2, 0, 0, 0], [0, 2, 0, 0], ...],
    'score': 0,
    'is_end': False,
    'epoch': 1
}

# Agent response
agent_response = '''
The board shows two 2s on the left side.
I should move them together.

Answer: LEFT
'''

# Verification
# 提取action: "LEFT"
# 调用/verify API
# 结果: score = 4 (合并两个2), is_end = False
# reward = 1.0 (score > 0)
```

---

## ⚙️ 配置要求

### 在evaluation配置中需要确保：

```yaml
# configs/eval/korgym/korgym_eval.yaml
korgym:
  enabled: true
  game_host: "localhost"
  game_port: 8775
  max_rounds: 100
  timeout_per_game: 600

verify_filename: "korgym.py"
verify_func_name: "verify_func"
```

### 在运行时需要：

1. **游戏服务器运行**
   ```bash
   cd KORGym/game_lib/8-word_puzzle
   python game_lib.py -p 8775
   ```

2. **Metadata正确传递**
   - `game_server_url`: 游戏服务器地址
   - `game_state`: 当前游戏状态

---

## 🔄 与旧版本的对比

| 特性 | 旧版本 | 新版本 |
|------|--------|--------|
| **验证方式** | 手动JSON解析 | 调用KORGym API |
| **答案提取** | 无 | ✅ 标准提取逻辑 |
| **游戏类型** | 只支持简单成功/失败 | ✅ 支持单轮和多轮 |
| **分数计算** | 二元（0或1） | ✅ 基于实际游戏分数 |
| **错误处理** | 基础异常捕获 | ✅ 详细的错误信息 |
| **兼容性** | 自定义逻辑 | ✅ 与KORGym官方一致 |

---

## 🐛 故障排查

### 问题1: "Connection refused"

**原因**: 游戏服务器未运行

**解决**:
```bash
# 检查服务器
curl http://localhost:8775/docs

# 启动服务器
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775
```

### 问题2: "verification_error in result"

**原因**: API调用失败

**检查**:
- 游戏服务器是否运行
- game_state格式是否正确
- 网络连接是否正常

### 问题3: Reward始终为0

**可能原因**:
1. 答案提取失败 - 检查Agent响应格式
2. API验证失败 - 检查game_state
3. 动作无效 - 检查游戏规则

**调试**:
```python
# 在verify_func中添加日志
print(f"Extracted action: {action}")
print(f"Verified state: {verified_state}")
print(f"Score: {score}, Reward: {reward}")
```

---

## 📊 性能影响

### 延迟
- **旧版本**: ~1ms (本地JSON解析)
- **新版本**: ~10-50ms (包括API调用)
- **建议**: 设置合理的verify_timeout（默认30秒）

### 准确性
- **旧版本**: 依赖手动判断逻辑
- **新版本**: 与KORGym官方完全一致 ✅

---

## ✅ 验证完整性

新版本验证函数确保：

1. ✅ **与KORGym官方eval_lib逻辑一致**
2. ✅ **支持所有KORGym游戏**（单轮/多轮）
3. ✅ **标准的答案提取机制**
4. ✅ **详细的错误处理和reasoning**
5. ✅ **灵活的配置选项**

---

## 🎯 下一步

使用新版本验证函数时：

1. 确保游戏服务器运行
2. 在metadata中正确传递game_state
3. 检查验证结果的reasoning字段以debug

---

**更新时间**: 2026-01-15  
**版本**: v2.0 (KORGym-Compatible)  
**兼容性**: KORGym eval_lib 完全兼容 ✅

