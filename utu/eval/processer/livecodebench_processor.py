"""
LiveCodeBench Processer for TF-LLM evaluation pipeline.

Handles code generation problems from LeetCode, AtCoder, and Codeforces.

Evaluation flow:
  preprocess_one  →  formats problem prompt (question + starter code)
  judge_one       →  extracts agent-generated code, runs test cases, computes reward
  calculate_metrics → pass@1, mean_reward, breakdown by difficulty / platform

Test case types:
  - stdin   : pipe input string to subprocess stdin, compare stdout (Codeforces/AtCoder)
  - functional : call a specific function/method (LeetCode); uses a generated harness

Reward:
  reward = num_passed_test_cases / total_test_cases   (partial credit supported)
  correct = (reward == 1.0)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from collections import defaultdict
from statistics import mean
from typing import TYPE_CHECKING

from ...config import EvalConfig
from ...utils import get_logger
from ..data import EvaluationSample
from .base_processor import BaseProcesser

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Per-test-case execution timeout in seconds.
# Keep low: a single code submission is tested against many cases.
_TEST_TIMEOUT_SEC = 10

# Maximum number of test cases to run per submission (cap to limit cost).
_MAX_TEST_CASES = 20


# ---------------------------------------------------------------------------
# Code extraction
# ---------------------------------------------------------------------------

def _extract_code(response: str) -> str:
    """
    Extract the last Python code block from the agent response.

    Priority:
    1. Last ```python ... ``` block
    2. Last ``` ... ``` block (language-agnostic)
    3. Full response (fallback)
    """
    if not response:
        return ""

    # Try ```python ... ```
    pattern_py = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
    matches_py = pattern_py.findall(response)
    if matches_py:
        return matches_py[-1].strip()

    # Try ``` ... ```
    pattern_any = re.compile(r"```\w*\s*\n(.*?)```", re.DOTALL)
    matches_any = pattern_any.findall(response)
    if matches_any:
        return matches_any[-1].strip()

    return response.strip()


# ---------------------------------------------------------------------------
# Test case runners
# ---------------------------------------------------------------------------

def _run_stdin_test(code: str, test_input: str, expected_output: str) -> bool:
    """
    Run `code` as a standalone Python script, feeding `test_input` via stdin.
    Return True iff stdout matches `expected_output` (after stripping whitespace).
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT_SEC,
        )
        actual = result.stdout.strip()
        expected = expected_output.strip()
        return actual == expected
    except subprocess.TimeoutExpired:
        logger.debug("Test case timed out")
        return False
    except Exception as exc:
        logger.debug(f"Test execution error: {exc}")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _build_functional_harness(code: str, func_name: str, test_input: str) -> str:
    """
    Wrap `code` in a harness that:
      1. Parses `test_input` (JSON-serialised list of arguments, one arg per line)
      2. Instantiates Solution (if present) and calls `func_name(*args)`
      3. Prints the result as JSON

    Handles both module-level functions and class Solution methods.
    """
    harness = textwrap.dedent(f"""
        import sys, json
        from typing import *
        from collections import *
        import heapq, math, functools, itertools, bisect, string, re

        {code}

        def _parse_arg(s):
            s = s.strip()
            try:
                return json.loads(s)
            except Exception:
                return s

        raw = sys.stdin.read().strip()
        lines = [l for l in raw.splitlines() if l.strip()]
        args = [_parse_arg(l) for l in lines]

        # Try Solution class first, then module-level function
        try:
            sol = Solution()
            fn = getattr(sol, {func_name!r})
        except NameError:
            fn = globals()[{func_name!r}]

        result = fn(*args)
        print(json.dumps(result, ensure_ascii=False))
    """)
    return harness


def _run_functional_test(
    code: str, func_name: str, test_input: str, expected_output: str
) -> bool:
    """
    Run a functional-style test (LeetCode): call `func_name` with deserialized args,
    compare JSON-serialised return value against `expected_output`.
    """
    harness = _build_functional_harness(code, func_name, test_input)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(harness)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT_SEC,
        )
        actual = result.stdout.strip()
        expected = expected_output.strip()

        # Try JSON comparison first (handles numeric types, list order, etc.)
        try:
            return json.loads(actual) == json.loads(expected)
        except Exception:
            return actual == expected
    except subprocess.TimeoutExpired:
        logger.debug("Functional test timed out")
        return False
    except Exception as exc:
        logger.debug(f"Functional test error: {exc}")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_test_cases(code: str, test_cases: list[dict], func_name: str = "") -> float:
    """
    Run `code` against all test cases.  Return pass_rate ∈ [0.0, 1.0].

    Each test case dict must have keys: input, output, testtype (stdin | functional).
    """
    if not code or not test_cases:
        return 0.0

    capped = test_cases[:_MAX_TEST_CASES]
    passed = 0

    for tc in capped:
        tc_input = tc.get("input", "")
        tc_output = tc.get("output", "")
        tc_type = str(tc.get("testtype", "stdin")).lower()

        try:
            if tc_type == "functional" and func_name:
                ok = _run_functional_test(code, func_name, tc_input, tc_output)
            else:
                ok = _run_stdin_test(code, tc_input, tc_output)
        except Exception as exc:
            logger.debug(f"Unexpected error running test case: {exc}")
            ok = False

        if ok:
            passed += 1

    return passed / len(capped)


# ---------------------------------------------------------------------------
# Processer
# ---------------------------------------------------------------------------

class LiveCodeBenchProcesser(BaseProcesser):
    """Processer for LiveCodeBench code generation problems."""

    name = "LiveCodeBench"

    def __init__(self, config: EvalConfig) -> None:
        super().__init__(config)

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    def preprocess_one(
        self, sample: EvaluationSample, recorder=None
    ) -> EvaluationSample:
        """
        Pass through the formatted prompt as-is.

        The question field already contains the full prompt built by
        prepare_livecodebench_data.py.  We just echo it into augmented_question
        so the rollout pipeline picks it up.
        """
        sample.update(augmented_question=sample.raw_question)
        return sample

    # ------------------------------------------------------------------
    # Judging
    # ------------------------------------------------------------------

    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        """
        Extract code from the agent response and run it against test cases.

        Uses public_test_cases for the reward signal.
        Falls back to private_test_cases if no public tests are available.
        """
        meta: dict = {}
        if data.meta:
            meta = data.meta if isinstance(data.meta, dict) else {}

        # --- Parse test cases ---
        public_raw = meta.get("public_test_cases") or "[]"
        private_raw = meta.get("private_test_cases") or "[]"

        def _load_tests(raw) -> list[dict]:
            if not raw:
                return []
            try:
                tests = json.loads(raw) if isinstance(raw, str) else raw
                return [t for t in tests if isinstance(t, dict)]
            except Exception:
                return []

        public_tests = _load_tests(public_raw)
        private_tests = _load_tests(private_raw)

        # Prefer private tests for a more reliable signal; fall back to public
        test_cases = private_tests if private_tests else public_tests
        if not test_cases:
            logger.warning(
                f"No test cases for problem {meta.get('question_id', '?')}; reward=0"
            )
            data.update(correct=False, reward=0.0, judged_response="no_test_cases")
            return data

        # --- Extract code ---
        code = _extract_code(data.response or "")
        if not code:
            data.update(correct=False, reward=0.0, judged_response="no_code_extracted")
            return data

        func_name = meta.get("func_name") or ""

        # --- Execute in thread to avoid blocking the event loop ---
        reward = await asyncio.to_thread(
            _run_test_cases, code, test_cases, func_name
        )

        correct = reward >= 1.0
        judged = f"passed {round(reward * len(test_cases[:_MAX_TEST_CASES]))}/{min(len(test_cases), _MAX_TEST_CASES)} tests"

        logger.debug(
            f"problem={meta.get('question_title','?')} "
            f"platform={meta.get('platform','?')} "
            f"difficulty={meta.get('difficulty','?')} "
            f"reward={reward:.3f}"
        )

        data.update(correct=correct, reward=reward, judged_response=judged)
        return data

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def calculate_metrics(self, samples: list[EvaluationSample]) -> dict:
        """
        Compute:
          - pass@1       : fraction of problems where reward == 1.0
          - mean_reward  : average reward (supports partial credit)
          - by_difficulty: pass rate per difficulty (easy / medium / hard)
          - by_platform  : pass rate per platform (leetcode / atcoder / codeforces)
        """
        if not samples:
            return {"pass_rate": 0.0, "mean_reward": 0.0}

        rewards: list[float] = []
        by_difficulty: dict[str, list[float]] = defaultdict(list)
        by_platform: dict[str, list[float]] = defaultdict(list)

        for s in samples:
            r = float(s.reward) if s.reward is not None else 0.0
            rewards.append(r)

            meta: dict = {}
            if s.meta:
                meta = s.meta if isinstance(s.meta, dict) else {}

            difficulty = str(meta.get("difficulty", "unknown")).lower()
            platform = str(meta.get("platform", "unknown")).lower()
            by_difficulty[difficulty].append(r)
            by_platform[platform].append(r)

        metrics = {
            "pass_rate": mean(1.0 if r >= 1.0 else 0.0 for r in rewards),
            "mean_reward": mean(rewards),
            "num_problems": len(samples),
            "by_difficulty": {
                d: round(mean(1.0 if r >= 1.0 else 0.0 for r in vs), 4)
                for d, vs in sorted(by_difficulty.items())
            },
            "by_platform": {
                p: round(mean(1.0 if r >= 1.0 else 0.0 for r in vs), 4)
                for p, vs in sorted(by_platform.items())
            },
        }
        return metrics
