# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:40 UTC

Split `test`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=lexical, COURSEBEE_EMBEDDING_MODEL=-, OLLAMA_THINK=false, COURSEBEE_SUPPORT_CHECK=on, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 92.6% | 3.7% | 0.0% | 3.7% |
| multi_hop | 13 | 53.8% | 15.4% | 15.4% | 15.4% |
| numeric | 10 | 100.0% | 0.0% | 0.0% | 0.0% |
| paraphrase | 10 | 40.0% | 0.0% | 0.0% | 60.0% |
| procedure | 8 | 87.5% | 12.5% | 0.0% | 0.0% |
| version_conflict | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| answerable (all) | 75 | 80.0% | 5.3% | 2.7% | 12.0% |
| unanswerable | 15 | - | - | 13.3% (made up) | 86.7% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 82.7%
- Stated something wrong (incorrect on any question): 4 / 90 (4.4%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 76 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 81.5% | 11.1% | 3.7% | 3.7% |
| multi_hop | 13 | 53.8% | 23.1% | 7.7% | 15.4% |
| numeric | 10 | 80.0% | 20.0% | 0.0% | 0.0% |
| paraphrase | 10 | 30.0% | 10.0% | 0.0% | 60.0% |
| procedure | 8 | 75.0% | 25.0% | 0.0% | 0.0% |
| version_conflict | 7 | 71.4% | 28.6% | 0.0% | 0.0% |
| answerable (all) | 75 | 68.0% | 17.3% | 2.7% | 12.0% |
| unanswerable | 15 | - | - | 20.0% (made up) | 80.0% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 76.7%
- Stated something wrong (incorrect on any question): 5 / 90 (5.6%)

## Deterministic checks

- Empty answers (nothing retrieved): 1 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 36 / 57 answers
- Documents shown as sources (all retrieved): precision 0.28 / recall 0.83
- Documents cited by answer sentences: precision 0.68 / recall 0.76
- Answers rewritten by the support check: 8 / 75 answerable, 10 / 15 unanswerable
- End-to-end latency p50 / p95: 3.0 s / 4.9 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
