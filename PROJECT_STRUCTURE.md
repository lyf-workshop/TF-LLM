# 项目结构说明

本项目是 **youtu-agent** 框架，核心是 **Training-Free GRPO（无梯度经验学习）** 算法：通过让 LLM 在任务上多次采样、对比好坏轨迹来提取经验，无需微调即可提升 Agent 性能。

---

## 整体架构

```
Configs（实验配置）→ utu/（核心实现）→ scripts/（运行入口）→ workspace/（运行产物）
```

---

## 根目录文件

| 文件 | 说明 |
|------|------|
| `README.md` | 项目总览：KORGym、Training-Free GRPO、层级经验机制、目录结构 |
| `pyproject.toml` | 包名 `youtu-agent`，依赖声明（litellm、search、e2b、documents 等可选组） |
| `install_all_dependencies.sh` | 自动安装 Python/uv 及项目依赖（含 KORGym）|
| `setup_korgym_wsl.sh` | WSL 下 KORGym 环境配置脚本 |
| `activate_korgym.sh` | 激活 KORGym 用的 `.venv` 虚拟环境 |
| `env_siliconflow.template` | `.env` 模板，包含 `UTU_LLM_*` 等环境变量示例 |
| `INSTALLATION_GUIDE.md` | 安装说明 |
| `CONTRIBUTING.md` | 贡献指南 |
| `CHANGELOG.md` | 版本变更记录 |

---

## `utu/` — 核心 Python 包

### `utu/__init__.py`
包入口，初始化日志、环境检查、OpenTelemetry tracing，并替换 OpenAI Agents SDK 的默认运行器为 `UTUAgentRunner`。

---

### `utu/agents/` — Agent 实现

| 文件 | 说明 |
|------|------|
| `__init__.py` | 导出 `get_agent()`，根据 `config.type` 分发到对应 Agent 类 |
| `simple_agent.py` | 基础 Agent：单一角色，工具从 config 注入 |
| `llm_agent.py` | 最简 LLM wrapper，只负责调用 LLM 并返回结果 |
| `orchestra_agent.py` | 多角色协同（规划者/执行者/汇报者）模式 |
| `orchestrator_agent.py` | 链式 Orchestrator 模式，多步推理 |
| `workforce_agent.py` | 多 Agent 流水线（规划→分配→执行→汇总）|
| `common.py` | Agent 共用工具类和辅助函数 |
| `orchestra/` | Orchestra 模式的子组件（planner、worker、reporter）|
| `orchestrator/` | Orchestrator 模式的子组件（chain 执行）|
| `workforce/` | Workforce 各角色实现（planner、assigner、executor、answerer）|

---

### `utu/config/` — 配置模型

| 文件 | 说明 |
|------|------|
| `loader.py` | Hydra `compose` 加载器，将 `configs/` YAML 解析为 Pydantic 对象 |
| `base_config.py` | 所有配置类的基础 Pydantic mixin |
| `agent_config.py` | Agent 配置：指令、工具、模型绑定 |
| `model_config.py` | 模型提供商、参数、温度等配置 |
| `eval_config.py` | 评估配置：数据集、并发、KORGym/SkillsBench 块、经验过滤 |
| `practice_config.py` | Training-Free GRPO 训练参数：epoch、batch、grpo_n 等 |

---

### `utu/db/` — 数据持久化

| 文件 | 说明 |
|------|------|
| `db_service.py` | CRUD 封装，`@require_db` 装饰器，支持无 DB 降级 |
| `utu_basemodel.py` | SQLModel 基类 |
| `eval_datapoint.py` | `EvaluationSample`、`DatasetSample` ORM 模型（评估核心数据表）|
| `trajectory_model.py` | Agent 轨迹存储模型 |
| `experience_cache_model.py` | 经验缓存表，避免重复计算 |
| `tool_cache_model.py` | 工具调用结果缓存 |
| `grpo_run_log_model.py` | GRPO 训练过程日志表 |
| `tracing_model.py` | Tracing 数据持久化模型 |

---

### `utu/eval/` — 评估框架

#### `utu/eval/benchmarks/`

| 文件 | 说明 |
|------|------|
| `base_benchmark.py` | **核心评估循环**：`preprocess → rollout → judge → stat`，含 SkillsBench Harbor 执行路径和经验过滤入口 |

#### `utu/eval/processer/` — 各数据集处理器

| 文件 | 说明 |
|------|------|
| `base_processor.py` | 所有处理器基类，定义 preprocess/judge/stat 接口 |
| `base_llm_processor.py` | 用 LLM 做裁判的处理器基类 |
| `base_match_processor.py` | 字符串匹配式裁判的处理器基类 |
| `gaia.py` | GAIA 基准数据集处理器 |
| `web_walker.py` | WebWalker 网页问答数据集处理器 |
| `xbench.py` | XBench 基准处理器 |
| `browse_comp.py` | BrowseComp 浏览器推理基准处理器 |
| `korgym_processor.py` | KORGym 游戏评估处理器（HTTP 游戏服务器通信）|
| `skillsbench_processor.py` | SkillsBench 任务评估处理器（Harbor 沙箱，按 domain/difficulty 统计）|
| `training_free_grpo_processor.py` | Training-Free GRPO 训练数据的处理器路径 |
| `__init__.py` | 注册 `PROCESSER_FACTORY`，将数据集名映射到对应处理器类 |

#### 其他 eval 文件

| 文件 | 说明 |
|------|------|
| `experience_filter.py` | 从经验库中过滤/重排最相关经验，注入到 Agent 指令 |
| `experience_loader.py` | 加载已有经验文件供评估使用 |
| `llm_experience_reranker.py` | 用 LLM 对候选经验进行重排序 |
| `data/data_manager.py` | 将数据集样本加载到 DB，供 `BaseBenchmark` 使用 |

---

### `utu/practice/` — Training-Free GRPO 核心

| 文件 | 说明 |
|------|------|
| `training_free_grpo.py` | **主控流程**：`build → practice（rollout+经验提取）→ 输出带经验的 agent YAML` |
| `rollout_manager.py` | 批次 rollout 管理：将数据集按 batch 分发，并发执行，收集结果 |
| `data_manager.py` | 训练数据加载：支持 pass_k 扩倍、Mistake Bank 采样、epoch 隔离 |
| `experience_updater.py` | **4 步经验提取流水线**：单轨迹摘要 → 组间对比 → 组级更新 → 批量合并 |
| `hierarchical_experience_manager.py` | **层级经验管理**：L0（案例）→ L1（模式）→ L2（元策略），含去重和自动聚合 |
| `experience_retriever.py` | 经验检索：BM25/静态等策略，供注入 prompt 使用 |
| `mistake_bank.py` | Mistake Bank：记录失败任务，下一 epoch 优先重训 |
| `korgym_adapter.py` | 桥接 TF-LLM 与 KORGym HTTP 游戏服务器，驱动多轮游戏 |
| `korgym_experience_extractor.py` | 从 KORGym 游戏轨迹中提取文字经验 |
| `skillsbench_adapter.py` | 桥接 TF-LLM 与 Harbor/SkillsBench：在 Docker 沙箱中运行任务，解析 reward |
| `skillsbench_harbor_agent.py` | Harbor 侧 Agent：实现 `BaseAgent` 接口，驱动 LLM 通过 bash_execute 完成任务 |
| `utils.py` | `TaskRecorder`：记录训练过程中的经验、统计、状态 |
| `verify/` | 各任务类型的验证函数（skillsbench、korgym、logic、math、webwalker）|

---

### `utu/tools/` — 工具库

| 文件/目录 | 说明 |
|-----------|------|
| `base.py` | `AsyncBaseToolkit` 基类，`@register_tool` 装饰器 |
| `search_toolkit.py`, `serper_toolkit.py` | 搜索工具（Google/Bing/Serper）|
| `search/` | 各搜索引擎实现（Google、百度、DuckDuckGo、Jina）|
| `bash_toolkit.py` | Bash 执行工具 |
| `python_executor_toolkit.py` | Python 代码执行工具 |
| `file_edit_toolkit.py` | 文件 SEARCH/REPLACE 编辑工具 |
| `document_toolkit.py` | 文档 QA 工具（PyMuPDF/Chunkr）|
| `image_toolkit.py`, `audio_toolkit.py`, `video_toolkit.py` | 多媒体处理工具 |
| `wikipedia_toolkit.py`, `arxiv_toolkit.py`, `github_toolkit.py` | 外部知识源工具 |
| `tabular_data_toolkit.py` | 表格数据处理工具 |
| `memory_toolkit.py` | 记忆/召回工具 |
| `thinking_toolkit.py` | 显式思考/草稿本工具 |
| `local_env/` | 工具的本地执行后端（bash、python、file edit）|

---

### `utu/env/` — 执行环境

| 文件 | 说明 |
|------|------|
| `base_env.py` | 执行环境抽象接口（shell、browser、sandbox）|
| `browser_env.py`, `browser_env_e2b.py` | 浏览器自动化环境（本地/E2B）|
| `e2b_env.py` | E2B 代码沙箱环境 |
| `shell_local_env.py` | 本地 Shell 执行环境 |
| `utils/docker_manager.py` | Docker 容器管理 |
| `utils/mcp_client.py` | MCP 协议客户端 |

---

### `utu/patch/`

| 文件 | 说明 |
|------|------|
| `runner.py` | `UTUAgentRunner`：替换 OpenAI Agents SDK 默认 Runner，增加上下文注入、token 限制终止等自定义行为 |

---

### `utu/utils/` — 通用工具

| 文件 | 说明 |
|------|------|
| `env.py` | 环境变量读取、校验 |
| `log.py` | 日志初始化（按模块分级）|
| `path.py` | 项目根路径 `DIR_ROOT` 等常量 |
| `sqlmodel_utils.py` | DB 可用性检测、SQLModel engine 管理 |
| `experience_cache.py` | 经验缓存读写（按 exp_id+step 去重）|
| `tool_cache.py` | 工具调用结果缓存 |
| `openai_utils/` | 轻量 OpenAI 客户端封装 (`SimplifiedAsyncOpenAI`)，含重试逻辑 |
| `agents_utils.py` | Agent 运行辅助（trace ID 生成等）|
| `token.py` | Token 计数工具 |
| `llm_output_parser.py` | LLM 输出解析工具 |
| `grpo_logger.py` | GRPO 训练过程专用日志 |

---

### `utu/tracing/` — 链路追踪

| 文件 | 说明 |
|------|------|
| `setup.py` | 初始化 OpenTelemetry / Phoenix tracing |
| `otel_agents_instrumentor.py` | 自动为 Agent 运行注入 OTEL span |
| `phoenix_utils.py` | Arize Phoenix 集成工具 |
| `db_tracer.py` | 将 trace 数据持久化到 DB |

---

### `utu/prompts/` — Prompt 资产

| 目录/文件 | 说明 |
|-----------|------|
| `practice/experience.yaml` | 经验提取 4 步流水线的所有 prompt 模板（单轨迹摘要、组间对比、组级更新、批量合并）|
| `practice/processor.yaml` | 训练流程中数据预处理/裁判用 prompt |
| `practice/verify.yaml` | 任务验证相关 prompt |
| `eval/judge_templates.yaml` | 各基准的 LLM 裁判 prompt 模板 |
| `eval/augmentation_templates.yaml` | 数据增强 prompt 模板 |
| `agents/workforce/*.yaml` | Workforce 各角色系统 prompt |
| `agents/orchestra/planner.yaml` | Orchestra 规划者 prompt |
| `agents/orchestrator/chain.yaml` | Orchestrator 链式推理 prompt |
| `meta/` | 工具/Agent 自动生成 prompt |

---

## `configs/` — 实验配置

所有 `.yaml` 文件通过 Hydra 组合加载，约 250+ 个文件，每个是一个具体实验的预设。

### `configs/model/`
默认模型参数（base URL、model name、temperature 等）。

### `configs/tools/`
各工具包配置（search、bash、browser、MCP server 地址等）。

### `configs/agents/`

| 子目录 | 说明 |
|--------|------|
| `simple/` | 基础 Agent 预设（搜索、GAIA、文档、代码）|
| `practice/` | 训练用 Agent（KORGym 各游戏、SkillsBench，含层级经验注入版本）|
| `examples/` | 演示 Agent（GAIA、RAG、MCP、邮件、PPT 等）|
| `orchestra/`, `orchestrator/`, `workforce/` | 多 Agent 协同预设 |
| `exp/` | 实验性 Agent 基础配置 |

### `configs/eval/`

| 子目录 | 说明 |
|--------|------|
| `skillsbench/` | SkillsBench 评估：`baseline`（无经验）、`with_skills`（注入官方 Skills）、`practice`（注入 TF-GRPO 经验）|
| `korgym/` | KORGym 各游戏评估（Wordle、word puzzle、alphabetical sorting 等）|
| `logic/` | Zebralogic 逻辑推理评估 |
| `math/` | AIME 数学评估 |
| `web/` | WebWalker/BrowseComp 网页基准 |
| `data/` | 数据集指针（GAIA、XBench 等）|

### `configs/practice/`

| 子目录 | 说明 |
|--------|------|
| `skillsbench/skillsbench_practice.yaml` | SkillsBench TF-GRPO 训练：epoch/batch/grpo_n/层级经验参数 |
| `korgym/` | KORGym 各游戏的 TF-GRPO 训练配置 |
| `logic/` | 逻辑推理训练配置 |
| `math/`, `web/` | 数学/网页训练配置 |

### `configs/prompts/`

| 文件 | 说明 |
|------|------|
| `hierarchical_critique.yaml` | L1/L2 层级经验聚合所用的 LLM prompt（L1 从 L0 提炼模式，L2 从 L1 提炼元策略）|

---

## `scripts/` — 运行入口与工具脚本

### 核心入口

| 文件 | 说明 |
|------|------|
| `run_eval.py` | 评估入口：加载 `EvalConfig`，运行 `BaseBenchmark`（支持 `all`/`rollout`/`judge` 阶段）|
| `run_training_free_GRPO.py` | 训练入口：运行 `TrainingFreeGRPO.run()`，产出带经验的 agent YAML |
| `cli_chat.py`, `chat_ui.py` | 交互式对话前端 |

### `scripts/data/` — 数据准备

| 文件 | 说明 |
|------|------|
| `prepare_skillsbench_data.py` | 扫描 SkillsBench 仓库，按 train/eval 比例分割，写入 DB |
| `prepare_korgym_data.py` | KORGym 游戏数据集初始化 |
| `prepare_zebralogic_*.py` | Zebralogic 逻辑数据集准备 |
| `process_gaia.py` | GAIA 数据集预处理 |
| `download_dataset.py`, `upload_dataset.py` | 数据集上传/下载工具 |

### `scripts/korgym/` — KORGym 运维

| 文件 | 说明 |
|------|------|
| `start_korgym_server.py` | 启动 KORGym HTTP 游戏服务器 |
| `run_korgym_eval.py` | 一键运行 KORGym 评估 |
| `compare_korgym_*.py` | 对比实验结果与论文基准 |
| `view_korgym_results.py` | 查看 KORGym 评估结果 |
| `test_korgym_*.py` | 服务器/适配器连通性测试 |

### `scripts/utils/` — 结果查看

| 文件 | 说明 |
|------|------|
| `view_eval_results.py` | 通用评估结果查看（准确率、Pass@K、对比）|
| `view_training_results.py` | 训练过程结果查看 |
| `view_evaluation_details.py` | 逐题详细结果查看 |
| `analyze_hierarchical_experiences.py` | 分析 L0/L1/L2 经验库内容 |
| `check_model_config.py` | 验证模型配置是否正确 |

### `scripts/db/`

| 文件 | 说明 |
|------|------|
| `dump_db.py` | 导出 DB 数据为 JSON |
| `clear_cache.py` | 清理工具/经验缓存 |

### `scripts/view_skillsbench_results.py`
SkillsBench 专用结果查看脚本：按 domain/difficulty 分类统计，支持多实验对比、失败任务列表、榜单定位。

---

## `workspace/` — 运行时产物

| 路径 | 说明 |
|------|------|
| `workspace/hierarchical_experiences/*.json` | Training-Free GRPO 产出的层级经验文件（L0/L1/L2），每个实验一个文件，被下一次评估加载注入到 Agent |
| `workspace/mistake_bank/*.json` | Mistake Bank 快照，记录各任务失败历史，供下一 epoch 优先重训 |

---

## 数据流总览

```
scripts/data/prepare_*.py
    ↓ 写入 DB（DatasetSample 表）
configs/practice/*.yaml
    ↓ Hydra 加载为 TrainingFreeGRPOConfig
scripts/run_training_free_GRPO.py
    ↓ TrainingFreeGRPO.run()
        ↓ RolloutManager：批次并发 rollout（Docker/游戏服务器）
        ↓ ExperienceUpdater：4 步 LLM 提炼经验
        ↓ HierarchicalExperienceManager：L0→L1→L2 聚合
        ↓ 产出：workspace/hierarchical_experiences/*.json
              + configs/agents/practice/*_agent.yaml（含经验的 Agent 配置）
configs/eval/skillsbench/skillsbench_practice_eval.yaml
    ↓ 加载带经验的 Agent 配置
scripts/run_eval.py
    ↓ BaseBenchmark：preprocess→rollout→judge→stat
        ↓ SkillsBenchProcesser：Harbor Docker 沙箱执行，读取 reward
scripts/view_skillsbench_results.py
    ↓ 查看/对比实验结果
```
