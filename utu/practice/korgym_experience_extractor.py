"""
KORGym Experience Extractor for Hierarchical Learning.

Extracts L0 experiences from KORGym game trajectories.
"""

import json
from typing import Any, Dict, List

from jinja2 import Template

from ..utils import SimplifiedAsyncOpenAI, get_logger

logger = get_logger(__name__)


# Prompt template for L0 experience extraction from game rounds
L0_EXTRACTION_PROMPT = """
You are an expert at analyzing game-playing strategies and extracting learning experiences.

Analyze the following game round and extract a concrete, actionable experience that can help improve future performance.

Game Information:
- Game Name: {{ game_name }}
- Game Category: {{ game_category }}
- Success: {{ success }}
- Final Score: {{ final_score }}
- Number of Rounds: {{ rounds }}

{% if game_type == 'single' %}
Game Prompt:
{{ prompt }}

Agent's Action:
{{ action }}

Agent's Response:
{{ response }}
{% else %}
Multi-Round Game Trajectory:
{% for i, step in enumerate(trajectory) %}
Round {{ i + 1 }}:
  Action: {{ step.get('action', 'N/A') }}
  Score: {{ step.get('score', 0) }}
  State: {{ step.get('board', 'N/A') if step.get('board') else 'N/A' }}
{% endfor %}

Final Outcome:
- Total Rounds: {{ rounds }}
- Final Score: {{ final_score }}
- Success: {{ success }}
{% endif %}

Please extract ONE specific experience from this game round. The experience should:
1. Identify a key mistake OR successful strategy
2. Provide concrete, actionable advice
3. Be specific to the game state/context
4. Help improve future performance

Format your response as:
[L0-Case] Experience Title: Detailed description of the experience, including what to do/avoid and why.

Focus on:
- Pattern recognition errors
- Strategic mistakes or successes
- Game-specific tactics
- Decision-making principles

Your response:
"""


class KORGymExperienceExtractor:
    """Extracts experiences from KORGym game trajectories."""
    
    def __init__(self, llm_config: Dict[str, Any]):
        """
        Initialize the experience extractor.
        
        Args:
            llm_config: Configuration for the LLM client
        """
        self.llm = SimplifiedAsyncOpenAI(**llm_config)
        self.prompt_template = Template(L0_EXTRACTION_PROMPT)
        logger.info("Initialized KORGym Experience Extractor")
    
    async def extract_l0_from_round(
        self,
        round_result: Dict,
        game_category: str,
        game_type: str
    ) -> str:
        """
        Extract L0 experience from a game round.
        
        Args:
            round_result: Result dictionary from a game round
            game_category: Category of the game
            game_type: Type of game (single/multiple)
            
        Returns:
            Extracted L0 experience string
        """
        try:
            # Prepare context for prompt
            context = {
                'game_name': round_result.get('game_name', 'Unknown'),
                'game_category': game_category,
                'game_type': game_type,
                'success': round_result.get('success', False),
                'final_score': round_result.get('final_score', round_result.get('score', 0)),
                'rounds': round_result.get('rounds', 1)
            }
            
            # Add game-specific details
            if game_type == 'single':
                context.update({
                    'prompt': round_result.get('prompt', ''),
                    'action': round_result.get('action', ''),
                    'response': round_result.get('response', '')
                })
            else:
                context.update({
                    'trajectory': round_result.get('trajectory', []),
                    'enumerate': enumerate  # Make enumerate available in template
                })
            
            # Generate prompt
            prompt = self.prompt_template.render(**context)
            
            # Call LLM
            response = await self.llm.generate(prompt)
            experience = response.strip()
            
            logger.info(
                f"Extracted L0 experience for {context['game_name']}: "
                f"{experience[:100]}..."
            )
            
            return experience
            
        except Exception as e:
            logger.error(f"Failed to extract L0 experience: {e}")
            # Return a fallback experience
            return self._generate_fallback_experience(round_result, game_category)
    
    def _generate_fallback_experience(
        self,
        round_result: Dict,
        game_category: str
    ) -> str:
        """
        Generate a simple fallback experience when LLM extraction fails.
        
        Args:
            round_result: Game round result
            game_category: Game category
            
        Returns:
            Fallback experience string
        """
        game_name = round_result.get('game_name', 'Unknown')
        success = round_result.get('success', False)
        score = round_result.get('final_score', round_result.get('score', 0))
        
        if success:
            return (
                f"[L0-Case] {game_name} Success Pattern: "
                f"Achieved score {score} through the applied strategy. "
                f"Continue using similar approach in future games."
            )
        else:
            return (
                f"[L0-Case] {game_name} Failure Analysis: "
                f"Failed to achieve goal (score: {score}). "
                f"Review decision-making process and avoid similar mistakes."
            )
    
    def format_trajectory(self, trajectory: List[Dict]) -> str:
        """
        Format trajectory for display in prompts.
        
        Args:
            trajectory: List of game states
            
        Returns:
            Formatted trajectory string
        """
        formatted = []
        for i, step in enumerate(trajectory, 1):
            formatted.append(f"Round {i}:")
            formatted.append(f"  Action: {step.get('action', 'N/A')}")
            formatted.append(f"  Score: {step.get('score', 0)}")
            
            # Include board state if available
            if 'board' in step and step['board']:
                formatted.append(f"  State: {self._format_board(step['board'])}")
            
            formatted.append("")  # Empty line between rounds
        
        return "\n".join(formatted)
    
    def _format_board(self, board: Any) -> str:
        """Format board state for readability."""
        if isinstance(board, str):
            # Already formatted
            return board[:200] + "..." if len(board) > 200 else board
        elif isinstance(board, list):
            # 2D array board
            try:
                return "\n".join(
                    "|".join(str(cell) for cell in row)
                    for row in board
                )
            except:
                return str(board)
        else:
            return str(board)[:200]
    
    async def extract_batch_l0(
        self,
        round_results: List[Dict],
        game_category: str,
        game_type: str,
        max_concurrent: int = 5
    ) -> List[str]:
        """
        Extract L0 experiences from multiple game rounds in parallel.
        
        Args:
            round_results: List of game round results
            game_category: Game category
            game_type: Game type
            max_concurrent: Maximum concurrent LLM calls
            
        Returns:
            List of extracted experiences
        """
        import asyncio
        
        # Create semaphore for concurrency control
        sem = asyncio.Semaphore(max_concurrent)
        
        async def extract_with_sem(round_result):
            async with sem:
                return await self.extract_l0_from_round(
                    round_result,
                    game_category,
                    game_type
                )
        
        # Extract in parallel
        tasks = [extract_with_sem(result) for result in round_results]
        experiences = await asyncio.gather(*tasks)
        
        logger.info(f"Extracted {len(experiences)} L0 experiences")
        return experiences












