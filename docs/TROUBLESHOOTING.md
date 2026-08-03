# 故障排查

先运行统一预检，再进入数据集专项检查：

```bash
PROFILE=core
uv run python scripts/setup/check_environment.py \
  --profile $PROFILE \
  --check-api
```

## API 连接、timeout、429 或 5xx

1. 确认 `.env` 中模型 ID、base URL、API key 与 `/v1` 路径正确。
2. 将 rollout、eval 和 judge 并发降低到 4 到 8。
3. 检查 endpoint 的限流、队列与最大请求时长。
4. 使用同一试次内的有限重试，不要无限重启整个任务。
5. 连续连接错误时暂停提交新任务，恢复后只补跑无效试次。

API 连接错误和 429/5xx 不应直接记为 verifier fail。模型已经正常响应、但 Agent 真正耗尽任务时间时仍是有效失败。

## 结果全部或大面积为 0

不要先假设模型能力为零，按顺序检查：

1. 数据集是否存在，记录数量是否与 YAML 一致。
2. 实验是否产生了有效模型输出，而不是空响应或异常文本。
3. verifier 是否读到了正确答案、文件或游戏 session。
4. parser 所需的输出格式是否与 Agent 指令一致。
5. 外部服务、容器或依赖是否在运行中退出。
6. 实际加载的模型和 Agent YAML 是否是预期版本。

普通实验可查看逐题输出：

```bash
EXP_ID='<your-exp-id>'
uv run python scripts/utils/view_results.py \
  -e $EXP_ID \
  --details \
  --limit 10
```

SkillsBench 先查看无效试次：

```bash
uv run python scripts/utils/view_benchmark_results.py \
  -b skillsbench \
  -e $EXP_ID \
  --infra \
  --detailed
```

## SkillsBench 与 Harbor

确认 Docker、Harbor 和外部仓库版本：

```bash
docker info
harbor --version
git -C SkillsBench-repo rev-parse HEAD
```

当前要求 Harbor 0.3.0，外部仓库 commit 为 `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`。`RewardFileNotFoundError`、镜像构建失败、容器异常与 Harbor 调用错误属于基础设施问题。

大量任务后可检查磁盘空间：

```bash
docker system df
df -h
```

不要在不确认用途时清除全部 Docker 镜像或其他用户的容器。

## KORGym 无法连接

检查配置中的游戏 ID、端口和实际进程完全一致：

```bash
PORT=8775
ss -lntp | grep :$PORT
curl -f http://127.0.0.1:${PORT}/docs >/dev/null
```

当前端口为 Word Puzzle 8775、Alphabetical Sorting 8776、Wordle 8777。出现 `address already in use` 时说明新服务没有启动成功；先识别现有进程，不要直接终止未知服务。改用新端口时必须同步修改 practice 和 eval 配置。

Wordle 还要检查 session 是否连续、seed 是否一致，以及每轮反馈是否被保留。

## SQLite 锁定或数据库过大

确认所有进程使用同一个预期的 `UTU_DB_URL`。避免多个高并发写进程同时操作同一 SQLite 文件；需要长期并行实验时改用独立数据库或 PostgreSQL。

WSL 中把 SQLite 放在 `/mnt/c`、`/mnt/d` 会明显变慢。建议将正式运行仓库和数据库放在 WSL 原生目录。

列出已有实验和数据集：

```bash
uv run python scripts/utils/view_results.py --list
uv run python scripts/utils/view_datasets.py
```

## 旧缓存与实验 ID

新代码、模型、数据或日期应使用新的 `exp_id`。结果异常时先确认是否读取了旧记录或 practice cache。不要直接删除数据库；先导出或备份相关结果，再使用项目清理工具按实验 ID 处理。

重新学习经验时，`--restart_step 0` 表示从第一步重新开始；省略时可能复用已有 cache。是否复用必须写入实验记录。

## Phoenix 警告

`PHOENIX_ENDPOINT or PHOENIX_PROJECT_NAME is not set` 只表示未启用 tracing，不会阻止普通训练和评估。只有需要链路追踪时才配置 `PHOENIX_*`。

## WSL 与 macOS

- WSL 无法访问 Docker 时，检查 Docker Desktop 的发行版 integration，而不是只检查 Windows 端 Docker。
- WSL 下 Windows 路径要转换为 `/mnt/<drive>/...`。
- Apple Silicon 上的 SkillsBench 镜像可能存在架构差异，只用于 smoke test；正式论文实验转到 Linux x86_64。

## 仍无法定位

保存完整命令、Git commit、配置 YAML、`exp_id`、错误堆栈、服务日志和一条失败样本。先构造单任务、`pass_k=1`、低并发复现，再判断问题属于 Agent、适配器还是基础设施。
