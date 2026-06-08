"""
TF-LLM Harbor Agent for SkillsBench evaluation.

This module implements the harbor ``BaseAgent`` interface so that TF-LLM's
LLM backend can drive task execution inside a Docker container managed by
harbor.  The agent performs a multi-turn bash-tool-calling loop:

    system prompt (instructions + experiences / curated Skills)
        ↓
    LLM → tool call: bash_execute(command)
        ↓
    environment.exec(command) → stdout / stderr
        ↓
    LLM sees output → next tool call or "task_complete"
        ↓  (repeat up to max_iterations)
    harbor runs tests/test.sh → reward.txt

Experiences (L0/L1/L2 from TF-GRPO) or curated Skills text are injected
into the system prompt before the first LLM call, making this the single
integration point between TF-LLM's knowledge and harbor's execution engine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..utils import get_logger

logger = get_logger(__name__)

# OpenAI function-calling schema for bash execution
BASH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "bash_execute",
        "description": (
            "Execute a bash command inside the task environment. "
            "Use this to explore the filesystem, run scripts, install packages, "
            "or write files needed to complete the task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                }
            },
            "required": ["command"],
        },
    },
}

TASK_COMPLETE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "task_complete",
        "description": (
            "Call this function when you have finished all required steps "
            "and believe the task is complete."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was accomplished.",
                }
            },
            "required": ["summary"],
        },
    },
}

SYSTEM_PROMPT_BASE = """\
You are an expert software engineer and problem-solver operating inside an \
isolated Linux environment.  You have access to a bash terminal.  Complete \
the task described by the user by executing bash commands step-by-step.

Guidelines:
- Think carefully before each command.
- Verify intermediate results to catch mistakes early.
- When the task is done, call task_complete() with a brief summary.
- Do NOT call task_complete() until the task is genuinely finished.
"""

EXPERIENCE_SECTION = """\

--- Past Experiences (use these to guide your approach) ---
{experiences}
--- End of Experiences ---
"""

# A short nudge is all that is needed: the full skills document lives on disk
# at /app/SKILLS.md (written by setup() before the agent starts).
SKILLS_NUDGE = """\

--- Curated Skills ---
A curated skill guide for this task has been written to /app/SKILLS.md.
Read it before you start working: cat /app/SKILLS.md
--- End of Curated Skills ---
"""

# Remote path where the skills file is placed inside the container.
_SKILLS_REMOTE_PATH = "/app/SKILLS.md"


def _build_system_prompt(
    experiences: dict[str, str] | None = None,
    inject_curated_skills: bool = False,
) -> str:
    parts = [SYSTEM_PROMPT_BASE]

    if experiences:
        formatted = "\n".join(f"[{k}] {v}" for k, v in experiences.items())
        parts.append(EXPERIENCE_SECTION.format(experiences=formatted))

    if inject_curated_skills:
        # Only add a short pointer; the actual content is a file in the container.
        parts.append(SKILLS_NUDGE)

    return "".join(parts)


class TFLLMHarborAgent:
    """
    Harbor-compatible agent backed by TF-LLM's LLM client.

    This class mimics the ``harbor.agents.base.BaseAgent`` interface so that
    it can be used directly with harbor's Python API.  It does NOT inherit
    from ``BaseAgent`` to avoid making ``harbor`` a hard import-time dependency
    (harbor may not be installed during normal TF-LLM development/testing).

    When harbor calls ``setup()`` and ``run()``, this agent:
      1. Builds a system prompt with optional experiences / Skills.
      2. Runs a multi-turn LLM loop, calling ``environment.exec()`` for each
         bash tool call.
      3. Stops when ``task_complete`` is called or ``max_iterations`` is reached.
    """

    # Set to True to produce ATIF-compatible trajectory logs
    SUPPORTS_ATIF: bool = False

    def __init__(
        self,
        experiences: dict[str, str] | None = None,
        inject_curated_skills: bool = False,
        skills_text: str | None = None,
        model_name: str | None = None,
        max_iterations: int = 30,
        logs_dir: Path | None = None,
    ) -> None:
        self._experiences = experiences or {}
        self._inject_curated_skills = inject_curated_skills
        self._skills_text = skills_text or ""
        self._model_name = model_name or os.getenv("UTU_LLM_MODEL", "deepseek-chat")
        self._max_iterations = max_iterations
        self._logs_dir = logs_dir or Path("/tmp/skillsbench_logs")
        self._logs_dir.mkdir(parents=True, exist_ok=True)

        # Lazy-initialise the LLM client (avoids import errors if openai not set up)
        self._llm = None

    # ------------------------------------------------------------------
    # Harbor BaseAgent interface
    # ------------------------------------------------------------------

    @staticmethod
    def name() -> str:
        return "tfllm-harbor-agent"

    def version(self) -> str | None:
        return "1.0.0"

    async def setup(self, environment) -> None:
        """Write the skills file into the container before the agent starts.

        Mirrors the official benchflow ``--skills-dir`` behaviour: skills are
        placed on the container filesystem so the agent can read them on demand
        instead of receiving a (possibly truncated) text blob in the prompt.
        """
        if self._inject_curated_skills and self._skills_text:
            import base64 as _b64
            skills_b64 = _b64.b64encode(self._skills_text.encode("utf-8")).decode()
            write_cmd = (
                f"python3 -c \""
                f"import base64; "
                f"open('{_SKILLS_REMOTE_PATH}', 'wb').write("
                f"base64.b64decode('{skills_b64}'))\""
            )
            try:
                result = await environment.exec(write_cmd, timeout_sec=30)
                if result.return_code != 0:
                    logger.warning(
                        f"Failed to write SKILLS.md (rc={result.return_code}): "
                        f"{result.stderr[:300]}"
                    )
                else:
                    logger.info(
                        f"Wrote {len(self._skills_text)} chars to "
                        f"{_SKILLS_REMOTE_PATH} in container"
                    )
            except Exception as exc:
                logger.warning(f"setup(): could not write SKILLS.md: {exc}")

    async def run(self, instruction: str, environment, context) -> None:
        """
        Execute the task inside the harbor Docker environment.

        Args:
            instruction: Task description from instruction.md.
            environment: harbor ``BaseEnvironment`` – provides ``exec()``.
            context: harbor ``AgentContext`` – used to report metrics.
        """
        llm = self._get_llm_client()
        system_prompt = _build_system_prompt(
            experiences=self._experiences,
            inject_curated_skills=self._inject_curated_skills,
        )

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ]

        tools = [BASH_TOOL, TASK_COMPLETE_TOOL]
        commands_executed = 0
        total_input_tokens = 0
        total_output_tokens = 0
        trajectory_log: list[dict] = []

        for iteration in range(self._max_iterations):
            try:
                response = await llm.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.2,
                    max_completion_tokens=4096,
                )
            except Exception as exc:
                logger.error(f"LLM call failed at iteration {iteration}: {exc}")
                # AgentContext may not have an error_message field depending on
                # the harbor version; use metadata as a safe fallback.
                try:
                    context.error_message = str(exc)
                except AttributeError:
                    if not hasattr(context, "metadata") or context.metadata is None:
                        context.metadata = {}
                    context.metadata["error_message"] = str(exc)
                break

            # Track token usage
            if response.usage:
                total_input_tokens += response.usage.prompt_tokens or 0
                total_output_tokens += response.usage.completion_tokens or 0

            message = response.choices[0].message
            messages.append(message.model_dump(exclude_unset=True))

            # No tool call → model produced a plain text response (unusual but possible)
            if not message.tool_calls:
                logger.info(f"[iter {iteration}] No tool call – model responded with text only.")
                trajectory_log.append({"iteration": iteration, "type": "text", "content": message.content})
                # Treat a final text reply as implicit task_complete
                break

            # Process each tool call
            done = False
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}

                if fn_name == "task_complete":
                    summary = fn_args.get("summary", "")
                    logger.info(f"[iter {iteration}] task_complete: {summary}")
                    trajectory_log.append({"iteration": iteration, "type": "task_complete", "summary": summary})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "Task marked as complete.",
                        }
                    )
                    done = True

                elif fn_name == "bash_execute":
                    command = fn_args.get("command", "")
                    logger.info(f"[iter {iteration}] bash: {command[:120]}")
                    try:
                        exec_result = await environment.exec(command, timeout_sec=120)
                        stdout = (exec_result.stdout or "")[:4000]
                        stderr = (exec_result.stderr or "")[:2000]
                        rc = exec_result.return_code
                        tool_output = f"exit_code={rc}\n{stdout}"
                        if stderr:
                            tool_output += f"\nstderr:\n{stderr}"
                    except Exception as exec_exc:
                        tool_output = f"Command execution error: {exec_exc}"
                        rc = -1

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_output,
                        }
                    )
                    commands_executed += 1
                    trajectory_log.append(
                        {
                            "iteration": iteration,
                            "type": "bash",
                            "command": command,
                            "exit_code": rc,
                            "stdout_preview": stdout[:500],
                        }
                    )
                else:
                    logger.warning(f"Unknown tool call: {fn_name}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Unknown function: {fn_name}",
                        }
                    )

            if done:
                break

        # Persist trajectory log for analysis
        log_file = self._logs_dir / "agent_trajectory.json"
        log_file.write_text(json.dumps(trajectory_log, ensure_ascii=False, indent=2))

        # Populate harbor AgentContext (only fields defined in the Pydantic model)
        context.n_input_tokens = total_input_tokens
        context.n_output_tokens = total_output_tokens
        context.metadata = {"commands_executed": commands_executed}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_llm_client(self):
        """Lazily initialise the OpenAI-compatible async client."""
        if self._llm is None:
            from openai import AsyncOpenAI

            self._llm = AsyncOpenAI(
                api_key=os.getenv("UTU_LLM_API_KEY", ""),
                base_url=os.getenv("UTU_LLM_BASE_URL"),
            )
        return self._llm
