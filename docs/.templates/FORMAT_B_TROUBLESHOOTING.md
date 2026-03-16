# 故障排除指南

本文档汇总了所有已知问题、报错及其解决方案。建议使用 Ctrl+F 搜索错误关键词。

---

## 目录

- [API 和网络错误](#api-和网络错误)
- [游戏服务器错误](#游戏服务器错误)
- [配置错误](#配置错误)
- [数据和数据库问题](#数据和数据库问题)
- [训练和经验学习错误](#训练和经验学习错误)
- [评估结果异常](#评估结果异常)

---

## API 和网络错误

### 问题：API Rate Limit (429 错误)

**现象**：
```
Error: 429 Too Many Requests
Rate limit exceeded
```

**根因**：
并发请求过多，触发 API 提供商的速率限制（如 DeepSeek/OpenAI）。

**修复方案**：

1. 降低并发数：
```yaml
# configs/eval/korgym/game_eval.yaml
concurrency: 4  # 从 32 降低到 4
```

2. 使用更小的模型：
```yaml
# configs/agents/practice/game_agent.yaml
agent:
  model:
    model_settings:
      model: "Qwen2.5-7B-Instruct"  # 从 72B 降级到 7B
```

3. 增加重试延迟：
```yaml
# configs/practice/game_practice.yaml
practice:
  rollout_concurrency: 2  # 训练时更保守的并发
```

**验证方式**：
重新运行评估/训练，观察日志中是否还有 429 错误。

**相关文件**：
- 配置：`configs/eval/korgym/*.yaml`
- 代码：`utu/practice/rollout_manager.py`

---

### 问题：[下一个问题...]

**现象**：  
**根因**：  
**修复方案**：  
**验证方式**：  
**相关文件**：

---

## 游戏服务器错误

### 问题：500 Internal Server Error

[按照相同格式...]

---

## [其他分类...]

---

## 快速诊断流程

1. **确认服务器是否启动**：`netstat -an | findstr 8777`（Windows）或 `netstat -tuln | grep 8777`（Linux）
2. **检查数据集是否存在**：`uv run python scripts/list_datasets.py | grep KORGym`
3. **查看最新日志**：`logs/` 目录下的最新文件
4. **清理缓存重试**：删除 `test.db` 或使用清理脚本

如果以上步骤无法解决，请在 GitHub 提交 Issue。
