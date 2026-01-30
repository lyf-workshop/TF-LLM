"""
Experience filter for controlling which experiences are injected into agent instructions.

This module provides utilities to:
1. Parse hierarchical experiences (L0/L1/L2) from agent instructions
2. Load experiences from external JSON files
3. Filter experiences based on configuration (max counts per level)
4. Support static filtering, BM25 retrieval, and LLM-based reranking
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import ExperienceFilterConfig
from ..utils import get_logger

logger = get_logger(__name__)


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
        self.experience_loader = None
        
        # Lazy import to avoid circular dependency
        if config.strategy == "retrieval":
            from ..practice.experience_retriever import ExperienceRetriever
            self.retriever = ExperienceRetriever()
        
        # Initialize LLM reranker if needed
        if config.strategy == "llm_rerank" or config.llm_rerank.enabled:
            from .llm_experience_reranker import LLMExperienceReranker
            self.llm_reranker = LLMExperienceReranker(config.llm_rerank)
        
        # Initialize experience loader if source is specified
        if config.experience_source:
            from .experience_loader import ExperienceLoader
            source_path = Path(config.experience_source)
            if source_path.exists():
                self.experience_loader = ExperienceLoader(source_path)
                logger.info(f"Experience loader initialized with source: {config.experience_source}")
            else:
                logger.warning(f"Experience source not found: {config.experience_source}")
    
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
        # Pattern: "When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:"
        # followed by [G0], [G1], etc. or [L0_X], [L1_X], [L2_X]
        
        pattern = r"When solving problems, you MUST first carefully read and understand the helpful instructions and experiences:\s*(.*?)$"
        match = re.search(pattern, instructions, re.DOTALL | re.IGNORECASE)
        
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
        else:
            logger.warning(f"Unknown strategy '{self.config.strategy}', using all experiences")
            return experiences
    
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
        
        # Apply limits (preserve original order)
        filtered = []
        
        if self.config.max_l2 is not None:
            filtered.extend(l2_exps[:self.config.max_l2])
        else:
            filtered.extend(l2_exps)
        
        if self.config.max_l1 is not None:
            filtered.extend(l1_exps[:self.config.max_l1])
        else:
            filtered.extend(l1_exps)
        
        if self.config.max_l0 is not None:
            filtered.extend(l0_exps[:self.config.max_l0])
        else:
            filtered.extend(l0_exps)
        
        # Sort by original order to maintain coherence
        filtered.sort(key=lambda e: e.order)
        
        logger.info(f"Static filtering: {len(experiences)} → {len(filtered)} experiences "
                   f"(L2={sum(1 for e in filtered if e.level=='L2')}, "
                   f"L1={sum(1 for e in filtered if e.level=='L1')}, "
                   f"L0={sum(1 for e in filtered if e.level=='L0')})")
        
        return filtered
    
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
            logger.warning("No query provided for retrieval, falling back to static filtering")
            return self._filter_static(experiences)
        
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
            logger.warning("LLM reranker not initialized, falling back to static filtering")
            return self._filter_static(experiences)
        
        # Stage 1: Recall candidates
        if self.config.recall.method == "static":
            candidates = self._recall_static(experiences)
        elif self.config.recall.method == "bm25":
            candidates = self._recall_bm25(experiences, task_context)
        else:  # "all"
            candidates = experiences
        
        logger.info(f"Recall stage: {len(experiences)} → {len(candidates)} candidates")
        
        # Stage 2: LLM reranking
        if not task_context:
            logger.warning("No task context provided for LLM reranking, using default context")
            task_context = "Wordle game: Guess the hidden word using feedback constraints."
        
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
        
        candidates = []
        
        if self.config.recall.max_l2 is not None:
            candidates.extend(l2_exps[:self.config.recall.max_l2])
        else:
            candidates.extend(l2_exps)
        
        if self.config.recall.max_l1 is not None:
            candidates.extend(l1_exps[:self.config.recall.max_l1])
        else:
            candidates.extend(l1_exps)
        
        if self.config.recall.max_l0 is not None:
            candidates.extend(l0_exps[:self.config.recall.max_l0])
        else:
            candidates.extend(l0_exps)
        
        # Maintain original order
        candidates.sort(key=lambda e: e.order)
        
        return candidates
    
    def _recall_bm25(self, experiences: list[ParsedExperience], query: str | None) -> list[ParsedExperience]:
        """Recall stage using BM25 retrieval.
        
        Args:
            experiences: All experiences
            query: Query string
            
        Returns:
            Retrieved candidates
        """
        if not query:
            logger.warning("No query for BM25 recall, using static recall")
            return self._recall_static(experiences)
        
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
        if not self.experience_loader:
            raise ValueError("No experience source configured or source file not found")
        
        return self.experience_loader.load()
    
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
        
        for i, exp in enumerate(experiences):
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
        # If experience source is configured, load from external file
        if self.experience_loader:
            logger.info("Loading experiences from external source")
            experiences = self.load_experiences_from_source()
            base_instructions = instructions.strip()
        else:
            # Parse experiences from instructions
            base_instructions, experiences = self.parse_experiences(instructions)
        
        # Filter experiences
        filtered = await self.filter_experiences(experiences, query)
        
        # Render back to instructions
        filtered_text = self.render_experiences(filtered)
        
        return base_instructions + filtered_text
