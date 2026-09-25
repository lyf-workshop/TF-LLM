"""
Experience filter for controlling which experiences are injected into agent instructions.

This module provides utilities to:
1. Parse hierarchical experiences (L0/L1/L2) from agent instructions
2. Load experiences from external JSON files
3. Filter experiences based on configuration (max counts per level)
4. Support static filtering, lexical TF-IDF retrieval, and LLM-based reranking
"""

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import ExperienceFilterConfig, RecallConfig
from ..utils import get_logger

logger = get_logger(__name__)

EXPERIENCE_SECTION_PATTERN = re.compile(
    r"When solving problems, you MUST first carefully read and understand "
    r"the helpful instructions and experiences:\s*(.*?)$",
    re.DOTALL | re.IGNORECASE,
)
RETRIEVED_SECTION_PATTERN = re.compile(
    r"(?:^|\n)Relevant experiences \(retrieved\):",
    re.IGNORECASE,
)
TRAINING_FREE_GRPO_EXPORT_PATTERN = re.compile(
    r"(?:You have developed the following principles through experience "
    r"completing similar tasks\. Apply them proactively:|"
    r"(?:^|\n)Proven patterns from past tasks:|"
    r"(?:^|\n)Specific lessons from recent tasks:)",
    re.IGNORECASE,
)


@dataclass
class ParsedExperience:
    """Parsed experience with metadata."""

    id: str
    """Experience ID (e.g., G0, G1, L0_5, L1_2, L2_0)"""
    level: str
    """Experience level: L0, L1, or L2"""
    content: str
    """Full experience content"""
    order: int
    """Original order in instructions"""


class ExperienceFilter:
    """Filter experiences from agent instructions based on configuration."""

    def __init__(self, config: ExperienceFilterConfig):
        """Initialize experience filter.

        Args:
            config: Experience filter configuration
        """
        self.config = config
        self.retriever = None
        self.llm_reranker = None
        self._source_experiences: tuple[ParsedExperience, ...] | None = None

        # Lazy import to avoid circular dependency
        if config.strategy == "retrieval":
            from ..practice.experience_retriever import ExperienceRetriever
            self.retriever = ExperienceRetriever()

        # ``strategy`` selects the active filtering implementation.  The
        # top-level ``enabled`` flag remains the explicit opt-out switch.
        if config.strategy == "llm_rerank":
            from .llm_experience_reranker import LLMExperienceReranker
            self.llm_reranker = LLMExperienceReranker(config.llm_rerank)

        # Initialize experience loader if source is specified
        if config.experience_source:
            from .experience_loader import ExperienceLoader
            source_path = Path(config.experience_source)
            if not source_path.is_file():
                raise FileNotFoundError(
                    "Configured experience_source does not exist or is not a file: "
                    f"{source_path}. Refusing to evaluate without the declared treatment."
                )
            loaded = ExperienceLoader(source_path).load()
            if not loaded:
                raise ValueError(
                    "Configured experience_source contains no active injectable experiences: "
                    f"{source_path}"
                )
            self._source_experiences = tuple(loaded)
            logger.info(f"Experience loader initialized with source: {config.experience_source}")

    @staticmethod
    def contains_injected_experience_section(instructions: str) -> bool:
        """Recognise prompt sections produced by either supported injector."""

        return bool(
            EXPERIENCE_SECTION_PATTERN.search(instructions)
            or RETRIEVED_SECTION_PATTERN.search(instructions)
            or TRAINING_FREE_GRPO_EXPORT_PATTERN.search(instructions)
        )

    @staticmethod
    def contains_training_free_grpo_export(instructions: str) -> bool:
        """Recognise the three-zone prompt emitted by TrainingFreeGRPO."""

        return bool(TRAINING_FREE_GRPO_EXPORT_PATTERN.search(instructions))

    def validate_base_instructions(self, instructions: str) -> None:
        """Prevent an external snapshot from being appended to baked experiences."""

        if self._source_experiences is not None and self.contains_injected_experience_section(instructions):
            raise ValueError(
                "experience_source cannot be combined with agent instructions that already "
                "contain an injected experience section. Use a clean base agent so the "
                "declared per-query filter is the only experience channel."
            )

    async def cleanup(self) -> None:
        if self.llm_reranker is not None:
            await self.llm_reranker.cleanup()

    def parse_experiences(self, instructions: str) -> tuple[str, list[ParsedExperience]]:
        """Parse experiences from agent instructions.

        Args:
            instructions: Agent instructions text

        Returns:
            Tuple of (base_instructions, experiences_list)
            - base_instructions: Instructions without experiences section
            - experiences_list: List of parsed experiences
        """
        # Find the experiences section
        # Pattern: "When solving problems, you MUST first carefully read and
        # understand the helpful instructions and experiences:"
        # followed by [G0], [G1], etc. or [L0_X], [L1_X], [L2_X]

        match = EXPERIENCE_SECTION_PATTERN.search(instructions)

        if not match:
            logger.warning("No experiences section found in instructions")
            return instructions, []

        base_instructions = instructions[:match.start()].rstrip()
        experiences_text = match.group(1).strip()

        # Parse individual experiences
        # Pattern: [ID]. [Level] **content** or [ID]. **content**
        exp_pattern = r'\[([^\]]+)\]\.\s*(?:\[([^\]]+)\]\s*)?(.+?)(?=\n\[|$)'
        experiences = []

        for i, match in enumerate(re.finditer(exp_pattern, experiences_text, re.DOTALL)):
            exp_id = match.group(1).strip()
            level_tag = match.group(2).strip() if match.group(2) else None
            content = match.group(3).strip()

            # Determine level from tag or ID
            if level_tag:
                if "L2" in level_tag or "Meta" in level_tag:
                    level = "L2"
                elif "L1" in level_tag or "Pattern" in level_tag:
                    level = "L1"
                elif "L0" in level_tag or "Case" in level_tag:
                    level = "L0"
                else:
                    level = "L1"  # Default to L1 for backward compatibility
            elif exp_id.startswith("L2"):
                level = "L2"
            elif exp_id.startswith("L1"):
                level = "L1"
            elif exp_id.startswith("L0"):
                level = "L0"
            else:
                # Legacy format: G0, G1, etc. - assume L1
                level = "L1"

            experiences.append(ParsedExperience(
                id=exp_id,
                level=level,
                content=f"[{level_tag}] {content}" if level_tag else content,
                order=i
            ))

        logger.info(f"Parsed {len(experiences)} experiences: "
                   f"L2={sum(1 for e in experiences if e.level=='L2')}, "
                   f"L1={sum(1 for e in experiences if e.level=='L1')}, "
                   f"L0={sum(1 for e in experiences if e.level=='L0')}")

        return base_instructions, experiences

    async def filter_experiences(
        self,
        experiences: list[ParsedExperience],
        query: str | None = None
    ) -> list[ParsedExperience]:
        """Filter experiences based on configuration.

        Args:
            experiences: List of parsed experiences
            query: Optional query for retrieval-based filtering or task context for LLM reranking

        Returns:
            Filtered list of experiences
        """
        if not self.config.enabled:
            logger.info("Experience filtering disabled, using all experiences")
            return experiences

        if self.config.strategy == "static":
            return self._filter_static(experiences)
        elif self.config.strategy == "retrieval":
            return self._filter_retrieval(experiences, query)
        elif self.config.strategy == "llm_rerank":
            return await self._filter_llm_rerank(experiences, query)
        else:  # pragma: no cover - rejected by ExperienceFilterConfig
            raise ValueError(f"Unsupported experience filtering strategy: {self.config.strategy!r}")

    def _filter_static(self, experiences: list[ParsedExperience]) -> list[ParsedExperience]:
        """Apply static filtering based on max counts per level.

        Args:
            experiences: List of parsed experiences

        Returns:
            Filtered experiences
        """
        # Separate by level
        l2_exps = [e for e in experiences if e.level == "L2"]
        l1_exps = [e for e in experiences if e.level == "L1"]
        l0_exps = [e for e in experiences if e.level == "L0"]

        filtered = self._apply_level_limits(
            l2_exps,
            l1_exps,
            l0_exps,
            self.config.recall,
        )

        logger.info(f"Static filtering: {len(experiences)} → {len(filtered)} experiences "
                   f"(L2={sum(1 for e in filtered if e.level=='L2')}, "
                   f"L1={sum(1 for e in filtered if e.level=='L1')}, "
                   f"L0={sum(1 for e in filtered if e.level=='L0')})")

        return filtered

    @staticmethod
    def _apply_level_limits(
        l2_experiences: list[ParsedExperience],
        l1_experiences: list[ParsedExperience],
        l0_experiences: list[ParsedExperience],
        limits: RecallConfig,
    ) -> list[ParsedExperience]:
        """Apply one canonical set of per-level limits and preserve order."""

        selected: list[ParsedExperience] = []
        for experiences, limit in (
            (l2_experiences, limits.max_l2),
            (l1_experiences, limits.max_l1),
            (l0_experiences, limits.max_l0),
        ):
            selected.extend(experiences if limit is None else experiences[:limit])
        selected.sort(key=lambda experience: experience.order)
        return selected

    def _filter_retrieval(
        self,
        experiences: list[ParsedExperience],
        query: str | None
    ) -> list[ParsedExperience]:
        """Apply retrieval-based filtering.

        Args:
            experiences: List of parsed experiences
            query: Query string for retrieval

        Returns:
            Retrieved experiences
        """
        if not query:
            raise ValueError(
                "Retrieval-based experience filtering requires a non-empty per-sample query"
            )

        # Lazy import if not already initialized
        if self.retriever is None:
            from ..practice.experience_retriever import ExperienceRetriever
            self.retriever = ExperienceRetriever()

        # Index all experiences
        docs = [{"id": e.id, "content": e.content, "meta": {"level": e.level, "order": e.order}}
                for e in experiences]
        self.retriever.index(docs)

        # Retrieve top-k
        retrieved = self.retriever.retrieve(
            query=query,
            top_k=self.config.retrieval_top_k,
            min_score=self.config.retrieval_min_score
        )

        # Convert back to ParsedExperience
        id_to_exp = {e.id: e for e in experiences}
        filtered = [id_to_exp[r.exp_id] for r in retrieved if r.exp_id in id_to_exp]

        logger.info(f"Retrieval filtering: {len(experiences)} → {len(filtered)} experiences")

        return filtered

    async def _filter_llm_rerank(
        self,
        experiences: list[ParsedExperience],
        task_context: str | None
    ) -> list[ParsedExperience]:
        """Apply LLM-based reranking.

        This implements a two-stage approach:
        1. Recall stage: Use configured recall method to get candidates
        2. Rerank stage: Use LLM to intelligently rank candidates

        Args:
            experiences: List of parsed experiences
            task_context: Task description for LLM evaluation

        Returns:
            Reranked experiences
        """
        if not self.llm_reranker:
            raise RuntimeError("LLM reranking was selected but the reranker is not initialized")
        if not task_context:
            raise ValueError(
                "LLM experience reranking requires non-empty per-sample task context"
            )

        # Stage 1: Recall candidates
        if self.config.recall.method == "static":
            candidates = self._recall_static(experiences)
        elif self.config.recall.method == "tfidf":
            candidates = self._recall_tfidf(experiences, task_context)
        else:  # "all"
            candidates = experiences

        logger.info(f"Recall stage: {len(experiences)} → {len(candidates)} candidates")

        # Stage 2: LLM reranking
        reranked = await self.llm_reranker.rerank(task_context, candidates)

        logger.info(f"LLM rerank complete: {len(candidates)} → {len(reranked)} experiences")

        return reranked

    def _recall_static(self, experiences: list[ParsedExperience]) -> list[ParsedExperience]:
        """Recall stage using static limits.

        Args:
            experiences: All experiences

        Returns:
            Recalled candidates
        """
        l2_exps = [e for e in experiences if e.level == "L2"]
        l1_exps = [e for e in experiences if e.level == "L1"]
        l0_exps = [e for e in experiences if e.level == "L0"]

        return self._apply_level_limits(
            l2_exps,
            l1_exps,
            l0_exps,
            self.config.recall,
        )

    def _recall_tfidf(self, experiences: list[ParsedExperience], query: str | None) -> list[ParsedExperience]:
        """Recall stage using the project's lexical TF-IDF retriever.

        Args:
            experiences: All experiences
            query: Query string

        Returns:
            Retrieved candidates
        """
        if not query:
            raise ValueError("TF-IDF recall requires a non-empty per-sample query")

        # Lazy import
        if self.retriever is None:
            from ..practice.experience_retriever import ExperienceRetriever
            self.retriever = ExperienceRetriever()

        # Index and retrieve
        docs = [{"id": e.id, "content": e.content, "meta": {"level": e.level, "order": e.order}}
                for e in experiences]
        self.retriever.index(docs)

        retrieved = self.retriever.retrieve(
            query=query,
            top_k=self.config.llm_rerank.max_candidates,
            min_score=0.0
        )

        id_to_exp = {e.id: e for e in experiences}
        return [id_to_exp[r.exp_id] for r in retrieved if r.exp_id in id_to_exp]

    def load_experiences_from_source(self) -> list[ParsedExperience]:
        """Load experiences from configured source file.

        Returns:
            List of loaded experiences

        Raises:
            ValueError: If no experience source is configured
        """
        if self._source_experiences is None:
            raise ValueError("No experience source configured or source file not found")

        return list(self._source_experiences)

    def render_experiences(self, experiences: list[ParsedExperience]) -> str:
        """Render filtered experiences back into instruction format.

        Args:
            experiences: List of filtered experiences

        Returns:
            Formatted experiences text
        """
        if not experiences:
            return ""

        lines = [
            "\n\nWhen solving problems, you MUST first carefully read and understand "
            "the helpful instructions and experiences:\n"
        ]

        for exp in experiences:
            # Use original ID or generate new sequential ID
            lines.append(f"[{exp.id}]. {exp.content}\n")

        return "".join(lines)

    async def apply(self, instructions: str, query: str | None = None) -> str:
        """Apply experience filtering to agent instructions.

        This is the main entry point that combines parsing, filtering, and rendering.

        Args:
            instructions: Original agent instructions (with or without experiences)
            query: Optional query for retrieval-based filtering or task context for LLM reranking

        Returns:
            Updated instructions with filtered experiences
        """
        rendered, _ = await self.apply_with_metadata(instructions, query=query)
        return rendered

    async def apply_with_metadata(
        self,
        instructions: str,
        query: str | None = None,
    ) -> tuple[str, list[ParsedExperience]]:
        """Filter one task and return both its prompt and selected records."""

        # External snapshots are immutable for one benchmark run. Loading once
        # also guarantees every concurrent sample sees the same source pool.
        if self._source_experiences is not None:
            self.validate_base_instructions(instructions)
            experiences = list(self._source_experiences)
            base_instructions = instructions.strip()
        else:
            if self.contains_training_free_grpo_export(instructions):
                raise ValueError(
                    "TrainingFreeGRPO's exported three-zone agent prompt cannot be parsed "
                    "into individually retrievable records. Per-query filtering requires "
                    "a clean base agent plus experience_source pointing at the hierarchy "
                    "snapshot."
                )
            base_instructions, experiences = self.parse_experiences(instructions)

        if not experiences:
            source = self.config.experience_source or "agent instructions"
            raise ValueError(
                f"Experience filtering is enabled but no injectable experiences were loaded from {source}"
            )

        # Filter experiences
        filtered = await self.filter_experiences(experiences, query)

        # Render back to instructions
        filtered_text = self.render_experiences(filtered)

        return base_instructions + filtered_text, filtered
