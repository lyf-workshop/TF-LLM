"""
LLM-based experience reranker for intelligent experience selection.

This module uses an LLM to evaluate and rank experiences based on their
relevance, generalization capability, and actionability for a given task.
"""

import asyncio
import json
import time
from typing import Any

from openai import AsyncOpenAI

from .experience_filter import ParsedExperience
from ..config import LLMRerankConfig
from ..utils import EnvUtils, get_logger

logger = get_logger(__name__)


class LLMExperienceReranker:
    """Use LLM to intelligently rank and select experiences."""
    
    # Prompt template for experience evaluation
    RERANK_SYSTEM_PROMPT = """You are an AI experience relevance evaluator for a game-playing agent.

Your task is to evaluate how useful each experience is for the agent to solve the current task.

Evaluation Criteria:
1. **Relevance** (0-4): How directly does this experience apply to the current task state?
2. **Generalization** (0-3): Is it broadly applicable vs overly specific to one case?
3. **Actionability** (0-3): Can the agent directly use this guidance in decision-making?

Output Format:
Return a strict JSON array with one entry per experience. Each entry must have:
- "id": the experience ID
- "score": total score (0-10)
- "reason": brief explanation (max 30 words)

Example:
[
  {"id": "L2_0", "score": 9, "reason": "Core meta-strategy directly applicable to constraint satisfaction"},
  {"id": "L1_0", "score": 7, "reason": "Useful pattern for opening moves but somewhat generic"},
  {"id": "L0_5", "score": 4, "reason": "Too specific to particular word lengths"}
]

CRITICAL: Return ONLY the JSON array, no other text."""

    RERANK_USER_PROMPT = """**Current Task Context**:
{task_context}

**Candidate Experiences** ({num_candidates} total):
{experiences_text}

Evaluate each experience and return the JSON array with scores."""
    
    def __init__(self, config: LLMRerankConfig):
        """Initialize LLM reranker.
        
        Args:
            config: LLM reranking configuration
        """
        self.config = config
        self.client = None
        self.cache: dict[str, list[tuple[str, float]]] = {}  # Cache: {cache_key: [(exp_id, score), ...]}
    
    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self.client is None:
            # Use project's unified environment variable naming
            api_key = EnvUtils.get_env("UTU_LLM_API_KEY", None)
            if not api_key:
                # Fallback to standard OPENAI_API_KEY for compatibility
                api_key = EnvUtils.get_env("OPENAI_API_KEY", None)
            
            if not api_key:
                raise ValueError(
                    "API key not found. Please set either UTU_LLM_API_KEY or OPENAI_API_KEY in your .env file"
                )
            
            base_url = EnvUtils.get_env("UTU_LLM_BASE_URL", None)
            if not base_url:
                base_url = EnvUtils.get_env("OPENAI_BASE_URL", None)
            
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            logger.info("Initialized LLM client with %s base URL", "configured" if base_url else "default")
        return self.client
    
    async def rerank(
        self,
        task_context: str,
        experiences: list[ParsedExperience],
        config: LLMRerankConfig | None = None
    ) -> list[ParsedExperience]:
        """Rerank experiences using LLM.
        
        Args:
            task_context: Description of the current task/problem
            experiences: Candidate experiences to evaluate
            config: Optional override config (uses instance config if None)
            
        Returns:
            Reranked experiences (top-k based on LLM scores)
        """
        config = config or self.config
        
        if not experiences:
            logger.warning("No experiences to rerank")
            return []
        
        # Limit candidates to max_candidates
        candidates = experiences[:config.max_candidates] if len(experiences) > config.max_candidates else experiences
        
        logger.info(f"LLM reranking: {len(experiences)} experiences → {len(candidates)} candidates for evaluation")
        
        # Check cache
        cache_key = self._compute_cache_key(task_context, candidates)
        if cache_key in self.cache:
            logger.info("Using cached LLM rerank result")
            return self._apply_cached_rankings(candidates, self.cache[cache_key], config.final_top_k)
        
        # Call LLM for evaluation
        start_time = time.time()
        try:
            rankings = await self._call_llm_reranker(task_context, candidates, config)
            elapsed = time.time() - start_time
            
            logger.info(f"LLM rerank completed in {elapsed:.2f}s")
            
            # Cache result
            self.cache[cache_key] = rankings
            
            # Apply rankings and return top-k
            return self._apply_cached_rankings(candidates, rankings, config.final_top_k)
            
        except Exception as e:
            logger.error(f"LLM reranking failed: {e}", exc_info=True)
            logger.warning("Falling back to original order")
            return candidates[:config.final_top_k]
    
    async def _call_llm_reranker(
        self,
        task_context: str,
        experiences: list[ParsedExperience],
        config: LLMRerankConfig
    ) -> list[tuple[str, float]]:
        """Call LLM to evaluate experiences.
        
        Args:
            task_context: Task description
            experiences: Candidate experiences
            config: Reranking configuration
            
        Returns:
            List of (experience_id, score) tuples
        """
        # Format experiences for prompt
        experiences_text = self._format_experiences_for_prompt(experiences)
        
        # Build messages
        messages = [
            {"role": "system", "content": self.RERANK_SYSTEM_PROMPT},
            {"role": "user", "content": self.RERANK_USER_PROMPT.format(
                task_context=task_context,
                num_candidates=len(experiences),
                experiences_text=experiences_text
            )}
        ]
        
        # Call LLM API
        client = self._get_client()
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=config.model,
                    messages=messages,
                    temperature=config.temperature,
                    max_tokens=2000,
                    response_format={"type": "json_object"} if "gpt" in config.model.lower() else None
                ),
                timeout=config.timeout
            )
            
            # Parse response
            content = response.choices[0].message.content
            logger.debug(f"LLM rerank response: {content}")
            
            # Extract JSON array from response
            rankings = self._parse_llm_response(content, experiences)
            
            # Log score distribution
            scores = [score for _, score in rankings]
            if scores:
                logger.info(f"Score distribution: min={min(scores):.1f}, max={max(scores):.1f}, "
                           f"avg={sum(scores)/len(scores):.1f}")
            
            return rankings
            
        except asyncio.TimeoutError:
            logger.error(f"LLM API call timed out after {config.timeout}s")
            raise
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise
    
    def _format_experiences_for_prompt(self, experiences: list[ParsedExperience]) -> str:
        """Format experiences for LLM prompt.
        
        Args:
            experiences: Experiences to format
            
        Returns:
            Formatted string
        """
        lines = []
        for i, exp in enumerate(experiences, 1):
            lines.append(f"{i}. **[{exp.id}]** ({exp.level})")
            lines.append(f"   {exp.content}")
            lines.append("")
        return "\n".join(lines)
    
    def _parse_llm_response(
        self,
        response: str,
        experiences: list[ParsedExperience]
    ) -> list[tuple[str, float]]:
        """Parse LLM response into rankings.
        
        Args:
            response: LLM response text
            experiences: Original experiences for validation
            
        Returns:
            List of (experience_id, score) tuples sorted by score (descending)
        """
        try:
            # Try to parse as JSON
            if response.strip().startswith('['):
                data = json.loads(response)
            else:
                # Try to extract JSON array from text
                start_idx = response.find('[')
                end_idx = response.rfind(']') + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response[start_idx:end_idx]
                    data = json.loads(json_str)
                else:
                    # Try as JSON object with "rankings" or "scores" key
                    data = json.loads(response)
                    if isinstance(data, dict):
                        data = data.get('rankings') or data.get('scores') or data.get('results') or []
            
            # Validate and extract rankings
            rankings = []
            valid_ids = {exp.id for exp in experiences}
            
            for item in data:
                if not isinstance(item, dict):
                    continue
                    
                exp_id = item.get('id')
                score = item.get('score', 0)
                
                if exp_id in valid_ids:
                    try:
                        score = float(score)
                        rankings.append((exp_id, score))
                        if self.config.include_reasoning and 'reason' in item:
                            logger.debug(f"  [{exp_id}] score={score:.1f}: {item['reason']}")
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid score for {exp_id}: {score}")
            
            # Sort by score (descending)
            rankings.sort(key=lambda x: x[1], reverse=True)
            
            logger.info(f"Parsed {len(rankings)}/{len(experiences)} experience rankings from LLM")
            
            return rankings
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response content: {response}")
            # Fallback: return experiences in original order with default scores
            return [(exp.id, 5.0) for exp in experiences]
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}", exc_info=True)
            return [(exp.id, 5.0) for exp in experiences]
    
    def _apply_cached_rankings(
        self,
        experiences: list[ParsedExperience],
        rankings: list[tuple[str, float]],
        top_k: int
    ) -> list[ParsedExperience]:
        """Apply cached rankings to experiences.
        
        Args:
            experiences: Original experiences
            rankings: List of (exp_id, score) tuples
            top_k: Number of top experiences to return
            
        Returns:
            Reranked experiences (top-k)
        """
        # Create ID to experience mapping
        id_to_exp = {exp.id: exp for exp in experiences}
        
        # Build reranked list
        reranked = []
        for exp_id, score in rankings[:top_k]:
            if exp_id in id_to_exp:
                reranked.append(id_to_exp[exp_id])
        
        logger.info(f"Applied rankings: {len(experiences)} → {len(reranked)} experiences")
        logger.info(f"  Selected levels: L2={sum(1 for e in reranked if e.level=='L2')}, "
                   f"L1={sum(1 for e in reranked if e.level=='L1')}, "
                   f"L0={sum(1 for e in reranked if e.level=='L0')}")
        
        return reranked
    
    def _compute_cache_key(self, task_context: str, experiences: list[ParsedExperience]) -> str:
        """Compute cache key for task context and experiences.
        
        Args:
            task_context: Task description
            experiences: List of experiences
            
        Returns:
            Cache key string
        """
        # Use hash of task context + experience IDs
        exp_ids = ",".join(sorted(exp.id for exp in experiences))
        cache_str = f"{task_context}|{exp_ids}"
        return str(hash(cache_str))
