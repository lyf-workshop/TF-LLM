"""Regression tests for interruptions during paid experience-generation stages."""

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError

from utu.db import EvaluationSample
from utu.practice.experience_updater import ExperienceUpdater, L0CandidateGenerationError
from utu.practice.generation_recovery import (
    GenerationOutputError,
    GenerationRecovery,
    GenerationServiceUnavailable,
    error_detail,
)


def validate(response):
    if not isinstance(response, str) or not response.strip():
        raise GenerationOutputError("empty response")


def client(responses):
    return SimpleNamespace(
        query_one=AsyncMock(side_effect=responses),
        default_config={"model": "test-model"},
        base_url="https://test.invalid/v1",
        api_key="test-credential",
        type="chat.completions",
    )


def request(text="task", stage="summary"):
    return {"request": {"messages": [{"role": "user", "content": text}]},
            "identity": {"stage": stage, "source_ids": ["trace-1"]}, "validate": validate}


@pytest.mark.asyncio
async def test_retries_connection_timeout_and_format_then_checkpoints(tmp_path):
    cache = tmp_path / "responses.sqlite3"
    llm = client([TimeoutError("timeout"), "", "summary"])
    recovery = GenerationRecovery(cache, retry_delay=0)
    assert await recovery.query(llm, **request()) == "summary"
    assert llm.query_one.await_count == 3
    assert await GenerationRecovery(cache).query(llm, **request()) == "summary"
    assert llm.query_one.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["prompt", "model", "endpoint", "language", "stage", "source", "fresh"])
async def test_checkpoint_never_reuses_changed_request(tmp_path, changed):
    cache = tmp_path / "responses.sqlite3"
    llm = client(["original", "new"])
    await GenerationRecovery(cache).query(llm, **request())
    args = request()
    if changed == "prompt":
        args["request"]["messages"][0]["content"] = "different task"
    elif changed == "model":
        llm.default_config = {"model": "new-model"}
    elif changed == "endpoint":
        llm.base_url = "https://other.invalid/v1"
    elif changed == "language":
        args["request"]["messages"].insert(0, {"role": "system", "content": "English only"})
    elif changed == "stage":
        args["identity"]["stage"] = "group_advantage"
    elif changed == "source":
        args["identity"]["source_ids"] = ["trace-2"]
    else:
        args["reuse_cache"] = False
    assert await GenerationRecovery(cache).query(llm, **args) == "new"
    assert llm.query_one.await_count == 2


@pytest.mark.asyncio
async def test_continuous_outage_stops_queued_calls_and_retains_completed_cache(tmp_path):
    cache = tmp_path / "responses.sqlite3"
    error = APIConnectionError(request=httpx.Request("POST", "https://test.invalid/v1"))
    llm = client(["saved"] + [error] * 20)
    recovery = GenerationRecovery(cache, retry_delay=0, failure_limit=2)
    await recovery.query(llm, **request("saved"))
    for i in range(2):
        with pytest.raises(APIConnectionError):
            await recovery.query(llm, **request(f"failing-{i}"))
    for i in range(20):
        with pytest.raises(GenerationServiceUnavailable):
            await recovery.query(llm, **request(f"queued-{i}"))
    assert llm.query_one.await_count == 7
    assert await recovery.query(llm, **request("saved")) == "saved"
    with sqlite3.connect(cache) as c:
        assert c.execute("SELECT count(*) FROM responses").fetchone() == (1,)


@pytest.mark.asyncio
async def test_authentication_failure_stops_without_retries(tmp_path):
    response = httpx.Response(401, request=httpx.Request("POST", "https://test.invalid/v1"))
    llm = client([AuthenticationError("invalid credentials", response=response, body=None)])
    recovery = GenerationRecovery(tmp_path / "responses.sqlite3", retry_delay=0)
    with pytest.raises(AuthenticationError):
        await recovery.query(llm, **request())
    with pytest.raises(GenerationServiceUnavailable):
        await recovery.query(llm, **request("another task"))
    assert llm.query_one.await_count == 1


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_cancellation_is_not_cached(tmp_path):
    async def hang(**kwargs):
        await asyncio.Event().wait()
    llm = client([])
    llm.query_one = AsyncMock(side_effect=hang)
    recovery = GenerationRecovery(tmp_path / "responses.sqlite3", request_timeout=0.01, max_attempts=2, retry_delay=0)
    with pytest.raises(TimeoutError):
        await recovery.query(llm, **request())
    assert llm.query_one.await_count == 2
    task = asyncio.create_task(recovery.query(llm, **request("cancelled")))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with sqlite3.connect(recovery.cache_path) as c:
        assert c.execute("SELECT count(*) FROM responses").fetchone() == (0,)


def make_updater(cache, llm):
    updater = ExperienceUpdater.__new__(ExperienceUpdater)
    updater.llm = llm
    updater.config = SimpleNamespace(model=SimpleNamespace(model_params=SimpleNamespace(model_dump=lambda: {})))
    updater.agent_objective = "solve"
    updater.learning_objective = "learn"
    updater.prompts = {
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_SP": "summarize",
        "SINGLE_ROLLOUT_SUMMARY_TEMPLATE_UP": "{{ question }} {{ reward }}",
        "SINGLE_QUERY_GROUP_ADVANTAGE_SP": "extract {{ num_experiences }} experiences",
        "SINGLE_QUERY_GROUP_ADVANTAGE_UP": "{{ question }} {{ trajectories }}",
    }
    updater.generation_recovery = GenerationRecovery(cache, retry_delay=0)
    return updater


@pytest.mark.asyncio
async def test_partial_summary_failure_resumes_only_missing_requests(tmp_path):
    cache = tmp_path / "responses.sqlite3"
    samples = [EvaluationSample(raw_question=f"task-{i}", trace_id=f"trace-{i}", reward=1) for i in range(2)]

    async def partial(**kwargs):
        if "task-1" in kwargs["messages"][1]["content"]:
            raise RuntimeError("unavailable")
        return "saved summary"

    updater = make_updater(cache, client([]))
    updater.llm.query_one.side_effect = partial
    with pytest.raises(L0CandidateGenerationError, match="refusing a partial candidate batch"):
        await updater._single_rollout_summary(samples, concurrency=1, given_ground_truth=False)
    resumed = make_updater(cache, client(["recovered summary"]))
    summaries = await resumed._single_rollout_summary(samples, concurrency=1, given_ground_truth=False)
    assert len(summaries) == 2
    assert resumed.llm.query_one.await_count == 1
    assert "task-1" in resumed.llm.query_one.call_args.kwargs["messages"][1]["content"]


@pytest.mark.asyncio
async def test_group_format_error_is_retried_before_any_candidates_are_returned(tmp_path):
    updater = make_updater(tmp_path / "responses.sqlite3", client([
        "missing required tags", "<Experiences></Experiences>",
        "<Experiences>Check boundary cases.</Experiences>",
    ]))
    groups = {"task": [{"raw_question": "task", "correct_answer": "answer", "reward": 1,
                        "trajectory_summary": "Checked boundaries", "trace_id": "trace-1"}]}
    result = await updater._group_advantage(groups, concurrency=1, given_ground_truth=True, num_experiences=1)
    assert result[0]["experiences"] == "Check boundary cases."
    assert updater.llm.query_one.await_count == 3
    resumed = make_updater(tmp_path / "responses.sqlite3", client([]))
    assert await resumed._group_advantage(groups, concurrency=1, given_ground_truth=True, num_experiences=1) == result
    resumed.llm.query_one.assert_not_called()


def test_error_diagnostics_preserve_causes_and_redact_credentials(monkeypatch):
    monkeypatch.setenv("UTU_LLM_API_KEY", "secret-value")
    cause = ConnectionError("Authorization: Bearer secret-value")
    error = RuntimeError("request failed")
    error.__cause__ = cause
    detail = error_detail(error)
    assert "ConnectionError" in detail
    assert "secret-value" not in detail


@pytest.mark.asyncio
async def test_repeated_invalid_output_is_not_checkpointed(tmp_path):
    cache = tmp_path / "responses.sqlite3"
    llm = client(["", "", ""])
    with pytest.raises(GenerationOutputError):
        await GenerationRecovery(cache, retry_delay=0).query(llm, **request())
    assert llm.query_one.await_count == 3
    with sqlite3.connect(cache) as c:
        assert c.execute("SELECT count(*) FROM responses").fetchone() == (0,)


@pytest.mark.asyncio
async def test_english_group_retries_wrong_language_before_checkpoint(tmp_path):
    updater = make_updater(tmp_path / "responses.sqlite3", client([
        "<Experiences>??????</Experiences>",
        "<Experiences>Check boundary conditions.</Experiences>",
    ]))
    updater.experience_output_language = "english"
    result = await updater._query_generation(
        stage="group_advantage", source_ids=["trace-1"], messages=[{"role": "user", "content": "summarize"}]
    )
    assert "Check boundary conditions" in result
    assert updater.llm.query_one.await_count == 2


@pytest.mark.asyncio
async def test_group_retries_when_one_candidate_is_symbol_only(tmp_path):
    updater = make_updater(tmp_path / "responses.sqlite3", client([
        "<Experiences>Valid English item\n2013</Experiences>",
        "<Experiences>Valid English item\nCheck the final answer.</Experiences>",
    ]))
    updater.experience_output_language = "english"
    result = await updater._query_generation(
        stage="group_advantage", source_ids=["trace-1"], messages=[{"role": "user", "content": "summarize"}]
    )
    assert "Check the final answer" in result
    assert updater.llm.query_one.await_count == 2
