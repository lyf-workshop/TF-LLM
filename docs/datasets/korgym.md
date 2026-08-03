# KORGym 总览

KORGym 将游戏封装为本地 HTTP 服务。TF-LLM 当前维护 Word Puzzle、Alphabetical Sorting 和 Wordle 三个实验入口；每个游戏使用独立数据、端口与文档。

## 安装与检查

```bash
bash scripts/setup/deploy.sh --profile korgym
uv run python scripts/setup/check_environment.py \
  --profile korgym \
  --check-api
```

## 约定表

| 游戏 | 目录 ID | 固定端口 | 交互方式 |
| --- | --- | --- | --- |
| [Word Puzzle](korgym-word-puzzle.md) | `8-word_puzzle` | 8775 | 单轮 |
| [Alphabetical Sorting](korgym-alphabetical-sorting.md) | `22-alphabetical_sorting` | 8776 | 单轮 |
| [Wordle](korgym-wordle.md) | `33-wordle` | 8777 | 最多 10 轮 |

这些名称与当前 `KORGym/game_lib/` 目录及 YAML 一致。旧文档中的 `2-alphabetical_sorting`、8780 或 Wordle 8765 均不再使用。

## 服务运行方式

在独立终端启动一个游戏服务并保持运行：

```bash
GAME_ID=8-word_puzzle
PORT=8775

uv run python scripts/korgym/start_korgym_server.py \
  $GAME_ID \
  --host 127.0.0.1 \
  --port $PORT
```

另一个终端执行数据准备、学习和评估。先检查端口与 API 文档：

```bash
ss -lntp | grep :$PORT
curl -f http://127.0.0.1:${PORT}/docs >/dev/null
```

如果端口已被其他用户或服务占用，不要杀掉未知进程。为本实验选择空闲端口时，还必须在该游戏的 practice 与 eval YAML 中同步修改 `game_port`，并保证两组一致。

## 公平对比

每个游戏都应复用 baseline eval 配置，只通过 `--agent_config` 注入经验。两组添加相同 `--agent_model`，并检查两个 Agent YAML 的 temperature、top-p、工具与最大轮数一致。

不要使用旧的 `*_practice_eval.yaml` 直接作为正式对照；其中部分配置和生成 Agent 已经与当前 practice 流程漂移。

## 服务错误

连接拒绝、端口错误、服务 5xx 和游戏进程退出属于基础设施错误，不应计为游戏失败。有效会话中模型给出非法动作、耗尽轮数或答案错误属于 Agent 失败。补跑前保存日志并确认服务仍对应正确游戏。
