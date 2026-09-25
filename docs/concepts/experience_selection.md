# Experience Selection

`utu/eval/experience_filter.py` supports three experience-selection modes:

| Strategy | Behavior | Extra model call |
| --- | --- | --- |
| `static` | Apply per-level limits without semantic retrieval. | No |
| `retrieval` | Retrieve task-relevant experiences with the local TF-IDF retriever. | No |
| `llm_rerank` | Recall candidates, then rank them with a separate LLM. | Yes |

## Canonical configuration

Use a clean base agent and declare the snapshot once:

```yaml
experience_filter:
  enabled: true
  strategy: retrieval
  experience_source: workspace/hierarchical_experiences/skillsbench_practice.json
  retrieval_top_k: 8
  retrieval_min_score: 0.0
```

Per-level limits have one canonical location: `experience_filter.recall`.
The same limits are used by `static` filtering and by `llm_rerank` when
`recall.method: static` is selected.

```yaml
experience_filter:
  enabled: true
  strategy: llm_rerank
  experience_source: workspace/hierarchical_experiences/skillsbench_practice.json
  recall:
    method: static       # static | tfidf | all
    max_l2: null         # null means no limit
    max_l1: null
    max_l0: 50
  llm_rerank:
    model: qwen3-32b
    max_candidates: 20
    final_top_k: 8
```

There are no top-level `max_l0`, `max_l1`, or `max_l2` fields. The old
`bm25` name is not accepted; use `tfidf`, which matches the implementation.
