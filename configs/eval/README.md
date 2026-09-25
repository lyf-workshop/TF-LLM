# Evaluation configuration contract

`SUPPORTED_CONFIGS.txt` is the exhaustive allowlist of maintained evaluation
entry points. CI composes each entry through Hydra, resolves interpolation,
and validates it with strict `EvalConfig` before comparing that result with
the production loader. This proves the configuration/runtime contract; an
actual run may still require its declared dataset, game server, and model
endpoint.

`LEGACY_CONFIGS.txt` classifies every other versioned evaluation entry point
with a reason code. Generated-Agent references remain legacy until the
corresponding artifact exists in a reproducible workflow; CI does not pretend
that such a file is available. KORGym template files containing placeholders
are examples, not entry points.

Files in `data/` are Hydra data fragments rather than standalone evaluation
configs. They are exhaustively validated against strict `DataConfig` by the
same catalog test.

Run the offline contract suite with:

```bash
uv run --offline --no-sync pytest -q tests/test_config_catalogs.py
```
