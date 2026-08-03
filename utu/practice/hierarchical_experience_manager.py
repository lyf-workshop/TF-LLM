"""
Hierarchical Experience Manager for L0/L1/L2 experience learning.

Design (Path Z):
    * L0 (case-level)   : raw, pre-merge per-problem insights from the
                          group-advantage step.  The most concrete layer.
    * L1 (pattern-level): general strategies aggregated *from L0* by an LLM.
    * L2 (meta-level)   : cross-task principles aggregated *from L1* by an LLM.

All three layers are stored as ``{id: content}`` pools and share ONE
deduplication / consolidation mechanism — the LLM ``ADD/UPDATE/DELETE/NONE``
merge in :mod:`utu.practice.experience_pool`.  There is no token-similarity
dedup any more.

Timing:
    * Every step  : new L0 candidates are merged into the L0 pool.
    * Every epoch : L1 is (re)aggregated from the L0 added during the epoch and
                    merged into the L1 pool; L2 is aggregated from the current
                    L1 pool and merged into the L2 pool.  Cross-epoch refinement
                    (UPDATE / DELETE of stale entries) is handled entirely by the
                    LLM merge.
"""

import json
import os
from typing import Any, Dict, List

from jinja2 import Template

from ..config import AgentConfig
from ..utils import DIR_ROOT, FileUtils, SimplifiedAsyncOpenAI, get_logger
from .experience_pool import pool_merge

logger = get_logger(__name__)


class HierarchicalExperienceManager:
    """Manages hierarchical experiences (L0, L1, L2) for agent learning."""

    def __init__(
        self,
        config: AgentConfig,
        hierarchical_config: Any,
        agent_objective: str,
        learning_objective: str,
    ):
        """Initialize hierarchical experience manager.

        Args:
            config: Agent configuration
            hierarchical_config: Hierarchical learning configuration
            agent_objective: Objective of the working agent
            learning_objective: Learning objective for experience generation
        """
        self.config = config
        self.h_config = hierarchical_config
        self.agent_objective = agent_objective
        self.learning_objective = learning_objective

        # Initialize LLM for experience generation
        self.llm = SimplifiedAsyncOpenAI(**config.model.model_provider.model_dump())
        self.model_params = config.model.model_params.model_dump()

        # Aggregation prompts (L1/L2) and the shared merge prompts.
        prompt_path = DIR_ROOT / "configs" / "prompts" / "hierarchical_critique.yaml"
        self.prompts = FileUtils.load_prompts(str(prompt_path))
        self.merge_prompts = FileUtils.load_prompts("practice/experience.yaml")

        # Experience pools: id -> content
        self.l0: Dict[str, str] = {}
        self.l1: Dict[str, str] = {}
        self.l2: Dict[str, str] = {}
        # L0 ids that have already been folded into L1 (so each epoch only
        # aggregates the freshly-added L0).
        self._l0_aggregated: set[str] = set()

        self._load_experiences()

    # ------------------------------------------------------------------
    #  Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _as_pool(raw: Any, prefix: str) -> Dict[str, str]:
        """Coerce loaded data into an ``{id: content}`` dict.

        Supports both the new dict format and the legacy list-of-dicts format.
        """
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        pool: Dict[str, str] = {}
        if isinstance(raw, list):
            for i, item in enumerate(raw):
                if isinstance(item, dict):
                    key = str(item.get("id") or f"{prefix}{i}")
                    pool[key] = str(item.get("content", ""))
                else:
                    pool[f"{prefix}{i}"] = str(item)
        return pool

    def _load_experiences(self):
        """Load existing experiences from JSON file."""
        save_path = self.h_config.experience_save_path
        if not os.path.exists(save_path):
            return
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.l0 = self._as_pool(data.get("l0_experiences", {}), "L0_")
            self.l1 = self._as_pool(data.get("l1_experiences", {}), "L1_")
            self.l2 = self._as_pool(data.get("l2_experiences", {}), "L2_")
            self._l0_aggregated = set(data.get("l0_aggregated_ids", []))
            logger.info(
                f"Loaded {len(self.l0)} L0, {len(self.l1)} L1, {len(self.l2)} L2 experiences"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to load experiences from {save_path}: {e}")

    def save_experiences(self):
        """Save all experiences to JSON file."""
        save_path = self.h_config.experience_save_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        data = {
            "l0_experiences": self.l0,
            "l1_experiences": self.l1,
            "l2_experiences": self.l2,
            "l0_aggregated_ids": sorted(self._l0_aggregated),
            "stats": {
                "total_l0": len(self.l0),
                "total_l1": len(self.l1),
                "total_l2": len(self.l2),
            },
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved experiences to {save_path}")

    # ------------------------------------------------------------------
    #  L0: per-step accumulation (LLM merge)
    # ------------------------------------------------------------------

    async def process_step_experiences(self, l0_candidates: List[str], step: int):
        """Merge raw L0 candidates from a step into the L0 pool.

        Args:
            l0_candidates: Raw, pre-merge per-problem insights (the most concrete
                lessons) produced by the group-advantage step.
            step: Current step number (for logging only).
        """
        candidates = [c for c in (l0_candidates or []) if c and c.strip()]
        if not candidates:
            logger.info(f"L0 (step {step}): no candidates to merge")
            return

        before = len(self.l0)
        self.l0 = await pool_merge(
            self.llm,
            self.merge_prompts,
            self.agent_objective,
            self.learning_objective,
            existing=self.l0,
            candidates=candidates,
            model_params=self.model_params,
            id_prefix="L0_",
        )
        logger.info(
            f"L0 (step {step}): merged {len(candidates)} candidates, "
            f"pool {before} -> {len(self.l0)}"
        )
        self.save_experiences()

    # ------------------------------------------------------------------
    #  Epoch-end aggregation: L0 -> L1 -> L2 (LLM merge)
    # ------------------------------------------------------------------

    async def aggregate_epoch(self, epoch: int):
        """Aggregate L1 from new L0 and L2 from the L1 pool, at the end of an epoch.

        Cross-epoch refinement (updating/deleting stale L1/L2) is delegated to the
        LLM merge — new candidates are reconciled against the existing pools.
        """
        await self._aggregate_l1(epoch)
        await self._aggregate_l2(epoch)
        self.save_experiences()
        logger.info(
            f"Epoch {epoch} hierarchy: L0={len(self.l0)}, L1={len(self.l1)}, L2={len(self.l2)}"
        )

    async def _aggregate_l1(self, epoch: int):
        """Generate L1 candidates from the L0 added during this epoch, then merge."""
        new_l0_ids = [eid for eid in self.l0 if eid not in self._l0_aggregated]
        threshold = self.h_config.l1_aggregation_threshold
        if len(new_l0_ids) < threshold:
            logger.info(
                f"L1 (epoch {epoch}): only {len(new_l0_ids)} new L0 (< {threshold}); skip"
            )
            return

        # Chunk new L0 and generate one L1 candidate per chunk.
        l1_candidates: List[str] = []
        for i in range(0, len(new_l0_ids), threshold):
            chunk_ids = new_l0_ids[i:i + threshold]
            chunk = [{"id": cid, "content": self.l0[cid]} for cid in chunk_ids]
            content = await self._generate_l1_from_l0(chunk)
            if content:
                l1_candidates.append(content)

        if not l1_candidates:
            return

        before = len(self.l1)
        self.l1 = await pool_merge(
            self.llm,
            self.merge_prompts,
            self.agent_objective,
            self.learning_objective,
            existing=self.l1,
            candidates=l1_candidates,
            model_params=self.model_params,
            id_prefix="L1_",
        )
        self._l0_aggregated.update(new_l0_ids)
        logger.info(
            f"L1 (epoch {epoch}): {len(l1_candidates)} candidates, pool {before} -> {len(self.l1)}"
        )

    async def _aggregate_l2(self, epoch: int):
        """Generate L2 candidates from the current L1 pool, then merge."""
        l1_items = [{"id": k, "content": v} for k, v in self.l1.items()]
        threshold = self.h_config.l2_aggregation_threshold
        if len(l1_items) < threshold:
            logger.info(
                f"L2 (epoch {epoch}): only {len(l1_items)} L1 (< {threshold}); skip"
            )
            return

        l2_candidates: List[str] = []
        for i in range(0, len(l1_items), threshold):
            chunk = l1_items[i:i + threshold]
            content = await self._generate_l2_from_l1(chunk)
            if content:
                l2_candidates.append(content)

        if not l2_candidates:
            return

        before = len(self.l2)
        self.l2 = await pool_merge(
            self.llm,
            self.merge_prompts,
            self.agent_objective,
            self.learning_objective,
            existing=self.l2,
            candidates=l2_candidates,
            model_params=self.model_params,
            id_prefix="L2_",
        )
        logger.info(
            f"L2 (epoch {epoch}): {len(l2_candidates)} candidates, pool {before} -> {len(self.l2)}"
        )

    async def _generate_l1_from_l0(self, l0_batch: List[Dict[str, Any]]) -> str | None:
        """Generate one L1 pattern from a batch of L0 cases using the LLM."""
        l1_prompt = self.prompts["L1_AGGREGATION_PROMPT"]
        system_prompt = Template(l1_prompt["system"]).render(
            agent_objective=self.agent_objective,
            learning_objective=self.learning_objective,
        )
        user_prompt = Template(l1_prompt["user"]).render(l0_experiences=l0_batch)
        try:
            response = await self.llm.query_one(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            return response.strip()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to generate L1: {e}")
            return None

    async def _generate_l2_from_l1(self, l1_batch: List[Dict[str, Any]]) -> str | None:
        """Generate one L2 meta-strategy from a batch of L1 patterns using the LLM.

        We also pass a sample of the L0 pool as supporting context so the model
        can ground the abstraction in concrete cases (the "why" behind the "how").
        """
        l2_prompt = self.prompts["L2_AGGREGATION_PROMPT"]
        system_prompt = Template(l2_prompt["system"]).render(
            agent_objective=self.agent_objective,
            learning_objective=self.learning_objective,
        )
        # The L2 template renders ``exp.source_l0_ids``; provide an empty list
        # since L1 is now merged across epochs and no longer tracks exact sources.
        l1_render = [{**item, "source_l0_ids": []} for item in l1_batch]
        l0_sample = [{"id": k, "content": v} for k, v in list(self.l0.items())[:30]]
        user_prompt = Template(l2_prompt["user"]).render(
            l1_experiences=l1_render,
            l0_experiences=l0_sample,
        )
        try:
            response = await self.llm.query_one(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            return response.strip()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to generate L2: {e}")
            return None

    # ------------------------------------------------------------------
    #  Accessors (return list-of-dicts for prompt injection compatibility)
    # ------------------------------------------------------------------

    def get_all_l0_experiences(self) -> List[Dict[str, Any]]:
        return [{"id": k, "content": v} for k, v in self.l0.items()]

    def get_all_l1_experiences(self) -> List[Dict[str, Any]]:
        return [{"id": k, "content": v} for k, v in self.l1.items()]

    def get_all_l2_experiences(self) -> List[Dict[str, Any]]:
        return [{"id": k, "content": v} for k, v in self.l2.items()]

    def get_recent_l0_experiences(self, limit: int) -> List[Dict[str, Any]]:
        """Get the most recently added L0 experiences."""
        items = [{"id": k, "content": v} for k, v in self.l0.items()]
        return items[-limit:] if items else []

    # Backwards-compatible attribute access for callers that read
    # ``manager.l0_experiences`` etc. for length logging.
    @property
    def l0_experiences(self) -> List[Dict[str, Any]]:
        return self.get_all_l0_experiences()

    @property
    def l1_experiences(self) -> List[Dict[str, Any]]:
        return self.get_all_l1_experiences()

    @property
    def l2_experiences(self) -> List[Dict[str, Any]]:
        return self.get_all_l2_experiences()
