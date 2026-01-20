# 多轮交互游戏评估系统改造 - Todo List 📋

## 🎯 目标

修改评估系统，使其支持多轮交互游戏（如Wordle），实现完整的多轮评估流程。

---

## 📊 问题分析总结

### 当前状态

| 组件 | 单轮游戏 | 多轮游戏 | 状态 |
|------|---------|---------|------|
| **训练-Rollout** | ✅ | ✅ | play_game()自动选择 |
| **训练-经验提取** | ✅ | ✅ | 多轮模板 |
| **评估-Preprocess** | ✅ | ✅ | 生成初始prompt |
| **评估-Rollout** | ✅ | ❌ | 只调用agent一次 |
| **评估-Judge** | ✅ | ❌ | 只验证一轮 |

### 核心问题

```python
# BaseBenchmark.rollout_one() - 第104行
async def rollout_one(self, sample: EvaluationSample):
    agent = get_agent(self.config.agent)
    result = await agent.run(sample.augmented_question, ...)  # ❌ 只调用一次
    sample.update(response=result.final_output, ...)  # ❌ 只有第一轮响应
    return sample

# KORGymProcesser.judge_one() - 第104行
async def judge_one(self, data: EvaluationSample):
    game_state = self.adapter.generate_game_instance(game_seed)
    action = self.adapter._extract_action(data.response)  # ❌ 只有第一轮action
    verified_state = self.adapter.verify_action(game_state)  # ❌ 只验证一轮
    score = verified_state.get('score', 0.0)
    return data
```

---

## ✅ Todo List

### 🔴 第1步：分析和设计 (已完成 ✅)

- [x] 分析当前评估流程的问题
- [x] 理解训练流程如何支持多轮游戏
- [x] 设计改造方案
- [x] 创建详细的Todo List

---

### 🟡 第2步：修改BaseBenchmark支持多轮游戏

**文件**: `utu/eval/benchmarks/base_benchmark.py`

**任务**:
- [ ] 在 `rollout_one()` 中检测游戏类型
- [ ] 对多轮游戏，使用 `KORGymAdapter.play_game()` 而不是 `agent.run()`
- [ ] 保存完整的多轮trajectory到 `sample.trajectories`
- [ ] 保存最终response和所有中间responses

**关键修改**:
```python
async def rollout_one(self, sample: EvaluationSample) -> EvaluationSample:
    agent = get_agent(self.config.agent)
    
    # ✅ 检查是否是KORGym多轮游戏
    if self._is_korgym_multiround(sample):
        # 使用KORGym adapter进行多轮交互
        result = await self._rollout_korgym_multiround(agent, sample)
    else:
        # 原有逻辑：单次调用
        trace_id = AgentsUtils.gen_trace_id()
        start_time = time.time()
        result = await agent.run(sample.augmented_question, trace_id=trace_id)
        end_time = time.time()
        
        sample.update(
            response=result.final_output,
            time_cost=end_time - start_time,
            trajectories=json.dumps(result.trajectories),
            stage="rollout"
        )
    
    self.dataset.save(sample)
    return sample
```

**预计时间**: 1-2小时

---

### 🟡 第3步：实现多轮rollout方法

**文件**: `utu/eval/benchmarks/base_benchmark.py`

**任务**:
- [ ] 创建 `_is_korgym_multiround()` 辅助方法
- [ ] 创建 `_rollout_korgym_multiround()` 方法
- [ ] 从sample.meta获取KORGym配置
- [ ] 初始化KORGymAdapter
- [ ] 调用 `adapter.play_game(agent, seed)`
- [ ] 格式化结果为EvaluationSample

**实现思路**:
```python
def _is_korgym_multiround(self, sample: EvaluationSample) -> bool:
    """检查是否是KORGym多轮游戏"""
    meta = sample.meta or {}
    if meta.get('game_name'):
        # 检查游戏类型
        from ...practice.korgym_adapter import KORGymGameClassifier
        game_type = KORGymGameClassifier.get_game_type(meta['game_name'])
        return game_type == 'multiple'
    return False

async def _rollout_korgym_multiround(self, agent, sample: EvaluationSample):
    """执行KORGym多轮游戏rollout"""
    from ...practice.korgym_adapter import KORGymAdapter
    
    # 从配置或meta获取KORGym参数
    korgym_config = self.config.korgym
    adapter = KORGymAdapter(
        game_name=korgym_config.game_name,
        game_host=korgym_config.game_host,
        game_port=korgym_config.game_port,
        level=korgym_config.level,
        max_rounds=korgym_config.max_rounds
    )
    
    # 获取seed
    meta = sample.meta or {}
    seed = meta.get('seed') or meta.get('game_seed')
    
    # 执行完整的多轮游戏
    start_time = time.time()
    result = await adapter.play_game(agent, seed)
    end_time = time.time()
    
    # 更新sample
    sample.update(
        response=result.get('responses', [''])[-1],  # 最后一轮响应
        time_cost=end_time - start_time,
        trajectories=json.dumps(result.get('trajectory', [])),
        meta={
            **meta,
            'game_result': result,
            'final_score': result.get('final_score', 0),
            'success': result.get('success', False),
            'rounds': result.get('rounds', 0)
        },
        stage="rollout"
    )
    
    return sample
```

**预计时间**: 2-3小时

---

### 🟡 第4步：修改KORGymProcesser.judge_one

**文件**: `utu/eval/processer/korgym_processor.py`

**任务**:
- [ ] 检测游戏类型（single vs multiple）
- [ ] 对多轮游戏，从meta读取已保存的game_result
- [ ] 直接使用已经得到的final_score和success
- [ ] 不需要重新验证（因为rollout阶段已经完整执行）

**关键修改**:
```python
async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
    if not self.adapter:
        return data
    
    meta = data.meta or {}
    
    # ✅ 检查是否是多轮游戏且已有结果
    if self.adapter.game_type == 'multiple' and 'game_result' in meta:
        # 多轮游戏：直接使用rollout阶段的结果
        game_result = meta['game_result']
        score = game_result.get('final_score', 0)
        success = game_result.get('success', False)
        rounds = game_result.get('rounds', 0)
        
        data.update(
            correct=success,
            reward=score,
            judged_response=f"Multi-round game: {rounds} rounds, Score: {score}",
            meta=meta
        )
        
        logger.debug(f"KORGym multi-round judged: seed={meta.get('seed')}, rounds={rounds}, score={score}")
        return data
    
    # 原有逻辑：单轮游戏
    game_seed = meta.get('game_seed') or meta.get('seed')
    # ... 原有代码 ...
```

**预计时间**: 1小时

---

### 🟢 第5步：测试和验证

**任务**:
- [ ] 创建测试脚本 `scripts/test_multiround_eval.py`
- [ ] 在Wordle游戏上测试2-3个样本
- [ ] 验证完整的多轮交互流程
- [ ] 验证final_score正确计算
- [ ] 验证trajectories正确保存

**测试脚本**:
```bash
# scripts/test_multiround_eval.py
# 测试2个Wordle样本的完整评估流程
uv run python scripts/test_multiround_eval.py \
  --game_name "33-wordle" \
  --seeds 1 2 \
  --config_name korgym/wordle_eval
```

**预计时间**: 1-2小时

---

### 🟢 第6步：完整评估测试

**任务**:
- [ ] 清理旧的Wordle评估数据
- [ ] 运行完整的Wordle基线评估（50个样本）
- [ ] 验证准确率 > 0%
- [ ] 运行训练
- [ ] 运行训练后评估
- [ ] 对比结果

**命令**:
```bash
# 清理
uv run python scripts/clean_experiment_data.py --exp_id wordle_baseline_eval wordle_practice_eval

# 基线评估
uv run python scripts/run_eval.py --config_name korgym/wordle_eval

# 训练
uv run python scripts/run_training_free_GRPO.py --config_name korgym/wordle_practice

# 训练后评估
uv run python scripts/run_eval.py --config_name korgym/wordle_practice_eval

# 查看结果
uv run python scripts/view_korgym_results.py --game wordle
```

**预计时间**: 3-4小时（包括训练时间）

---

### 🟢 第7步：文档更新

**任务**:
- [ ] 更新 `MULTI_ROUND_GAME_SUPPORT_ANALYSIS.md`
- [ ] 更新 `KORGYM_THREE_GAMES_COMMANDS.md`
- [ ] 创建 `MULTI_ROUND_EVAL_IMPLEMENTATION.md` 实现文档
- [ ] 添加多轮游戏评估的使用说明

**预计时间**: 30分钟

---

## 📊 工作量估算

| 阶段 | 任务 | 预计时间 | 优先级 |
|------|------|---------|--------|
| 第1步 | 分析设计 | ✅ 完成 | - |
| 第2步 | 修改BaseBenchmark | 1-2小时 | 🔴 高 |
| 第3步 | 实现多轮rollout | 2-3小时 | 🔴 高 |
| 第4步 | 修改judge方法 | 1小时 | 🔴 高 |
| 第5步 | 测试验证 | 1-2小时 | 🟡 中 |
| 第6步 | 完整测试 | 3-4小时 | 🟡 中 |
| 第7步 | 文档更新 | 30分钟 | 🟢 低 |
| **总计** | - | **9-12.5小时** | - |

---

## 🔑 关键决策

### 设计方案A: 最小侵入式修改（推荐）⭐

**优点**:
- 不破坏现有单轮游戏的评估
- 在BaseBenchmark层面添加分支逻辑
- 复用训练流程中的adapter代码

**缺点**:
- 在benchmark层面引入KORGym依赖
- 需要在多处检查游戏类型

### 设计方案B: 创建专用的多轮评估类

**优点**:
- 代码分离，不影响现有代码
- 可以针对多轮游戏优化

**缺点**:
- 需要创建新的benchmark类
- 代码重复较多
- 需要修改配置系统

### 推荐方案：**方案A + 渐进式改造**

1. 第一阶段：修改BaseBenchmark和KORGymProcesser（最小改动）
2. 第二阶段：验证Wordle能正常评估
3. 第三阶段：优化和重构（如果需要）

---

## 🚀 实施计划

### Phase 1: 核心功能实现（预计4-5小时）

- [ ] Task 2: 修改BaseBenchmark.rollout_one
- [ ] Task 3: 实现_rollout_korgym_multiround方法
- [ ] Task 4: 修改KORGymProcesser.judge_one

### Phase 2: 测试验证（预计1-2小时）

- [ ] Task 5: 创建测试脚本
- [ ] 小规模测试（2-3个样本）
- [ ] 验证多轮交互正确

### Phase 3: 完整测试（预计3-4小时）

- [ ] Task 6: 完整Wordle评估（50样本）
- [ ] 训练和对比测试
- [ ] 性能验证

### Phase 4: 文档和收尾（预计30分钟）

- [ ] Task 7: 更新文档
- [ ] 添加使用说明
- [ ] 创建示例

---

## 📝 技术细节

### 修改1: BaseBenchmark.rollout_one

```python
# 在 utu/eval/benchmarks/base_benchmark.py
async def rollout_one(self, sample: EvaluationSample) -> EvaluationSample:
    agent = get_agent(self.config.agent)
    if hasattr(agent, "build"):
        await agent.build()
    
    # ✅ 新增：检查是否是KORGym多轮游戏
    if self._should_use_korgym_multiround(sample):
        return await self._rollout_korgym_multiround(agent, sample)
    
    # 原有逻辑：单次rollout
    trace_id = AgentsUtils.gen_trace_id()
    start_time = time.time()
    result = await agent.run(sample.augmented_question, trace_id=trace_id)
    end_time = time.time()
    
    sample.update(
        trace_id=trace_id,
        response=result.final_output,
        time_cost=end_time - start_time,
        trajectories=json.dumps(result.trajectories, ensure_ascii=False),
        stage="rollout"
    )
    
    self.dataset.save(sample)
    return sample
```

### 修改2: 新增辅助方法

```python
def _should_use_korgym_multiround(self, sample: EvaluationSample) -> bool:
    """判断是否需要使用KORGym多轮模式"""
    # 检查是否有KORGym配置
    if not hasattr(self.config, 'korgym') or not self.config.korgym:
        return False
    
    # 检查是否启用
    if not self.config.korgym.enabled:
        return False
    
    # 检查游戏类型
    from ...practice.korgym_adapter import KORGymGameClassifier
    game_type = KORGymGameClassifier.get_game_type(self.config.korgym.game_name)
    return game_type == 'multiple'

async def _rollout_korgym_multiround(self, agent, sample: EvaluationSample):
    """执行KORGym多轮游戏的完整rollout"""
    from ...practice.korgym_adapter import KORGymAdapter
    
    # 初始化adapter
    korgym_config = self.config.korgym
    adapter = KORGymAdapter(
        game_name=korgym_config.game_name,
        game_host=korgym_config.game_host,
        game_port=korgym_config.game_port,
        level=korgym_config.level,
        max_rounds=korgym_config.max_rounds
    )
    
    # 获取seed
    meta = sample.meta or {}
    seed = meta.get('seed') or meta.get('game_seed', 0)
    
    # 执行完整游戏
    start_time = time.time()
    game_result = await adapter.play_game(agent, seed)
    end_time = time.time()
    
    # 更新sample
    sample.update(
        trace_id=game_result.get('round_id', ''),
        response=game_result.get('responses', [''])[-1] if game_result.get('responses') else '',
        time_cost=end_time - start_time,
        trajectories=json.dumps(game_result.get('trajectory', []), ensure_ascii=False),
        meta={
            **meta,
            'multiround_result': game_result,
            'final_score': game_result.get('final_score', 0),
            'success': game_result.get('success', False),
            'rounds': game_result.get('rounds', 0)
        },
        stage="rollout"
    )
    
    return sample
```

### 修改3: KORGymProcesser.judge_one

```python
# 在 utu/eval/processer/korgym_processor.py
async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
    if not self.adapter:
        return data
    
    meta = data.meta or {}
    
    # ✅ 新增：检查是否是多轮游戏且已有完整结果
    if self.adapter.game_type == 'multiple' and 'multiround_result' in meta:
        # 多轮游戏：直接使用rollout阶段已经得到的结果
        multiround_result = meta['multiround_result']
        
        score = multiround_result.get('final_score', 0)
        success = multiround_result.get('success', False)
        rounds = multiround_result.get('rounds', 0)
        
        data.update(
            correct=success,
            reward=float(score),
            judged_response=f"Multi-round game completed in {rounds} rounds. Score: {score}",
            meta=meta
        )
        
        logger.debug(f"KORGym multi-round judged: seed={meta.get('seed')}, rounds={rounds}, score={score}, success={success}")
        return data
    
    # 原有逻辑：单轮游戏
    game_seed = meta.get('game_seed') or meta.get('seed')
    # ... 保持原有代码 ...
```

---

## ✅ 验证标准

修改完成后，应该满足：

### 功能验证
- [ ] Wordle评估能完成10轮交互
- [ ] 最终score正确（0或1）
- [ ] trajectories包含所有轮次
- [ ] 不影响单轮游戏评估

### 性能验证
- [ ] 基线准确率 > 0%（预期8-15%）
- [ ] 训练后准确率更高（预期15-25%）
- [ ] 平均轮数合理（7-9轮）

### 代码验证
- [ ] 通过现有测试
- [ ] 无语法错误
- [ ] 日志输出清晰

---

## 🎯 开始实施

**当前状态**: Todo list已创建 ✅

**下一步**: 开始第2步 - 修改BaseBenchmark

**需要确认**:
1. 是否使用方案A（最小侵入式修改）？
2. 是否现在开始实施？
3. 是否需要先做小规模测试验证思路？

---

**准备开始实施吗？** 🚀



