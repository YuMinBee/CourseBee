# Evaluation

CourseBee v2 treats retrieval as a behavior that should be checked, not only described. The evaluation harness validates whether `mode="auto"` chooses the expected retrieval strategy, returns source evidence, uses graph context when appropriate, and falls back clearly when course graph evidence is missing.

## Files

```text
eval/
- golden_questions.jsonl
- expected_routes.json
- expected_sources.json
- run_eval.py
- generalization_suite.json
- run_generalization_eval.py
- robustness_suite.json
- run_robustness_eval.py
- semantic_retrieval_suite.json
- run_semantic_retrieval_eval.py
- results/latest_eval.md
- results/latest_generalization_eval.md
- results/latest_robustness_eval.md
- results/latest_semantic_retrieval_eval.md
```

The fixture used by `run_eval.py` is synthetic and public. It does not depend on private lecture materials.

## Run

```bash
python eval/run_eval.py
python eval/run_generalization_eval.py
python eval/run_robustness_eval.py
pip install -e ".[semantic]"
python eval/run_semantic_retrieval_eval.py
```

The first command creates a synthetic NLP Course Pack under `outputs/_eval_runtime`, runs the golden questions through the same v2 service path used by the app, and writes `eval/results/latest_eval.md`. The second command repeats fact and relation checks across biology, economics, and software engineering. The robustness suite adds OCR line-break noise, conflicting source versions, cross-document relations, unrelated distractors, and explicit abstention checks. The optional semantic suite downloads real Sentence Transformers models and compares local, dense+RRF, and Cross-Encoder rankings on paraphrased and cross-lingual questions, so it is intentionally excluded from the lightweight default CI job.

## Citation Quality

Citation quality is evaluated separately from answer style. The important question is whether generated claims remain tied to retrieved source chunks.

Tracked signals:

- source coverage
- unsupported claim detection
- source/chunk preview readiness
- answer sentence to supporting chunk mapping through preserved `sources`

`check_text_grounding` compares generated claim terms with source chunk terms and returns `coverage`, `matched_terms`, `unsupported_terms`, and warnings. API-refined Course Pack summaries must pass this check or CourseBee falls back to rule-based grounded output.

See [Citation and Grounding](CITATION_GROUNDING.md) for the source metadata flow.

## Current Snapshot

| Metric | Result |
| --- | --- |
| Overall pass rate | 10 / 10 |
| Router accuracy | 10 / 10 |
| Source recall@5 | 9 / 9 required-source cases |
| Citation coverage | 0.90 |
| No-context fallback pass | 1 / 1 |
| Graph route useful cases | 4 / 4 |

Multi-domain snapshot:

| Metric | Result |
| --- | --- |
| Overall pass rate | 6 / 6 |
| Router accuracy | 6 / 6 |
| Required source recall | 6 / 6 |
| Citation coverage | 6 / 6 |
| Graph evidence usefulness | 3 / 3 |

Robustness snapshot:

| Metric | Result |
| --- | --- |
| Overall pass rate | 5 / 5 |
| Source recall and precision checks | 5 / 5 |
| Graph evidence checks | 2 / 2 |
| Abstention checks | 1 / 1 |
| Local ask latency p50 / p95 | 9.97 ms / 13.51 ms |

Semantic retrieval snapshot:

| Mode | Recall@3 | MRR | Mean warm latency | Fallbacks |
| --- | ---: | ---: | ---: | ---: |
| Local hybrid | 0.17 | 0.167 | 2.29 ms | 0 |
| E5 + RRF | 1.00 | 0.917 | 9.09 ms | 0 |
| E5 + RRF + Cross-Encoder | 1.00 | 1.000 | 12.03 ms | 0 |

The semantic snapshot uses six public synthetic cases. It tests retrieval ranking only and does not claim the same gain for generated answers or production lecture data. All local latency values are environment-dependent snapshots; the versioned result files are authoritative for the latest run.

## Metrics

- Router accuracy: checks `question_type`, `routed_mode`, and final `retrieval_mode` against `expected_routes.json`.
- Source recall@5: checks whether required filenames appear in answer sources, graph evidence, or hierarchical supporting chunks.
- Citation coverage: measures whether each answer returns at least one source-like evidence reference.
- Graph route useful cases: checks that graph-routed questions return graph context or graph paths and required concepts.
- No-context fallback pass: checks that relation questions without matching course graph evidence fall back with a warning instead of silently pretending graph evidence exists.
- Source precision: verifies unrelated distractor filenames do not appear in returned evidence.
- Conflict coverage: requires both versioned sources when the question compares conflicting values.
- Local ask latency: records deterministic local retrieval and composition time; it is not a hosted LLM or network latency benchmark.
- Semantic Recall@k and MRR: compare expected-source ranking for Korean paraphrases and cross-lingual questions after model warm-up.

## Example Golden Case

```json
{
  "question": "BPE와 OOV는 어떤 관계야?",
  "expected_question_type": "relation_question",
  "expected_route": "local_graph",
  "must_include_sources": ["자연어처리_11주차_1차시.txt"],
  "must_include_concepts": ["BPE", "OOV"]
}
```

## Related Graph Evaluation

For a focused comparison of vector retrieval vs concept graph-assisted retrieval, see [Concept Graph Retrieval Evaluation](GRAPH_RAG_EVALUATION.md).

## Why It Matters

This makes CourseBee easier to judge as an engineering system. The router, provenance handling, concept graph-assisted path, multi-level summary path, and fallback behavior can be checked with repeatable data instead of only being explained in prose.
