"""
Lightweight lexical retrieval for practice and evaluation experience injection.

Motivation:
- As the experience pool grows, concatenating everything into agent instructions
  increases prompt length and noise.
- A retrieval layer can select top-k relevant experiences per query/context.

This module is environment-agnostic and does not require external dependencies.
It uses a lightweight bag-of-words + IDF scoring.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable


_LEXICAL_RUN = re.compile(r"[a-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    """Tokenize Latin text by word and CJK text into overlapping bigrams."""

    if not text:
        return []
    tokens: list[str] = []
    for run in _LEXICAL_RUN.findall(text.lower()):
        if "\u3400" <= run[0] <= "\u9fff":
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        else:
            tokens.append(run)
    return tokens


@dataclass(frozen=True)
class RetrievedExperience:
    exp_id: str
    content: str
    score: float
    meta: dict[str, Any] | None = None


class ExperienceRetriever:
    """Lightweight text retriever for experience snippets."""

    def __init__(self) -> None:
        self._docs: list[tuple[str, str, dict[str, Any] | None]] = []  # (id, content, meta)
        self._df: dict[str, int] = {}
        self._n_docs: int = 0

    def index(self, experiences: Iterable[tuple[str, str]] | dict[str, str] | list[dict[str, Any]]) -> None:
        """Index experiences.

        Supported formats:
        - dict[str, str]: {id: content}
        - Iterable[tuple[id, content]]
        - list[dict]: {"id": "...", "content": "...", "meta": {...}}
        """
        docs: list[tuple[str, str, dict[str, Any] | None]] = []
        if isinstance(experiences, dict):
            docs = [(k, v, None) for k, v in experiences.items()]
        else:
            for item in experiences:
                if isinstance(item, tuple) and len(item) == 2:
                    docs.append((item[0], item[1], None))
                elif isinstance(item, dict):
                    docs.append((str(item.get("id", "")), str(item.get("content", "")), item.get("meta")))
                else:
                    raise TypeError(f"Unsupported experience item type: {type(item)}")

        self._docs = docs
        self._n_docs = len(docs)
        self._df = {}
        for _, content, _ in docs:
            seen = set(_tokenize(content))
            for t in seen:
                self._df[t] = self._df.get(t, 0) + 1

    def retrieve(self, query: str, top_k: int = 5, min_score: float = 0.0) -> list[RetrievedExperience]:
        if not self._docs:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        q_tf: dict[str, int] = {}
        for t in q_tokens:
            q_tf[t] = q_tf.get(t, 0) + 1

        results: list[RetrievedExperience] = []
        for exp_id, content, meta in self._docs:
            d_tokens = _tokenize(content)
            if not d_tokens:
                continue
            d_tf: dict[str, int] = {}
            for t in d_tokens:
                d_tf[t] = d_tf.get(t, 0) + 1

            score = 0.0
            for t, q_cnt in q_tf.items():
                if t not in d_tf:
                    continue
                df = self._df.get(t, 0)
                idf = math.log((self._n_docs + 1) / (df + 1)) + 1.0
                score += idf * (1.0 + math.log(1 + d_tf[t])) * (1.0 + math.log(1 + q_cnt))

            # A zero-overlap document is not a retrieval result. In
            # particular, ``min_score=0`` must not inject arbitrary documents
            # merely because the requested top-k has spare capacity.
            if score > 0.0 and score >= min_score:
                results.append(RetrievedExperience(exp_id=exp_id, content=content, score=score, meta=meta))

        results.sort(key=lambda result: (-result.score, result.exp_id))
        return results[: max(0, top_k)]

    def render_for_injection(self, retrieved: list[RetrievedExperience]) -> str:
        """Render retrieved experiences into a compact prompt block."""
        if not retrieved:
            return ""
        lines = ["\n\nRelevant experiences (retrieved):"]
        for i, r in enumerate(retrieved, 1):
            lines.append(f"[R{i}][{r.exp_id}] {r.content}")
        return "\n".join(lines)

