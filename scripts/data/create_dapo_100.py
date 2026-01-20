"""
Create DAPO-100 dataset by sampling 100 questions from DAPO-Math-17k.
This script is used for reproducing the paper experiment.
"""
import random
from sqlmodel import select

from utu.db.eval_datapoint import DatasetSample
from utu.utils.sqlmodel_utils import SQLModelUtils


def create_dapo_100(seed: int = 42):
    """Sample 100 questions from DAPO-Math-17k to create DAPO-100 dataset."""
    
    # Check if DAPO-100 already exists
    with SQLModelUtils.create_session() as session:
        existing = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == "DAPO-100")
        ).all()
        
        if existing:
            print(f"Dataset DAPO-100 already exists with {len(existing)} samples, skipping creation.")
            return
        
        # Get all samples from DAPO-Math-17k
        dapo_samples = session.exec(
            select(DatasetSample).where(DatasetSample.dataset == "DAPO-Math-17k")
        ).all()
        
        if not dapo_samples:
            raise ValueError(
                "DAPO-Math-17k dataset not found in database. "
                "Please run 'python scripts/data/process_training_free_GRPO_data.py' first."
            )
        
        print(f"Found {len(dapo_samples)} samples in DAPO-Math-17k")
        
        # Sample 100 questions
        rng = random.Random(seed)
        sampled = rng.sample(dapo_samples, 100)
        
        # Create new dataset samples for DAPO-100
        new_samples = []
        for idx, sample in enumerate(sampled):
            new_sample = DatasetSample(
                dataset="DAPO-100",
                index=idx,
                source="training_free_grpo",
                question=sample.question,
                answer=sample.answer,
            )
            new_samples.append(new_sample)
        
        # Save to database
        session.add_all(new_samples)
        session.commit()
        
        print(f"Successfully created DAPO-100 dataset with {len(new_samples)} samples")


if __name__ == "__main__":
    create_dapo_100()

