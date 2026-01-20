"""
Initialize KORGym evaluation dataset with virtual samples
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import DatasetSample
from utu.utils import SQLModelUtils
from sqlmodel import select
import random


def create_korgym_eval_dataset(dataset_name: str, num_samples: int = 50):
    """Create a virtual KORGym dataset for evaluation"""
    
    print(f"Creating KORGym dataset: {dataset_name}")
    print(f"Number of samples: {num_samples}")
    
    with SQLModelUtils.create_session() as session:
        # Check if dataset already exists
        existing = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == dataset_name)
        ).all()
        
        if existing:
            print(f"⚠️  Dataset {dataset_name} already exists with {len(existing)} samples")
            response = input("Delete existing dataset and recreate? (y/n): ")
            if response.lower() == 'y':
                for sample in existing:
                    session.delete(sample)
                session.commit()
                print(f"Deleted {len(existing)} existing samples")
            else:
                print("Keeping existing dataset")
                return
        
        # Generate unique seeds for evaluation
        # Use higher seed range to avoid overlap with training data
        base_seed = 10000
        seeds = list(range(base_seed, base_seed + num_samples))
        random.shuffle(seeds)
        
        # Create virtual samples
        samples = []
        for i, seed in enumerate(seeds):
            sample = DatasetSample(
                dataset=dataset_name,
                index=i,
                source="KORGym",  # Important: tells system to use KORGymProcesser
                question=f"KORGym Word Puzzle (seed={seed})",  # Placeholder
                answer="",  # Will be generated dynamically
                meta={
                    "korgym": True,
                    "seed": seed,
                    "note": "Virtual dataset sample - game will be generated on-the-fly"
                }
            )
            samples.append(sample)
        
        # Batch insert
        print(f"Inserting {len(samples)} samples...")
        session.add_all(samples)
        session.commit()
        
        # Verify
        count = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == dataset_name)
        ).all()
        
        print(f"✓ Dataset {dataset_name} created successfully!")
        print(f"  Total samples in database: {len(count)}")
        print(f"  Seed range: {min(seeds)} - {max(seeds)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset_name', type=str, required=True,
                       help='Name of the dataset to create')
    parser.add_argument('--num_samples', type=int, default=50,
                       help='Number of samples to create (default: 50)')
    args = parser.parse_args()
    
    create_korgym_eval_dataset(args.dataset_name, args.num_samples)

