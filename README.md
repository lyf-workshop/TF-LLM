# KORGym 游戏实验框架

基于 Training-Free GRPO 的知识导向推理游戏环境与分层经验学习系统

---


### 🎯 核心特性

- **🎮 KORGym 游戏集成**：支持 Word Puzzle、Alphabetical Sorting、Wordle 等推理游戏
- **🧠 分层经验学习**：实现 L0（案例级）→ L1（模式级）→ L2（元策略级）的自动化经验提取
- **💰 零参数更新训练**：基于 Training-Free GRPO，无需微调 LLM 即可提升性能
- **🔄 多轮交互支持**：完整支持 Wordle 等多轮对话游戏的评估与学习
- **📊 完整评估流程**：preprocess → rollout → judge → stat 四阶段自动化评估

---

## 🗂️ 项目结构

```
youtu-agent/
├── utu/                          # 核心代码库
│   ├── agents/                   # Agent 定义
│   ├── tools/                    # 工具集
│   ├── eval/                     # 评估系统
│   │   ├── benchmarks/           # 基准测试（含 KORGym 适配器）
│   │   └── processer/            # KORGym 结果处理器
│   └── practice/                 # 训练与经验学习
│       ├── training_free_grpo.py # GRPO 主流程
│       └── experience_updater.py # 分层经验生成
├── configs/                      # YAML 配置文件
│   ├── agents/practice/          # Agent 配置（含分层学习 Agent）
│   ├── eval/korgym/              # KORGym 评估配置
│   └── practice/                 # 训练配置
├── scripts/                      # 可执行脚本
│   ├── data/prepare_korgym_data.py  # KORGym 数据集准备
│   ├── run_eval.py                  # 评估脚本
│   └── run_training_free_GRPO.py    # 训练脚本
├── KORGym/                       # KORGym 游戏服务器
│   └── game_lib/                 # 游戏实现
│       ├── 8-word_puzzle/
│       ├── 22-alphabetical_sorting/
│       └── 33-wordle/
└── docs/                         # 项目文档
    └── korgym/                   # KORGym 专项文档
```

---

## 🚀 完整部署流程

> **从零开始**：假设你刚从 GitHub 克隆了这个项目，以下是完整的部署和运行步骤。

### 第一步：环境准备

#### 1.1 检查 Python 版本

**要求**: Python 3.12 或更高版本

```bash
# 检查 Python 版本
python --version   # Windows
python3 --version  # Linux/macOS
```

如果版本不符合要求，请先安装：
- **Windows**: 从 [python.org](https://www.python.org/downloads/) 下载安装
- **Linux**: `sudo apt install python3.12` (Ubuntu/Debian)
- **macOS**: `brew install python@3.12`

#### 1.2 克隆项目

```bash
# 克隆仓库
git clone https://github.com/your-username/your-repo.git
cd youtu-agent
```

### 第二步：安装所有依赖

#### 2.1 自动安装（推荐）

我们提供了一键安装脚本：

**Windows**:
```cmd
install_all_dependencies.bat
```

**Linux/WSL/macOS**:
```bash
chmod +x install_all_dependencies.sh
./install_all_dependencies.sh
```

脚本会自动完成：
- ✅ 安装 uv 包管理器
- ✅ 安装主项目依赖
- ✅ 安装 KORGym 游戏环境依赖
- ✅ 创建 .env 配置文件
- ✅ 验证安装结果

#### 2.2 手动安装

如果自动安装失败，可以手动执行：

```bash
# 1. 安装 uv 包管理器
pip install uv

# 2. 安装主项目依赖
uv sync

# 3. 激活虚拟环境
source .venv/bin/activate  # Linux/WSL/macOS
# 或
.venv\Scripts\activate     # Windows

# 4. 安装 KORGym 依赖
pip install -r KORGym/requirements.txt

# 5. 创建环境配置文件
cp .env.example .env
```

### 第三步：配置 API Keys

编辑 `.env` 文件，填入你的 LLM API Key：

```bash
# 必需配置
UTU_LLM_TYPE=chat.completions
UTU_LLM_MODEL=deepseek-chat  # 或其他模型
UTU_LLM_BASE_URL=https://api.deepseek.com/v1
UTU_LLM_API_KEY=your-api-key-here  # 替换为你的实际 API Key

# 可选配置（用于搜索功能）
SERPER_API_KEY=your-serper-key
JINA_API_KEY=your-jina-key

# 数据库配置（默认使用 SQLite）
UTU_DB_URL=sqlite:///test.db
```

**获取 API Key**:
- **DeepSeek**: https://platform.deepseek.com/ (推荐，性价比高)
- **OpenAI**: https://platform.openai.com/
- **其他**: 支持 OpenAI API 格式的任何服务

### 第四步：验证安装

运行环境检查脚本：

```bash
# 激活虚拟环境（如果还未激活）
source .venv/bin/activate  # Linux/WSL/macOS
# 或 .venv\Scripts\activate  # Windows

# 检查 KORGym 环境
python scripts/korgym/check_korgym_env.py
```

**预期输出**:
```
✓ Python 版本正确
✓ UTU 包可用
✓ Flask 已安装
✓ 游戏服务器可访问
```

如果有错误，请查看 [故障排除文档](docs/korgym/troubleshooting.md)。

### 第五步：运行第一个 KORGym 实验

现在可以开始运行你的第一个实验了！以 **Wordle** 游戏为例：

#### 5.1 启动游戏服务器

**打开第一个终端**，启动 Wordle 游戏服务器：

```bash
# 进入 Wordle 游戏目录
cd KORGym/game_lib/33-wordle

# 启动游戏服务器（端口 8777）
python game_lib.py -p 8777
```

**看到以下输出表示服务器启动成功**:
```
 * Running on http://127.0.0.1:8777
 * Running on http://0.0.0.0:8777
```

**保持这个终端运行**，不要关闭！

#### 5.2 准备数据集

**打开第二个终端**，回到项目根目录：

```bash
# 回到项目根目录
cd /path/to/youtu-agent

# 激活虚拟环境
source .venv/bin/activate  # Linux/WSL/macOS
# 或 .venv\Scripts\activate  # Windows

# 准备 Wordle 数据集（50 题评估 + 100 题训练）
uv run python scripts/data/prepare_korgym_data.py --game_name "33-wordle"
```

**预期输出**:
```
✓ 创建评估数据集: KORGym-Wordle-Eval-50 (50 题)
✓ 创建训练数据集: KORGym-Wordle-Train-100 (100 题)
```

#### 5.3 运行基线评估

```bash
# 运行基线评估（不使用任何经验）
uv run python scripts/run_eval.py --config_name korgym/wordle_eval
```

这将评估 Agent 在没有任何学习的情况下的表现。**评估可能需要 5-10 分钟**。

**完成后看到**:
```
✓ Evaluation completed
  Accuracy: 35.2%  # 示例结果
```

#### 5.4 运行训练（生成经验）

```bash
# 运行 Training-Free GRPO 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice
```

这将：
- 对每个训练样本生成多个候选答案
- 根据相对表现提取高质量经验
- 自动生成分层经验（L0/L1/L2）

**训练可能需要 15-30 分钟**，取决于训练集大小。

**完成后看到**:
```
✓ Training completed
  Generated experiences: 
    L0: 45 case-level experiences
    L1: 9 pattern-level experiences  
    L2: 3 meta-strategy experiences
```

#### 5.5 运行训练后评估

```bash
# 使用生成的经验重新评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval
```

#### 5.6 查看对比结果

```bash
# 对比训练前后的性能
uv run python scripts/korgym/view_korgym_results.py \
  wordle_baseline_eval \
  wordle_practice_eval
```

**预期输出**:
```
=== KORGym 结果对比 ===

wordle_baseline_eval:
  准确率: 35.2%
  平均分: 0.352

wordle_practice_eval:  
  准确率: 45.8%  ✓ 提升 +10.6%
  平均分: 0.458

🎉 训练后性能提升明显！
```

---

### 🎯 其他游戏快速开始

#### Word Puzzle

```bash
# 终端 1: 启动服务器
cd KORGym/game_lib/8-word_puzzle
python game_lib.py -p 8775

# 终端 2: 完整流程
uv run python scripts/data/prepare_korgym_data.py --game_name "8-word_puzzle"
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/word_puzzle_practice
uv run python scripts/run_eval.py --config_name korgym/word_puzzle_practice_eval
```

#### Alphabetical Sorting

```bash
# 终端 1: 启动服务器
cd KORGym/game_lib/22-alphabetical_sorting
python game_lib.py -p 8776

# 终端 2: 完整流程
uv run python scripts/data/prepare_korgym_data.py --game_name "22-alphabetical_sorting"
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_eval
uv run python scripts/run_training_free_GRPO.py --config_name korgym/alphabetical_sorting_practice
uv run python scripts/run_eval.py --config_name korgym/alphabetical_sorting_practice_eval
```

---

## 🎓 进阶：分层经验学习实验

完成 KORGym 游戏实验后，可以尝试更复杂的分层经验学习：

### ZebraLogic 逻辑推理任务

```bash
# 1. 准备 ZebraLogic 数据集
uv run python scripts/games/zebralogic/analyze_zebra_dataset.py

# 2. 训练（生成 L0/L1/L2 经验）
uv run python scripts/run_training_free_GRPO.py \
  --config_name medium_reasoning_hierarchical_num1

# 3. 评估
uv run python scripts/run_eval.py \
  --config_name logic/easy_practice_hierarchical_num1

# 4. 查看生成的经验
cat workspace/hierarchical_experiences/medium_reasoning_hierarchical_num3.json
```

### 理解生成的经验

训练完成后，你会在 `workspace/hierarchical_experiences/` 目录看到生成的经验文件：

```json
{
  "L0": [
    {
      "experience": "在猜测 'apple' 时...",
      "level": "case",
      "source": "problem_15"
    }
  ],
  "L1": [
    {
      "experience": "优先使用高频字母...",
      "level": "pattern",
      "aggregated_from": ["L0_1", "L0_2", ...]
    }
  ],
  "L2": [
    {
      "experience": "系统性地缩小可能空间...",
      "level": "meta-strategy"
    }
  ]
}
```

---

## 🎮 支持的 KORGym 游戏

| 游戏名称 | 游戏 ID | 端口 | 类型 | 最大回合 | 难度 |
|---------|---------|------|------|---------|------|
| **Word Puzzle** | `8-word_puzzle` | 8775 | 单轮 | 1 | 中等 |
| **Alphabetical Sorting** | `22-alphabetical_sorting` | 8776 | 单轮 | 1 | 简单 |
| **Wordle** | `33-wordle` | 8777 | 多轮 | 10 | 中等 |

### 游戏说明

- **Word Puzzle**：根据线索猜测单词，支持部分正确评分
- **Alphabetical Sorting**：将单词按字母顺序排序
- **Wordle**：经典猜词游戏，根据颜色反馈（绿/黄/灰）推理目标单词

---

## 🧠 分层经验学习系统

### 三层架构

```
L0（案例级）
  ↓ 每 5 个 L0 聚合
L1（模式级）
  ↓ 每 3 个 L1 + 源 L0 聚合
L2（元策略级）
```

- **L0**：从单个问题的成功/失败案例中提取具体教训
- **L1**：从 5 个 L0 案例中抽象出可复用的策略模式
- **L2**：从 3 个 L1 模式 + 对应的 L0 案例中提炼跨任务原则

### 关键创新

**L2 基于 L1+L0 双重输入**，避免过度抽象：
- 传统方法：`L2 = LLM(L1_batch)`
- 本系统：`L2 = LLM(L1_batch + source_L0)`
- 优势：保持原则的实用性和可解释性

### 配置示例

```yaml
# configs/practice/medium_reasoning_hierarchical_num1.yaml
hierarchical_learning:
  enabled: true
  l1_aggregation_threshold: 5    # 5 个 L0 → 1 个 L1
  l2_aggregation_threshold: 3    # 3 个 L1 → 1 个 L2
  max_l0_per_problem: 1
  max_l1_total: 50
  max_l2_total: 10
  include_l0_in_prompt: true     # Agent prompt 包含 L0
  max_l0_recent: 10
```

---

## 📊 实验结果

### KORGym 游戏性能提升

| 游戏 | 基线准确率 | 训练后准确率 | 提升 |
|------|-----------|-------------|------|
| Word Puzzle | 30-50% | 40-65% | **+10-15%** |
| Alphabetical Sorting | 70-85% | 80-95% | **+5-10%** |
| Wordle | 40-60% | 50-70% | **+10%** |

### 分层经验学习效果

- **Pass@1 提升**：5-15%（取决于任务复杂度）
- **跨难度迁移**：L2 经验在不同难度级别间展现更好的泛化能力
- **成本控制**：完整训练成本约 $8（基于 DeepSeek API）

---

## 📚 详细文档

- **KORGym 游戏指南**：[`docs/korgym/index.md`](docs/korgym/index.md)
- **分层经验学习指南**：[`分层经验学习-完整运行指南.md`](分层经验学习-完整运行指南.md)
- **三游戏命令速查**：[`KORGYM_THREE_GAMES_COMMANDS.md`](KORGYM_THREE_GAMES_COMMANDS.md)
- **故障排除**：[`docs/korgym/troubleshooting.md`](docs/korgym/troubleshooting.md)

---

## 🛠️ 配置文件模板

项目提供了完整的配置模板，可快速适配新游戏：

```bash
configs/eval/korgym/
├── TEMPLATE_korgym_game_eval.yaml           # 基线评估模板
└── TEMPLATE_korgym_game_practice_eval.yaml  # 训练后评估模板

configs/practice/
└── TEMPLATE_korgym_game_practice.yaml       # 训练配置模板

configs/agents/practice/
└── TEMPLATE_korgym_game_agent.yaml          # Agent 配置模板
```

查看 [`configs/eval/korgym/README_TEMPLATES.md`](configs/eval/korgym/README_TEMPLATES.md) 了解使用方法。

---

## 🧪 高级功能

### 1. 批量结果对比

```bash
# 对比多个实验结果
uv run python scripts/view_korgym_results.py \
  word_puzzle_baseline_eval \
  word_puzzle_practice_eval \
  --show-details
```

### 2. Wordle 前 20 题分析

```bash
# 针对 Wordle 的详细得分分析
uv run python scripts/analyze_wordle_top20.py \
  --exp_id wordle_practice_eval \
  --top_n 20
```

### 3. 自定义验证逻辑

```python
# utu/practice/verify/logic.py
def verify_answer(answer: str, ground_truth: str) -> tuple[bool, float]:
    """自定义验证逻辑"""
    # 实现你的验证代码
    return is_correct, score
```

---

## 🔧 常见部署问题

### Q1: `uv: command not found`

**原因**: uv 包管理器未安装

**解决**:
```bash
pip install uv
# 或者
pip3 install uv
```

### Q2: Python 版本过低

**错误**: `Python 3.11 detected, but 3.12+ is required`

**解决**: 升级 Python 到 3.12 或更高版本
- **Windows**: 从 [python.org](https://www.python.org/downloads/) 下载最新版
- **Linux**: `sudo apt install python3.12 python3.12-venv`
- **macOS**: `brew install python@3.12`

### Q3: 游戏服务器连接失败

**错误**: `Connection refused to http://localhost:8777`

**解决**:
1. 确认游戏服务器已启动：
   ```bash
   # Linux/WSL
   netstat -tuln | grep 8777
   
   # Windows
   netstat -an | findstr 8777
   ```
2. 检查服务器终端是否有错误信息
3. 确认端口未被占用：
   ```bash
   # 如果端口被占用，可以换一个端口
   python game_lib.py -p 8778
   # 然后在配置文件中也修改端口
   ```

### Q4: API Key 相关错误

**错误**: `AuthenticationError: Invalid API key`

**解决**:
1. 检查 `.env` 文件是否存在于项目根目录
2. 确认 `UTU_LLM_API_KEY` 已正确设置
3. 验证 API Key 的有效性（登录提供商网站检查）
4. 注意不要在 API Key 前后添加引号或空格

### Q5: 依赖安装失败

**错误**: `Failed to install package XXX`

**解决**:
```bash
# 清理并重新安装
rm -rf .venv
uv sync

# 如果还是失败，尝试单独安装问题包
pip install XXX

# 对于 KORGym 依赖
pip install -r KORGym/requirements.txt --no-cache-dir
```

### Q6: 训练过程中断

**原因**: 网络问题、API 限流、或超时

**解决**:
- 训练会自动保存进度到数据库
- 重新运行相同的训练命令即可继续
- 系统会跳过已完成的样本

### Q7: 内存不足

**错误**: `MemoryError` 或系统卡死

**解决**:
1. 减少并发数：在配置文件中设置 `rollout_concurrency: 2`
2. 减少训练集大小：`--train_count 50`
3. 使用更小的模型（如 7B 而不是 72B）

### Q8: 权限错误（Linux/WSL）

**错误**: `Permission denied`

**解决**:
```bash
# 给脚本添加执行权限
chmod +x install_all_dependencies.sh
chmod +x scripts/korgym/*.sh

# 如果虚拟环境无法激活
chmod +x .venv/bin/activate
```

更多问题请查看：
- 📖 [完整安装指南](INSTALLATION_GUIDE.md)
- 🔧 [故障排除文档](docs/korgym/troubleshooting.md)
- 💬 [GitHub Issues](https://github.com/your-repo/issues)

---

## 📖 引用

本项目基于以下研究：

```bibtex
@misc{training_free_grpo,
  title={Training-Free Group Relative Policy Optimization}, 
  author={Tencent Youtu Lab},
  year={2025},
  eprint={2510.08191},
  archivePrefix={arXiv},
  primaryClass={cs.CL},
  url={https://arxiv.org/abs/2510.08191}, 
}
```

---

## 🙏 致谢

本项目基于 [Tencent Youtu-Agent](https://github.com/TencentCloudADP/youtu-agent) 框架开发，感谢原作者团队的开源贡献。

核心依赖：
- [openai-agents](https://github.com/openai/openai-agents-python)
- [KORGym](https://github.com/microsoft/KORGym)（游戏环境）
- [DeepSeek](https://www.deepseek.com/)（推荐 LLM 后端）

---

## 📝 许可证

本项目遵循 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 🚀 快速索引

### 部署相关
- [📦 完整部署流程](#🚀-完整部署流程) - 从零开始的详细步骤
- [💾 安装所有依赖](#第二步安装所有依赖) - 一键安装脚本
- [🔑 配置 API Keys](#第三步配置-api-keys) - 必需的配置
- [✅ 验证安装](#第四步验证安装) - 检查环境是否正确

### 实验相关
- [🎮 运行第一个实验](#第五步运行第一个-korgym-实验) - Wordle 游戏完整流程
- [🎯 其他游戏](#🎯-其他游戏快速开始) - Word Puzzle, Alphabetical Sorting
- [🎓 进阶实验](#🎓-进阶分层经验学习实验) - ZebraLogic 逻辑推理

### 文档资源
- [📚 KORGym 游戏指南](docs/korgym/index.md) - 详细的游戏文档
- [🧠 分层经验学习](#🧠-分层经验学习系统) - 核心技术说明
- [🔧 常见问题](#🔧-常见部署问题) - 故障排除
- [📖 完整安装指南](INSTALLATION_GUIDE.md) - 深入的安装说明

**从克隆项目到运行第一个实验，只需 15 分钟！** 🎮🧠

---

*最后更新：2026-01-21*
