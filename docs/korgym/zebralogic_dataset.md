# ZebraLogic Dataset Preparation - Medium-Lower Difficulty

This guide explains how to prepare a dataset of medium-lower difficulty problems from the ZebraLogic game for training and evaluation.

## 📋 Overview

Select **100 medium-lower difficulty problems** from the original ZebraLogic dataset (~1000 problems) for training and evaluation purposes.

## 🛠️ Usage

### 1️⃣ Analyze Dataset Difficulty Distribution (Recommended First)

```bash
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py --analyze_only
```

This command will:
- Load the original ZebraLogic dataset
- Analyze difficulty fields and distribution
- Display the number of problems for each difficulty level
- **Not save** any data

### 2️⃣ Create Medium-Lower Difficulty Dataset

```bash
# Default: select 100 medium-lower difficulty problems
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py

# Custom number and name
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py \
  --num_samples 150 \
  --dataset_name "ZebraLogic-MediumLower-150"

# Automatically overwrite existing dataset (no prompt)
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py --overwrite
```

### 3️⃣ Use in Training Configuration

Update your training config file (e.g., `configs/practice/your_config.yaml`):

```yaml
data:
  practice_dataset_name: "ZebraLogic-MediumLower-100"
  batch_size: 30
  num_epochs: 3
```

## 🎯 Difficulty Selection Strategy

The script intelligently selects medium-lower difficulty problems:

1. **Analyze difficulty distribution**: Count problems for each difficulty level
2. **Define medium-lower range**: Based on the distribution, select appropriate difficulty levels
3. **Random sampling**: Randomly select the specified number of problems from the medium-lower range
4. **Ensure diversity**: Try to cover different problem types

### Expected Difficulty Levels

Depending on the dataset's difficulty field, the script will select from:
- If difficulty is numeric (1-10): Select from levels 3-6
- If difficulty is categorical (Easy/Medium/Hard): Select "Medium" and "Easy-Medium"
- Automatically adapt to dataset structure

## 📊 Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--num_samples` | int | 100 | Number of problems to select |
| `--dataset_name` | str | "ZebraLogic-MediumLower-100" | Name of the new dataset |
| `--overwrite` | flag | False | Overwrite existing dataset without prompting |
| `--analyze_only` | flag | False | Only analyze distribution, don't save |
| `--seed` | int | 42 | Random seed for reproducibility |

## 🔍 Validation

After creating the dataset, validate it:

```bash
# View dataset samples
uv run python scripts/view_dataset.py \
    --dataset_name "ZebraLogic-MediumLower-100" \
    --limit 5

# Check dataset statistics
uv run python scripts/list_datasets.py | grep ZebraLogic
```

## 📈 Expected Results

For a medium-lower difficulty dataset:
- **Baseline accuracy**: 30-50%
- **After Training-Free GRPO**: 40-60%
- **Expected improvement**: +10-20%

Medium-lower difficulty problems are ideal for:
- ✅ Training agents effectively (not too easy, not too hard)
- ✅ Demonstrating clear improvement from experience learning
- ✅ Evaluating reasoning capabilities

## 🎮 Training Workflow

1. **Prepare dataset**:
   ```bash
   uv run python scripts/data/prepare_zebralogic_medium_lower_100.py
   ```

2. **Baseline evaluation**:
   ```bash
   uv run python scripts/run_eval.py \
       --config_name zebralogic_eval
   ```

3. **Training-Free GRPO**:
   ```bash
   uv run python scripts/run_training_free_GRPO.py \
       --config_name zebralogic_practice
   ```

4. **Enhanced evaluation**:
   ```bash
   uv run python scripts/run_eval.py \
       --config_name zebralogic_practice_eval
   ```

## 🔧 Troubleshooting

### Dataset Already Exists

**Error**: `Dataset already exists: ZebraLogic-MediumLower-100`

**Solution**:
```bash
# Option 1: Use --overwrite flag
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py --overwrite

# Option 2: Use different name
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py \
    --dataset_name "ZebraLogic-MediumLower-100-v2"

# Option 3: Delete old dataset manually
uv run python scripts/clean_experiment_data.py --dataset_name "ZebraLogic-MediumLower-100"
```

### No Difficulty Field Found

**Error**: `Cannot find difficulty field in dataset`

**Solution**:
The script will automatically:
1. Try common difficulty field names: `difficulty`, `level`, `hardness`
2. If not found, use random sampling from the entire dataset
3. Check the original dataset structure to confirm field names

### Insufficient Problems in Range

**Warning**: `Only X problems found in medium-lower range, requested Y`

**Solution**:
```bash
# First, analyze the distribution
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py --analyze_only

# Adjust num_samples based on available problems
uv run python scripts/data/prepare_zebralogic_medium_lower_100.py \
    --num_samples 80  # Reduce to available amount
```

## 📚 Related Documents

- [KORGym Overview](index.md) - KORGym games introduction
- [Troubleshooting Guide](troubleshooting.md) - Common problems and solutions
- [Training-Free GRPO](../practice.md) - Training framework details

## 💡 Tips

1. **Start with analysis**: Always run with `--analyze_only` first to understand the distribution
2. **Choose appropriate size**: 100 problems is usually good for initial experiments
3. **Use seed for reproducibility**: The default seed (42) ensures reproducible results
4. **Validate before training**: Always check a few samples before starting training
5. **Consider difficulty range**: Medium-lower provides best learning signal for most models

---

**Related Scripts**:
- `scripts/data/prepare_zebralogic_medium_lower_100.py` - Dataset preparation script
- `scripts/view_dataset.py` - View dataset samples
- `scripts/list_datasets.py` - List all datasets






