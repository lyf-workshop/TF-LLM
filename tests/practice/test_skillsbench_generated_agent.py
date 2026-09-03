import ast
import asyncio
import json
from types import SimpleNamespace

import pytest

from utu.practice.skillsbench_adapter import SkillsBenchAdapter, _build_standalone_agent_source
from utu.practice.skillsbench_harbor_agent import TFLLMHarborAgent


class APIConnectionError(Exception):
    pass


class _AlwaysFailingCompletions:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        raise APIConnectionError("endpoint unavailable")


def test_generated_agent_uses_paper_runtime_settings():
    source = _build_standalone_agent_source(
        experiences_json="[]",
        inject_curated_skills=False,
        skills_text_json='""',
        model_name="deepseek-v4-pro",
        max_iterations=30,
        temperature=0.0,
        connect_timeout_sec=10,
        read_timeout_sec=120,
        llm_max_retries=4,
        retry_initial_delay_sec=2,
        retry_max_delay_sec=30,
    )

    compile(source, "<generated-skillsbench-agent>", "exec")
    assert "TEMPERATURE = 0.0" in source
    assert "CONNECT_TIMEOUT_SEC = 10.0" in source
    assert "READ_TIMEOUT_SEC = 120.0" in source
    assert "LLM_MAX_RETRIES = 4" in source
    assert "max_retries=0" in source
    assert "temperature=0.2" not in source
    assert "infra_error.json" in source


def test_generated_agent_treats_quota_exhaustion_as_fatal():
    source = _build_standalone_agent_source(
        experiences_json="[]",
        inject_curated_skills=False,
        skills_text_json='""',
        model_name="deepseek-v4-pro",
        max_iterations=30,
        temperature=0.0,
        connect_timeout_sec=10,
        read_timeout_sec=120,
        llm_max_retries=4,
        retry_initial_delay_sec=2,
        retry_max_delay_sec=30,
    )
    tree = ast.parse(source)
    classifier = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_classify_llm_error"
    )
    module = ast.fix_missing_locations(ast.Module(body=[classifier], type_ignores=[]))
    namespace: dict = {}
    exec(compile(module, "<generated-classifier>", "exec"), namespace)

    classification = namespace["_classify_llm_error"](
        RuntimeError("Error code: 405 - quota_not_enough")
    )
    assert classification == {
        "error_type": "api_configuration_error",
        "retryable": False,
        "fatal": True,
    }


@pytest.mark.asyncio
async def test_local_agent_retries_transient_request_with_bounded_backoff(tmp_path, monkeypatch):
    completions = _AlwaysFailingCompletions()
    llm = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("utu.practice.skillsbench_harbor_agent.asyncio.sleep", fake_sleep)
    agent = TFLLMHarborAgent(
        model_name="deepseek-v4-pro",
        logs_dir=tmp_path,
        temperature=0.0,
        llm_max_retries=4,
        retry_initial_delay_sec=1,
        retry_max_delay_sec=3,
    )

    with pytest.raises(RuntimeError, match="TFLLM_INFRA_ERROR"):
        await agent._create_completion_with_retry(
            llm=llm,
            messages=[],
            tools=[],
            context=SimpleNamespace(error_message=None),
            iteration=2,
        )

    payload = json.loads((tmp_path / "infra_error.json").read_text(encoding="utf-8"))
    assert completions.calls == 5
    assert sleeps == [1.0, 2.0, 3.0, 3.0]
    assert payload["error_type"] == "api_connection_error"
    assert payload["request_attempts"] == 5


@pytest.mark.asyncio
async def test_parent_cancellation_is_not_converted_to_task_timeout(monkeypatch):
    adapter = SkillsBenchAdapter(SimpleNamespace())

    async def wait_forever(**kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(adapter, "_run_with_harbor", wait_forever)
    task = asyncio.create_task(
        adapter._run_task_once(
            task_path="/tmp/test-task",
            experiences=None,
            inject_curated_skills=False,
            skills_text="",
            model_name="deepseek-v4-pro",
            timeout=600,
            max_iterations=30,
            model_temperature=0.0,
        )
    )
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
