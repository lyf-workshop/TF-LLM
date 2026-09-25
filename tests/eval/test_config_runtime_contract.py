import asyncio
import inspect
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from utu.agents.orchestra_agent import OrchestraAgent
from utu.agents.orchestrator_agent import OrchestratorAgent
from utu.agents.workforce_agent import WorkforceAgent
from utu.config import AgentConfig, EvalConfig, ExperienceFilterConfig
from utu.config.agent_config import ToolkitConfig
from utu.config.eval_config import RecallConfig
from utu.config.model_config import ModelSettingsConfig
from utu.db import DatasetSample, EvaluationSample
from utu.eval.data.data_manager import (
    DATASET_SNAPSHOT_KEY,
    EVALUATION_IDENTITY_KEY,
    IDENTITY_SCHEMA_KEY,
    DBDataManager,
)
from utu.eval.experience_filter import ExperienceFilter
from utu.eval.experience_loader import ExperienceLoader
from utu.utils import SQLModelUtils


def _eval_config(tmp_path, *, exp_id="contract-test") -> EvalConfig:
    return EvalConfig(
        exp_id=exp_id,
        db_url=f"sqlite:///{tmp_path / (exp_id + '.db')}",
        data={"dataset": "unit-dataset"},
        agent={"agent": {"instructions": "base prompt"}},
    )


def _seed_dataset(config: EvalConfig) -> None:
    SQLModelUtils.configure(config.db_url)
    with SQLModelUtils.create_session() as session:
        session.add(
            DatasetSample(
                dataset=config.data.dataset,
                index=0,
                source="unit",
                question="question",
                answer="answer",
                meta={"task_id": "task-0"},
            )
        )
        session.commit()


def test_typed_configs_reject_unknown_fields_and_invalid_assignment():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvalConfig(data={"dataset": "x", "question_field": "legacy"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ModelSettingsConfig(temperature=0.0, misspelled_temperature=0.1)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExperienceFilterConfig(max_l0=1)

    config = EvalConfig(data={"dataset": "x"})
    with pytest.raises(ValidationError, match="greater_than"):
        config.concurrency = 0

    # Explicit extension dictionaries remain open for tool-specific options.
    toolkit = ToolkitConfig(config={"provider_private_option": {"anything": True}})
    assert toolkit.config["provider_private_option"]["anything"] is True


def test_recall_rejects_removed_bm25_alias():
    with pytest.raises(ValidationError, match="literal_error"):
        RecallConfig(method="bm25")


def test_static_filter_uses_recall_level_limits():
    instructions = """Base prompt.

When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:
[L2_one]. [L2-Meta] meta one
[L1_one]. [L1-Pattern] pattern one
[L1_two]. [L1-Pattern] pattern two
[L0_one]. [L0-Case] case one
[L0_two]. [L0-Case] case two
"""
    experience_filter = ExperienceFilter(
        ExperienceFilterConfig(
            enabled=True,
            strategy="static",
            recall={"max_l2": 1, "max_l1": 1, "max_l0": 1},
        )
    )

    base, selected = asyncio.run(
        experience_filter.apply_with_metadata(instructions, query="task")
    )

    assert [item.id for item in selected] == ["L2_one", "L1_one", "L0_one"]
    assert "[L1_two]" not in base


def test_llm_rerank_strategy_is_the_only_enable_switch():
    config = ExperienceFilterConfig(enabled=True, strategy="llm_rerank")
    assert config.llm_rerank.model
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ExperienceFilterConfig(
            enabled=True,
            strategy="llm_rerank",
            llm_rerank={"enabled": True},
        )


def test_missing_declared_experience_source_fails_closed(tmp_path):
    config = ExperienceFilterConfig(
        enabled=True,
        strategy="static",
        experience_source=str(tmp_path / "missing.json"),
    )
    with pytest.raises(FileNotFoundError, match="Refusing to evaluate"):
        ExperienceFilter(config)


@pytest.mark.asyncio
async def test_external_source_rejects_agent_with_baked_experiences(tmp_path):
    snapshot = tmp_path / "hierarchy.json"
    snapshot.write_text(
        json.dumps({"l0_experiences": [{"id": "L0_external", "content": "external"}]}),
        encoding="utf-8",
    )
    experience_filter = ExperienceFilter(
        ExperienceFilterConfig(
            enabled=True,
            strategy="static",
            experience_source=str(snapshot),
        )
    )
    baked = """Base prompt.

When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:
[L0_baked]. [L0-Case] Already injected."""

    with pytest.raises(ValueError, match="cannot be combined"):
        await experience_filter.apply(baked, query="task")


@pytest.mark.asyncio
async def test_external_source_rejects_training_free_grpo_three_zone_export(tmp_path):
    snapshot = tmp_path / "hierarchy.json"
    snapshot.write_text(
        json.dumps({"l0_experiences": [{"id": "L0_external", "content": "external"}]}),
        encoding="utf-8",
    )
    experience_filter = ExperienceFilter(
        ExperienceFilterConfig(
            enabled=True,
            strategy="static",
            experience_source=str(snapshot),
        )
    )
    exported = (
        "You have developed the following principles through experience "
        "completing similar tasks. Apply them proactively:\n"
        "- global principle\n\n"
        "Base prompt.\n\n"
        "Proven patterns from past tasks:\n"
        "- reusable pattern\n\n"
        "Specific lessons from recent tasks:\n"
        "- local lesson"
    )

    with pytest.raises(ValueError, match="cannot be combined"):
        await experience_filter.apply(exported, query="task")


@pytest.mark.asyncio
async def test_three_zone_export_requires_snapshot_for_per_query_filtering():
    exported = """Base prompt.

Proven patterns from past tasks:
- reusable pattern"""
    experience_filter = ExperienceFilter(
        ExperienceFilterConfig(enabled=True, strategy="retrieval")
    )

    with pytest.raises(ValueError, match="clean base agent plus experience_source"):
        await experience_filter.apply(exported, query="specific task")


def test_loader_excludes_provisional_upper_layers_but_keeps_active_l0(tmp_path):
    snapshot = tmp_path / "hierarchy.json"
    snapshot.write_text(
        json.dumps(
            {
                "l2_experiences": [
                    {
                        "id": "L2_provisional",
                        "content": "not ready",
                        "lifecycle_status": "active",
                        "validation_status": "provisional",
                    },
                    {
                        "id": "L2_validated",
                        "content": "ready",
                        "lifecycle_status": "active",
                        "validation_status": "validated",
                    },
                ],
                "l1_experiences": [
                    {
                        "id": "L1_provisional",
                        "content": "not ready",
                        "lifecycle_status": "active",
                        "validation_status": "provisional",
                    },
                    # Legacy upper records follow ExperienceRecord's explicit
                    # compatibility default and are treated as validated.
                    {"id": "L1_legacy", "content": "legacy", "lifecycle_status": "active"},
                ],
                "l0_experiences": [
                    {
                        "id": "L0_active",
                        "content": "case evidence",
                        "lifecycle_status": "active",
                        "validation_status": "provisional",
                    },
                    {
                        "id": "L0_inactive",
                        "content": "retired",
                        "lifecycle_status": "inactive",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = ExperienceLoader(snapshot).load()

    assert [item.id for item in loaded] == ["L2_validated", "L1_legacy", "L0_active"]


@pytest.mark.asyncio
async def test_enabled_filter_rejects_empty_treatment():
    experience_filter = ExperienceFilter(
        ExperienceFilterConfig(enabled=True, strategy="static")
    )
    with pytest.raises(ValueError, match="no injectable experiences"):
        await experience_filter.apply("base prompt")


@pytest.mark.asyncio
async def test_query_dependent_filter_rejects_missing_per_sample_query():
    instructions = """Base prompt.

When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:
[L0_one]. [L0-Case] Relevant case evidence."""
    experience_filter = ExperienceFilter(
        ExperienceFilterConfig(
            enabled=True,
            strategy="retrieval",
            retrieval_top_k=1,
        )
    )

    with pytest.raises(ValueError, match="non-empty per-sample query"):
        await experience_filter.apply(instructions, query="")


@pytest.mark.asyncio
async def test_llm_rerank_failure_does_not_silently_change_treatment(monkeypatch):
    from utu.eval.experience_filter import ParsedExperience
    from utu.eval.llm_experience_reranker import LLMExperienceReranker

    config = ExperienceFilterConfig(
        enabled=True,
        strategy="llm_rerank",
        llm_rerank={"final_top_k": 1},
    ).llm_rerank
    reranker = LLMExperienceReranker(config)

    async def fail(*_args, **_kwargs):
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(reranker, "_call_llm_reranker", fail)
    experiences = [
        ParsedExperience(id="L0_one", level="L0", content="evidence", order=0)
    ]

    with pytest.raises(RuntimeError, match="refusing to silently change"):
        await reranker.rerank("specific task", experiences)


@pytest.mark.asyncio
async def test_retrieval_is_per_sample_and_does_not_mutate_shared_config():
    from utu.eval.benchmarks.base_benchmark import BaseBenchmark

    instructions = """Base prompt.

When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:
[L0_cat]. [L0-Case] For feline questions, use cat whiskers and paws.
[L0_math]. [L0-Case] For algebra equations, isolate the variable carefully."""
    original_config = EvalConfig(
        data={"dataset": "unit"},
        agent={"agent": {"instructions": instructions}},
        experience_filter={
            "enabled": True,
            "strategy": "retrieval",
            "retrieval_top_k": 1,
            "retrieval_min_score": 0.01,
        },
    )
    benchmark = object.__new__(BaseBenchmark)
    benchmark.config = original_config.model_copy(deep=True)
    benchmark._base_agent_instructions = instructions
    benchmark.experience_filter = ExperienceFilter(benchmark.config.experience_filter)

    cat_sample = EvaluationSample(
        dataset="unit",
        dataset_index=0,
        raw_question="Which feline has whiskers and paws?",
    )
    math_sample = EvaluationSample(
        dataset="unit",
        dataset_index=1,
        raw_question="Solve this algebra equation for the variable.",
    )

    cat_agent, math_agent = await asyncio.gather(
        benchmark._agent_config_for_sample(cat_sample),
        benchmark._agent_config_for_sample(math_sample),
    )

    assert cat_sample.meta["injected_experience_ids"] == ["L0_cat"]
    assert math_sample.meta["injected_experience_ids"] == ["L0_math"]
    assert cat_sample.meta["experience_injected_prompt_sha256"]
    assert math_sample.meta["experience_injected_prompt_sha256"]
    assert (
        cat_sample.meta["experience_injected_prompt_sha256"]
        != math_sample.meta["experience_injected_prompt_sha256"]
    )
    assert "cat whiskers" in cat_agent.agent.instructions
    assert "algebra equations" not in cat_agent.agent.instructions
    assert "algebra equations" in math_agent.agent.instructions
    assert "cat whiskers" not in math_agent.agent.instructions
    assert original_config.agent.agent.instructions == instructions
    assert benchmark.config.agent.agent.instructions == instructions


@pytest.mark.asyncio
async def test_skillsbench_uses_the_same_per_sample_retrieval_contract():
    from utu.eval.benchmarks.base_benchmark import BaseBenchmark

    instructions = """Base prompt.

When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:
[L0_shell]. [L0-Case] For shell tasks, inspect files with command line tools.
[L0_sheet]. [L0-Case] For spreadsheet tasks, validate workbook formulas."""
    config = EvalConfig(
        data={"dataset": "skills"},
        agent={"agent": {"instructions": instructions}},
        skillsbench={"enabled": True},
        experience_filter={
            "enabled": True,
            "strategy": "retrieval",
            "retrieval_top_k": 1,
            "retrieval_min_score": 0.01,
        },
    )
    captured_prompts = []

    class Adapter:
        async def run_task(self, **kwargs):
            captured_prompts.append(kwargs["agent_instructions"])
            return SimpleNamespace(
                error="",
                trajectory="[]",
                agent_log="done",
                metadata={},
                outcome="success",
                reward=1.0,
                fatal=False,
                retryable=False,
                error_type=None,
                attempts=1,
            )

    benchmark = object.__new__(BaseBenchmark)
    benchmark.config = config.model_copy(deep=True)
    benchmark._base_agent_instructions = instructions
    benchmark._config_fingerprint = "config-fingerprint"
    benchmark._skillsbench_health_models = []
    benchmark._skillsbench_adapter = Adapter()
    benchmark._skillsbench_circuit_breaker = None
    benchmark.experience_filter = ExperienceFilter(benchmark.config.experience_filter)
    benchmark.dataset = SimpleNamespace(save=lambda _sample: None)
    shell_sample = EvaluationSample(
        dataset="skills",
        dataset_index=0,
        raw_question="Use shell command line tools to inspect these files.",
        augmented_question='{"experiences": {}, "inject_curated_skills": false}',
        meta={"task_path": "/task/shell", "task_id": "shell"},
    )
    sheet_sample = EvaluationSample(
        dataset="skills",
        dataset_index=1,
        raw_question="Repair spreadsheet workbook formulas.",
        augmented_question='{"experiences": {}, "inject_curated_skills": false}',
        meta={"task_path": "/task/sheet", "task_id": "sheet"},
    )

    await asyncio.gather(
        benchmark._rollout_skillsbench_harbor(shell_sample),
        benchmark._rollout_skillsbench_harbor(sheet_sample),
    )

    assert shell_sample.meta["injected_experience_ids"] == ["L0_shell"]
    assert sheet_sample.meta["injected_experience_ids"] == ["L0_sheet"]
    assert any("shell tasks" in prompt and "spreadsheet tasks" not in prompt for prompt in captured_prompts)
    assert any("spreadsheet tasks" in prompt and "shell tasks" not in prompt for prompt in captured_prompts)
    assert config.agent.agent.instructions == instructions


@pytest.mark.asyncio
async def test_skillsbench_rejects_ambiguous_double_experience_channel():
    from utu.eval.benchmarks.base_benchmark import BaseBenchmark

    benchmark = object.__new__(BaseBenchmark)
    benchmark.config = EvalConfig(
        data={"dataset": "skills"},
        agent={"agent": {"instructions": "base"}},
        skillsbench={"enabled": True},
        experience_filter={"enabled": True, "strategy": "static"},
    )
    benchmark._base_agent_instructions = "base"
    benchmark.experience_filter = ExperienceFilter(benchmark.config.experience_filter)
    benchmark.dataset = SimpleNamespace(save=lambda _sample: None)
    sample = EvaluationSample(
        dataset="skills",
        raw_question="task",
        augmented_question=json.dumps(
            {
                "experiences": {"L0_payload": "payload experience"},
                "inject_curated_skills": False,
            }
        ),
        meta={"task_path": "/task", "task_id": "task"},
    )

    with pytest.raises(ValueError, match="ambiguous double injection"):
        await benchmark._rollout_skillsbench_harbor(sample)


@pytest.mark.asyncio
async def test_filter_failure_does_not_write_partial_audit_metadata():
    from utu.eval.benchmarks.base_benchmark import BaseBenchmark

    class FailingFilter:
        async def apply_with_metadata(self, _instructions, *, query):
            raise RuntimeError(f"failed for {query}")

    benchmark = object.__new__(BaseBenchmark)
    benchmark.config = EvalConfig(data={"dataset": "unit"})
    benchmark._base_agent_instructions = "base"
    benchmark.experience_filter = FailingFilter()
    sample = EvaluationSample(dataset="unit", raw_question="task", meta={"existing": True})

    with pytest.raises(RuntimeError, match="failed for task"):
        await benchmark._filtered_instructions_for_sample(sample)

    assert sample.meta == {"existing": True}


def test_new_eval_rows_are_fingerprinted_and_matching_run_resumes(tmp_path):
    config = _eval_config(tmp_path)
    _seed_dataset(config)

    rows = DBDataManager(config).load()
    assert len(rows) == 1
    assert rows[0].meta[EVALUATION_IDENTITY_KEY]
    assert rows[0].meta[DATASET_SNAPSHOT_KEY]
    assert rows[0].meta[IDENTITY_SCHEMA_KEY]

    resumed = DBDataManager(config.model_copy(deep=True)).load()
    assert [row.id for row in resumed] == [rows[0].id]


def test_eval_cache_rejects_changed_prompt_under_same_exp_id(tmp_path):
    config = _eval_config(tmp_path)
    _seed_dataset(config)
    DBDataManager(config).load()

    changed = config.model_copy(deep=True)
    changed.agent.agent.instructions = "different prompt"
    with pytest.raises(ValueError, match="different evaluation config/model/prompt"):
        DBDataManager(changed).load()


def test_eval_cache_identity_binds_model_and_endpoint(tmp_path):
    config = _eval_config(tmp_path)
    config.agent.model.model_provider.model = "model-a"
    config.agent.model.model_provider.base_url = "https://endpoint-a.example/v1"
    _seed_dataset(config)
    DBDataManager(config).load()

    changed_model = config.model_copy(deep=True)
    changed_model.agent.model.model_provider.model = "model-b"
    with pytest.raises(ValueError, match="different evaluation config/model/prompt"):
        DBDataManager(changed_model).load()

    changed_endpoint = config.model_copy(deep=True)
    changed_endpoint.agent.model.model_provider.base_url = "https://endpoint-b.example/v1"
    with pytest.raises(ValueError, match="different evaluation config/model/prompt"):
        DBDataManager(changed_endpoint).load()


def test_legacy_eval_cache_requires_explicit_opt_in(tmp_path):
    config = _eval_config(tmp_path)
    _seed_dataset(config)
    rows = DBDataManager(config).load()
    rows[0].meta = {"task_id": "task-0", "trial_index": 0}
    DBDataManager(config).save(rows[0])

    with pytest.raises(ValueError, match="legacy rows without an evaluation fingerprint"):
        DBDataManager(config).load()

    config.allow_legacy_cache_reuse = True
    assert len(DBDataManager(config).load()) == 1


def test_all_benchmark_agents_accept_shared_run_logging_contract():
    for agent_type in (OrchestraAgent, OrchestratorAgent, WorkforceAgent):
        assert "log_to_db" in inspect.signature(agent_type.run).parameters


@pytest.mark.asyncio
async def test_benchmark_main_always_cleans_up(monkeypatch):
    from utu.eval.benchmarks import base_benchmark as benchmark_module

    benchmark = object.__new__(benchmark_module.BaseBenchmark)
    benchmark.config = SimpleNamespace(exp_id="cleanup-test", model_dump=lambda: {})
    cleanup_calls = []

    def fail_preprocess():
        raise RuntimeError("preprocess failed")

    async def cleanup():
        cleanup_calls.append(True)

    benchmark.preprocess = fail_preprocess
    benchmark.cleanup = cleanup
    monkeypatch.setattr(benchmark_module, "trace", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(benchmark_module, "gen_trace_id", lambda: "trace")

    with pytest.raises(RuntimeError, match="preprocess failed"):
        await benchmark.main()

    assert cleanup_calls == [True]


@pytest.mark.asyncio
async def test_rollout_cancels_sibling_tasks_on_base_exception():
    from utu.eval.benchmarks.base_benchmark import BaseBenchmark

    first = SimpleNamespace(raw_question="first")
    second = SimpleNamespace(raw_question="second")
    sibling_cancelled = asyncio.Event()
    benchmark = object.__new__(BaseBenchmark)
    benchmark.config = SimpleNamespace(concurrency=2)
    benchmark._skillsbench_adapter = None
    benchmark.dataset = SimpleNamespace(get_samples=lambda stage: [first, second])

    async def rollout_sample(sample):
        if sample is first:
            await asyncio.sleep(0)
            raise asyncio.CancelledError()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            sibling_cancelled.set()
            raise

    benchmark.rollout_sample = rollout_sample

    with pytest.raises(asyncio.CancelledError):
        await benchmark.rollout(max_retries=1)

    assert sibling_cancelled.is_set()


def test_workforce_assigner_uses_declared_assigner_model(monkeypatch):
    from utu.agents.workforce import assigner as assigner_module

    captured = {}

    class FakeLLM:
        def __init__(self, *, model_config):
            captured["model_config"] = model_config

    monkeypatch.setattr(assigner_module, "LLMAgent", FakeLLM)
    config = AgentConfig(
        workforce_planner_model={"model_provider": {"model": "planner"}},
        workforce_assigner_model={"model_provider": {"model": "assigner"}},
    )

    assigner_module.AssignerAgent(config)

    assert captured["model_config"] is config.workforce_assigner_model


@pytest.mark.asyncio
async def test_orchestra_planner_uses_declared_orchestra_model(monkeypatch):
    from utu.agents.orchestra import planner as planner_module
    from utu.agents.orchestra.common import OrchestraTaskRecorder

    captured = {}

    class FakeStream:
        final_output = (
            '<analysis>ok</analysis><plan>[{"agent_name": "worker", '
            '"task": "do it", "completed": false}]</plan>'
        )

        async def stream_events(self):
            if False:
                yield None

    class FakeLLM:
        def __init__(self, *, model_config, **_kwargs):
            captured["model_config"] = model_config

        def run_streamed(self, _input):
            return FakeStream()

    monkeypatch.setattr(planner_module, "LLMAgent", FakeLLM)
    config = AgentConfig(
        planner_model={"model_provider": {"model": "orchestra-planner"}},
        workforce_planner_model={"model_provider": {"model": "wrong-workforce-model"}},
        workers_info=[
            {
                "name": "worker",
                "desc": "worker",
                "strengths": "testing",
                "weaknesses": "none",
            }
        ],
    )
    planner = planner_module.PlannerAgent(config)

    await planner.create_plan(OrchestraTaskRecorder(task="task", trace_id="trace"))

    assert captured["model_config"] is config.planner_model


@pytest.mark.asyncio
async def test_korgym_multiround_timeout_is_enforced(monkeypatch, tmp_path):
    from utu.eval.benchmarks.base_benchmark import BaseBenchmark
    from utu.practice import korgym_adapter

    class SlowAdapter:
        def __init__(self, **_kwargs):
            pass

        async def play_game(self, _agent, _seed):
            await asyncio.sleep(0.1)

    monkeypatch.setattr(korgym_adapter, "KORGymAdapter", SlowAdapter)
    benchmark = object.__new__(BaseBenchmark)
    benchmark.config = _eval_config(tmp_path)
    benchmark.config.korgym.enabled = True
    benchmark.config.korgym.timeout_per_game = 0.01
    benchmark.dataset = SimpleNamespace(save=lambda _sample: None)
    sample = SimpleNamespace(
        meta={"seed": 1},
        update=lambda **values: sample.__dict__.update(values),
    )

    with pytest.raises(TimeoutError):
        await benchmark._rollout_korgym_multiround(object(), sample)

    assert not hasattr(sample, "response")
