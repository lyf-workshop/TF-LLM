"""
Prepare KORGym datasets for training and evaluation.

This script creates:
- Evaluation dataset: 50 samples with seeds 1-50
- Training dataset: 100 samples with seeds 51-150
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utu.db import DatasetSample, DBService
from utu.utils import get_logger, SQLModelUtils

logger = get_logger(__name__)


def game_name_to_dataset_name(game_name: str) -> str:
    """
    Convert KORGym game ID to dataset name format.
    
    Examples:
        "8-word_puzzle" -> "WordPuzzle"
        "22-alphabetical_sorting" -> "AlphabeticalSorting"
        "33-wordle" -> "Wordle"
    
    Args:
        game_name: KORGym game ID (e.g., "8-word_puzzle")
    
    Returns:
        Dataset name component (e.g., "WordPuzzle")
    """
    # Remove number prefix (e.g., "8-", "22-", "33-")
    parts = game_name.split("-", 1)
    if len(parts) > 1:
        game_part = parts[1]  # Get part after number prefix
    else:
        game_part = parts[0]
    
    # Convert underscore-separated words to CamelCase
    words = game_part.split("_")
    camel_case = "".join(word.capitalize() for word in words)
    
    return camel_case


def create_korgym_datasets(
    game_name: str = "8-word_puzzle",
    eval_seeds_start: int = 1,
    eval_seeds_end: int = 50,
    train_seeds_start: int = 51,
    train_seeds_end: int = 150,
):
    """
    Create training and evaluation datasets for KORGym.
    
    Args:
        game_name: KORGym game name (e.g., "8-word_puzzle", "3-2048")
        eval_seeds_start: Start seed for evaluation dataset
        eval_seeds_end: End seed for evaluation dataset (inclusive)
        train_seeds_start: Start seed for training dataset
        train_seeds_end: End seed for training dataset (inclusive)
    """
    
    eval_count = eval_seeds_end - eval_seeds_start + 1
    train_count = train_seeds_end - train_seeds_start + 1
    
    # Generate dataset names based on game name
    game_dataset_name = game_name_to_dataset_name(game_name)
    eval_dataset_name = f"KORGym-{game_dataset_name}-Eval-{eval_count}"
    train_dataset_name = f"KORGym-{game_dataset_name}-Train-{train_count}"
    
    logger.info(f"Creating KORGym datasets for game: {game_name}")
    logger.info(f"  - Evaluation dataset: {eval_dataset_name}")
    logger.info(f"    Samples: {eval_count} (seeds {eval_seeds_start}-{eval_seeds_end})")
    logger.info(f"  - Training dataset: {train_dataset_name}")
    logger.info(f"    Samples: {train_count} (seeds {train_seeds_start}-{train_seeds_end})")
    
    # Evaluation dataset
    eval_samples = []
    for seed in range(eval_seeds_start, eval_seeds_end + 1):
        sample = DatasetSample(
            dataset=eval_dataset_name,
            source="KORGym",  # Use "KORGym" to match KORGymProcesser
            question=f"Play KORGym game '{game_name}' with seed {seed}",
            answer="success",  # Expected outcome
            meta={  # ✅ 使用 meta 而不是 metadata
                "seed": seed,
                "game_name": game_name,
                "dataset_type": "eval"
            }
        )
        eval_samples.append(sample)
    
    # Training dataset
    train_samples = []
    for seed in range(train_seeds_start, train_seeds_end + 1):
        sample = DatasetSample(
            dataset=train_dataset_name,
            source="KORGym",  # Use "KORGym" to match KORGymProcesser
            question=f"Play KORGym game '{game_name}' with seed {seed}",
            answer="success",
            meta={  # ✅ 使用 meta 而不是 metadata
                "seed": seed,
                "game_name": game_name,
                "dataset_type": "train"
            }
        )
        train_samples.append(sample)
    
    # Check database availability
    if not SQLModelUtils.check_db_available():
        logger.error("Database is not available. Please check your UTU_DB_URL environment variable.")
        return
    
    # Upload to database
    logger.info(f"\nUploading {len(eval_samples)} evaluation samples...")
    DBService.add(eval_samples)
    logger.info(f"✓ Evaluation dataset created: {eval_dataset_name}")
    
    logger.info(f"\nUploading {len(train_samples)} training samples...")
    DBService.add(train_samples)
    logger.info(f"✓ Training dataset created: {train_dataset_name}")
    
    logger.info("\n📊 Dataset Summary:")
    logger.info(f"  - Game: {game_name}")
    logger.info(f"  - Evaluation: {eval_dataset_name} ({eval_count} samples, seeds {eval_seeds_start}-{eval_seeds_end})")
    logger.info(f"  - Training: {train_dataset_name} ({train_count} samples, seeds {train_seeds_start}-{train_seeds_end})")
    logger.info("\n✅ Datasets created successfully!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Prepare KORGym datasets")
    parser.add_argument(
        "--game_name",
        type=str,
        default="8-word_puzzle",
        help="KORGym game name (default: 8-word_puzzle)"
    )
    parser.add_argument(
        "--eval_seeds_start",
        type=int,
        default=1,
        help="Start seed for evaluation dataset (default: 1)"
    )
    parser.add_argument(
        "--eval_seeds_end",
        type=int,
        default=50,
        help="End seed for evaluation dataset (default: 50)"
    )
    parser.add_argument(
        "--train_seeds_start",
        type=int,
        default=51,
        help="Start seed for training dataset (default: 51)"
    )
    parser.add_argument(
        "--train_seeds_end",
        type=int,
        default=150,
        help="End seed for training dataset (default: 150)"
    )
    
    args = parser.parse_args()
    
    create_korgym_datasets(
        game_name=args.game_name,
        eval_seeds_start=args.eval_seeds_start,
        eval_seeds_end=args.eval_seeds_end,
        train_seeds_start=args.train_seeds_start,
        train_seeds_end=args.train_seeds_end,
    )

