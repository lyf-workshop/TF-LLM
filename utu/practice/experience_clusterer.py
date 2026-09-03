"""Deterministic clustering for hierarchical experiences.

No third-party clustering package is required by the clustering algorithm.
Formal runs use a configurable local sentence-transformer, while the stable
hashing vectorizer remains available only as a lexical baseline and for tests.
Callers may inject any provider implementing ``embed(texts)``. Clustering is
agglomerative with an unknown number of clusters and stops at a configured
similarity threshold.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .experience_models import ExperienceRecord


class EmbeddingProvider(Protocol):
    """Minimal replaceable embedding interface."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerEmbeddingProvider:
    """Local, version-bound sentence embedding with a content-addressed cache.

    ``sentence-transformers`` is intentionally an optional dependency.  This
    provider never downloads silently when ``local_files_only`` is true and it
    never falls back to lexical hashing.  Formal runs must pin a model revision
    and install/cache that exact model explicitly.
    """

    def __init__(
        self,
        *,
        model_name: str,
        model_revision: str,
        expected_dimensions: int,
        cache_path: str | Path,
        device: str = "cpu",
        batch_size: int = 32,
        local_files_only: bool = True,
        random_seed: int = 42,
    ):
        if not model_name.strip():
            raise ValueError("semantic embedding model_name must be set")
        if not model_revision.strip():
            raise ValueError("semantic embedding model_revision must be pinned")
        if expected_dimensions < 1:
            raise ValueError("expected_dimensions must be positive")
        if batch_size < 1:
            raise ValueError("embedding batch_size must be positive")
        self.model_name = model_name
        self.model_revision = model_revision
        self.expected_dimensions = expected_dimensions
        self.cache_path = Path(cache_path)
        self.device = device
        self.batch_size = batch_size
        self.local_files_only = local_files_only
        self.random_seed = random_seed
        self._model = None
        self._package_version: str | None = None

    @property
    def model_signature(self) -> str:
        payload = (
            f"sentence-transformers|{self.model_name}|{self.model_revision}|"
            f"{self.expected_dimensions}|seed={self.random_seed}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def info(self) -> dict[str, object]:
        return {
            "provider": "sentence_transformer",
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "package_version": self._package_version,
            "dimensions": self.expected_dimensions,
            "device": self.device,
            "batch_size": self.batch_size,
            "normalized": True,
            "cache_path": str(self.cache_path),
            "model_signature": self.model_signature,
            "local_files_only": self.local_files_only,
            "random_seed": self.random_seed,
        }

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            import sentence_transformers
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "semantic embedding requires the optional 'sentence-transformers' package; "
                "install it explicitly before a formal run"
            ) from error
        self._package_version = getattr(sentence_transformers, "__version__", "unknown")
        random.seed(self.random_seed)
        try:
            import numpy as np
            import torch

            np.random.seed(self.random_seed)
            torch.manual_seed(self.random_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(self.random_seed)
                torch.backends.cudnn.deterministic = True
                torch.backends.cudnn.benchmark = False
        except ImportError:
            # sentence-transformers normally provides these dependencies; the
            # model loader below will emit the actionable error if it cannot.
            pass
        try:
            model = SentenceTransformer(
                self.model_name,
                revision=self.model_revision,
                device=self.device,
                local_files_only=self.local_files_only,
            )
        except Exception as error:  # noqa: BLE001
            mode = "local cache" if self.local_files_only else "configured model source"
            raise RuntimeError(
                f"cannot load semantic embedding model {self.model_name}@{self.model_revision} "
                f"from {mode}: {error}"
            ) from error
        dimensions = model.get_sentence_embedding_dimension()
        if dimensions != self.expected_dimensions:
            raise ValueError(
                f"embedding dimension mismatch for {self.model_name}@{self.model_revision}: "
                f"expected {self.expected_dimensions}, got {dimensions}"
            )
        model.eval()
        self._model = model
        return model

    def _connect_cache(self) -> sqlite3.Connection:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.cache_path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_cache (
                cache_key TEXT PRIMARY KEY,
                model_signature TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        return connection

    def _cache_key(self, text: str) -> tuple[str, str]:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cache_key = hashlib.sha256(f"{self.model_signature}|{content_hash}".encode()).hexdigest()
        return cache_key, content_hash

    def _validate_vector(self, vector: Sequence[float]) -> list[float]:
        values = [float(value) for value in vector]
        if len(values) != self.expected_dimensions:
            raise ValueError(
                f"embedding vector dimension mismatch: expected {self.expected_dimensions}, got {len(values)}"
            )
        norm = math.sqrt(sum(value * value for value in values))
        if not math.isfinite(norm) or norm == 0.0:
            raise ValueError("embedding vector has invalid zero/non-finite norm")
        return [value / norm for value in values]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str, str, str]] = []
        with self._connect_cache() as connection:
            for index, raw_text in enumerate(texts):
                text = raw_text or ""
                cache_key, content_hash = self._cache_key(text)
                row = connection.execute(
                    "SELECT dimensions, vector_json FROM embedding_cache "
                    "WHERE cache_key = ? AND model_signature = ?",
                    (cache_key, self.model_signature),
                ).fetchone()
                if row is None:
                    missing.append((index, text, cache_key, content_hash))
                    continue
                dimensions, vector_json = row
                if int(dimensions) != self.expected_dimensions:
                    raise ValueError(
                        f"cached embedding dimension mismatch for key {cache_key}: "
                        f"expected {self.expected_dimensions}, got {dimensions}"
                    )
                results[index] = self._validate_vector(json.loads(vector_json))

            if missing:
                model = self._load_model()
                encoded = model.encode(
                    [item[1] for item in missing],
                    batch_size=self.batch_size,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                if len(encoded) != len(missing):
                    raise ValueError("semantic embedding model returned the wrong batch size")
                now = datetime.now(UTC).isoformat()
                for item, raw_vector in zip(missing, encoded, strict=True):
                    index, _text, cache_key, content_hash = item
                    vector = self._validate_vector(raw_vector.tolist())
                    results[index] = vector
                    connection.execute(
                        "INSERT OR REPLACE INTO embedding_cache "
                        "(cache_key, model_signature, content_sha256, dimensions, vector_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            cache_key,
                            self.model_signature,
                            content_hash,
                            self.expected_dimensions,
                            json.dumps(vector, separators=(",", ":")),
                            now,
                        ),
                    )
                connection.commit()
        if any(vector is None for vector in results):
            raise RuntimeError("embedding cache/model failed to produce every requested vector")
        return [vector for vector in results if vector is not None]


class HashingEmbeddingProvider:
    """Dependency-free local text embedding for reproducible clustering.

    This is deliberately modest rather than pretending to be a neural semantic
    model.  The interface makes it straightforward to inject a stronger local
    or hosted provider without hard-coding credentials or endpoints into the
    clustering algorithm.
    """

    def __init__(self, dimensions: int = 512, seed: int = 42):
        self.dimensions = dimensions
        self.seed = seed

    def info(self) -> dict[str, object]:
        return {
            "provider": "hashing",
            "algorithm": "keyed_blake2b_signed_feature_hashing",
            "dimensions": self.dimensions,
            "seed": self.seed,
            "normalized": True,
            "semantic": False,
        }

    @staticmethod
    def _tokens(text: str) -> list[str]:
        words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", (text or "").lower())
        bigrams = [f"{words[i]}::{words[i + 1]}" for i in range(len(words) - 1)]
        return words + bigrams

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        key = str(self.seed).encode("ascii")
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in self._tokens(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8, key=key).digest()
                bucket = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[bucket] += sign
            norm = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / norm for value in vector] if norm else vector)
        return vectors


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


@dataclass(frozen=True)
class ExperienceCluster:
    cluster_id: str
    experience_ids: list[str]
    centroid: list[float]
    representative_id: str
    representative_content: str
    intra_cluster_similarity: float
    metadata_consistency: float
    metadata_completeness: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ClusteringReport:
    level: str
    input_count: int
    threshold: float
    method: str
    clusters: list[ExperienceCluster]
    metadata_constraint_splits: list[dict] = field(default_factory=list)
    embedding_info: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "input_count": self.input_count,
            "threshold": self.threshold,
            "method": self.method,
            "cluster_count": len(self.clusters),
            "clusters": [cluster.as_dict() for cluster in self.clusters],
            "metadata_constraint_splits": self.metadata_constraint_splits,
            "embedding_info": self.embedding_info,
        }


class ExperienceClusterer:
    """Metadata-constrained, threshold-based agglomerative clusterer."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        *,
        method: str = "agglomerative",
        max_cluster_size: int = 20,
        use_metadata_constraints: bool = True,
        hard_constraint_fields: Sequence[str] = ("task_stage", "failure_mode"),
        soft_constraint_fields: Sequence[str] = (
            "domain",
            "task_family",
            "tool_type",
            "strategy_type",
        ),
        random_seed: int = 42,
    ):
        if method != "agglomerative":
            raise ValueError(f"Unsupported clustering method: {method}")
        if max_cluster_size < 1:
            raise ValueError("max_cluster_size must be positive")
        self.embedding_provider = embedding_provider
        self.method = method
        self.max_cluster_size = max_cluster_size
        self.use_metadata_constraints = use_metadata_constraints
        self.hard_constraint_fields = tuple(hard_constraint_fields)
        self.soft_constraint_fields = tuple(soft_constraint_fields)
        self.random_seed = random_seed

    @staticmethod
    def _known(value: object) -> bool:
        if value is None:
            return False
        raw = getattr(value, "value", value)
        return str(raw).strip().lower() not in {"", "unknown", "null"}

    @staticmethod
    def _metadata_text(value: object) -> str:
        return str(getattr(value, "value", value))

    def _hard_compatible(self, left: ExperienceRecord, right: ExperienceRecord) -> tuple[bool, str | None]:
        if not self.use_metadata_constraints:
            return True, None
        for field_name in self.hard_constraint_fields:
            left_value = getattr(left, field_name, None)
            right_value = getattr(right, field_name, None)
            if self._known(left_value) and self._known(right_value) and left_value != right_value:
                return False, field_name
        return True, None

    def _adjusted_similarity(
        self,
        left: ExperienceRecord,
        right: ExperienceRecord,
        semantic_similarity: float,
    ) -> float:
        if not self.use_metadata_constraints:
            return semantic_similarity
        known_pairs = 0
        matches = 0
        mismatches = 0
        for field_name in self.soft_constraint_fields:
            left_value = getattr(left, field_name, None)
            right_value = getattr(right, field_name, None)
            if not (self._known(left_value) and self._known(right_value)):
                continue
            known_pairs += 1
            if left_value == right_value:
                matches += 1
            else:
                mismatches += 1
        if known_pairs == 0:
            return semantic_similarity
        # Soft metadata may refine a semantic decision but can never override a
        # hard constraint.  A mismatch is intentionally more costly than a
        # match is beneficial, making cross-tool/domain merges conservative.
        return semantic_similarity + 0.02 * (matches / known_pairs) - 0.10 * (mismatches / known_pairs)

    def _metadata_metrics(self, records: Sequence[ExperienceRecord]) -> tuple[float, float]:
        fields = self.hard_constraint_fields + self.soft_constraint_fields
        if not records or not fields:
            return 1.0, 0.0
        consistent: list[float] = []
        known_cells = 0
        total_cells = len(records) * len(fields)
        for field_name in fields:
            values = [getattr(record, field_name, None) for record in records]
            values = [self._metadata_text(value) for value in values if self._known(value)]
            known_cells += len(values)
            if not values:
                continue
            counts = {value: values.count(value) for value in set(values)}
            consistent.append(max(counts.values()) / len(values))
        consistency = sum(consistent) / len(consistent) if consistent else 1.0
        completeness = known_cells / total_cells if total_cells else 0.0
        return consistency, completeness

    @staticmethod
    def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
        if not vectors:
            return []
        centroid = [sum(values) / len(vectors) for values in zip(*vectors, strict=True)]
        norm = math.sqrt(sum(value * value for value in centroid))
        return [value / norm for value in centroid] if norm else centroid

    @staticmethod
    def _pair_key(left: int, right: int) -> tuple[int, int]:
        return (left, right) if left < right else (right, left)

    def _build_cluster(
        self,
        records: Sequence[ExperienceRecord],
        vectors: dict[str, list[float]],
        semantic_pairs: dict[tuple[str, str], float],
        *,
        level: str,
        threshold: float,
    ) -> ExperienceCluster:
        ordered = sorted(records, key=lambda record: record.id)
        ids = [record.id for record in ordered]
        pair_values = [
            semantic_pairs[tuple(sorted((left.id, right.id)))]
            for index, left in enumerate(ordered)
            for right in ordered[index + 1 :]
        ]
        intra_similarity = sum(pair_values) / len(pair_values) if pair_values else 1.0
        centroid = self._mean_vector([vectors[record.id] for record in ordered])
        representative = max(
            ordered,
            key=lambda record: (cosine_similarity(vectors[record.id], centroid), record.id),
        )
        consistency, completeness = self._metadata_metrics(ordered)
        cluster_payload = f"{level}|{threshold:.8f}|{self.random_seed}|" + "|".join(ids)
        cluster_id = "cluster_" + hashlib.sha256(cluster_payload.encode("utf-8")).hexdigest()[:20]
        return ExperienceCluster(
            cluster_id=cluster_id,
            experience_ids=ids,
            centroid=centroid,
            representative_id=representative.id,
            representative_content=representative.content,
            intra_cluster_similarity=intra_similarity,
            metadata_consistency=consistency,
            metadata_completeness=completeness,
        )

    def _prepare(
        self, experiences: Sequence[ExperienceRecord]
    ) -> tuple[
        list[ExperienceRecord],
        dict[str, list[float]],
        dict[tuple[str, str], float],
        list[dict],
    ]:
        records = sorted(experiences, key=lambda record: record.id)
        if len({record.id for record in records}) != len(records):
            raise ValueError("Experience IDs must be unique within a clustering input")
        raw_vectors = self.embedding_provider.embed([record.content for record in records])
        if len(raw_vectors) != len(records):
            raise ValueError("Embedding provider returned a different number of vectors than inputs")
        vectors = {record.id: vector for record, vector in zip(records, raw_vectors, strict=True)}
        semantic_pairs: dict[tuple[str, str], float] = {}
        constraint_splits: list[dict] = []
        for index, left in enumerate(records):
            for right in records[index + 1 :]:
                key = tuple(sorted((left.id, right.id)))
                semantic_pairs[key] = cosine_similarity(vectors[left.id], vectors[right.id])
                compatible, field_name = self._hard_compatible(left, right)
                if not compatible:
                    constraint_splits.append(
                        {
                            "experience_ids": [left.id, right.id],
                            "field": field_name,
                            "values": [
                                getattr(left, field_name or "", None),
                                getattr(right, field_name or "", None),
                            ],
                        }
                    )
        return records, vectors, semantic_pairs, constraint_splits

    def cluster(
        self,
        experiences: Sequence[ExperienceRecord],
        *,
        level: str,
        similarity_threshold: float,
    ) -> ClusteringReport:
        records, vectors, semantic_pairs, constraint_splits = self._prepare(experiences)
        clusters: list[list[ExperienceRecord]] = [[record] for record in records]

        while True:
            best: tuple[float, tuple[str, ...], int, int] | None = None
            for left_index, left_cluster in enumerate(clusters):
                for right_index in range(left_index + 1, len(clusters)):
                    right_cluster = clusters[right_index]
                    if len(left_cluster) + len(right_cluster) > self.max_cluster_size:
                        continue
                    cross_scores: list[float] = []
                    compatible = True
                    for left in left_cluster:
                        for right in right_cluster:
                            hard_ok, _ = self._hard_compatible(left, right)
                            if not hard_ok:
                                compatible = False
                                break
                            semantic = semantic_pairs[tuple(sorted((left.id, right.id)))]
                            cross_scores.append(self._adjusted_similarity(left, right, semantic))
                        if not compatible:
                            break
                    if not compatible or not cross_scores:
                        continue
                    average_score = sum(cross_scores) / len(cross_scores)
                    if average_score < similarity_threshold:
                        continue
                    ids = tuple(sorted(record.id for record in left_cluster + right_cluster))
                    candidate = (average_score, ids, left_index, right_index)
                    if (
                        best is None
                        or candidate[0] > best[0]
                        or (math.isclose(candidate[0], best[0]) and candidate[1] < best[1])
                    ):
                        best = candidate
            if best is None:
                break
            _, _, left_index, right_index = best
            merged = sorted(clusters[left_index] + clusters[right_index], key=lambda record: record.id)
            clusters[left_index] = merged
            del clusters[right_index]

        built = [
            self._build_cluster(
                cluster,
                vectors,
                semantic_pairs,
                level=level,
                threshold=similarity_threshold,
            )
            for cluster in clusters
        ]
        built.sort(key=lambda cluster: cluster.experience_ids)
        return ClusteringReport(
            level=level,
            input_count=len(records),
            threshold=similarity_threshold,
            method=self.method,
            clusters=built,
            metadata_constraint_splits=constraint_splits,
            embedding_info=(
                self.embedding_provider.info() if hasattr(self.embedding_provider, "info") else {}
            ),
        )

    def sequential_groups(
        self,
        experiences: Sequence[ExperienceRecord],
        *,
        level: str,
        group_size: int,
    ) -> ClusteringReport:
        """Compatibility mode: group by creation order, leaving a short tail pending."""

        records = sorted(experiences, key=lambda record: (record.created_at, record.id))
        _, vectors, semantic_pairs, constraint_splits = self._prepare(records)
        groups = [records[index : index + group_size] for index in range(0, len(records), group_size)]
        built = [
            self._build_cluster(
                group,
                vectors,
                semantic_pairs,
                level=level,
                threshold=0.0,
            )
            for group in groups
            if group
        ]
        return ClusteringReport(
            level=level,
            input_count=len(records),
            threshold=0.0,
            method="sequential",
            clusters=built,
            metadata_constraint_splits=constraint_splits,
            embedding_info=(
                self.embedding_provider.info() if hasattr(self.embedding_provider, "info") else {}
            ),
        )


_EXPLICIT_NEGATION = re.compile(r"\b(?:not|never|cannot|can't|must\s+not|should\s+not|do\s+not|don't)\b", re.I)


def detect_strategy_conflicts(
    records: Sequence[ExperienceRecord],
    *,
    lexical_overlap_threshold: float = 0.65,
) -> list[dict[str, object]]:
    """Conservatively flag near-duplicate advice with opposite polarity.

    Sentence embeddings commonly place a sentence and its negation close
    together.  This pre-aggregation guard only fires when the non-negation word
    sets overlap strongly and exactly one side contains explicit negation.
    False positives remain pending, which is safer than committing a conflicted
    upper-level experience.
    """

    conflicts: list[dict[str, object]] = []
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            left_negated = bool(_EXPLICIT_NEGATION.search(left.content))
            right_negated = bool(_EXPLICIT_NEGATION.search(right.content))
            if left_negated == right_negated:
                continue
            left_words = set(re.findall(r"[a-z0-9_]+", _EXPLICIT_NEGATION.sub(" ", left.content.lower())))
            right_words = set(re.findall(r"[a-z0-9_]+", _EXPLICIT_NEGATION.sub(" ", right.content.lower())))
            union = left_words | right_words
            overlap = len(left_words & right_words) / len(union) if union else 0.0
            if overlap >= lexical_overlap_threshold:
                conflicts.append(
                    {
                        "experience_ids": [left.id, right.id],
                        "reason": "explicit_negation_with_high_lexical_overlap",
                        "lexical_overlap": overlap,
                    }
                )
    return conflicts
