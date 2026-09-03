# 配置参考

## 环境变量

项目从仓库根目录的 `.env` 读取配置。以 `.env.example` 为模板，不要提交真实密钥。

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `UTU_LLM_TYPE` | 是 | 当前常用值为 `chat.completions` |
| `UTU_LLM_MODEL` | 是 | Agent 使用的固定模型 ID |
| `UTU_LLM_BASE_URL` | 是 | OpenAI 兼容 API 的 `/v1` 地址 |
| `UTU_LLM_API_KEY` | 是 | Agent 模型密钥 |
| `JUDGE_LLM_*` | 按任务 | LLM judge 使用的类型、模型、地址和密钥 |
| `SERPER_API_KEY` | Web 任务 | 搜索服务密钥 |
| `JINA_API_KEY` | Web 任务 | 网页内容读取服务密钥 |
| `UTU_DB_URL` | 否 | 默认 `sqlite:///test.db` |
| `UTU_DB_POOL_SIZE` | 否 | 连接池常驻连接数；SQLite 默认 5，服务端数据库默认 20 |
| `UTU_DB_MAX_OVERFLOW` | 否 | 连接池临时溢出连接数；SQLite 默认 10，服务端数据库默认 20 |
| `UTU_DB_POOL_TIMEOUT` | 否 | 等待连接池可用连接的秒数，默认 30 |
| `UTU_DB_POOL_RECYCLE` | 否 | 服务端数据库连接回收秒数，默认 1800 |
| `UTU_DB_SQLITE_TIMEOUT` | 否 | SQLite 等待文件锁的秒数，默认 30 |
| `UTU_DB_SQLITE_WAL` | 否 | 是否对文件型 SQLite 启用 WAL，默认 `true` |
| `UTU_LOG_LEVEL` | 否 | 日志级别 |
| `PHOENIX_*` | 否 | OpenTelemetry/Phoenix tracing |

SiliconFlow provider 可从专用示例开始：

```bash
cp configs/env/siliconflow.env.example .env
```

该命令会覆盖现有 `.env`，仅在首次创建配置时使用；已有配置应手动合并相应的 `UTU_LLM_*` 字段。

## YAML 覆盖

Hydra 配置名不含 `.yaml`，并以配置根目录为基准，例如：

```bash
uv run python scripts/run_eval.py \
  --config_name math/math_AIME24 \
  --exp_id example_run
```

命令行可覆盖 Agent：

```bash
--agent_config practice/generated_agent_name
```

正式对比建议只覆盖 Agent，让 baseline 与经验组共享同一份 eval YAML。

## 实验标识

`exp_id` 必须唯一且可读，推荐包含数据集、组别与 UTC 时间：

```bash
RUN_TAG=$(date -u +%Y%m%dT%H%M%SZ)
BASE_ID="aime24_baseline_${RUN_TAG}"
EXP_ID="aime24_experience_${RUN_TAG}"
```

不要把不同日期、不同模型或不同代码版本的数据追加到同一个正式实验 ID。

## 并发与超时

并发、`pass_k`、温度和任务超时由具体配置决定。增加并发只缩短墙钟时间，不减少请求总数。受到 429 限流时先降低并发；真正的任务超时仍是有效失败，不能无限补跑。

各数据集的固定参数和额外服务见[数据集索引](../datasets/index.md)。

## 数据库索引

新建数据库会自动包含高频查询索引。已有数据库不会在程序导入时自动执行耗时的索引迁移；先检查缺失索引（不创建索引），再在没有实验写入的维护窗口执行：

```bash
uv run python scripts/db/ensure_indexes.py
uv run python scripts/db/ensure_indexes.py --apply
```

大型 SQLite 数据库创建索引需要额外磁盘空间并会暂时持有写锁，执行前应备份数据库并停止 rollout、judge 和 tracing 写入。
