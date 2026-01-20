"""KORGym game processer for evaluation and training."""

from typing import TYPE_CHECKING

from ...config import EvalConfig
from ...utils import get_logger
from ..data import EvaluationSample
from .base_match_processor import BaseMatchProcesser

# Lazy import to avoid circular dependency
if TYPE_CHECKING:
    from ...practice.korgym_adapter import KORGymAdapter

logger = get_logger(__name__)


class KORGymProcesser(BaseMatchProcesser):
    """Processer for KORGym games."""
    
    name = "KORGym"
    
    def __init__(self, config: EvalConfig) -> None:
        super().__init__(config)
        
        # 初始化 KORGym adapter（如果配置了 korgym）
        self.adapter = None
        
        # Debug logging
        logger.info(f"KORGymProcesser init: hasattr(config, 'korgym')={hasattr(config, 'korgym')}")
        if hasattr(config, 'korgym'):
            logger.info(f"KORGymProcesser init: config.korgym={config.korgym}")
            if config.korgym:
                logger.info(f"KORGymProcesser init: config.korgym.enabled={config.korgym.enabled}")
        
        if hasattr(config, 'korgym') and config.korgym and config.korgym.enabled:
            # Import here to avoid circular dependency
            from ...practice.korgym_adapter import KORGymAdapter
            
            korgym_config = config.korgym
            self.adapter = KORGymAdapter(
                game_name=korgym_config.game_name,
                game_host=korgym_config.game_host,
                game_port=korgym_config.game_port,
                level=korgym_config.level,
                max_rounds=getattr(korgym_config, 'max_rounds', 50)
            )
            logger.info(f"✓ KORGymProcesser initialized with adapter for {korgym_config.game_name}")
        else:
            logger.warning(f"✗ KORGymProcesser: KORGym adapter not initialized (korgym config missing or disabled)")
    
    def preprocess_one(self, sample: EvaluationSample, recorder=None) -> EvaluationSample:
        """
        Preprocess a single KORGym game sample.
        
        For KORGym games, we need to:
        1. Generate the game instance using the seed from meta
        2. Get the game prompt
        3. Store the game_state in meta for later verification
        
        Args:
            sample: The evaluation sample
            recorder: Optional recorder (for compatibility)
            
        Returns:
            Processed sample with game prompt as augmented_question
        """
        if not self.adapter:
            logger.warning("KORGym adapter not initialized, using placeholder question")
            sample.update(augmented_question=sample.raw_question)
            return sample
        
        # 从 meta 中获取 seed
        meta = sample.meta or {}
        seed = meta.get('seed', 0)
        
        try:
            # 生成游戏实例
            game_state = self.adapter.generate_game_instance(seed)
            
            # 获取游戏提示
            prompt = self.adapter.get_game_prompt(game_state)
            
            # 不保存完整 game_state（避免序列化问题），只保存 seed
            # 在 judge 时会用 seed 重新生成游戏
            meta['game_seed'] = seed
            meta['game_prompt'] = prompt
            
            # 设置 augmented_question 为游戏提示
            sample.update(
                raw_question=prompt,
                augmented_question=prompt,
                meta=meta
            )
            
        except Exception as e:
            logger.error(f"Failed to generate KORGym game with seed {seed}: {e}")
            sample.update(
                augmented_question="Game generation failed",
                meta=meta
            )
        
        return sample
    
    async def judge_one(self, data: EvaluationSample) -> EvaluationSample:
        """
        Judge a single KORGym game result.
        
        For single-turn games:
        1. Extract the action from agent's response
        2. Verify the action with the game server
        3. Get the score from verification result
        
        For multi-round games:
        1. Use the complete game result from rollout phase
        2. Extract final score and success status
        3. No need to re-verify (already done in rollout)
        
        Args:
            data: The evaluation sample with game results
            
        Returns:
            Judged sample with score
        """
        if not self.adapter:
            logger.warning("KORGym adapter not initialized, cannot judge")
            data.update(
                correct=False,
                reward=0.0,
                judged_response="KORGym adapter not available"
            )
            return data
        
        meta = data.meta or {}
        
        # Check if this is a multi-round game with complete results
        if self.adapter.game_type == 'multiple' and 'multiround_result' in meta:
            # Multi-round game: use results from rollout phase
            logger.info(f"Judging multi-round game result for seed {meta.get('seed')}")
            
            multiround_result = meta['multiround_result']
            score = float(multiround_result.get('final_score', 0))
            success = multiround_result.get('success', False)
            rounds = multiround_result.get('rounds', 0)
            
            data.update(
                correct=success,
                reward=score,
                judged_response=f"Multi-round game completed in {rounds} rounds. Final score: {score}, Success: {success}",
                meta=meta
            )
            
            logger.info(
                f"KORGym multi-round judged: seed={meta.get('seed')}, "
                f"rounds={rounds}, score={score}, success={success}"
            )
            
            return data
        
        # Single-turn game: original logic
        game_seed = meta.get('game_seed') or meta.get('seed')
        
        if game_seed is None:
            logger.error("No game_seed found in meta, cannot judge")
            data.update(
                correct=False,
                reward=0.0,
                judged_response="No game seed available"
            )
            return data
        
        try:
            # 用 seed 重新生成游戏（避免序列化问题）
            game_state = self.adapter.generate_game_instance(game_seed)
            
            # 从 agent 响应中提取动作
            action = self.adapter._extract_action(data.response)
            
            # 将动作添加到 game_state
            game_state['action'] = action
            game_state['response'] = [data.response]
            
            # 验证动作并获取分数
            verified_state = self.adapter.verify_action(game_state)
            
            score = verified_state.get('score', 0.0)
            success = score > 0
            
            # 保存结果到 meta
            meta['score'] = score
            meta['success'] = success
            meta['action'] = action
            meta['verified_state'] = verified_state
            
            # 设置 correct 和 reward
            data.update(
                correct=success,
                reward=score,
                judged_response=f"Action: {action}, Score: {score}",
                meta=meta
            )
            
            logger.debug(f"KORGym game judged: seed={meta.get('seed')}, score={score}, action={action}")
            
        except Exception as e:
            logger.error(f"Failed to judge KORGym game: {e}")
            data.update(
                correct=False,
                reward=0.0,
                judged_response=f"Judging failed: {str(e)}",
                meta=meta
            )
        
        return data

