"""
View dataset contents from database
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utu.db import DatasetSample
from utu.utils import SQLModelUtils
from sqlmodel import select
import json


def view_dataset(dataset_name: str, limit: int = 10):
    """View dataset contents"""
    
    with SQLModelUtils.create_session() as session:
        # Get all samples from the dataset
        samples = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == dataset_name)
        ).all()
        
        if not samples:
            print(f"❌ Dataset '{dataset_name}' not found in database")
            return
        
        print(f"\n{'='*80}")
        print(f"Dataset: {dataset_name}")
        print(f"{'='*80}")
        print(f"Total samples: {len(samples)}")
        print()
        
        # Show first N samples
        print(f"Showing first {min(limit, len(samples))} samples:")
        print(f"{'-'*80}")
        
        for i, sample in enumerate(samples[:limit]):
            print(f"\n[Sample {i}]")
            print(f"  ID: {sample.id}")
            print(f"  Index: {sample.index}")
            print(f"  Source: {sample.source}")
            print(f"  Question: {sample.question[:100]}..." if len(sample.question) > 100 else f"  Question: {sample.question}")
            print(f"  Answer: {sample.answer[:100]}..." if sample.answer and len(sample.answer) > 100 else f"  Answer: {sample.answer}")
            if sample.meta:
                print(f"  Meta: {json.dumps(sample.meta, indent=4)}")
        
        # Show statistics
        if len(samples) > limit:
            print(f"\n... and {len(samples) - limit} more samples")
        
        # Seed statistics
        if samples and samples[0].meta and 'seed' in samples[0].meta:
            seeds = [s.meta['seed'] for s in samples if s.meta and 'seed' in s.meta]
            print(f"\n{'='*80}")
            print(f"Seed Statistics:")
            print(f"  Min seed: {min(seeds)}")
            print(f"  Max seed: {max(seeds)}")
            print(f"  Seed range: {min(seeds)} - {max(seeds)}")
            print(f"  Total unique seeds: {len(set(seeds))}")
            print(f"{'='*80}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset_name', type=str, required=True,
                       help='Name of the dataset to view')
    parser.add_argument('--limit', type=int, default=10,
                       help='Number of samples to display (default: 10)')
    args = parser.parse_args()
    
    view_dataset(args.dataset_name, args.limit)

