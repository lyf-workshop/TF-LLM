#!/usr/bin/env python3
"""Cleanup temporary KORGym training data."""

from sqlmodel import select
from utu.utils import SQLModelUtils
from utu.db import DatasetSample, EvaluationSample

with SQLModelUtils.create_session() as session:
    # 删除旧的训练和评估样本
    for dataset in ['KORGym-WordPuzzle-Qwen-Temp1-Train', 'KORGym-WordPuzzle-Qwen-Temp1-Eval']:
        samples = session.exec(select(DatasetSample).where(DatasetSample.dataset == dataset)).all()
        for s in samples:
            session.delete(s)
        session.commit()
        print(f'Deleted {len(samples)} dataset samples from {dataset}')
    
    # 删除所有 epoch 的评估数据
    eval_samples = session.exec(
        select(EvaluationSample).where(
            EvaluationSample.exp_id.like('word_puzzle_qwen_temp1_hierarchical%')
        )
    ).all()
    for s in eval_samples:
        session.delete(s)
    session.commit()
    print(f'Deleted {len(eval_samples)} evaluation samples')

print('✓ Database cleaned')











