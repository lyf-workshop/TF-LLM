"""
SkillsBench Adapter for TF-LLM.

This adapter is the bridge between TF-LLM's rollout/evaluation pipeline and
harbor's task execution engine.  It mirrors the role that ``korgym_adapter.py``
plays for KORGym games, but instead of talking to a Flask HTTP game server it
drives harbor's Python API (or falls back to the harbor CLI subprocess).

Public interface
----------------
    adapter = SkillsBenchAdapter(config)
    result  = await adapter.run_task(task_path, experiences, inject_curated_skills)
    # result.reward       – float from /logs/verifier/reward.txt (or reward.json)
    # result.trajectory   – JSON string for TF-LLM's trajectories field
    # result.agent_log    – raw stdout / stderr of the agent for experience extraction

Harbor execution strategy
--------------------------
1. **Python API** (preferred): ``import harbor`` and call
   ``harbor.runner.TaskRunner().run(...)`` programmatically.  This keeps
   everything in-process and avoids subprocess overhead.
2. **CLI subprocess** (fallback): if harbor's Python API is not importable,
   falls back to ``harbor trials start -p <task_path> -a <agent_file>:<class>``
   and parses the resulting reward file from the log directory.

The active strategy is detected at first use.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..skillsbench_reliability import (
    OUTCOME_FATAL_ERROR,
    OUTCOME_INFRA_ERROR,
    OUTCOME_TASK_TIMEOUT,
    OUTCOME_VALID,
    TRANSIENT_API_ERROR_TYPES,
    classify_infra_error,
    redact_command,
)
from ..utils import DIR_ROOT, get_logger

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is provided by Hydra in normal runs.
    yaml = None

logger = get_logger(__name__)

_HARBOR_COMPAT_VERSION = "v3-tests-mount-logs"


@dataclass
class SkillsBenchResult:
    """Result of a single SkillsBench task execution."""

    reward: float | None = None
    """Score from the task verifier (0.0 = fail, 1.0 = full pass, partial possible)."""
    trajectory: str = ""
    """JSON-serialised list of steps for TF-LLM's ``trajectories`` field."""
    agent_log: str = ""
    """Raw agent stdout/stderr for debugging and experience extraction."""
    error: str = ""
    """Non-empty if the run failed for infrastructure reasons."""
    outcome: str = OUTCOME_VALID
    """One of valid, infra_error, task_timeout, or fatal_error."""
    error_type: str = ""
    retryable: bool = False
    fatal: bool = False
    attempts: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    elapsed_sec: float = 0.0


def _try_import_harbor():
    """Return harbor's TaskRunner class, or None if harbor is not installed."""
    try:
        from harbor.runner import TaskRunner  # type: ignore[import]
        return TaskRunner
    except ImportError:
        return None


def _build_standalone_agent_source(
    experiences_json: str,
    inject_curated_skills: bool,
    skills_text_json: str,
    model_name: str,
    max_iterations: int,
    agent_instructions_json: str = '""',
    temperature: float = 0.0,
    connect_timeout_sec: float = 10.0,
    read_timeout_sec: float = 120.0,
    llm_max_retries: int = 4,
    retry_initial_delay_sec: float = 2.0,
    retry_max_delay_sec: float = 30.0,
) -> str:
    """
    Generate a fully self-contained Python source file for the harbor agent.

    The generated file must NOT import anything from ``utu`` because harbor
    runs inside its own isolated Python environment (installed via
    ``uv tool install harbor``) that only ships ``openai`` and standard-lib.

    Skills alignment with official benchflow (``bench run --skills-dir``):
    - Skills text is base64-encoded here and embedded as a constant in the
      generated file.
    - ``setup()`` decodes it and writes /app/SKILLS.md inside the container
      before the agent starts, so the agent reads it on demand via bash.
    - The system prompt only contains a brief nudge (not the full text).
    """
    import base64 as _b64

    # Pre-encode skills at generation time; avoids complex escaping in the template.
    skills_raw: str = json.loads(skills_text_json) if skills_text_json and skills_text_json != '""' else ""
    skills_b64: str = _b64.b64encode(skills_raw.encode("utf-8")).decode() if skills_raw else ""

    # The setup() method in the generated code will reference the module-level
    # SKILLS_B64 constant.  The write command passes it as a CLI arg to python3
    # so there are no shell-escaping issues (base64 chars are shell-safe).
    setup_body = (
        "        if INJECT_CURATED_SKILLS and SKILLS_B64:\n"
        "            cmd = (\n"
        "                \"python3 -c 'import base64, sys;\"\n"
        "                \" open(\\\"/app/SKILLS.md\\\", \\\"wb\\\").write(\"\n"
        "                \"base64.b64decode(sys.argv[1]))' \"\n"
        "                + SKILLS_B64\n"
        "            )\n"
        "            try:\n"
        "                await environment.exec(cmd, timeout_sec=30)\n"
        "            except Exception:\n"
        "                pass\n"
    )

    return f'''\
"""Auto-generated self-contained TFLLMHarborAgent for harbor CLI."""
import json, os, asyncio, base64, re
from pathlib import Path
from openai import AsyncOpenAI
from httpx import Timeout
from harbor.agents.base import BaseAgent
from harbor.models.trial.result import AgentInfo, ModelInfo

EXPERIENCES = {experiences_json}
INJECT_CURATED_SKILLS = {inject_curated_skills}
SKILLS_B64 = "{skills_b64}"
MODEL_NAME = "{model_name}"
MAX_ITERATIONS = {max_iterations}
AGENT_INSTRUCTIONS = {agent_instructions_json}
TEMPERATURE = {float(temperature)!r}
CONNECT_TIMEOUT_SEC = {float(connect_timeout_sec)!r}
READ_TIMEOUT_SEC = {float(read_timeout_sec)!r}
LLM_MAX_RETRIES = {max(0, int(llm_max_retries))}
RETRY_INITIAL_DELAY_SEC = {max(0.0, float(retry_initial_delay_sec))!r}
RETRY_MAX_DELAY_SEC = {max(0.0, float(retry_max_delay_sec))!r}

BASH_TOOL = {{
    "type": "function",
    "function": {{
        "name": "bash_execute",
        "description": "Execute a bash command inside the task environment.",
        "parameters": {{
            "type": "object",
            "properties": {{
                "command": {{"type": "string", "description": "The bash command to execute."}}
            }},
            "required": ["command"],
        }},
    }},
}}

TASK_COMPLETE_TOOL = {{
    "type": "function",
    "function": {{
        "name": "task_complete",
        "description": "Call when you have finished the task.",
        "parameters": {{
            "type": "object",
            "properties": {{
                "summary": {{"type": "string", "description": "Brief summary."}}
            }},
            "required": ["summary"],
        }},
    }},
}}


def _build_system_prompt():
    # When agent_instructions are provided (eval mode: baked experiences live in
    # the agent YAML), use them as the system prompt base instead of the generic
    # fallback. The EXPERIENCES dict (training mode) is still appended on top.
    if AGENT_INSTRUCTIONS:
        parts = [AGENT_INSTRUCTIONS]
    else:
        parts = [
            "You are an expert software engineer operating inside an isolated Linux "
            "environment. Complete the task by executing bash commands step-by-step. "
            "When done, call task_complete(). Verify results before finishing."
        ]
    if EXPERIENCES:
        fmt = "\\n".join(f"[{{k}}] {{v}}" for k, v in EXPERIENCES.items())
        parts.append("\\n--- Past Experiences ---\\n" + fmt + "\\n--- End ---")
    if INJECT_CURATED_SKILLS and SKILLS_B64:
        parts.append(
            "\\n--- Curated Skills ---\\n"
            "A curated skill guide has been written to /app/SKILLS.md.\\n"
            "Read it before starting: cat /app/SKILLS.md\\n"
            "--- End of Curated Skills ---"
        )
    return "\\n".join(parts)


TRANSIENT_ERROR_TYPES = {{"api_connection_error", "api_timeout", "api_rate_limit", "api_5xx"}}


def _classify_llm_error(error):
    name = type(error).__name__.lower()
    text = str(error).lower()
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    quota_markers = (
        "quota_not_enough",
        "insufficient_quota",
        "insufficient quota",
        "quota exceeded",
        "quota exhausted",
        "insufficient balance",
        "balance not enough",
        "billing hard limit",
        "credit balance",
        "\\u4f59\\u989d\\u4e0d\\u8db3",
    )
    if status == 402 or any(marker in text for marker in quota_markers):
        return {{"error_type": "api_configuration_error", "retryable": False, "fatal": True}}
    if "apiconnectionerror" in name or "connection error" in text:
        return {{"error_type": "api_connection_error", "retryable": True, "fatal": False}}
    if "apitimeouterror" in name or "request timed out" in text or "read timeout" in text:
        return {{"error_type": "api_timeout", "retryable": True, "fatal": False}}
    if "ratelimiterror" in name or status == 429 or "rate limit" in text:
        return {{"error_type": "api_rate_limit", "retryable": True, "fatal": False}}
    if (isinstance(status, int) and 500 <= status <= 599) or "internalservererror" in name:
        return {{"error_type": "api_5xx", "retryable": True, "fatal": False}}
    if status in {{400, 401, 403, 404, 405, 422}} or any(
        token in name for token in ("authenticationerror", "badrequesterror", "notfounderror")
    ):
        return {{"error_type": "api_configuration_error", "retryable": False, "fatal": True}}
    return {{"error_type": "api_unknown_error", "retryable": False, "fatal": False}}


async def _completion_with_retry(client, kwargs, logs_dir, context, iteration):
    for retry_index in range(LLM_MAX_RETRIES + 1):
        try:
            return await client.chat.completions.create(**kwargs)
        except Exception as error:
            classification = _classify_llm_error(error)
            can_retry = (
                classification["error_type"] in TRANSIENT_ERROR_TYPES
                and retry_index < LLM_MAX_RETRIES
            )
            if can_retry:
                delay = min(RETRY_INITIAL_DELAY_SEC * (2 ** retry_index), RETRY_MAX_DELAY_SEC)
                headers = getattr(getattr(error, "response", None), "headers", {{}}) or {{}}
                retry_after = headers.get("retry-after") if hasattr(headers, "get") else None
                try:
                    delay = max(delay, float(retry_after)) if retry_after is not None else delay
                except (TypeError, ValueError):
                    pass
                print(
                    "LLM transient error " + classification["error_type"]
                    + f"; retry {{retry_index + 1}}/{{LLM_MAX_RETRIES}} in {{delay:.1f}}s",
                    flush=True,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                continue

            payload = {{
                "error_type": classification["error_type"],
                "message": str(error)[:1000],
                "retryable": classification["retryable"],
                "fatal": classification["fatal"],
                "request_attempts": retry_index + 1,
                "iteration": iteration,
            }}
            try:
                (logs_dir / "infra_error.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError:
                pass
            try:
                context.error_message = payload["message"]
            except (AttributeError, ValueError):
                if not hasattr(context, "metadata") or context.metadata is None:
                    context.metadata = {{}}
                context.metadata["infra_error"] = payload
            raise RuntimeError(
                "TFLLM_INFRA_ERROR:" + json.dumps(payload, ensure_ascii=True)
            ) from error
    raise AssertionError("unreachable LLM retry loop")


class TFLLMHarborAgent(BaseAgent):
    """Self-contained harbor BaseAgent for TF-LLM."""
    SUPPORTS_ATIF = False

    def __init__(self, logs_dir=None, model_name=None, **kwargs):
        super().__init__(logs_dir=Path(logs_dir) if logs_dir else Path("/tmp/tfllm_agent_logs"),
                         model_name=model_name or MODEL_NAME, **kwargs)
        self._llm = None

    @staticmethod
    def name():
        return "tfllm-harbor-agent"

    def version(self):
        return "1.0.0"

    async def setup(self, environment):
        """Write skills file into container before agent starts (mirrors benchflow --skills-dir)."""
{setup_body}
    async def run(self, instruction, environment, context):
        if self._llm is None:
            self._llm = AsyncOpenAI(
                api_key=os.getenv("UTU_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
                base_url=os.getenv("UTU_LLM_BASE_URL", os.getenv("OPENAI_BASE_URL")),
                timeout=Timeout(READ_TIMEOUT_SEC, connect=CONNECT_TIMEOUT_SEC),
                max_retries=0,
            )

        system_prompt = _build_system_prompt()
        messages = [
            {{"role": "system", "content": system_prompt}},
            {{"role": "user", "content": instruction}},
        ]
        tools = [BASH_TOOL, TASK_COMPLETE_TOOL]
        commands_executed = 0
        trajectory = []
        actual_models = []

        for i in range(MAX_ITERATIONS):
            resp = await _completion_with_retry(
                self._llm,
                {{
                    "model": self.model_name or MODEL_NAME,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": TEMPERATURE,
                    "max_completion_tokens": 4096,
                }},
                self.logs_dir,
                context,
                i,
            )
            response_model = getattr(resp, "model", None)
            if response_model and response_model not in actual_models:
                actual_models.append(str(response_model))

            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_unset=True))

            if not msg.tool_calls:
                break

            done = False
            for tc in msg.tool_calls:
                fn = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{{}}")
                except json.JSONDecodeError:
                    args = {{}}

                if fn == "task_complete":
                    messages.append({{"role": "tool", "tool_call_id": tc.id, "content": "Done."}})
                    trajectory.append({{"iter": i, "type": "done", "summary": args.get("summary", "")}})
                    done = True
                elif fn == "bash_execute":
                    cmd = args.get("command", "")
                    try:
                        r = await environment.exec(cmd, timeout_sec=120)
                        out = (r.stdout or "")[:4000]
                        err = (r.stderr or "")[:2000]
                        rc = r.return_code
                        content = f"exit_code={{rc}}\\n{{out}}"
                        if err:
                            content += f"\\nstderr:\\n{{err}}"
                    except Exception as ex:
                        content = f"exec error: {{ex}}"
                        rc = -1
                    messages.append({{"role": "tool", "tool_call_id": tc.id, "content": content}})
                    commands_executed += 1
                    trajectory.append({{"iter": i, "type": "bash", "cmd": cmd[:200], "rc": rc}})
                else:
                    messages.append({{"role": "tool", "tool_call_id": tc.id, "content": f"Unknown: {{fn}}"}})

            if done:
                break

        # Save trajectory to agent logs dir (harbor mounts this as /logs/agent/)
        try:
            (self.logs_dir / "agent_trajectory.json").write_text(
                json.dumps(trajectory, ensure_ascii=False, indent=2)
            )
        except OSError:
            pass

        # Populate AgentContext with valid harbor fields only
        context.metadata = {{
            "commands_executed": commands_executed,
            "iterations_used": len(trajectory),
            "requested_model": self.model_name or MODEL_NAME,
            "actual_models": actual_models,
            "temperature": TEMPERATURE,
        }}
        try:
            (self.logs_dir / "agent_run_metadata.json").write_text(
                json.dumps(context.metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
'''


class SkillsBenchAdapter:
    """
    Adapter that runs a SkillsBench task with the TFLLMHarborAgent and
    returns a structured result the TF-LLM pipeline can consume.
    """

    def __init__(self, config: Any | None = None) -> None:
        """
        Args:
            config: ``SkillsBenchConfig`` Pydantic object (from EvalConfig).
                    Falls back to sensible defaults if None.
        """
        self._config = config
        self._harbor_available: bool | None = None  # detected on first use
        self._tasks_completed: int = 0  # counter for builder-prune interval

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_task(
        self,
        task_path: str,
        experiences: dict[str, str] | None = None,
        inject_curated_skills: bool = False,
        skills_text: str = "",
        model_name: str | None = None,
        timeout_sec: int | None = None,
        max_iterations: int | None = None,
        agent_instructions: str = "",
        model_temperature: float = 0.0,
    ) -> SkillsBenchResult:
        """
        Run a single SkillsBench task and return the reward.

        Args:
            task_path: Absolute path to the task directory in the SkillsBench repo.
            experiences: Dict of TF-LLM experience strings to inject into the agent.
            inject_curated_skills: Whether to inject curated Skills from ``skills_text``.
            skills_text: The curated Skills text to inject (if enabled).
            model_name: LLM model name override.
            timeout_sec: Per-task wall-clock timeout in seconds.
            max_iterations: Maximum bash-tool iterations for the agent.
            agent_instructions: Full agent instructions (with baked experiences) to
                use as the system prompt base. Used in eval mode where experiences
                are stored in the agent YAML rather than the experiences dict.

        Returns:
            ``SkillsBenchResult`` with reward, trajectory, logs.
        """
        task_path = self._ensure_harbor_compat_task(task_path)
        cfg = self._config
        _timeout = timeout_sec or (getattr(cfg, "task_timeout_sec", None) or 600)
        _max_iter = max_iterations or (getattr(cfg, "max_agent_iterations", None) or 30)
        _model = model_name or os.getenv("UTU_LLM_MODEL", "deepseek-chat")
        _temperature = float(model_temperature)

        max_retries = getattr(cfg, "max_retries", 0) or 0
        retry_delay = getattr(cfg, "retry_delay_sec", None)
        if retry_delay is None:
            retry_delay = 5.0
        retry_on_timeout = getattr(cfg, "retry_on_timeout", False)

        task_name = Path(task_path).name
        attempt = 0
        result = SkillsBenchResult(
            outcome=OUTCOME_INFRA_ERROR,
            error="no attempt made",
            error_type="adapter_not_started",
            retryable=True,
        )
        while True:
            attempt += 1
            result = await self._run_task_once(
                task_path=task_path,
                experiences=experiences,
                inject_curated_skills=inject_curated_skills,
                skills_text=skills_text,
                model_name=_model,
                timeout=_timeout,
                max_iterations=_max_iter,
                agent_instructions=agent_instructions,
                model_temperature=_temperature,
            )
            result.attempts = attempt

            # Stop when we have a usable result or have exhausted retries.
            if attempt > max_retries:
                break
            if not self._is_retryable_error(result, retry_on_timeout):
                break

            logger.warning(
                f"Task {task_name} attempt {attempt}/{max_retries + 1} hit an "
                f"infrastructure error; retrying in {retry_delay:.0f}s. "
                f"Error: {(result.error or '')[:200]}"
            )
            # Clear potentially corrupted Docker state before the next attempt
            # (a half-built image/container can otherwise poison the retry).
            if getattr(cfg, "docker_cleanup_after_task", True):
                await self._docker_cleanup(prune_builder=False)
            if retry_delay > 0:
                await asyncio.sleep(retry_delay)

        if attempt > 1:
            outcome = "succeeded" if result.outcome in {OUTCOME_VALID, OUTCOME_TASK_TIMEOUT} else "still failing"
            logger.info(
                f"Task {task_name} {outcome} after {attempt} attempt(s); "
                f"reward={result.reward}"
            )

        # Post-task Docker cleanup to prevent ext4.vhdx from growing unboundedly.
        self._tasks_completed += 1
        if getattr(cfg, "docker_cleanup_after_task", True):
            prune_builder_every = getattr(cfg, "docker_cleanup_builder_every_n", 10)
            do_builder = (
                prune_builder_every > 0
                and self._tasks_completed % prune_builder_every == 0
            )
            await self._docker_cleanup(prune_builder=do_builder)

        return result

    async def health_check(
        self,
        *,
        model_name: str,
        temperature: float = 0.0,
        attempts: int | None = None,
    ) -> list[str]:
        """Require successful lightweight requests before measured trials."""

        import httpx
        from openai import AsyncOpenAI

        cfg = self._config
        required = max(1, int(attempts or getattr(cfg, "healthcheck_attempts", 3)))
        client = AsyncOpenAI(
            api_key=os.getenv("UTU_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            base_url=os.getenv("UTU_LLM_BASE_URL", os.getenv("OPENAI_BASE_URL")),
            timeout=httpx.Timeout(
                getattr(cfg, "llm_read_timeout_sec", 120.0),
                connect=getattr(cfg, "llm_connect_timeout_sec", 10.0),
            ),
            max_retries=0,
        )
        actual_models: list[str] = []
        try:
            for probe_index in range(required):
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": "Reply with OK."}],
                    temperature=float(temperature),
                    max_completion_tokens=8,
                )
                actual = str(getattr(response, "model", "") or model_name)
                actual_models.append(actual)
                logger.info(
                    "SkillsBench endpoint probe %s/%s succeeded (model=%s)",
                    probe_index + 1,
                    required,
                    actual,
                )
        finally:
            await client.close()
        return actual_models

    # ------------------------------------------------------------------
    # SkillsBench v1.1 -> legacy harbor compatibility
    # ------------------------------------------------------------------

    @staticmethod
    def _split_task_md(task_md: Path) -> tuple[dict[str, Any], str]:
        """Parse BenchFlow-native task.md into frontmatter and instruction body."""
        text = task_md.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}, text.strip()
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text.strip()
        frontmatter = parts[1].strip()
        body = parts[2].strip()
        if yaml is None:
            return {}, body
        try:
            return yaml.safe_load(frontmatter) or {}, body
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to parse task.md frontmatter for {task_md}: {exc}")
            return {}, body

    @staticmethod
    def _toml_value(value: Any) -> str:
        """Serialize a small TOML value set needed by legacy harbor."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return "[" + ", ".join(SkillsBenchAdapter._toml_value(v) for v in value) + "]"
        return json.dumps("" if value is None else str(value))

    @staticmethod
    def _legacy_task_toml(frontmatter: dict[str, Any]) -> str:
        """Generate the legacy task.toml expected by harbor 0.x."""
        metadata = frontmatter.get("metadata") or {}
        verifier = frontmatter.get("verifier") or {}
        agent = frontmatter.get("agent") or {}
        environment = frontmatter.get("environment") or {}

        category = metadata.get("category") or metadata.get("domain") or "general"
        tags = metadata.get("tags") or []
        network_mode = str(environment.get("network_mode", "")).lower()
        allow_internet = network_mode not in {"none", "disabled", "offline"}

        lines = [
            'version = "1.0"',
            "",
            "[metadata]",
            f"author_name = {SkillsBenchAdapter._toml_value(metadata.get('author_name', ''))}",
            f"author_email = {SkillsBenchAdapter._toml_value(metadata.get('author_email', ''))}",
            f"difficulty = {SkillsBenchAdapter._toml_value(metadata.get('difficulty', 'medium'))}",
            f"category = {SkillsBenchAdapter._toml_value(category)}",
            f"tags = {SkillsBenchAdapter._toml_value(tags)}",
            "",
            "[verifier]",
            f"timeout_sec = {SkillsBenchAdapter._toml_value(verifier.get('timeout_sec', 900.0))}",
            "",
            "[agent]",
            f"timeout_sec = {SkillsBenchAdapter._toml_value(agent.get('timeout_sec', 1800.0))}",
            "",
            "[environment]",
            f"build_timeout_sec = {SkillsBenchAdapter._toml_value(environment.get('build_timeout_sec', 600.0))}",
            f"cpus = {SkillsBenchAdapter._toml_value(environment.get('cpus', 2))}",
            f"memory_mb = {SkillsBenchAdapter._toml_value(environment.get('memory_mb', 4096))}",
            f"storage_mb = {SkillsBenchAdapter._toml_value(environment.get('storage_mb', 10240))}",
            f"gpus = {SkillsBenchAdapter._toml_value(environment.get('gpus', 0))}",
            f"allow_internet = {SkillsBenchAdapter._toml_value(allow_internet)}",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _rewrite_legacy_test_mount_paths(tests_dir: Path) -> None:
        """Translate BenchFlow verifier paths to harbor's legacy tests mount."""
        text_suffixes = {
            ".bash",
            ".cfg",
            ".ini",
            ".json",
            ".md",
            ".py",
            ".sh",
            ".toml",
            ".txt",
            ".yaml",
            ".yml",
        }
        for path in tests_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rewritten = text.replace("/verifier", "/tests")
            rewritten = rewritten.replace("/logs/tests", "/logs/verifier")
            if rewritten != text:
                path.write_text(rewritten, encoding="utf-8")

    @staticmethod
    def _ensure_harbor_compat_task(task_path: str) -> str:
        """Return a legacy harbor-readable task path.

        SkillsBench v1.1 stores tasks as BenchFlow-native ``task.md`` packages:
        ``task.md``, ``environment/``, ``oracle/``, ``verifier/``.  The harbor
        CLI used by this project still expects the older shape:
        ``instruction.md``, ``task.toml``, ``environment/``, ``tests/``.
        This method materializes a cached compatibility directory under
        ``workspace/skillsbench_harbor_compat`` and returns that path.
        """
        source = Path(task_path)
        if (source / "instruction.md").exists() and (source / "task.toml").exists():
            return task_path
        task_md = source / "task.md"
        if not task_md.exists():
            return task_path

        compat_root = DIR_ROOT / "workspace" / "skillsbench_harbor_compat" / source.name
        ready_marker = compat_root / ".tfllm_compat_ready"
        if ready_marker.exists():
            try:
                marker = json.loads(ready_marker.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                marker = {}
            if marker.get("version") == _HARBOR_COMPAT_VERSION:
                return str(compat_root)

        logger.info(f"Materializing harbor-compatible SkillsBench task: {source.name}")
        compat_root.mkdir(parents=True, exist_ok=True)
        frontmatter, instruction = SkillsBenchAdapter._split_task_md(task_md)
        (compat_root / "instruction.md").write_text(instruction, encoding="utf-8")
        (compat_root / "task.toml").write_text(
            SkillsBenchAdapter._legacy_task_toml(frontmatter),
            encoding="utf-8",
        )

        for src_name, dst_name in (("environment", "environment"), ("verifier", "tests")):
            src_dir = source / src_name
            dst_dir = compat_root / dst_name
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            if src_dir.exists():
                shutil.copytree(src_dir, dst_dir)
                if dst_name == "tests":
                    SkillsBenchAdapter._rewrite_legacy_test_mount_paths(dst_dir)

        ready_marker.write_text(
            json.dumps(
                {"version": _HARBOR_COMPAT_VERSION, "source": str(source)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return str(compat_root)

    @staticmethod
    def _is_retryable_error(result: SkillsBenchResult, retry_on_timeout: bool) -> bool:
        """Decide whether a failed result is worth retrying.

        Only *infrastructure* failures are retryable. These are signalled by a
        non-empty ``result.error`` (harbor crash, Docker build failure, missing
        trial output, etc.). A result with an empty ``error`` means the agent
        ran to completion and the verifier scored it — even a 0.0 reward there
        is a legitimate task failure and must NOT be retried.
        """
        if result.outcome != OUTCOME_INFRA_ERROR or result.fatal or not result.retryable:
            return False
        # Transient API errors already exhausted their retries inside the same
        # trial. Keep the trial invalid so retry-infra can rerun it later.
        if result.error_type in TRANSIENT_API_ERROR_TYPES:
            return False
        return True

    async def _run_task_once(
        self,
        task_path: str,
        experiences: dict[str, str] | None,
        inject_curated_skills: bool,
        skills_text: str,
        model_name: str,
        timeout: int,
        max_iterations: int,
        agent_instructions: str = "",
        model_temperature: float = 0.0,
    ) -> SkillsBenchResult:
        """Run a single attempt of a SkillsBench task (no retry, no cleanup)."""
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self._run_with_harbor(
                    task_path=task_path,
                    experiences=experiences,
                    inject_curated_skills=inject_curated_skills,
                    skills_text=skills_text,
                    model_name=model_name,
                    max_iterations=max_iterations,
                    agent_instructions=agent_instructions,
                    model_temperature=model_temperature,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            elapsed = time.monotonic() - start
            logger.warning(f"Task timed out after {elapsed:.0f}s: {task_path}")
            result = SkillsBenchResult(
                reward=0.0,
                outcome=OUTCOME_TASK_TIMEOUT,
                error_type="task_timeout",
                elapsed_sec=elapsed,
                metadata={"task_timeout_sec": timeout},
            )
        except asyncio.CancelledError:
            # Parent cancellation is scheduler control, not a measured task
            # timeout. The harbor subprocess path handles its own termination.
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(f"Task failed: {task_path}: {exc}", exc_info=True)
            classification = classify_infra_error(exc)
            result = SkillsBenchResult(
                reward=None,
                outcome=OUTCOME_FATAL_ERROR if classification.fatal else OUTCOME_INFRA_ERROR,
                error=str(exc),
                error_type=classification.error_type,
                retryable=classification.retryable,
                fatal=classification.fatal,
                elapsed_sec=elapsed,
            )

        result.elapsed_sec = time.monotonic() - start
        return result

    async def _docker_cleanup(self, prune_builder: bool = False) -> None:
        """Remove stopped containers, dangling images, and optionally build cache.

        Runs the Docker CLI in a thread to avoid blocking the event loop.
        Errors are logged at DEBUG level so a missing Docker daemon never
        breaks the evaluation pipeline.

        Cleanup levels
        --------------
        Every task (always):
          • ``docker container prune -f``  – removes exited harbor containers
          • ``docker image prune -f``      – removes untagged (dangling) image layers
        Every N tasks (``prune_builder=True``):
          • ``docker builder prune -f``    – removes build cache (the largest consumer)
        """
        def _run_prune(cmds: list[list[str]]) -> None:
            for cmd in cmds:
                try:
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=60,
                    )
                    out = result.stdout.decode("utf-8", errors="replace").strip()
                    if out:
                        logger.debug(f"docker cleanup [{' '.join(cmd[1:])}]: {out[:300]}")
                except subprocess.TimeoutExpired:
                    logger.debug(f"docker cleanup timed out: {' '.join(cmd)}")
                except FileNotFoundError:
                    logger.debug("docker not found; skipping cleanup")
                    break
                except Exception as exc:
                    logger.debug(f"docker cleanup error ({' '.join(cmd)}): {exc}")

        docker_bin = shutil.which("docker") or "docker"
        cmds = [
            [docker_bin, "container", "prune", "-f"],
            [docker_bin, "image", "prune", "-f"],
        ]
        if prune_builder:
            cmds.append([docker_bin, "builder", "prune", "-f"])
            logger.info(
                f"Docker deep cleanup at task {self._tasks_completed} "
                "(containers + dangling images + build cache)"
            )
        else:
            logger.debug(
                f"Docker light cleanup at task {self._tasks_completed} "
                "(containers + dangling images)"
            )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run_prune, cmds)

    # ------------------------------------------------------------------
    # Internal execution helpers
    # ------------------------------------------------------------------

    async def _run_with_harbor(
        self,
        task_path: str,
        experiences: dict[str, str] | None,
        inject_curated_skills: bool,
        skills_text: str,
        model_name: str,
        max_iterations: int,
        agent_instructions: str = "",
        model_temperature: float = 0.0,
    ) -> SkillsBenchResult:
        """Dispatch to Python API or CLI subprocess depending on availability."""
        if self._harbor_available is None:
            self._harbor_available = _try_import_harbor() is not None

        if self._harbor_available:
            return await self._run_via_python_api(
                task_path, experiences, inject_curated_skills, skills_text, model_name,
                max_iterations, agent_instructions, model_temperature,
            )
        else:
            logger.info("harbor Python API not importable; falling back to CLI subprocess.")
            return await self._run_via_cli(
                task_path, experiences, inject_curated_skills, skills_text, model_name,
                max_iterations, agent_instructions, model_temperature,
            )

    async def _run_via_python_api(
        self,
        task_path: str,
        experiences: dict[str, str] | None,
        inject_curated_skills: bool,
        skills_text: str,
        model_name: str,
        max_iterations: int,
        agent_instructions: str = "",
        model_temperature: float = 0.0,
    ) -> SkillsBenchResult:
        """Execute a task using harbor's Python API."""
        from harbor.runner import TaskRunner  # type: ignore[import]

        from .skillsbench_harbor_agent import TFLLMHarborAgent

        with tempfile.TemporaryDirectory(prefix="tfllm_harbor_") as tmp_logs:
            logs_dir = Path(tmp_logs)

            agent = TFLLMHarborAgent(
                experiences=experiences,
                inject_curated_skills=inject_curated_skills,
                skills_text=skills_text,
                model_name=model_name,
                max_iterations=max_iterations,
                logs_dir=logs_dir,
                agent_instructions=agent_instructions,
                temperature=model_temperature,
                connect_timeout_sec=getattr(self._config, "llm_connect_timeout_sec", 10.0),
                read_timeout_sec=getattr(self._config, "llm_read_timeout_sec", 120.0),
                llm_max_retries=getattr(self._config, "llm_max_retries", 4),
                retry_initial_delay_sec=getattr(
                    self._config, "llm_retry_initial_delay_sec", 2.0
                ),
                retry_max_delay_sec=getattr(self._config, "llm_retry_max_delay_sec", 30.0),
            )

            runner = TaskRunner()
            try:
                run_result = await runner.run(
                    task_path=task_path,
                    agent=agent,
                )
            except Exception as exc:
                logger.error(f"harbor TaskRunner.run() failed: {exc}", exc_info=True)
                payload = self._read_json_artifact(logs_dir, "infra_error.json")
                if payload:
                    return self._infra_result_from_payload(payload)
                classification = classify_infra_error(exc, default_type="harbor_runtime_error")
                return SkillsBenchResult(
                    reward=None,
                    outcome=OUTCOME_FATAL_ERROR if classification.fatal else OUTCOME_INFRA_ERROR,
                    error=str(exc),
                    error_type=classification.error_type,
                    retryable=classification.retryable,
                    fatal=classification.fatal,
                )

            payload = self._read_json_artifact(logs_dir, "infra_error.json")
            if payload:
                return self._infra_result_from_payload(payload)

            reward = self._extract_reward(run_result, logs_dir)
            if reward is None:
                return self._infra_result_from_payload(
                    {
                        "error_type": "reward_file_missing",
                        "message": "Harbor completed without a verifier reward",
                        "retryable": False,
                        "fatal": False,
                    }
                )
            trajectory = self._build_trajectory_json(logs_dir)
            agent_log = self._read_agent_log(logs_dir)
            metadata = self._read_json_artifact(logs_dir, "agent_run_metadata.json") or {}

            return SkillsBenchResult(
                reward=reward,
                trajectory=trajectory,
                agent_log=agent_log,
                outcome=OUTCOME_VALID,
                metadata=metadata,
            )

    async def _run_via_cli(
        self,
        task_path: str,
        experiences: dict[str, str] | None,
        inject_curated_skills: bool,
        skills_text: str,
        model_name: str,
        max_iterations: int,
        agent_instructions: str = "",
        model_temperature: float = 0.0,
    ) -> SkillsBenchResult:
        """
        Execute a task via the harbor CLI subprocess.

        Writes the TFLLMHarborAgent to a temp file, then calls:
            harbor trials start -p <task_path> \
                --agent tfllm_agent:TFLLMHarborAgent \
                --agent-import-path <tmp_agent_file>
        and reads the resulting reward from the output logs.
        """
        # ignore_cleanup_errors=True: some harbor tasks (e.g. fix-druid-loophole-cve)
        # create root-owned files inside Docker that the host process cannot delete.
        # Without this flag the PermissionError propagates as an infrastructure error
        # and triggers needless retries.  The temp dir will be cleaned by the OS on
        # the next reboot; disk impact is negligible (a few KB of trial metadata).
        with tempfile.TemporaryDirectory(prefix="tfllm_harbor_", ignore_cleanup_errors=True) as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Write a fully self-contained agent file.
            # Harbor runs in its own Python env (installed via `uv tool`)
            # which does NOT have the `utu` package or its dependencies.
            # The only dependency we can rely on is `openai`.
            agent_file = tmp_path / "tfllm_agent.py"
            experiences_json = json.dumps(experiences or {})
            skills_escaped = json.dumps(skills_text or "")
            agent_instructions_json = json.dumps(agent_instructions or "")
            agent_file.write_text(
                _build_standalone_agent_source(
                    experiences_json=experiences_json,
                    inject_curated_skills=inject_curated_skills,
                    skills_text_json=skills_escaped,
                    model_name=model_name,
                    max_iterations=max_iterations,
                    agent_instructions_json=agent_instructions_json,
                    temperature=model_temperature,
                    connect_timeout_sec=getattr(self._config, "llm_connect_timeout_sec", 10.0),
                    read_timeout_sec=getattr(self._config, "llm_read_timeout_sec", 120.0),
                    llm_max_retries=getattr(self._config, "llm_max_retries", 4),
                    retry_initial_delay_sec=getattr(
                        self._config, "llm_retry_initial_delay_sec", 2.0
                    ),
                    retry_max_delay_sec=getattr(self._config, "llm_retry_max_delay_sec", 30.0),
                ),
                encoding="utf-8",
            )

            trials_dir = tmp_path / "trials"
            trials_dir.mkdir()

            # Use a fixed trial name so we know exactly where harbor puts results
            trial_name = f"tfllm_{Path(task_path).name}"

            harbor_cmd = shutil.which("harbor")
            if harbor_cmd is None:
                harbor_cmd = os.path.expanduser("~/.local/bin/harbor")

            # Pass LLM credentials to the agent via --ae (agent env vars).
            # harbor runs the agent in its own isolated Python env which does
            # NOT inherit the parent process environment automatically.
            agent_env_vars = {}
            for key in ("UTU_LLM_API_KEY", "UTU_LLM_BASE_URL", "UTU_LLM_MODEL",
                        "OPENAI_API_KEY", "OPENAI_BASE_URL"):
                val = os.environ.get(key)
                if val:
                    agent_env_vars[key] = val

            env_build_multiplier = getattr(
                self._config, "env_build_timeout_multiplier", None
            ) or 3.0

            cmd = [
                harbor_cmd,
                "trials",
                "start",
                "-p", task_path,
                "--agent-import-path", "tfllm_agent:TFLLMHarborAgent",
                "--trials-dir", str(trials_dir),
                "--trial-name", trial_name,
                "--environment-build-timeout-multiplier", str(env_build_multiplier),
            ]
            # Inject LLM credentials into the agent process via --ae flags
            for k, v in agent_env_vars.items():
                cmd += ["--ae", f"{k}={v}"]

            # Add the temp dir to PYTHONPATH so harbor can import tfllm_agent
            env = {**os.environ}
            existing_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                str(tmp_path) + (":" + existing_pythonpath if existing_pythonpath else "")
            )

            logger.info(f"Running harbor CLI: {redact_command(cmd)}")

            # Run the harbor subprocess in a thread so it never blocks the
            # event loop.  This is critical: asyncio.wait_for relies on the
            # event loop scheduler to fire the timeout callback; if the loop
            # is saturated by many concurrent asyncio subprocesses the callback
            # can be delayed by hundreds of seconds, causing tasks to run far
            # beyond their nominal timeout.  A thread-pool worker releases the
            # GIL while waiting on the child process and lets the event loop
            # run freely.
            proc_holder: list[subprocess.Popen] = []
            cancel_requested = threading.Event()

            def _signal_harbor_process(proc: subprocess.Popen, *, force: bool) -> None:
                if proc.poll() is not None:
                    return
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL if force else signal.SIGTERM)
                    elif force:
                        proc.kill()
                    else:
                        proc.terminate()
                except (ProcessLookupError, OSError):
                    pass

            def _run_harbor_blocking() -> tuple[str, str, int]:
                if cancel_requested.is_set():
                    return "", "cancelled before harbor process start", -1
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    start_new_session=os.name == "posix",
                )
                proc_holder.append(proc)
                if cancel_requested.is_set():
                    _signal_harbor_process(proc, force=False)
                try:
                    stdout_bytes, stderr_bytes = proc.communicate()
                finally:
                    if proc.poll() is None:
                        _signal_harbor_process(proc, force=True)
                        proc.communicate()
                return (
                    stdout_bytes.decode("utf-8", errors="replace"),
                    stderr_bytes.decode("utf-8", errors="replace"),
                    proc.returncode or 0,
                )

            loop = asyncio.get_event_loop()
            stdout_str = ""
            stderr_str = ""
            returncode = 0
            worker = loop.run_in_executor(None, _run_harbor_blocking)
            try:
                stdout_str, stderr_str, returncode = await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancel_requested.set()
                logger.warning(
                    f"harbor CLI subprocess cancelled for task {Path(task_path).name}; "
                    "killing process tree."
                )
                for proc in proc_holder:
                    _signal_harbor_process(proc, force=False)
                try:
                    await asyncio.wait_for(asyncio.shield(worker), timeout=5)
                except TimeoutError:
                    for proc in proc_holder:
                        _signal_harbor_process(proc, force=True)
                    try:
                        await asyncio.wait_for(asyncio.shield(worker), timeout=5)
                    except Exception:
                        pass
                except Exception:
                    pass
                raise

            if returncode != 0:
                logger.error(f"harbor CLI exited with {returncode}:\n{stderr_str}")
                classification = classify_infra_error(
                    stderr_str or stdout_str or f"harbor CLI exit {returncode}",
                    default_type="harbor_runtime_error",
                )
                return SkillsBenchResult(
                    reward=None,
                    outcome=OUTCOME_FATAL_ERROR if classification.fatal else OUTCOME_INFRA_ERROR,
                    error=f"harbor CLI failed (exit {returncode}): {stderr_str[:500]}",
                    error_type=classification.error_type,
                    retryable=classification.retryable,
                    fatal=classification.fatal,
                    agent_log=stdout_str,
                )

            # Harbor writes results into: trials_dir/<trial_name>/
            #   result.json           – structured TrialResult (primary reward source)
            #   verifier/reward.txt   – plain float (fallback)
            #   verifier/reward.json  – dict of rewards (fallback)
            trial_result_dir = trials_dir / trial_name

            # Log diagnostic info if trial dir is missing or exception occurred
            if not trial_result_dir.exists():
                logger.warning(f"Trial result dir does not exist: {trial_result_dir}")
                logger.warning(f"harbor stdout: {stdout_str[:2000]}")
                logger.warning(f"harbor stderr: {stderr_str[:1000]}")
                # No trial output despite a clean exit code almost always means
                # an environment/Docker build failure. Flag it as an infra error
                # so the retry logic in run_task() can pick it up.
                return SkillsBenchResult(
                    reward=None,
                    outcome=OUTCOME_INFRA_ERROR,
                    error=(
                        "harbor produced no trial result directory "
                        "(likely environment/Docker build failure)"
                    ),
                    error_type="harbor_environment_error",
                    retryable=True,
                    agent_log=stdout_str,
                )
            else:
                payload = self._read_json_artifact(trial_result_dir, "infra_error.json")
                if payload:
                    result = self._infra_result_from_payload(payload, agent_log=stdout_str)
                    result.trajectory = self._build_trajectory_json(trial_result_dir)
                    return result
                result_json_path = trial_result_dir / "result.json"
                if result_json_path.exists():
                    try:
                        rj = json.loads(result_json_path.read_text())
                        exc = rj.get("exception_info")
                        if exc:
                            logger.warning(
                                f"Task exception: {exc.get('exception_message', '')[:1000]}\n"
                                f"Traceback: {exc.get('exception_traceback', '')[:2000]}"
                            )
                            message = exc.get("exception_message", "Harbor trial exception")
                            classification = classify_infra_error(
                                message, default_type="harbor_runtime_error"
                            )
                            return SkillsBenchResult(
                                reward=None,
                                outcome=(
                                    OUTCOME_FATAL_ERROR
                                    if classification.fatal
                                    else OUTCOME_INFRA_ERROR
                                ),
                                error=message,
                                error_type=classification.error_type,
                                retryable=classification.retryable,
                                fatal=classification.fatal,
                                agent_log=stdout_str,
                                trajectory=self._build_trajectory_json(trial_result_dir),
                            )
                    except Exception:
                        pass
                # Always log harbor stdout/stderr when task produces no reward,
                # so we can diagnose agent startup failures.
                if stdout_str:
                    logger.warning(f"harbor stdout [{Path(task_path).name}]:\n{stdout_str[:3000]}")
                if stderr_str:
                    logger.warning(f"harbor stderr [{Path(task_path).name}]:\n{stderr_str[:3000]}")

            reward = self._extract_reward_from_result_json(trial_result_dir)
            if reward is None:
                reward = self._extract_reward_from_dir(trial_result_dir)
                if reward is None:
                    # Last resort: check the whole trials_dir (harbor might use different layout)
                    reward = self._extract_reward_from_dir(trials_dir)
            if reward is None:
                return SkillsBenchResult(
                    reward=None,
                    outcome=OUTCOME_INFRA_ERROR,
                    error="Harbor completed without a verifier reward",
                    error_type="reward_file_missing",
                    retryable=False,
                    agent_log=stdout_str,
                    trajectory=self._build_trajectory_json(trial_result_dir),
                )
            trajectory = self._build_trajectory_json(trial_result_dir)
            metadata = self._read_json_artifact(trial_result_dir, "agent_run_metadata.json") or {}
            return SkillsBenchResult(
                reward=reward,
                trajectory=trajectory,
                agent_log=stdout_str,
                outcome=OUTCOME_VALID,
                metadata=metadata,
            )

    # ------------------------------------------------------------------
    # Reward / log parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json_artifact(root_dir: Path, filename: str) -> dict[str, Any] | None:
        for path in root_dir.rglob(filename):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
            except (json.JSONDecodeError, OSError):
                continue
        return None

    @staticmethod
    def _infra_result_from_payload(
        payload: dict[str, Any],
        *,
        agent_log: str = "",
    ) -> SkillsBenchResult:
        fatal = bool(payload.get("fatal", False))
        return SkillsBenchResult(
            reward=None,
            outcome=OUTCOME_FATAL_ERROR if fatal else OUTCOME_INFRA_ERROR,
            error=str(payload.get("message") or "SkillsBench infrastructure error"),
            error_type=str(payload.get("error_type") or "harbor_error"),
            retryable=bool(payload.get("retryable", False)),
            fatal=fatal,
            agent_log=agent_log,
            metadata={"infra_error": payload},
        )

    @staticmethod
    def _extract_reward(run_result: Any, root_dir: Path) -> float | None:
        """Extract reward from harbor run result object or fallback to log files."""
        # harbor Python API result object may expose .reward directly
        if hasattr(run_result, "reward") and run_result.reward is not None:
            try:
                return float(run_result.reward)
            except (TypeError, ValueError):
                pass

        # Fallback: read reward file written by tests/test.sh
        return SkillsBenchAdapter._extract_reward_from_dir(root_dir)

    @staticmethod
    def _extract_reward_from_result_json(trial_dir: Path) -> float | None:
        """
        Parse harbor's result.json to extract reward from verifier_result.rewards.

        Harbor always writes this file in _cleanup_and_finalize(), so it is the
        most reliable reward source. Returns None if the file doesn't exist or
        has no verifier result.
        """
        result_json = trial_dir / "result.json"
        if not result_json.exists():
            logger.debug(f"result.json not found at {result_json}")
            return None
        try:
            data = json.loads(result_json.read_text())
            vr = data.get("verifier_result")
            if not vr:
                # verifier may have been disabled or not yet run
                logger.debug(f"No verifier_result in {result_json}")
                return None
            rewards = vr.get("rewards") or {}
            if not rewards:
                logger.debug(f"Empty rewards in {result_json}")
                return None
            # Primary key is "reward"; fall back to first numeric value
            if "reward" in rewards:
                return float(rewards["reward"])
            for v in rewards.values():
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.debug(f"Failed to parse {result_json}: {e}")
        return None

    @staticmethod
    def _extract_reward_from_dir(root_dir: Path) -> float | None:
        """
        Search recursively under root_dir for reward.txt or reward.json.

        Harbor writes these inside the verifier container at /logs/verifier/
        which maps to trial_dir/verifier/ on the host.
        """
        # Try reward.txt first (higher priority per harbor spec)
        for reward_txt in root_dir.rglob("reward.txt"):
            try:
                value = float(reward_txt.read_text().strip())
                logger.debug(f"Found reward.txt at {reward_txt}: {value}")
                return value
            except (ValueError, OSError):
                continue

        # Fallback: reward.json
        for reward_json in root_dir.rglob("reward.json"):
            try:
                data = json.loads(reward_json.read_text())
                if isinstance(data, (int, float)):
                    return float(data)
                if isinstance(data, dict):
                    for v in data.values():
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            continue
            except (json.JSONDecodeError, OSError):
                continue

        logger.warning(f"No reward file found under {root_dir}")
        return None

    @staticmethod
    def _build_trajectory_json(root_dir: Path) -> str:
        """Build a TF-LLM-compatible trajectory JSON string from agent logs."""
        # Search recursively for agent_trajectory.json written by TFLLMHarborAgent
        for traj_file in root_dir.rglob("agent_trajectory.json"):
            try:
                steps = json.loads(traj_file.read_text())
                return json.dumps(
                    [{"trajectory": [{"role": "tool", "content": json.dumps(s)} for s in steps]}],
                    ensure_ascii=False,
                )
            except (json.JSONDecodeError, OSError):
                continue
        return "[]"

    @staticmethod
    def _read_agent_log(root_dir: Path) -> str:
        for log_file in root_dir.rglob("agent.log"):
            try:
                return log_file.read_text(encoding="utf-8", errors="replace")[:10000]
            except OSError:
                continue
        return ""
