# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:41 UTC

Split `test`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=semantic, COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1, OLLAMA_THINK=false, COURSEBEE_SUPPORT_CHECK=on, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 96.3% | 0.0% | 0.0% | 3.7% |
| multi_hop | 13 | 69.2% | 7.7% | 15.4% | 7.7% |
| numeric | 10 | 90.0% | 0.0% | 0.0% | 10.0% |
| paraphrase | 10 | 70.0% | 20.0% | 0.0% | 10.0% |
| procedure | 8 | 100.0% | 0.0% | 0.0% | 0.0% |
| version_conflict | 7 | 71.4% | 0.0% | 0.0% | 28.6% |
| answerable (all) | 75 | 85.3% | 4.0% | 2.7% | 8.0% |
| unanswerable | 15 | - | - | 6.7% (made up) | 93.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 87.3%
- Stated something wrong (incorrect on any question): 3 / 90 (3.3%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 70 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 77.8% | 18.5% | 0.0% | 3.7% |
| multi_hop | 13 | 53.8% | 30.8% | 7.7% | 7.7% |
| numeric | 10 | 70.0% | 20.0% | 0.0% | 10.0% |
| paraphrase | 10 | 60.0% | 20.0% | 10.0% | 10.0% |
| procedure | 8 | 75.0% | 25.0% | 0.0% | 0.0% |
| version_conflict | 7 | 42.9% | 14.3% | 14.3% | 28.6% |
| answerable (all) | 75 | 66.7% | 21.3% | 4.0% | 8.0% |
| unanswerable | 15 | - | - | 20.0% (made up) | 80.0% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 77.3%
- Stated something wrong (incorrect on any question): 6 / 90 (6.7%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 37 / 57 answers
- Documents shown as sources (all retrieved): precision 0.33 / recall 0.91
- Documents cited by answer sentences: precision 0.76 / recall 0.79
- Answers rewritten by the support check: 6 / 75 answerable, 11 / 15 unanswerable
- End-to-end latency p50 / p95: 3.0 s / 6.0 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
