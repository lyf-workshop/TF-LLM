# Practice configuration templates

`configs/practice` contains Hydra configurations for Training-Free GRPO.  A
practice run creates and maintains reusable experience; it does **not** update
model parameters.

## Canonical templates

| Dataset family | Template | Practice dataset | Evaluation dataset |
| --- | --- | --- | --- |
| Math / AIME | `math/TEMPLATE_math_practice.yaml` | `DAPO-Math-17k` | `AIME24` |
| WebWalkerQA | `web/TEMPLATE_webwalkerqa_practice.yaml` | `AFM_web_RL` | `WebWalkerQA` |
| ZebraLogic | `logic/TEMPLATE_zebralogic_practice.yaml` | `ZebraLogic-Train-100` | `ZebraLogic-Test-30` |
| LiveCodeBench | `livecodebench/TEMPLATE_livecodebench_practice.yaml` | `LiveCodeBench-Train-30` | `LiveCodeBench-Eval-50` |
| SkillsBench | `skillsbench/TEMPLATE_skillsbench_practice.yaml` | `SkillsBench-v1.1-FamilyHoldout-SelfContained-Train` | `SkillsBench-v1.1-FamilyHoldout-SelfContained-Eval` |
| KORGym Word Puzzle | `korgym/TEMPLATE_word_puzzle_practice.yaml` | `KORGym-WordPuzzle-Train-100` | `KORGym-WordPuzzle-Eval-50` |
| KORGym Alphabetical Sorting | `korgym/TEMPLATE_alphabetical_sorting_practice.yaml` | `KORGym-AlphabeticalSorting-Train-100` | `KORGym-AlphabeticalSorting-Eval-50` |
| KORGym Wordle | `korgym/TEMPLATE_wordle_practice.yaml` | `KORGym-Wordle-Train-100` | `KORGym-Wordle-Eval-50` |

KORGym uses concrete per-game templates because its eval default, dataset,
agent objective, port, level, and round protocol must change together.  In each
template the root `korgym` block is checked against `evaluation.korgym` to avoid
silently training and evaluating different game protocols.

## Using a template

Copy the closest template to a non-`TEMPLATE_` filename.  Before a measured
run, assign a unique `exp_id` and unique `experience_save_path` /
`clustering_audit_path`, then verify that both named datasets exist in the
configured database.

```bash
uv run python scripts/run_training_free_GRPO.py --config_name math/my_math_practice
```

The canonical templates enable clustered hierarchical learning and all three
candidate-review gates.  Their similarity thresholds are explicitly marked
provisional, so L0 can be collected but L0->L1 and L1->L2 aggregation remains
blocked until a training-only calibration is accepted.  Do not bypass that
gate for a formal experiment.  The sentence-transformer revision must be
installed and cached explicitly; `embedding_local_files_only: true` prevents a
run from downloading it implicitly.

For a sequential ablation without semantic embeddings, set
`clustering_enabled: false` and `l0_review_retrieval: lexical`.  The hashing
provider is retained only as a test/lexical baseline, not as the formal
clustering default.

## Offline validation

The targeted test composes every canonical template through Hydra, validates
the fully composed object with Pydantic's strict unknown-field policy, checks
dataset-specific invariants, and rejects unresolved placeholders.  It does not
open the database, download a model, or call an LLM.

```bash
uv run --offline --no-sync pytest -q tests/practice/test_practice_config_templates.py
```

Passing this test proves configuration structure and references are valid.  It
does not prove that a dataset has been imported locally, a KORGym server is
running, SkillsBench/Harbor is installed, credentials are usable, or a formal
experiment succeeds.
