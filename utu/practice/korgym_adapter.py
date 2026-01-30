"""
KORGym Game Adapter for Hierarchical Experience Learning System.

This module provides the interface between KORGym games and the 
Training-Free GRPO hierarchical experience learning system.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests

from ..utils import get_logger

logger = get_logger(__name__)


# Game categories mapping from KORGym paper
GAME_CATEGORIES = {
    'math_logic': [
        '1-DateCount', '4-SudoKu', '16-jiafa', '32-numeral_bricks',
        '47-jiafa_multimodal', '50-SudoKu_MultiModal'
    ],
    'control_interaction': [
        '10-minigrid', '11-maze', '12-sokoban', '41-PVZ', '45-free_the_key'
    ],
    'puzzle': [
        '2-GuessWord', '5-light_out_game', '8-word_puzzle', '9-Jigsaw_puzzle',
        '13-play_lines', '14-Arrow-pathway', '15-emoji_connect', '17-fill_game',
        '21-Anagramania', '22-alphabetical_sorting', '23-puzzlegame',
        '28-word_encryption', '33-wordle', '34-one_touch_drawing', '35-pipe_game',
        '36-CryptoWord', '38-minesweeper', '42-diagram_coloring', 
        '46-wordle_multimodal'
    ],
    'spatial_geometric': [
        '7-black_white_copy', '18-alien', '19-party_time', '20-city_path',
        '29-Construction_Company', '30-Tower_of_Hanoi', '31-ball_arrange',
        '44-city', '48-map_position_simulation_text', 
        '49_map_position_simulation_multimodal', '51-ball_arrange_multimodal'
    ],
    'strategic': [
        '3-2048', '24-snake', '25-Tetris', '26-TrustRovolution', '27-NpointPlus',
        '37-SpiderSolitaire', '39-Nullify', '40-CircleTheCat-Text',
        '43-CircleTheCat-Multimodal'
    ],
    'multimodal': [
        '17-fill_game', '43-CircleTheCat-Multimodal', '46-wordle_multimodal',
        '47-jiafa_multimodal', '49_map_position_simulation_multimodal',
        '50-SudoKu_MultiModal', '51-ball_arrange_multimodal'
    ]
}

# Game types: single-turn or multi-turn
GAME_TYPES = {
    'single': [
        '1-DateCount', '2-GuessWord', '4-SudoKu', '5-light_out_game',
        '8-word_puzzle', '9-Jigsaw_puzzle', '11-maze', '12-sokoban',
        '13-play_lines', '14-Arrow-pathway', '15-emoji_connect', '16-jiafa',
        '17-fill_game', '18-alien', '19-party_time', '20-city_path',
        '21-Anagramania', '22-alphabetical_sorting', '23-puzzlegame',
        '28-word_encryption', '29-Construction_Company', '32-numeral_bricks',
        '34-one_touch_drawing', '35-pipe_game', '42-diagram_coloring',
        '44-city', '47-jiafa_multimodal', '48-map_position_simulation_text',
        '49_map_position_simulation_multimodal', '50-SudoKu_MultiModal',
        '6-LongCat', '7-black_white_copy'
    ],
    'multiple': [
        '3-2048', '10-minigrid', '24-snake', '25-Tetris', '26-TrustRovolution',
        '27-NpointPlus', '30-Tower_of_Hanoi', '31-ball_arrange', '33-wordle',
        '36-CryptoWord', '37-SpiderSolitaire', '38-minesweeper', '39-Nullify',
        '40-CircleTheCat-Text', '41-PVZ', '43-CircleTheCat-Multimodal',
        '45-free_the_key', '46-wordle_multimodal', '51-ball_arrange_multimodal'
    ]
}


class KORGymGameClassifier:
    """Classifier for KORGym games to categorize by reasoning dimension."""
    
    @staticmethod
    def get_category(game_name: str) -> str:
        """Get the reasoning category for a game."""
        for category, games in GAME_CATEGORIES.items():
            if game_name in games:
                return category
        return 'unknown'
    
    @staticmethod
    def get_all_categories(game_name: str) -> List[str]:
        """Get all categories a game belongs to (some games span multiple)."""
        categories = []
        for category, games in GAME_CATEGORIES.items():
            if game_name in games:
                categories.append(category)
        return categories if categories else ['unknown']
    
    @staticmethod
    def get_game_type(game_name: str) -> str:
        """Get the game type (single-turn or multi-turn)."""
        for game_type, games in GAME_TYPES.items():
            if game_name in games:
                return game_type
        return 'unknown'
    
    @staticmethod
    def is_multimodal(game_name: str) -> bool:
        """Check if a game requires multimodal input."""
        return 'multimodal' in KORGymGameClassifier.get_all_categories(game_name)


class KORGymAdapter:
    """Adapter for KORGym games to work with the hierarchical experience system."""
    
    def __init__(
        self,
        game_name: str,
        game_host: str = "localhost",
        game_port: int = 8775,
        level: int = 4,
        max_rounds: int = 100
    ):
        """
        Initialize KORGym game adapter.
        
        Args:
            game_name: Name of the game (e.g., '3-2048')
            game_host: Host where game server is running
            game_port: Port where game server is running
            level: Difficulty level (1-5)
            max_rounds: Maximum number of rounds for multi-turn games
        """
        self.game_name = game_name
        self.game_url = f"http://{game_host}:{game_port}"
        self.level = level
        self.max_rounds = max_rounds
        
        # Game metadata
        self.game_category = KORGymGameClassifier.get_category(game_name)
        self.game_type = KORGymGameClassifier.get_game_type(game_name)
        self.is_multimodal = KORGymGameClassifier.is_multimodal(game_name)
        
        logger.info(
            f"Initialized KORGym adapter for {game_name} "
            f"(category: {self.game_category}, type: {self.game_type})"
        )
    
    def generate_game_instance(self, seed: int) -> Dict:
        """
        Generate a new game instance.
        
        Args:
            seed: Random seed for game generation
            
        Returns:
            Dict containing game state
        """
        try:
            response = requests.post(
                f"{self.game_url}/generate",
                json={"seed": seed, "level": self.level},
                timeout=30
            )
            response.raise_for_status()
            game_state = response.json()
            game_state['seed'] = seed
            game_state['response'] = []
            return game_state
        except Exception as e:
            logger.error(f"Failed to generate game instance: {e}")
            raise
    
    def get_game_prompt(self, game_state: Dict) -> str:
        """
        Get the current game board/state as a prompt.
        
        Args:
            game_state: Current game state
            
        Returns:
            Formatted prompt string
        """
        try:
            response = requests.post(
                f"{self.game_url}/print_board",
                json=game_state,
                timeout=30
            )
            response.raise_for_status()
            return response.json()['board']
        except Exception as e:
            logger.error(f"Failed to get game prompt: {e}")
            raise
    
    def verify_action(self, game_state: Dict) -> Dict:
        """
        Verify the agent's action and update game state.
        
        Args:
            game_state: Game state with agent's action
            
        Returns:
            Updated game state with verification result
        """
        try:
            response = requests.post(
                f"{self.game_url}/verify",
                json=game_state,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            game_state.update(result)
            return game_state
        except Exception as e:
            logger.error(f"Failed to verify action: {e}")
            game_state['score'] = 0
            game_state['is_end'] = True
            return game_state
    
    async def play_single_round(self, agent, seed: int) -> Dict:
        """
        Play a single-turn game.
        
        Args:
            agent: The agent to play the game
            seed: Random seed
            
        Returns:
            Game result dictionary
        """
        # Generate game instance
        game_state = self.generate_game_instance(seed)
        prompt = self.get_game_prompt(game_state)
        
        # Get agent's response
        start_time = time.time()
        agent_result = await agent.run(prompt)
        response_time = time.time() - start_time
        
        # Extract action from response
        action = self._extract_action(agent_result.final_output)
        game_state['action'] = action
        game_state['response'] = [agent_result.final_output]
        
        # Verify action
        game_state = self.verify_action(game_state)
        
        return {
            'game_name': self.game_name,
            'game_category': self.game_category,
            'seed': seed,
            'prompt': prompt,
            'action': action,
            'response': agent_result.final_output,
            'score': game_state.get('score', 0),
            'success': game_state.get('score', 0) > 0,
            'is_end': True,
            'rounds': 1,
            'response_time': response_time,
            'trajectory': [game_state],
            'round_id': f"{self.game_name}_seed{seed}_{int(time.time())}"
        }
    
    async def play_multiple_rounds(self, agent, seed: int) -> Dict:
        """
        Play a multi-turn game with compact history format.
        
        Uses a compact history representation (e.g., "apple → G:a@0 Y:p@1 N:p@2 N:l@3 N:e@4")
        instead of full conversation history to keep prompts short and efficient.
        
        Args:
            agent: The agent to play the game
            seed: Random seed
            
        Returns:
            Game result dictionary
        """
        # Generate game instance
        game_state = self.generate_game_instance(seed)
        trajectory = []
        responses = []
        total_time = 0
        compact_history = []  # Compact history for prompt context
        
        for round_num in range(1, self.max_rounds + 1):
            # ⚠️ CRITICAL FIX: Don't use game server's verbose history!
            # Build our own prompt with compact history only
            
            # Get game info (without history) from game state
            game_title = f"{self.game_name.title()} Game"
            attempt_info = f"Attempt: {round_num} of {self.max_rounds}"
            word_length = f"Word length: {game_state.get('level', len(game_state.get('secret_word', '')))}"
            
            # Build base prompt manually (without game server's verbose history)
            base_prompt_lines = [
                "You are a good game player, I'll give you a game board and rules.",
                "Your task is:",
                "- First, give your answer according to the game board and rules.",
                "- Second, output the answer in the required format. The last line of your response should be in the following format: 'Answer: $YOUR_ANSWER' (without quotes), where YOUR_ANSWER is your final answer to the question, e.g., 'Answer: happy'",
                "You need to guess a specific location-based word according to the information provided below. You have several attempts, and each guess result will be recorded in the History for future reference. Please provide your guess for this round based on the following information, e.g., 'Answer: happy'.",
                game_title,
                attempt_info,
                word_length,
            ]
            
            # Build compact history section for prompt
            if compact_history:
                base_prompt_lines.append("History (Compact Format):")
                for i, entry in enumerate(compact_history, 1):
                    base_prompt_lines.append(f"{i}. {entry}")
                base_prompt_lines.append("\nNote: G=Green (correct spot), Y=Yellow (wrong spot), N=Gray (not in word)")
            else:
                base_prompt_lines.append("History:")
            
            prompt = "\n".join(base_prompt_lines)
            
            # Get agent's response
            # ⚠️ IMPORTANT: save=False to prevent full conversation history accumulation
            # We manually manage compact history instead
            start_time = time.time()
            agent_result = await agent.run(prompt, save=False)
            response_time = time.time() - start_time
            total_time += response_time
            
            # Extract action
            action = self._extract_action(agent_result.final_output)
            game_state['action'] = action
            responses.append(agent_result.final_output)
            
            # Verify action and update state
            game_state = self.verify_action(game_state)
            trajectory.append(dict(game_state))
            
            # Extract compact feedback and add to history
            compact_feedback = self._extract_compact_feedback(game_state, action)
            if compact_feedback:
                compact_history.append(compact_feedback)
            
            # Check if game ended
            if game_state.get('is_end', False):
                break
        
        return {
            'game_name': self.game_name,
            'game_category': self.game_category,
            'seed': seed,
            'responses': responses,
            'final_score': game_state.get('score', 0),
            'success': game_state.get('score', 0) > 0,
            'is_end': game_state.get('is_end', True),
            'rounds': round_num,
            'response_time': total_time,
            'trajectory': trajectory,
            'compact_history': compact_history,  # Save compact history for analysis
            'round_id': f"{self.game_name}_seed{seed}_{int(time.time())}"
        }
    
    async def play_game(self, agent, seed: int) -> Dict:
        """
        Play a game (automatically chooses single or multi-turn).
        
        Args:
            agent: The agent to play the game
            seed: Random seed
            
        Returns:
            Game result dictionary
        """
        if self.game_type == 'single':
            return await self.play_single_round(agent, seed)
        else:
            return await self.play_multiple_rounds(agent, seed)
    
    def _extract_compact_feedback(self, game_state: Dict, action: str) -> str:
        """
        Extract compact feedback from game state for history tracking.
        
        Converts verbose feedback into compact format:
        - Wordle: "apple → G:a@0 Y:p@1 N:p@2 N:l@3 N:e@4"
        - Other games: may use different formats
        
        Args:
            game_state: Current game state after verification
            action: The action taken this round
            
        Returns:
            Compact feedback string
        """
        # For Wordle-like games, extract from history
        if 'history' in game_state and game_state['history']:
            last_entry = game_state['history'][-1]
            guess = last_entry.get('guess', action)
            feedback = last_entry.get('feedback', '')
            
            # Parse verbose feedback into compact format
            # Example feedback: "The letter a located at idx=0 is in the word and in the correct spot,"
            compact_parts = []
            for line in feedback.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Extract letter and position
                if 'located at idx=' in line:
                    # Extract letter (after "The letter ")
                    letter_start = line.find('The letter ') + len('The letter ')
                    letter_end = line.find(' located at')
                    letter = line[letter_start:letter_end] if letter_end > letter_start else '?'
                    
                    # Extract position
                    idx_start = line.find('idx=') + 4
                    idx_end = line.find(' ', idx_start)
                    if idx_end == -1:
                        idx_end = line.find(',', idx_start)
                    if idx_end == -1:
                        idx_end = len(line)
                    position = line[idx_start:idx_end]
                    
                    # Determine color
                    if 'correct spot' in line:
                        color = 'G'  # Green
                    elif 'wrong spot' in line:
                        color = 'Y'  # Yellow
                    else:
                        color = 'N'  # Gray/None
                    
                    compact_parts.append(f"{color}:{letter}@{position}")
            
            if compact_parts:
                return f"{guess} → {' '.join(compact_parts)}"
        
        # Fallback: just return the action
        return f"{action} → [no detailed feedback]"
    
    def _extract_action(self, response: str) -> str:
        """
        Extract action from agent's response.
        
        Args:
            response: Agent's response text
            
        Returns:
            Extracted action string
        """
        if response is None:
            return ""
        
        # Normalize response
        normalized = self._normalize_response(response)
        
        # Find last occurrence of "Answer"
        pos = normalized.lower().rfind("answer")
        if pos == -1:
            return ""
        
        # Extract after "Answer:"
        gen = normalized[pos:]
        pattern = r"(?i)Answer\s*:\s*(.*)"
        match = re.findall(pattern, gen)
        return match[-1].strip() if match else ""
    
    def _normalize_response(self, response: str) -> str:
        """Normalize response by removing LaTeX formatting."""
        return (
            response.replace("**", "")
                    .replace("$\\boxed{", "")
                    .replace("}$", "")
                    .replace("\\$", "")
                    .replace("$\\text{", "")
                    .replace("$", "")
                    .replace("\\mathrm{", "")
                    .replace("\\{", "")
                    .replace("\\text", "")
                    .replace("\\(", "")
                    .replace("\\mathbf{", "")
                    .replace("{", "")
                    .replace("\\boxed", "")
        )












