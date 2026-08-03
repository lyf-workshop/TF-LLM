# 部署指南

本文只说明所有数据集共用的首次安装。数据准备、经验学习和评估命令请进入对应的[数据集文档](datasets/index.md)。

## 环境要求

- Git、Bash 与可访问模型 endpoint 的网络。
- Python 3.10 及以上，推荐 3.12。
- 项目使用 `uv` 管理 Python 和依赖。
- SkillsBench 额外要求 Docker，并建议使用 Linux x86_64。
- 正式实验应使用固定模型版本，不能使用会静默升级的模型别名。

部署 profile：

| Profile | 用途 | 额外依赖 |
| --- | --- | --- |
| `core` | AIME、LiveCodeBench、WebWalkerQA、ZebraLogic | 无 |
| `korgym` | core 加三类 KORGym 游戏 | FastAPI、Uvicorn 等最小运行时 |
| `skillsbench` | core 加 SkillsBench | Docker、Harbor 0.3.0、固定外部仓库版本 |
| `all` | 安装全部支持 | 上述全部 |

## Linux

Ubuntu/Debian 首次安装：

```bash
sudo apt update
sudo apt install -y git curl build-essential

git clone --branch slim-research-baseline \
  https://github.com/lyf-workshop/TF-LLM.git
cd TF-LLM
bash scripts/setup/deploy.sh --profile core
```

SkillsBench 需要先安装并启动 Docker。Ubuntu 可使用发行版软件包：

```bash
sudo apt install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

重新登录 shell 使用户组生效，然后确认 Docker 可用并安装 SkillsBench profile：

```bash
docker info
bash scripts/setup/deploy.sh --profile skillsbench
```

部署脚本会安装 `uv`、Python、锁定依赖，并在缺少 `.env` 时从 `.env.example` 创建它。已有 `.env` 不会被覆盖。

## WSL2

先在 Windows 管理员终端安装 WSL2 与 Ubuntu：

```powershell
wsl --install -d Ubuntu
```

重启后进入 Ubuntu，执行与 Linux 相同的部署命令。若运行 SkillsBench，请安装 Docker Desktop，启用 WSL integration，并确认：

```bash
docker info
```

项目放在 `/mnt/c` 或 `/mnt/d` 可以运行，但 SQLite、大量小文件和 Docker build 通常更慢。长期正式实验建议把仓库放在 WSL 原生文件系统，例如 `~/projects/TF-LLM`。

## macOS

```bash
xcode-select --install

git clone --branch slim-research-baseline \
  https://github.com/lyf-workshop/TF-LLM.git
cd TF-LLM
bash scripts/setup/deploy.sh --profile core
```

KORGym 可使用：

```bash
bash scripts/setup/deploy.sh --profile korgym
```

SkillsBench 需要 Docker Desktop。已安装 Homebrew 时可执行：

```bash
brew install --cask docker
open -a Docker
docker info
bash scripts/setup/deploy.sh --profile skillsbench
```

等待 Docker Desktop 完成启动后再运行 `docker info`。Apple Silicon 可用于环境检查和小规模 smoke test；论文规模实验建议转到 Linux x86_64，以减少镜像架构和运行时差异。

## 配置密钥

编辑 `.env`，至少设置 `UTU_LLM_MODEL`、`UTU_LLM_BASE_URL` 和 `UTU_LLM_API_KEY`。不要把真实密钥提交到 Git。变量含义和可选服务见[配置参考](reference/configuration.md)。

## 环境检查

```bash
uv run python scripts/setup/check_environment.py \
  --profile core \
  --check-api
```

将 `core` 换成实际安装的 profile。检查成功后，再进入对应数据集文档执行实验。

## 更新环境

代码更新后，在仓库根目录执行：

```bash
git pull
uv sync --locked
```

只有 `pyproject.toml` 或 `uv.lock` 更新时才需要重新同步。KORGym 最小运行时可通过再次运行对应部署 profile 补齐。

## 正式运行前

记录 Git commit、模型 ID、endpoint、配置文件、数据集名和运行时间。先跑少量 smoke test，再提交高成本实验；正式对比不要复用旧 `exp_id`。
