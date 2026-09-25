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

`SUPPORTED_CONFIGS.txt` is the machine-checked allowlist of maintained practice
entry points. Every listed entry is composed through Hydra and validated with
unknown fields forbidden. `LEGACY_CONFIGS.txt` classifies every other
versioned non-smoke YAML with a machine-readable reason. Legacy files may be
schema-valid historical provenance, or may target an obsolete schema or a
missing Agent; none is a supported entry point. Files whose names contain
`smoke` are transient diagnostics and intentionally do not enter either catalog.

Supported means configuration-compatible, not automatically suitable for a
formal result. The maintained DAPO-100/DAPO-200 exploratory runs still use a
signed schema-v2 sampling manifest. Strict measured execution requires the
schema-v3 task inventory, split, and row-level enrichment contract; those runs
therefore keep `require_practice_manifest: false` until genuine v3 enrichment
artifacts exist. The v2 files are retained as sampling provenance and are not
silently relabelled as v3.

KORGym uses concrete per-game templates because its evaluation dataset, agent
objective, port, level, and round protocol must change together. In a canonical
practice config, the shared `runtime.korgym` block is the only source for that
protocol. Historical files may still contain a root `korgym` or `evaluation`
block; the loader accepts those shapes only as read-only migration input and
never emits them in the resolved canonical model.

The top-level layout is intentionally small:

- `exp_id`: durable experiment identity;
- `practice`: rollout, experience, hierarchy, and optional in-run evaluation
  controls;
- `data`: practice dataset and manifest contract;
- `runtime`: Agent, judge, verifier, database, and benchmark dependencies.

Do not add a second `evaluation` block or copy `concurrency`, `pass_k`, Agent,
judge, or benchmark settings into another section. Practice constructs the
temporary evaluation adapter internally when it starts a rollout.

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

Canonical templates explicitly select `upper_pool_update_mode: clustered` and
`candidate_review_scope: retrieval`. Incremental stacked-pool experiments must
override both fields deliberately. `resume_from_hierarchy` is likewise
explicitly false in templates; set it true only when the target snapshot was
created by the same resolved configuration and dataset identity.

`l0_injection_top_k` limits query-time L0 retrieval during practice. It does
not control the final Agent artifact. Final export is configured separately by
`export_include_l0` and `export_max_l0`. Maintained configs either export no L0
or set the latter to `null` to export every active L0. Partial L0 exports are
legacy-only and cannot silently become a maintained experiment treatment.

For a sequential ablation without semantic embeddings, set
`clustering_enabled: false` and `l0_review_retrieval: lexical`.  The hashing
provider is retained only as a test/lexical baseline, not as the formal
clustering default.

## Offline validation

The targeted test composes every canonical template and every entry in
`SUPPORTED_CONFIGS.txt` through Hydra, validates the fully composed object with
Pydantic's strict unknown-field policy, checks dataset-specific invariants, and
rejects unresolved placeholders. It does not open the database, download a
model, or call an LLM.

```bash
uv run --offline --no-sync pytest -q tests/practice/test_practice_config_templates.py
```

Passing this test proves configuration structure and references are valid.  It
does not prove that a dataset has been imported locally, a KORGym server is
running, SkillsBench/Harbor is installed, credentials are usable, or a formal
experiment succeeds.
