# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:39 UTC

Split `dev`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=lexical, OLLAMA_THINK=false, support check not yet implemented, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 93.9% | 3.0% | 0.0% | 3.0% |
| multi_hop | 7 | 14.3% | 28.6% | 57.1% | 0.0% |
| numeric | 10 | 90.0% | 0.0% | 0.0% | 10.0% |
| paraphrase | 15 | 33.3% | 0.0% | 13.3% | 53.3% |
| procedure | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| version_conflict | 3 | 100.0% | 0.0% | 0.0% | 0.0% |
| answerable (all) | 75 | 74.7% | 4.0% | 8.0% | 13.3% |
| unanswerable | 15 | - | - | 33.3% (made up) | 66.7% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 76.7%
- Stated something wrong (incorrect on any question): 11 / 90 (12.2%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 70 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 84.8% | 9.1% | 3.0% | 3.0% |
| multi_hop | 7 | 14.3% | 57.1% | 28.6% | 0.0% |
| numeric | 10 | 80.0% | 10.0% | 0.0% | 10.0% |
| paraphrase | 15 | 20.0% | 13.3% | 53.3% | 13.3% |
| procedure | 7 | 85.7% | 14.3% | 0.0% | 0.0% |
| version_conflict | 3 | 33.3% | 66.7% | 0.0% | 0.0% |
| answerable (all) | 75 | 62.7% | 17.3% | 14.7% | 5.3% |
| unanswerable | 15 | - | - | 26.7% (made up) | 73.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 71.3%
- Stated something wrong (incorrect on any question): 15 / 90 (16.7%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 31 / 54 answers
- Documents shown as sources (all retrieved): precision 0.23 / recall 0.83
- Documents cited by answer sentences: precision 0.86 / recall 0.73
- Answers rewritten by the support check: 0 / 75 answerable, 0 / 15 unanswerable
- End-to-end latency p50 / p95: 1.0 s / 2.6 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
