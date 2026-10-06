# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:41 UTC

Split `test`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=semantic, COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1, OLLAMA_THINK=true, COURSEBEE_SUPPORT_CHECK=on, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 85.2% | 11.1% | 0.0% | 3.7% |
| multi_hop | 13 | 61.5% | 15.4% | 7.7% | 15.4% |
| numeric | 10 | 90.0% | 0.0% | 0.0% | 10.0% |
| paraphrase | 10 | 70.0% | 0.0% | 0.0% | 30.0% |
| procedure | 8 | 100.0% | 0.0% | 0.0% | 0.0% |
| version_conflict | 7 | 71.4% | 0.0% | 0.0% | 28.6% |
| answerable (all) | 75 | 80.0% | 6.7% | 1.3% | 12.0% |
| unanswerable | 15 | - | - | 6.7% (made up) | 93.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 83.3%
- Stated something wrong (incorrect on any question): 2 / 90 (2.2%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 72 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 77.8% | 14.8% | 3.7% | 3.7% |
| multi_hop | 13 | 53.8% | 23.1% | 7.7% | 15.4% |
| numeric | 10 | 80.0% | 10.0% | 0.0% | 10.0% |
| paraphrase | 10 | 50.0% | 20.0% | 0.0% | 30.0% |
| procedure | 8 | 75.0% | 25.0% | 0.0% | 0.0% |
| version_conflict | 7 | 28.6% | 42.9% | 0.0% | 28.6% |
| answerable (all) | 75 | 65.3% | 20.0% | 2.7% | 12.0% |
| unanswerable | 15 | - | - | 13.3% (made up) | 86.7% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 75.3%
- Stated something wrong (incorrect on any question): 4 / 90 (4.4%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 38 / 57 answers
- Documents shown as sources (all retrieved): precision 0.33 / recall 0.91
- Documents cited by answer sentences: precision 0.70 / recall 0.85
- Answers rewritten by the support check: 9 / 75 answerable, 11 / 15 unanswerable
- End-to-end latency p50 / p95: 7.5 s / 12.0 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
