"""LLM helpers for legacy flat merging and strict L0 candidate review.

The original two-stage helpers remain the compatibility path for the flat
pool. Hierarchical L0 uses the strict single-candidate reviewer defined here,
while :class:`HierarchicalExperienceManager` is the sole state-change owner so
stable IDs, provenance, archives, and parent links cannot be lost.

The merge is a two-stage LLM process, identical to the flat-pool logic:

1. ``propose_operations``  – for each chunk of candidate experiences, ask the
   LLM to compare them against the existing pool and emit ADD/UPDATE/DELETE/NONE
   operations (``GROUP_EXPERIENCE_UPDATE`` prompt).
2. ``consolidate_and_apply`` – reconcile the whole batch of operations into a
   single revision plan (``BATCH_EXPERIENCE_UPDATE`` prompt) and apply it.

``pool_merge`` chains the two stages and returns the updated pool.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from typing import Any

from jinja2 import Template
from pydantic import ValidationError

from ..utils import FileUtils, get_logger
from .experience_models import (
    ExperienceCandidateRecord,
    ExperienceReviewDecision,
    L0CandidateRecord,
    L0ReviewDecision,
)

logger = get_logger(__name__)


class CandidateReviewError(RuntimeError):
    """A candidate review could not be parsed or safely interpreted."""


def parse_candidate_review(response: str) -> L0ReviewDecision:
    """Parse one strict ADD/UPDATE/DELETE/KEEP decision.

    Markdown JSON fences are accepted for robustness, but surrounding prose,
    arrays, unknown fields, and action-specific violations are rejected.
    """

    text = (response or "").strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) != 3 or parts[0].strip() or parts[2].strip():
            raise CandidateReviewError("review output must contain only one JSON object")
        text = parts[1].strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CandidateReviewError(f"invalid candidate review JSON: {error}") from error
    if not isinstance(payload, dict):
        raise CandidateReviewError("candidate review output must be a JSON object")
    try:
        return L0ReviewDecision.model_validate(payload)
    except ValidationError as error:
        raise CandidateReviewError(f"candidate review schema validation failed: {error}") from error


async def review_l0_candidate(
    llm: Any,
    prompts: dict[str, Any],
    agent_objective: str,
    learning_objective: str,
    candidate: L0CandidateRecord,
    related_experiences: list[dict[str, Any]],
    *,
    candidate_view: dict[str, Any] | None = None,
    allowed_evidence_ids: list[str],
    comparison_scope: str,
    model_params: dict[str, Any] | None = None,
    temperature: float = 0.0,
    experience_output_language_instruction: str = (
        "Use the same language as the input trajectory and supplied experiences."
    ),
) -> L0ReviewDecision:
    """Review exactly one candidate against a fresh active-pool view."""

    return await review_experience_candidate(
        llm,
        prompts,
        agent_objective,
        learning_objective,
        candidate,
        related_experiences,
        prompt_name="L0_CANDIDATE_REVIEW_PROMPT",
        candidate_view=candidate_view,
        allowed_evidence_ids=allowed_evidence_ids,
        comparison_scope=comparison_scope,
        model_params=model_params,
        temperature=temperature,
        experience_output_language_instruction=experience_output_language_instruction,
    )


async def review_experience_candidate(
    llm: Any,
    prompts: dict[str, Any],
    agent_objective: str,
    learning_objective: str,
    candidate: ExperienceCandidateRecord,
    related_experiences: list[dict[str, Any]],
    *,
    prompt_name: str,
    candidate_view: dict[str, Any] | None = None,
    allowed_evidence_ids: list[str],
    comparison_scope: str,
    model_params: dict[str, Any] | None = None,
    temperature: float = 0.0,
    experience_output_language_instruction: str = (
        "Use the same language as the input trajectory and supplied experiences."
    ),
) -> ExperienceReviewDecision:
    """Review one candidate using the level-specific policy and shared schema."""

    prompt = prompts[prompt_name]
    system_prompt = Template(prompt["system"]).render(
        agent_objective=agent_objective,
        learning_objective=learning_objective,
        experience_output_language_instruction=experience_output_language_instruction,
    )
    user_prompt = Template(prompt["user"]).render(
        candidate_json=json.dumps(
            candidate_view if candidate_view is not None else candidate.public_dict(),
            ensure_ascii=False,
            sort_keys=True,
        ),
        related_experiences_json=json.dumps(related_experiences, ensure_ascii=False, sort_keys=True),
        allowed_evidence_ids_json=json.dumps(sorted(allowed_evidence_ids), ensure_ascii=False),
        comparison_scope=comparison_scope,
    )
    params = dict(model_params or {})
    params["temperature"] = temperature
    response = await llm.query_one(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        **params,
    )
    return parse_candidate_review(response)


def split_experiences(text: str) -> list[str]:
    """Split a free-text experience blob into individual experience strings.

    The group-advantage step emits experiences as a (possibly bulleted or
    numbered) list inside ``<Experiences>...</Experiences>``.  We strip leading
    bullets / numbering and keep each non-empty line as one raw L0 candidate.
    """
    items: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # Drop leading bullets / list numbering like "- ", "* ", "1. ", "1) ".
        line = re.sub(r"^[\-\*•]+\s*", "", line)
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        line = line.strip()
        if line:
            items.append(line)
    return items


def _next_numeric_id(existing: dict[str, str], prefix: str) -> int:
    """Return the next free integer suffix for ``prefix`` (e.g. ``L0_`` → 7)."""
    mx = -1
    for key in existing:
        if prefix:
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix):]
        else:
            suffix = key
        try:
            mx = max(mx, int(suffix))
        except (TypeError, ValueError):
            continue
    return mx + 1


def apply_revision_plan(
    existing: dict[str, str],
    revision_plan: list[dict],
    id_prefix: str = "",
) -> dict[str, str]:
    """Apply ADD/UPDATE/DELETE/NONE operations to a pool, returning a new dict."""
    next_id = _next_numeric_id(existing, id_prefix)
    new_pool = copy.deepcopy(existing)
    for plan in revision_plan:
        if not isinstance(plan, dict):
            continue
        operation = (plan.get("operation") or "ADD").upper()
        content = plan.get("content", "")
        target_id = plan.get("id", None)

        if operation == "DELETE":
            if target_id in new_pool:
                del new_pool[target_id]
            continue

        if not content:
            continue

        if operation == "ADD":
            new_pool[f"{id_prefix}{next_id}"] = content
            next_id += 1
        elif operation == "UPDATE":
            if target_id in new_pool:
                new_pool[target_id] = content
            else:
                new_pool[f"{id_prefix}{next_id}"] = content
                next_id += 1
        # NONE → no change
    return new_pool


def format_exp_and_ops(experiences: dict[str, str], operations: list[dict]) -> str:
    """Render the existing pool together with the proposed operations."""
    if not operations:
        return "No batch operations."

    formatted_res = []
    for id, exp in experiences.items():
        curr_str = f"Experience {id}:\nContent: {exp}\n"
        related_ops = [op for op in operations if op.get("id") == id]
        if related_ops:
            curr_str += "Related Operations:\n"
            curr_str += "\n".join(json.dumps(op, ensure_ascii=False, indent=2) for op in related_ops)
        else:
            curr_str += "No related operations."
        formatted_res.append(curr_str)

    no_id_ops = [op for op in operations if not op.get("id", None)]
    if no_id_ops:
        curr_str = "Operations without specific Experience ID:\n"
        curr_str += "\n".join(json.dumps(op, ensure_ascii=False, indent=2) for op in no_id_ops)
        formatted_res.append(curr_str)

    return "\n\n".join(formatted_res)


def _is_rate_limit(error: Exception) -> bool:
    s = str(error).lower()
    return "429" in s or "rate limit" in s or "tpm limit" in s


async def propose_operations(
    llm: Any,
    prompts: dict,
    agent_objective: str,
    learning_objective: str,
    existing: dict[str, str],
    candidates: list[str],
    *,
    model_params: dict | None = None,
    concurrency: int = 8,
    chunk_size: int = 10,
    max_retries: int = 5,
    base_delay: float = 10.0,
    experience_output_language_instruction: str = (
        "Use the same language as the input trajectory and supplied experiences."
    ),
) -> list[dict]:
    """Stage 1: emit ADD/UPDATE/DELETE/NONE operations for ``candidates``."""
    model_params = model_params or {}
    candidates = [c.strip() for c in candidates if c and c.strip()]
    if not candidates:
        return []

    chunks = [candidates[i:i + chunk_size] for i in range(0, len(candidates), chunk_size)]
    formatted_existing = (
        "\n".join(f"[{i}]. {e}" for i, e in existing.items()) if existing else "None"
    )
    sp = FileUtils.get_jinja_template_str(prompts["GROUP_EXPERIENCE_UPDATE_TEMPLATE_SP"]).render(
        agent_objective=agent_objective,
        learning_objective=learning_objective,
        experience_output_language_instruction=experience_output_language_instruction,
    )
    semaphore = asyncio.Semaphore(concurrency)

    async def one_chunk(chunk: list[str]) -> list[dict]:
        new_experiences_text = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(chunk))
        async with semaphore:
            for attempt in range(max_retries):
                try:
                    up = FileUtils.get_jinja_template_str(
                        prompts["GROUP_EXPERIENCE_UPDATE_TEMPLATE_UP"]
                    ).render(
                        existing_experiences=formatted_existing,
                        new_experiences=new_experiences_text,
                    )
                    response = await llm.query_one(
                        messages=[
                            {"role": "system", "content": sp},
                            {"role": "user", "content": up},
                        ],
                        **model_params,
                    )
                    parsed = json.loads(response.split("```json")[-1].split("```")[0])
                    return parsed if isinstance(parsed, list) else []
                except Exception as e:  # noqa: BLE001
                    if _is_rate_limit(e) and attempt < max_retries - 1:
                        await asyncio.sleep(base_delay * (2 ** attempt))
                        continue
                    logger.warning(f"pool_merge: propose_operations chunk failed: {e}")
                    return []
            return []

    results = await asyncio.gather(*[one_chunk(c) for c in chunks])
    operations: list[dict] = []
    for r in results:
        operations.extend(r)
    return operations


async def consolidate_and_apply(
    llm: Any,
    prompts: dict,
    agent_objective: str,
    learning_objective: str,
    existing: dict[str, str],
    operations: list[dict],
    *,
    model_params: dict | None = None,
    id_prefix: str = "",
    max_retries: int = 3,
    experience_output_language_instruction: str = (
        "Use the same language as the input trajectory and supplied experiences."
    ),
) -> dict[str, str]:
    """Stage 2: reconcile ``operations`` into a revision plan and apply it."""
    model_params = model_params or {}
    if not operations:
        return dict(existing)

    sp = FileUtils.get_jinja_template_str(prompts["BATCH_EXPERIENCE_UPDATE_TEMPLATE_SP"]).render(
        agent_objective=agent_objective,
        learning_objective=learning_objective,
        experience_output_language_instruction=experience_output_language_instruction,
    )
    revision_plan: list[dict] = []
    for _ in range(max_retries):
        try:
            up = FileUtils.get_jinja_template_str(
                prompts["BATCH_EXPERIENCE_UPDATE_TEMPLATE_UP"]
            ).render(experiences_and_operations=format_exp_and_ops(existing, operations))
            response = await llm.query_one(
                messages=[
                    {"role": "system", "content": sp},
                    {"role": "user", "content": up},
                ],
                **model_params,
            )
            revision_plan = json.loads(response.split("```json")[-1].split("```")[0])
            break
        except Exception:  # noqa: BLE001
            logger.warning("pool_merge: failed to decode batch revision plan")

    return apply_revision_plan(existing, revision_plan, id_prefix=id_prefix)


async def pool_merge(
    llm: Any,
    prompts: dict,
    agent_objective: str,
    learning_objective: str,
    existing: dict[str, str],
    candidates: list[str],
    *,
    model_params: dict | None = None,
    id_prefix: str = "",
    concurrency: int = 8,
    chunk_size: int = 10,
    experience_output_language_instruction: str = (
        "Use the same language as the input trajectory and supplied experiences."
    ),
) -> dict[str, str]:
    """End-to-end LLM merge: compare ``candidates`` against the pool, consolidate
    the resulting operations, and apply them.

    Returns the updated pool as an ``{id: content}`` dict. This permissive
    numeric-ID helper is intentionally limited to the legacy flat path.
    """
    candidates = [c.strip() for c in candidates if c and c.strip()]
    if not candidates:
        return dict(existing)

    operations = await propose_operations(
        llm,
        prompts,
        agent_objective,
        learning_objective,
        existing,
        candidates,
        model_params=model_params,
        concurrency=concurrency,
        chunk_size=chunk_size,
        experience_output_language_instruction=experience_output_language_instruction,
    )
    return await consolidate_and_apply(
        llm,
        prompts,
        agent_objective,
        learning_objective,
        existing,
        operations,
        model_params=model_params,
        id_prefix=id_prefix,
        experience_output_language_instruction=experience_output_language_instruction,
    )
