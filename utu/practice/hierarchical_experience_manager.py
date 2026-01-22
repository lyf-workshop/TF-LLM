"""
Hierarchical Experience Manager for L0/L1/L2 experience learning.
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Template

from ..config import AgentConfig
from ..utils import DIR_ROOT, FileUtils, SimplifiedAsyncOpenAI, get_logger

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
        
        # Load prompt templates
        prompt_path = DIR_ROOT / "configs" / "prompts" / "hierarchical_critique.yaml"
        self.prompts = FileUtils.load_prompts(str(prompt_path))
        
        # Experience storage
        self.l0_experiences: List[Dict[str, Any]] = []
        self.l1_experiences: List[Dict[str, Any]] = []
        self.l2_experiences: List[Dict[str, Any]] = []
        
        # Load existing experiences if available
        self._load_experiences()
    
    def _load_experiences(self):
        """Load existing experiences from JSON file."""
        save_path = self.h_config.experience_save_path
        if os.path.exists(save_path):
            try:
                with open(save_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.l0_experiences = data.get('l0_experiences', [])
                self.l1_experiences = data.get('l1_experiences', [])
                self.l2_experiences = data.get('l2_experiences', [])
                logger.info(f"Loaded {len(self.l0_experiences)} L0, {len(self.l1_experiences)} L1, {len(self.l2_experiences)} L2 experiences")
            except Exception as e:
                logger.warning(f"Failed to load experiences from {save_path}: {e}")
    
    def save_experiences(self):
        """Save all experiences to JSON file."""
        save_path = self.h_config.experience_save_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        data = {
            'l0_experiences': self.l0_experiences,
            'l1_experiences': self.l1_experiences,
            'l2_experiences': self.l2_experiences,
            'stats': {
                'total_l0': len(self.l0_experiences),
                'total_l1': len(self.l1_experiences),
                'total_l2': len(self.l2_experiences),
            }
        }
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved experiences to {save_path}")
    
    async def process_step_experiences(
        self, 
        step_experiences: Dict[str, str],
        step: int,
        problem_count: int
    ):
        """Process experiences from a step and convert to L0.
        
        Args:
            step_experiences: Dict of experiences {id: content}
            step: Current step number
            problem_count: Number of problems in this step
        """
        # Convert traditional experiences to L0
        for exp_id, content in step_experiences.items():
            scope_key = self._extract_scope_key(content)
            # Cautious dedup: only skip if it's extremely similar within the same scope.
            if self._is_too_similar_to_recent_l0(content, scope_key=scope_key, threshold=0.95, window=50):
                continue
            l0_exp = {
                'id': f"L0_{len(self.l0_experiences)}",
                'content': content,
                'original_id': exp_id,
                'scope_key': scope_key,
                'step': step,
                'problem_count': problem_count
            }
            self.l0_experiences.append(l0_exp)
        
        logger.info(f"Added {len(step_experiences)} L0 experiences from step {step}")
        
        # Check if we should generate L1
        await self._try_generate_l1(step)
        
        # Check if we should generate L2
        await self._try_generate_l2(step)
        
        # Save after processing
        self.save_experiences()

    def _extract_scope_key(self, content: str) -> str | None:
        if not content:
            return None
        patterns = [
            r"game_name\s*[:=]\s*([A-Za-z0-9_\- ]+)",
            r"Game Name\s*:\s*([A-Za-z0-9_\- ]+)",
            r"context=([A-Za-z0-9_\- ]+)",
            r"problem\s*[:=]\s*([A-Za-z0-9_\- ]+)",
            r"question\s*[:=]\s*([A-Za-z0-9_\- ]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip().lower()
        return None

    def _is_too_similar_to_recent_l0(
        self,
        content: str,
        scope_key: str | None,
        threshold: float = 0.95,
        window: int = 50,
    ) -> bool:
        if not content or not self.l0_experiences or not scope_key:
            return False
        recent = self.l0_experiences[-window:] if window > 0 else self.l0_experiences
        content_tokens = self._tokenize(content)
        for exp in recent:
            if exp.get("scope_key") != scope_key:
                continue
            existing = exp.get("content", "")
            if not existing:
                continue
            if self._jaccard(content_tokens, self._tokenize(existing)) >= threshold:
                return True
        return False

    def _tokenize(self, text: str) -> set[str]:
        cleaned = []
        for ch in (text or "").lower():
            cleaned.append(ch if ch.isalnum() else " ")
        return {w for w in "".join(cleaned).split() if w}

    def _jaccard(self, a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)
    
    async def _try_generate_l1(self, step: int):
        """Try to generate L1 from accumulated L0 experiences."""
        # Get recent L0 experiences not yet aggregated into L1
        recent_l0 = self._get_unaggregated_l0()
        
        if len(recent_l0) >= self.h_config.l1_aggregation_threshold:
            logger.info(f"Generating L1 from {len(recent_l0)} L0 experiences...")
            
            # Take the threshold number of L0 experiences
            l0_batch = recent_l0[:self.h_config.l1_aggregation_threshold]
            
            # Generate L1
            l1_content = await self._generate_l1_from_l0(l0_batch)
            
            if l1_content:
                l1_exp = {
                    'id': f"L1_{len(self.l1_experiences)}",
                    'content': l1_content,
                    'source_l0_ids': [exp['id'] for exp in l0_batch],
                    'step': step
                }
                self.l1_experiences.append(l1_exp)
                logger.info(f"Generated L1_{len(self.l1_experiences)-1}")
    
    async def _try_generate_l2(self, step: int):
        """Try to generate L2 from accumulated L1 experiences and their source L0."""
        # Get recent L1 experiences not yet aggregated into L2
        recent_l1 = self._get_unaggregated_l1()
        
        if len(recent_l1) >= self.h_config.l2_aggregation_threshold:
            logger.info(f"Generating L2 from {len(recent_l1)} L1 experiences and their source L0...")
            
            # Take the threshold number of L1 experiences
            l1_batch = recent_l1[:self.h_config.l2_aggregation_threshold]
            
            # Get all source L0 experiences
            source_l0_ids = set()
            for l1 in l1_batch:
                source_l0_ids.update(l1['source_l0_ids'])
            
            source_l0 = [exp for exp in self.l0_experiences if exp['id'] in source_l0_ids]
            
            # Generate L2 from L1 + L0
            l2_content = await self._generate_l2_from_l1_and_l0(l1_batch, source_l0)
            
            if l2_content:
                l2_exp = {
                    'id': f"L2_{len(self.l2_experiences)}",
                    'content': l2_content,
                    'source_l1_ids': [exp['id'] for exp in l1_batch],
                    'step': step
                }
                self.l2_experiences.append(l2_exp)
                logger.info(f"Generated L2_{len(self.l2_experiences)-1}")
    
    def _get_unaggregated_l0(self) -> List[Dict[str, Any]]:
        """Get L0 experiences that haven't been aggregated into L1 yet."""
        aggregated_ids = set()
        for l1 in self.l1_experiences:
            aggregated_ids.update(l1['source_l0_ids'])
        
        return [exp for exp in self.l0_experiences if exp['id'] not in aggregated_ids]
    
    def _get_unaggregated_l1(self) -> List[Dict[str, Any]]:
        """Get L1 experiences that haven't been aggregated into L2 yet."""
        aggregated_ids = set()
        for l2 in self.l2_experiences:
            aggregated_ids.update(l2['source_l1_ids'])
        
        return [exp for exp in self.l1_experiences if exp['id'] not in aggregated_ids]
    
    async def _generate_l1_from_l0(self, l0_batch: List[Dict[str, Any]]) -> str:
        """Generate L1 pattern from L0 cases using LLM.
        
        Args:
            l0_batch: List of L0 experiences
            
        Returns:
            L1 pattern content
        """
        # Load prompt templates
        l1_prompt = self.prompts["L1_AGGREGATION_PROMPT"]
        
        # Render system prompt
        system_template = Template(l1_prompt["system"])
        system_prompt = system_template.render(
            agent_objective=self.agent_objective,
            learning_objective=self.learning_objective,
        )
        
        # Render user prompt
        user_template = Template(l1_prompt["user"])
        user_prompt = user_template.render(l0_experiences=l0_batch)

        try:
            response = await self.llm.query_one(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate L1: {e}")
            return None
    
    async def _generate_l2_from_l1_and_l0(
        self, 
        l1_batch: List[Dict[str, Any]],
        source_l0: List[Dict[str, Any]]
    ) -> str:
        """Generate L2 meta-strategy from L1 patterns and their source L0 using LLM.
        
        Args:
            l1_batch: List of L1 experiences
            source_l0: List of all L0 experiences that led to these L1
            
        Returns:
            L2 meta-strategy content
        """
        # Load prompt templates
        l2_prompt = self.prompts["L2_AGGREGATION_PROMPT"]
        
        # Render system prompt
        system_template = Template(l2_prompt["system"])
        system_prompt = system_template.render(
            agent_objective=self.agent_objective,
            learning_objective=self.learning_objective,
        )
        
        # Render user prompt with L1 and L0 experiences
        user_template = Template(l2_prompt["user"])
        user_prompt = user_template.render(
            l1_experiences=l1_batch,
            l0_experiences=source_l0,
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
        except Exception as e:
            logger.error(f"Failed to generate L2: {e}")
            return None
    
    def get_all_l0_experiences(self) -> List[Dict[str, Any]]:
        """Get all L0 experiences."""
        return self.l0_experiences
    
    def get_all_l1_experiences(self) -> List[Dict[str, Any]]:
        """Get all L1 experiences."""
        return self.l1_experiences
    
    def get_all_l2_experiences(self) -> List[Dict[str, Any]]:
        """Get all L2 experiences."""
        return self.l2_experiences
    
    def get_recent_l0_experiences(self, limit: int) -> List[Dict[str, Any]]:
        """Get recent L0 experiences.
        
        Args:
            limit: Maximum number of recent L0 to return
            
        Returns:
            List of recent L0 experiences
        """
        return self.l0_experiences[-limit:] if self.l0_experiences else []
