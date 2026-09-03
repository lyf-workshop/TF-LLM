# Hierarchical experience experiment protocol

The formal SkillsBench comparison has three conditions: `no_experience`,
`sequential`, and `clustered`. All conditions use the same versioned evaluation
task order and model/run parameters. Sequential and clustered aggregation start
from byte-identical normalized L0 snapshots and record both the source file
SHA-256 and the canonical L0 SHA-256.

## Task inventory and split

`configs/data/skillsbench/skillsbench_v1_1_task_splits.json` records every task
found under `SkillsBench-repo/tasks` and `tasks-extra`, the pinned repository
commit, metadata field mappings, inventory hash, exclusions, and deterministic
splits. The formal default is `family_holdout_self_contained_v1`: primary task
families are disjoint, and tasks marked as external-API-dependent or observed
runtime-invalid are excluded. `family_holdout_v1` retains the external-API
tasks for inventory analysis. `in_family_v1` and
`in_family_self_contained_v1` support task-ID-disjoint within-primary-family
transfer, with the latter excluding external-API tasks.

The repository's multi-label `task_type` graph is fully connected across all
73 self-contained eligible paper tasks. Therefore, a non-empty split that
holds out every secondary task-type label is impossible with the current data;
the class-out split is strict for the documented singular `task_family`
(normalized primary task type), not for every secondary label.

Unknown metadata never creates a hard-constraint mismatch. A hard constraint
only separates two experiences when both normalized enum values are known and
different. `domain` and `task_family` come from dataset metadata; the L0
generator does not guess them from model prose.

`task_stage` is restricted to `planning`, `execution`, `recovery`,
`verification`, `submission`, or `unknown`. `failure_mode` is restricted to
`none`, `verifier_failure`, `infrastructure_error`, `timeout`,
`execution_error`, `mixed_outcome`, or `unknown`. The latter is derived only
from recorded verifier reward/outcome and runtime error metadata.

Validate the selected split without changing the database:

```bash
python scripts/data/prepare_skillsbench_data.py \
  --repo_path SkillsBench-repo \
  --split_manifest configs/data/skillsbench/skillsbench_v1_1_task_splits.json \
  --split_name family_holdout_self_contained_v1 \
  --train_dataset_name SkillsBench-v1.1-FamilyHoldout-SelfContained-Train \
  --eval_dataset_name SkillsBench-v1.1-FamilyHoldout-SelfContained-Eval \
  --dry_run
```

Remove `--dry_run` only after approving the database write. Do not use
`--force` unless replacing those specifically named generated datasets is
intentional.

## Semantic embedding and threshold calibration

Formal clustering defaults to the pinned
`sentence-transformers/all-MiniLM-L6-v2` revision. It is a compact English
sentence encoder suitable for CPU batch inference and emits 384-dimensional
vectors. Vectors are normalized, dimension-checked, and cached by content hash
in a SQLite cache bound to provider, model revision, and dimension. The model
is loaded with `local_files_only=true`, so a run cannot download weights
silently. Hashing embeddings remain a lexical baseline and test fixture only.

The repository does not currently install or cache this optional model. Obtain
approval before adding `sentence-transformers` or downloading the pinned model.

The configured L0/L1 thresholds are deliberately marked provisional, and
clustered aggregation is blocked while that flag remains true. Calibrate from
training L0 only:

```bash
python scripts/experiments/calibrate_hierarchical_clustering.py \
  --experiences PATH_TO_TRAINING_L0_JSON \
  --output PATH_TO_NEW_CALIBRATION_REPORT.json
```

The script validates every usable L0 source against the manifest training
split. It reports `waiting_for_data` before loading an embedding model when
there are too few new-format records or same/different-family proxy pairs. A
reported threshold remains provisional until its cluster samples are reviewed;
formal evaluation outcomes must never be used for calibration.

## Unified experiment

First create a no-cost plan:

```bash
python scripts/experiments/run_hierarchical_ablation.py \
  --config-name skillsbench/skillsbench_practice \
  --source-experiences PATH_TO_TRAINING_L0_JSON \
  --output-dir PATH_TO_NEW_OUTPUT_DIR \
  --plan-only
```

After dependency/model approval, dataset creation, L0 review, and threshold
acceptance, omit `--plan-only` to aggregate and generate the two learned agent
configs. Aggregation temperature is fixed at `0.0`. The resulting experiment
plan contains the three evaluation commands in one fixed order.

After all three evaluations finish, build one paired report:

```bash
python scripts/experiments/report_hierarchical_ablation.py \
  --sequential-hierarchy OUTPUT_DIR/sequential.json \
  --clustered-hierarchy OUTPUT_DIR/clustered.json \
  --no-experience-exp-id NO_EXPERIENCE_EXP_ID \
  --sequential-exp-id SEQUENTIAL_EXP_ID \
  --clustered-exp-id CLUSTERED_EXP_ID \
  --output OUTPUT_DIR/report.json
```

The report rejects task-set/order, L0 snapshot, or recorded runtime-parameter
mismatches. It includes group pass rates, paired per-task outcomes, treatment
wins/losses/ties, token injection, pending/clustering metrics, domain/family
breakdowns, a deterministic paired bootstrap interval, and an exact McNemar
test. Its conclusion can be positive, tied, or negative for clustered learning.
