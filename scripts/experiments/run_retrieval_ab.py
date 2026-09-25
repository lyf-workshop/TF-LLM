"""Paired A/B/C evaluation for experience retrieval policies.

The experiment deliberately leaves the production evaluation pipeline untouched.
It compares, on the same tasks and model:

1. ``no_experience``: the base prompt only;
2. ``current``: the current TF-LLM lexical L0 top-k policy, with all L1/L2;
3. ``hybrid``: BM25 + dense recall, reciprocal-rank fusion, and MMR diversity;
4. optional ``gated_hybrid``: a conservative, training-free applicability
   judge may select a small subset of hybrid candidates or abstain entirely.

Every condition uses the same generation settings. Experience blocks are capped by
the same token budget, and the output records enough information to reproduce the
selection decision without persisting API credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import statistics
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(raise_error_if_not_found=False), override=True)
os.environ.setdefault("UTU_SKIP_AUTO_SETUP", "1")

from math_verify.metric import math_metric  # noqa: E402
from math_verify.parser import ExprExtractionConfig, LatexExtractionConfig  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402

from utu.practice.experience_clusterer import (  # noqa: E402
    SentenceTransformerEmbeddingProvider,
)
from utu.practice.experience_retriever import ExperienceRetriever  # noqa: E402

DEFAULT_EXPERIENCE_PATH = Path(
    "workspace/hierarchical_experiences/math_dapo_random_100_full_hierarchy_en_v1_wsl_20260915.json"
)
DEFAULT_EMBEDDING_CACHE = Path("workspace/cache/retrieval_ab_experience_embeddings.sqlite3")
DEFAULT_OUTPUT = Path("workspace/experiments/retrieval_ab_aime24.jsonl")
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_MODEL_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
CONDITIONS = ("no_experience", "current", "hybrid")
GATED_CONDITION = "gated_hybrid"

BASE_SYSTEM_PROMPT = """You are solving a competition mathematics problem.
Reason carefully and verify the result. Do not call external tools.
The final part of your response must use exactly this format:
<answer>
\\boxed{the final answer}
</answer>"""

EXPERIENCE_HEADER = """Relevant lessons from earlier, disjoint training tasks are
provided below. Use a lesson only when its assumptions match the current problem;
ignore any lesson that is irrelevant or conflicts with the problem.
"""

GATE_SYSTEM_PROMPT = """You are a conservative retrieval gate for reusable
mathematical problem-solving lessons. Do not solve the problem. Judge whether any
candidate lesson contains a concrete method that is directly applicable under the
current problem's objects, goal, and assumptions. Topic or notation overlap alone is
not enough. Reject generic, overly specific, mismatched, or conflicting lessons. When
uncertain, abstain.

Return only one JSON object with this schema:
{"use_retrieval": false, "confidence": 0.0, "selected_ids": [], "reason": "short reason"}

The confidence is your estimated probability that injecting exactly the selected
lessons will improve final-answer correctness compared with solving unaided. Select
no more than the requested number of IDs and never invent an ID."""

GATE_CANDIDATE_HEADER = """Candidate lessons returned by a first-stage retriever.
They are unverified and may be irrelevant or actively misleading."""


@dataclass(frozen=True)
class Experience:
    id: str
    level: str
    content: str
    metadata: dict[str, Any]

    @property
    def retrieval_text(self) -> str:
        fields = [
            self.metadata.get("domain"),
            self.metadata.get("task_family"),
            self.metadata.get("strategy_type"),
            self.metadata.get("tool_type"),
            self.metadata.get("task_stage"),
            self.metadata.get("failure_mode"),
            self.content,
        ]
        return "\n".join(str(value) for value in fields if value not in (None, "", "none", "unknown"))


@dataclass(frozen=True)
class Selection:
    experience: Experience
    score: float
    lexical_score: float | None = None
    dense_score: float | None = None


@dataclass(frozen=True)
class Task:
    dataset_index: int
    question: str
    answer: str
    source: str


def _iter_level(raw: Any, level: str) -> Iterable[dict[str, Any]]:
    if isinstance(raw, dict):
        for exp_id, value in raw.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault("id", str(exp_id))
            else:
                item = {"id": str(exp_id), "content": str(value)}
            item.setdefault("level", level)
            yield item
    elif isinstance(raw, list):
        for index, value in enumerate(raw):
            item = dict(value) if isinstance(value, dict) else {"content": str(value)}
            item.setdefault("id", f"{level}_{index}")
            item.setdefault("level", level)
            yield item


def load_experiences(path: Path) -> list[Experience]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)
    experiences: list[Experience] = []
    for level, key in (("L2", "l2_experiences"), ("L1", "l1_experiences"), ("L0", "l0_experiences")):
        for item in _iter_level(payload.get(key, []), level):
            if str(item.get("lifecycle_status", "active")).lower() != "active":
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            experiences.append(
                Experience(
                    id=str(item["id"]),
                    level=level,
                    content=content,
                    metadata=item,
                )
            )
    if len({experience.id for experience in experiences}) != len(experiences):
        raise ValueError("active experience IDs are not unique")
    return experiences


def _sqlite_path(db_url: str) -> Path:
    prefixes = ("sqlite:///", "sqlite+pysqlite:///")
    for prefix in prefixes:
        if db_url.startswith(prefix):
            return Path(db_url[len(prefix) :])
    raise ValueError("This pilot currently supports a SQLite UTU_DB_URL only")


def load_tasks(dataset: str, limit: int, seed: int) -> list[Task]:
    db_url = os.getenv("UTU_DB_URL", "sqlite:///test.db")
    db_path = _sqlite_path(db_url)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            'SELECT "index", question, answer, source FROM data WHERE dataset = ? ORDER BY "index"',
            (dataset,),
        ).fetchall()
    tasks = [Task(int(index), str(question), str(answer), str(source)) for index, question, answer, source in rows]
    if not tasks:
        raise ValueError(f"dataset has no rows: {dataset}")
    if limit and limit < len(tasks):
        tasks = sorted(random.Random(seed).sample(tasks, limit), key=lambda task: task.dataset_index)
    return tasks


def tokenize(text: str) -> list[str]:
    """Math-aware lexical tokens with individual CJK characters."""

    return re.findall(r"\\[a-zA-Z]+|[a-z0-9_]+|[\u4e00-\u9fff]", (text or "").lower())


try:
    import tiktoken  # type: ignore[import-not-found]

    _TOKENIZER = tiktoken.get_encoding("cl100k_base")
    TOKENIZER_NAME = "cl100k_base"
except ImportError:
    _TOKENIZER = None
    TOKENIZER_NAME = "regex_approximation"


def count_tokens(text: str) -> int:
    if _TOKENIZER is not None:
        return len(_TOKENIZER.encode(text))
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|\\[A-Za-z]+|[^\w\s]", text))


def truncate_tokens(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if _TOKENIZER is not None:
        tokens = _TOKENIZER.encode(text)
        return text if len(tokens) <= limit else _TOKENIZER.decode(tokens[:limit]) + "..."
    matches = list(re.finditer(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|\\[A-Za-z]+|[^\w\s]", text))
    if len(matches) <= limit:
        return text
    return text[: matches[limit - 1].end()] + "..."


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class BM25Okapi:
    """Small dependency-free BM25 implementation used only by this pilot."""

    def __init__(self, corpus: Sequence[Sequence[str]], *, k1: float = 1.5, b: float = 0.75):
        self.corpus = [list(document) for document in corpus]
        self.k1 = k1
        self.b = b
        self.document_lengths = [len(document) for document in self.corpus]
        self.average_length = sum(self.document_lengths) / len(self.document_lengths) if self.document_lengths else 0.0
        self.term_frequencies: list[dict[str, int]] = []
        document_frequency: dict[str, int] = defaultdict(int)
        for document in self.corpus:
            frequencies: dict[str, int] = defaultdict(int)
            for term in document:
                frequencies[term] += 1
            self.term_frequencies.append(dict(frequencies))
            for term in frequencies:
                document_frequency[term] += 1
        document_count = len(self.corpus)
        self.idf = {
            term: math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def get_scores(self, query: Sequence[str]) -> list[float]:
        if not self.corpus or self.average_length == 0.0:
            return [0.0] * len(self.corpus)
        scores: list[float] = []
        for frequencies, document_length in zip(self.term_frequencies, self.document_lengths, strict=True):
            normalizer = self.k1 * (1.0 - self.b + self.b * document_length / self.average_length)
            score = 0.0
            for term in query:
                term_frequency = frequencies.get(term, 0)
                if term_frequency:
                    score += self.idf.get(term, 0.0) * (
                        term_frequency * (self.k1 + 1.0) / (term_frequency + normalizer)
                    )
            scores.append(score)
        return scores


class CurrentSelector:
    """Faithful reproduction of TrainingFreeGRPOProcesser._select_experiences."""

    def __init__(self, experiences: Sequence[Experience], top_k: int):
        self.top_k = top_k
        self.global_experiences = [experience for experience in experiences if experience.level != "L0"]
        self.l0 = [experience for experience in experiences if experience.level == "L0"]
        self.by_id = {experience.id: experience for experience in experiences}
        self.retriever = ExperienceRetriever()
        self.retriever.index({experience.id: experience.content for experience in self.l0})

    def select(self, query: str) -> list[Selection]:
        if self.top_k == 0:
            return [Selection(experience, 0.0) for experience in self.by_id.values()]
        selected = [Selection(experience, math.inf) for experience in self.global_experiences]
        selected.extend(
            Selection(self.by_id[item.exp_id], item.score, lexical_score=item.score)
            for item in self.retriever.retrieve(query, top_k=self.top_k, min_score=1e-12)
        )
        return selected


class HybridSelector:
    """BM25 + dense RRF recall followed by MMR diversity selection."""

    def __init__(
        self,
        experiences: Sequence[Experience],
        *,
        top_k: int,
        recall_k: int,
        mmr_lambda: float,
        embedding_model: str,
        embedding_revision: str,
        embedding_dimensions: int,
        embedding_cache: Path,
    ):
        if not experiences:
            raise ValueError("hybrid selector requires at least one experience")
        self.experiences = list(experiences)
        self.top_k = top_k
        self.recall_k = min(recall_k, len(self.experiences))
        self.mmr_lambda = mmr_lambda
        self.texts = [experience.retrieval_text for experience in self.experiences]
        self.bm25 = BM25Okapi([tokenize(text) for text in self.texts])
        self.embedding_provider = SentenceTransformerEmbeddingProvider(
            model_name=embedding_model,
            model_revision=embedding_revision,
            expected_dimensions=embedding_dimensions,
            cache_path=embedding_cache,
            device="cpu",
            batch_size=32,
            local_files_only=True,
            random_seed=42,
        )
        self.vectors = self.embedding_provider.embed(self.texts)

    def select(self, query: str) -> list[Selection]:
        lexical_scores = [float(value) for value in self.bm25.get_scores(tokenize(query))]
        query_vector = self.embedding_provider.embed([query])[0]
        dense_scores = [dot(query_vector, vector) for vector in self.vectors]

        lexical_rank = sorted(
            (index for index, score in enumerate(lexical_scores) if score > 0.0),
            key=lambda index: (-lexical_scores[index], self.experiences[index].id),
        )[: self.recall_k]
        dense_rank = sorted(
            range(len(self.experiences)),
            key=lambda index: (-dense_scores[index], self.experiences[index].id),
        )[: self.recall_k]

        rrf: dict[int, float] = defaultdict(float)
        for ranking in (lexical_rank, dense_rank):
            for rank, index in enumerate(ranking, start=1):
                rrf[index] += 1.0 / (60.0 + rank)
        if not rrf:
            return []
        max_rrf = max(rrf.values())
        candidates = set(rrf)
        selected: list[int] = []
        level_limits = {"L2": 1, "L1": 3, "L0": self.top_k}
        level_counts: dict[str, int] = defaultdict(int)

        while candidates and len(selected) < self.top_k:
            eligible = [
                index
                for index in candidates
                if level_counts[self.experiences[index].level]
                < level_limits.get(self.experiences[index].level, self.top_k)
            ]
            if not eligible:
                break

            def mmr_key(index: int) -> tuple[float, str]:
                relevance = rrf[index] / max_rrf
                redundancy = max(
                    (max(0.0, dot(self.vectors[index], self.vectors[prior])) for prior in selected),
                    default=0.0,
                )
                score = self.mmr_lambda * relevance - (1.0 - self.mmr_lambda) * redundancy
                return score, self.experiences[index].id

            best = max(eligible, key=mmr_key)
            candidates.remove(best)
            selected.append(best)
            level_counts[self.experiences[best].level] += 1

        return [
            Selection(
                experience=self.experiences[index],
                score=rrf[index] / max_rrf,
                lexical_score=lexical_scores[index],
                dense_score=dense_scores[index],
            )
            for index in selected
        ]


def render_experiences(
    selections: Sequence[Selection],
    token_budget: int,
    *,
    header: str = EXPERIENCE_HEADER,
) -> tuple[str, int]:
    if not selections or token_budget <= 0:
        return "", 0
    header = header.strip()
    header_tokens = count_tokens(header)
    available = token_budget - header_tokens
    if available < 24:
        return "", 0
    per_item_budget = max(24, available // len(selections))
    lines: list[str] = [header]
    for selection in selections:
        prefix = f"[{selection.experience.id}][{selection.experience.level}] "
        # Reserve three approximate tokens for the truncation ellipsis. A
        # per-item allowance prevents the first long experience from consuming
        # the complete slate budget before the other selected items are shown.
        remaining = per_item_budget - count_tokens(prefix) - 3
        if remaining < 24:
            continue
        content = truncate_tokens(selection.experience.content, remaining)
        lines.append(prefix + content)
    rendered = "\n".join(lines)
    if len(lines) == 1:
        return "", 0
    rendered_tokens = count_tokens(rendered)
    if rendered_tokens > token_budget:
        rendered = truncate_tokens(rendered, token_budget - 3)
        rendered_tokens = count_tokens(rendered)
    return rendered, rendered_tokens


def parse_gate_decision(
    response: str,
    candidates: Sequence[Selection],
    *,
    confidence_threshold: float,
    max_selected: int,
) -> tuple[list[Selection], dict[str, Any]]:
    """Parse a fail-closed retrieval decision from an untrusted model response."""

    start = response.find("{")
    end = response.rfind("}")
    if start < 0 or end <= start:
        if re.search(r'"use_retrieval"\s*:\s*false', response, re.IGNORECASE) is None:
            raise ValueError("gate response does not contain a JSON object")
        payload = {
            "use_retrieval": False,
            "confidence": 0.0,
            "selected_ids": [],
            "reason": "truncated JSON with explicit rejection",
        }
    else:
        try:
            payload = json.loads(response[start : end + 1])
        except json.JSONDecodeError:
            # A malformed *rejection* can still be handled safely. Never recover
            # an affirmative decision from invalid JSON because that could inject
            # an unintended lesson.
            explicit_rejection = re.search(r'"use_retrieval"\s*:\s*false', response, re.IGNORECASE)
            if explicit_rejection is None:
                raise
            payload = {
                "use_retrieval": False,
                "confidence": 0.0,
                "selected_ids": [],
                "reason": "malformed JSON with explicit rejection",
            }
    if not isinstance(payload, dict):
        raise ValueError("gate response JSON must be an object")

    raw_confidence = payload.get("confidence", 0.0)
    if isinstance(raw_confidence, bool):
        raise ValueError("gate confidence must be numeric")
    confidence = min(1.0, max(0.0, float(raw_confidence)))
    requested_ids = payload.get("selected_ids", [])
    if not isinstance(requested_ids, list):
        raise ValueError("gate selected_ids must be a list")

    by_id = {selection.experience.id: selection for selection in candidates}
    valid_ids: list[str] = []
    for raw_id in requested_ids:
        experience_id = str(raw_id)
        if experience_id in by_id and experience_id not in valid_ids:
            valid_ids.append(experience_id)
    valid_ids = valid_ids[:max_selected]
    requested_use = payload.get("use_retrieval") is True
    accepted = requested_use and confidence >= confidence_threshold and bool(valid_ids)
    selected = [by_id[experience_id] for experience_id in valid_ids] if accepted else []
    return selected, {
        "parsed": True,
        "requested_use": requested_use,
        "confidence": confidence,
        "accepted": accepted,
        "requested_ids": [str(value) for value in requested_ids],
        "valid_ids": valid_ids,
        "reason": str(payload.get("reason", ""))[:500],
    }


def combine_usage(*usages: dict[str, Any] | None) -> dict[str, int] | None:
    """Add token counts across gate and generation calls for fair cost reporting."""

    present = [usage for usage in usages if isinstance(usage, dict)]
    if not present:
        return None
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {field: sum(int(usage.get(field, 0) or 0) for usage in present) for field in fields}


def make_user_prompt(task: Task, experience_block: str) -> str:
    if not experience_block:
        return task.question
    return f"{experience_block}\n\nProblem:\n{task.question}"


def verify_math(answer: str, response: str) -> float:
    verifier = math_metric(
        gold_extraction_target=(LatexExtractionConfig(),),
        pred_extraction_target=(ExprExtractionConfig(), LatexExtractionConfig()),
    )
    try:
        score, _ = verifier([f"\\boxed{{{answer}}}"], [response])
        return float(score)
    except Exception:  # noqa: BLE001 - mirror the production verifier's fail-closed behavior
        return 0.0


def validate_no_leakage(experiences: Sequence[Experience], eval_dataset: str) -> None:
    needle = eval_dataset.casefold()
    leaked: list[tuple[str, str]] = []
    for experience in experiences:
        for source_id in experience.metadata.get("source_task_ids", []) or []:
            source_dataset = str(source_id).rsplit(":", 1)[0].casefold()
            if source_dataset == needle:
                leaked.append((experience.id, str(source_id)))
    if leaked:
        raise ValueError(f"evaluation-source leakage detected: {leaked[:5]}")


def language_profile(experiences: Sequence[Experience]) -> dict[str, float | int]:
    total = sum(len(experience.content) for experience in experiences)
    cjk = sum(1 for experience in experiences for char in experience.content if "\u4e00" <= char <= "\u9fff")
    latin = sum(1 for experience in experiences for char in experience.content if ("a" <= char.lower() <= "z"))
    return {
        "characters": total,
        "cjk_fraction": round(cjk / total, 4) if total else 0.0,
        "latin_fraction": round(latin / total, 4) if total else 0.0,
    }


def selection_diagnostics(
    tasks: Sequence[Task],
    current: CurrentSelector,
    hybrid: HybridSelector,
    token_budget: int,
) -> dict[str, Any]:
    rows = []
    overlaps = []
    for task in tasks:
        current_selection = current.select(task.question)
        hybrid_selection = hybrid.select(task.question)
        current_ids = [item.experience.id for item in current_selection]
        hybrid_ids = [item.experience.id for item in hybrid_selection]
        union = set(current_ids) | set(hybrid_ids)
        overlap = len(set(current_ids) & set(hybrid_ids)) / len(union) if union else 1.0
        overlaps.append(overlap)
        current_block, current_tokens = render_experiences(current_selection, token_budget)
        hybrid_block, hybrid_tokens = render_experiences(hybrid_selection, token_budget)
        rows.append(
            {
                "dataset_index": task.dataset_index,
                "current_ids": current_ids,
                "hybrid_ids": hybrid_ids,
                "jaccard": round(overlap, 4),
                "current_tokens": current_tokens,
                "hybrid_tokens": hybrid_tokens,
                "current_block_sha256": hashlib.sha256(current_block.encode()).hexdigest(),
                "hybrid_block_sha256": hashlib.sha256(hybrid_block.encode()).hexdigest(),
            }
        )
    return {
        "mean_selection_jaccard": round(statistics.mean(overlaps), 4),
        "tasks_with_different_selection": sum(row["current_ids"] != row["hybrid_ids"] for row in rows),
        "rows": rows,
    }


def exact_mcnemar_p(current_only: int, hybrid_only: int) -> float:
    discordant = current_only + hybrid_only
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, value) for value in range(0, min(current_only, hybrid_only) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def paired_bootstrap_ci(differences: Sequence[float], seed: int, samples: int = 10_000) -> list[float]:
    if not differences:
        return [0.0, 0.0]
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        draw = [differences[rng.randrange(len(differences))] for _ in differences]
        means.append(statistics.mean(draw))
    means.sort()
    return [means[int(0.025 * samples)], means[min(samples - 1, int(0.975 * samples))]]


def _record_is_usable(record: dict[str, Any]) -> bool:
    return (
        record.get("error") is None
        and bool(str(record.get("response", "")).strip())
        and record.get("finish_reason") != "length"
    )


def summarize(
    records: Sequence[dict[str, Any]],
    seed: int,
    *,
    allowed_indices: set[int] | None = None,
    model: str | None = None,
    conditions: Sequence[str] = CONDITIONS,
) -> dict[str, Any]:
    latest: dict[tuple[int, int, str], dict[str, Any]] = {}
    for record in records:
        if allowed_indices is not None and record["dataset_index"] not in allowed_indices:
            continue
        if model is not None and record.get("model") != model:
            continue
        key = (record["dataset_index"], record["repeat"], record["condition"])
        is_usable = _record_is_usable(record)
        previous = latest.get(key)
        previous_usable = previous is not None and _record_is_usable(previous)
        if previous is None or is_usable or not previous_usable:
            latest[key] = record
    usable = [record for record in latest.values() if _record_is_usable(record)]
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_pair: dict[tuple[int, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in usable:
        by_condition[record["condition"]].append(record)
        by_pair[(record["dataset_index"], record["repeat"])][record["condition"]] = record

    def mean_usage(rows: Sequence[dict[str, Any]], field: str) -> float | None:
        values = [row["usage"].get(field) for row in rows if isinstance(row.get("usage"), dict)]
        numeric = [float(value) for value in values if value is not None]
        return statistics.mean(numeric) if numeric else None

    aggregates = {}
    for condition in conditions:
        rows = by_condition.get(condition, [])
        mean_prompt_tokens = mean_usage(rows, "prompt_tokens")
        mean_completion_tokens = mean_usage(rows, "completion_tokens")
        aggregates[condition] = {
            "n": len(rows),
            "accuracy": sum(row["reward"] for row in rows) / len(rows) if rows else None,
            "mean_injected_tokens": statistics.mean(row["injected_tokens"] for row in rows) if rows else None,
            "mean_api_prompt_tokens": mean_prompt_tokens,
            "mean_api_completion_tokens": mean_completion_tokens,
            "mean_api_total_tokens": (
                mean_prompt_tokens + mean_completion_tokens
                if mean_prompt_tokens is not None and mean_completion_tokens is not None
                else None
            ),
        }

    comparisons = {}
    policies_and_baselines = [("hybrid", "no_experience"), ("hybrid", "current")]
    if GATED_CONDITION in conditions:
        policies_and_baselines.extend(
            [
                (GATED_CONDITION, "no_experience"),
                (GATED_CONDITION, "current"),
                (GATED_CONDITION, "hybrid"),
            ]
        )
    for policy, baseline in policies_and_baselines:
        pairs = [pair for pair in by_pair.values() if baseline in pair and policy in pair]
        differences = [pair[policy]["reward"] - pair[baseline]["reward"] for pair in pairs]
        policy_only = sum(pair[policy]["reward"] > 0 and pair[baseline]["reward"] == 0 for pair in pairs)
        baseline_only = sum(pair[baseline]["reward"] > 0 and pair[policy]["reward"] == 0 for pair in pairs)
        comparisons[f"{policy}_vs_{baseline}"] = {
            "paired_n": len(pairs),
            "accuracy_delta": statistics.mean(differences) if differences else None,
            "bootstrap_95_ci": paired_bootstrap_ci(differences, seed) if differences else None,
            f"{policy}_only_correct": policy_only,
            "baseline_only_correct": baseline_only,
            "mcnemar_exact_p": exact_mcnemar_p(baseline_only, policy_only),
        }
    return {
        "completed_records": len(usable),
        "failed_records": len(latest) - len(usable),
        "aggregates": aggregates,
        "comparisons": comparisons,
    }


def read_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))
    return records


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


async def run_online(
    args: argparse.Namespace,
    tasks: Sequence[Task],
    current: CurrentSelector,
    hybrid: HybridSelector,
    conditions: Sequence[str],
) -> list[dict[str, Any]]:
    api_key = os.getenv("UTU_LLM_API_KEY")
    base_url = os.getenv("UTU_LLM_BASE_URL")
    model = args.model or os.getenv("UTU_LLM_MODEL")
    if not api_key or not base_url or not model:
        raise ValueError("UTU_LLM_API_KEY, UTU_LLM_BASE_URL, and UTU_LLM_MODEL must be configured")

    gated_policy_config = {
        "version": 2,
        "condition": GATED_CONDITION,
        "model": model,
        "experience_sha256": hashlib.sha256(args.experience_path.read_bytes()).hexdigest(),
        "top_k": args.top_k,
        "recall_k": args.recall_k,
        "mmr_lambda": args.mmr_lambda,
        "embedding_model": args.embedding_model,
        "embedding_revision": args.embedding_revision,
        "confidence_threshold": args.gate_confidence_threshold,
        "max_selected": args.gate_max_selected,
        "candidate_token_budget": args.token_budget,
        "injection_token_budget": args.gated_token_budget,
        "gate_max_output_tokens": args.gate_max_output_tokens,
        "abstention_mode": "reuse_no_experience_record",
        "gate_prompt_sha256": hashlib.sha256(GATE_SYSTEM_PROMPT.encode()).hexdigest(),
    }
    gated_policy_hash = hashlib.sha256(json.dumps(gated_policy_config, sort_keys=True).encode()).hexdigest()
    existing = read_existing(args.output)
    no_experience_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    for record in existing:
        if not (
            _record_is_usable(record)
            and record.get("model") == model
            and record.get("dataset") == args.dataset
            and record.get("condition") == "no_experience"
        ):
            continue
        no_experience_by_pair[(int(record["dataset_index"]), int(record["repeat"]))] = record
    completed = set()
    for record in existing:
        if not (_record_is_usable(record) and record.get("model") == model and record.get("dataset") == args.dataset):
            continue
        if record.get("condition") == GATED_CONDITION and record.get("retrieval_policy_hash") != gated_policy_hash:
            continue
        completed.add((record.get("dataset_index"), record.get("repeat"), record.get("condition")))
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)
    semaphore = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()

    jobs: list[tuple[Task, int, str]] = []
    rng = random.Random(args.seed)
    for repeat in range(args.repeats):
        for task in tasks:
            order = list(conditions)
            rng.shuffle(order)
            jobs.extend((task, repeat, condition) for condition in order)

    async def apply_gate(task: Task, candidates: Sequence[Selection]) -> tuple[list[Selection], dict[str, Any]]:
        candidate_block, candidate_tokens = render_experiences(
            candidates,
            args.token_budget,
            header=GATE_CANDIDATE_HEADER,
        )
        gate_prompt = (
            f"Maximum selected lessons: {args.gate_max_selected}\n\nProblem:\n{task.question}\n\n{candidate_block}"
        )
        gate_response = ""
        gate_error = None
        gate_finish_reason = None
        gate_usage: dict[str, Any] | None = None
        gate_reasoning_chars = 0
        gate_started = time.perf_counter()
        for attempt in range(1, args.max_attempts + 1):
            try:
                async with semaphore:
                    request: dict[str, Any] = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": GATE_SYSTEM_PROMPT},
                            {"role": "user", "content": gate_prompt},
                        ],
                        "temperature": 0.0,
                        "max_tokens": args.gate_max_output_tokens,
                    }
                    if args.disable_thinking:
                        request["extra_body"] = {"enable_thinking": False}
                    completion = await client.chat.completions.create(**request)
                choice = completion.choices[0]
                message = choice.message
                gate_response = message.content or ""
                gate_finish_reason = choice.finish_reason
                reasoning = getattr(message, "reasoning_content", None)
                if reasoning is None and getattr(message, "model_extra", None):
                    reasoning = message.model_extra.get("reasoning_content")
                gate_reasoning_chars = len(reasoning or "")
                gate_usage = completion.usage.model_dump() if completion.usage is not None else None
                if gate_finish_reason == "length":
                    gate_error = "IncompleteGateResponse: finish_reason=length"
                elif not gate_response.strip():
                    gate_error = f"EmptyGateResponse: finish_reason={gate_finish_reason}"
                else:
                    gate_error = None
                break
            except Exception as exc:  # noqa: BLE001
                gate_error = f"{type(exc).__name__}: {exc}"
                if attempt < args.max_attempts:
                    await asyncio.sleep(min(2**attempt, 8))

        decision: dict[str, Any] = {
            "candidate_ids": [selection.experience.id for selection in candidates],
            "candidate_tokens": candidate_tokens,
            "confidence_threshold": args.gate_confidence_threshold,
            "max_selected": args.gate_max_selected,
            "response": gate_response,
            "error": gate_error,
            "finish_reason": gate_finish_reason,
            "usage": gate_usage,
            "reasoning_chars": gate_reasoning_chars,
            "latency_seconds": round(time.perf_counter() - gate_started, 3),
        }
        if gate_error is not None:
            decision.update({"parsed": False, "accepted": False, "selected_ids": []})
            return [], decision
        try:
            selected, parsed = parse_gate_decision(
                gate_response,
                candidates,
                confidence_threshold=args.gate_confidence_threshold,
                max_selected=args.gate_max_selected,
            )
            decision.update(parsed)
            decision["selected_ids"] = [selection.experience.id for selection in selected]
            return selected, decision
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            decision.update(
                {
                    "parsed": False,
                    "accepted": False,
                    "selected_ids": [],
                    "parse_error": f"{type(exc).__name__}: {exc}",
                }
            )
            return [], decision

    async def execute(task: Task, repeat: int, condition: str) -> dict[str, Any] | None:
        key = (task.dataset_index, repeat, condition)
        if key in completed:
            return None
        started = time.perf_counter()
        gate_decision: dict[str, Any] | None = None
        if condition == "current":
            selections = current.select(task.question)
        elif condition == "hybrid":
            selections = hybrid.select(task.question)
        elif condition == GATED_CONDITION:
            candidates = hybrid.select(task.question)
            selections, gate_decision = await apply_gate(task, candidates)
        else:
            selections = []
        injection_budget = args.gated_token_budget if condition == GATED_CONDITION else args.token_budget
        block, injected_tokens = render_experiences(selections, injection_budget)
        prompt = make_user_prompt(task, block)
        response = ""
        error = None
        finish_reason = None
        generation_usage: dict[str, Any] | None = None
        reasoning_chars = 0
        reused_baseline = None
        if condition == GATED_CONDITION and not selections:
            reused_baseline = no_experience_by_pair.get((task.dataset_index, repeat))
        if reused_baseline is not None:
            response = str(reused_baseline["response"])
            error = reused_baseline.get("error")
            finish_reason = reused_baseline.get("finish_reason")
            generation_usage = reused_baseline.get("generation_usage") or reused_baseline.get("usage")
            reasoning_chars = int(reused_baseline.get("reasoning_chars", 0) or 0)
        else:
            for attempt in range(1, args.max_attempts + 1):
                try:
                    async with semaphore:
                        request: dict[str, Any] = {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": BASE_SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": 0.0,
                            "max_tokens": args.max_output_tokens,
                        }
                        if args.disable_thinking:
                            request["extra_body"] = {"enable_thinking": False}
                        completion = await client.chat.completions.create(
                            **request,
                        )
                    choice = completion.choices[0]
                    message = choice.message
                    response = message.content or ""
                    finish_reason = choice.finish_reason
                    reasoning = getattr(message, "reasoning_content", None)
                    if reasoning is None and getattr(message, "model_extra", None):
                        reasoning = message.model_extra.get("reasoning_content")
                    reasoning_chars = len(reasoning or "")
                    generation_usage = completion.usage.model_dump() if completion.usage is not None else None
                    if finish_reason == "length":
                        error = "IncompleteModelResponse: finish_reason=length"
                    elif not response.strip():
                        error = f"EmptyModelResponse: finish_reason={finish_reason}"
                    else:
                        error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    error = f"{type(exc).__name__}: {exc}"
                    if attempt < args.max_attempts:
                        await asyncio.sleep(min(2**attempt, 8))

        reward = verify_math(task.answer, response) if error is None else 0.0
        gate_usage = gate_decision.get("usage") if gate_decision is not None else None
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "dataset": args.dataset,
            "dataset_index": task.dataset_index,
            "repeat": repeat,
            "condition": condition,
            "model": model,
            "temperature": 0.0,
            "thinking_disabled": args.disable_thinking,
            "answer": task.answer,
            "reward": reward,
            "response": response,
            "error": error,
            "finish_reason": finish_reason,
            "usage": combine_usage(gate_usage, generation_usage),
            "generation_usage": generation_usage,
            "reasoning_chars": reasoning_chars,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "selected_ids": [selection.experience.id for selection in selections],
            "selection_scores": [
                {
                    "id": selection.experience.id,
                    "score": selection.score,
                    "lexical": selection.lexical_score,
                    "dense": selection.dense_score,
                }
                for selection in selections
            ],
            "injected_tokens": injected_tokens,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "gate_decision": gate_decision,
            "retrieval_policy_hash": gated_policy_hash if condition == GATED_CONDITION else None,
            "reused_no_experience": reused_baseline is not None,
            "reused_record_timestamp": reused_baseline.get("timestamp") if reused_baseline is not None else None,
        }
        async with write_lock:
            append_record(args.output, record)
        print(
            f"task={task.dataset_index:02d} repeat={repeat} condition={condition:<13} "
            f"reward={reward:.0f} exp={len(selections)} tokens={injected_tokens} "
            f"gate={gate_decision.get('accepted') if gate_decision else '-'} error={error is not None}",
            flush=True,
        )
        return record

    try:
        new_records = await asyncio.gather(*(execute(*job) for job in jobs))
    finally:
        await client.close()
    return existing + [record for record in new_records if record is not None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experience-path", type=Path, default=DEFAULT_EXPERIENCE_PATH)
    parser.add_argument("--embedding-cache", type=Path, default=DEFAULT_EMBEDDING_CACHE)
    parser.add_argument("--embedding-model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--embedding-revision", default=DEFAULT_MODEL_REVISION)
    parser.add_argument("--embedding-dimensions", type=int, default=384)
    parser.add_argument("--dataset", default="AIME24")
    parser.add_argument("--limit", type=int, default=6, help="0 uses the full dataset")
    parser.add_argument(
        "--exclude-index",
        type=int,
        nargs="*",
        default=[],
        help="Dataset indices excluded after sampling, e.g. known common infrastructure failures",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--recall-k", type=int, default=20)
    parser.add_argument("--mmr-lambda", type=float, default=0.75)
    parser.add_argument("--token-budget", type=int, default=1600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument(
        "--disable-thinking",
        action="store_true",
        help="Send enable_thinking=false through the provider's OpenAI-compatible extra body",
    )
    parser.add_argument(
        "--include-gated-hybrid",
        action="store_true",
        help="Add a conservative LLM applicability gate that may inject 0 to N hybrid candidates",
    )
    parser.add_argument("--gate-confidence-threshold", type=float, default=0.8)
    parser.add_argument("--gate-max-selected", type=int, default=2)
    parser.add_argument("--gate-max-output-tokens", type=int, default=512)
    parser.add_argument(
        "--gated-token-budget",
        type=int,
        default=800,
        help="Final experience-token budget after gated candidate filtering",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build selectors and report selections without model calls",
    )
    parser.add_argument(
        "--summarize-only",
        action="store_true",
        help="Rebuild the summary from an existing JSONL file without model calls",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if not 0.0 <= args.mmr_lambda <= 1.0:
        raise ValueError("--mmr-lambda must be in [0, 1]")
    if not 0.0 <= args.gate_confidence_threshold <= 1.0:
        raise ValueError("--gate-confidence-threshold must be in [0, 1]")
    if args.gate_max_selected < 1:
        raise ValueError("--gate-max-selected must be positive")
    if args.gate_max_output_tokens < 32:
        raise ValueError("--gate-max-output-tokens must be at least 32")
    if args.gated_token_budget < 0:
        raise ValueError("--gated-token-budget must be non-negative")
    conditions = CONDITIONS + ((GATED_CONDITION,) if args.include_gated_hybrid else ())
    experiences = load_experiences(args.experience_path)
    validate_no_leakage(experiences, args.dataset)
    tasks = load_tasks(args.dataset, args.limit, args.seed)
    excluded_indices = set(args.exclude_index)
    tasks = [task for task in tasks if task.dataset_index not in excluded_indices]
    if not tasks:
        raise ValueError("no tasks remain after --exclude-index filtering")
    current = CurrentSelector(experiences, args.top_k)
    hybrid = HybridSelector(
        experiences,
        top_k=args.top_k,
        recall_k=args.recall_k,
        mmr_lambda=args.mmr_lambda,
        embedding_model=args.embedding_model,
        embedding_revision=args.embedding_revision,
        embedding_dimensions=args.embedding_dimensions,
        embedding_cache=args.embedding_cache,
    )
    diagnostics = {
        "dataset": args.dataset,
        "task_count": len(tasks),
        "experience_path": str(args.experience_path),
        "experience_sha256": hashlib.sha256(args.experience_path.read_bytes()).hexdigest(),
        "experience_counts": {
            level: sum(experience.level == level for experience in experiences) for level in ("L0", "L1", "L2")
        },
        "language_profile": language_profile(experiences),
        "tokenizer": TOKENIZER_NAME,
        "embedding": hybrid.embedding_provider.info(),
        "selection": selection_diagnostics(tasks, current, hybrid, args.token_budget),
        "conditions": list(conditions),
        "gated_policy": (
            {
                "confidence_threshold": args.gate_confidence_threshold,
                "max_selected": args.gate_max_selected,
                "candidate_token_budget": args.token_budget,
                "injection_token_budget": args.gated_token_budget,
                "gate_max_output_tokens": args.gate_max_output_tokens,
            }
            if args.include_gated_hybrid
            else None
        ),
    }
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        return

    records = (
        read_existing(args.output)
        if args.summarize_only
        else await run_online(args, tasks, current, hybrid, conditions)
    )
    summary = {
        "run_config": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "diagnostics": diagnostics,
        "results": summarize(
            records,
            args.seed,
            allowed_indices={task.dataset_index for task in tasks},
            model=args.model or os.getenv("UTU_LLM_MODEL"),
            conditions=conditions,
        ),
    }
    summary_path = args.summary_output or args.output.with_suffix(".summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print(json.dumps(summary["results"], ensure_ascii=False, indent=2), flush=True)
    print(f"summary={summary_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
