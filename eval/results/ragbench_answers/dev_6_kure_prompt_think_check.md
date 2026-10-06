# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:40 UTC

Split `dev`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=semantic, COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1, OLLAMA_THINK=true, COURSEBEE_SUPPORT_CHECK=on, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 93.9% | 3.0% | 0.0% | 3.0% |
| multi_hop | 7 | 71.4% | 14.3% | 14.3% | 0.0% |
| numeric | 10 | 100.0% | 0.0% | 0.0% | 0.0% |
| paraphrase | 15 | 86.7% | 0.0% | 0.0% | 13.3% |
| procedure | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| version_conflict | 3 | 100.0% | 0.0% | 0.0% | 0.0% |
| answerable (all) | 75 | 92.0% | 2.7% | 1.3% | 4.0% |
| unanswerable | 15 | - | - | 6.7% (made up) | 93.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 93.3%
- Stated something wrong (incorrect on any question): 2 / 90 (2.2%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 77 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 87.9% | 9.1% | 0.0% | 3.0% |
| multi_hop | 7 | 71.4% | 14.3% | 14.3% | 0.0% |
| numeric | 10 | 90.0% | 10.0% | 0.0% | 0.0% |
| paraphrase | 15 | 66.7% | 20.0% | 0.0% | 13.3% |
| procedure | 7 | 71.4% | 28.6% | 0.0% | 0.0% |
| version_conflict | 3 | 0.0% | 66.7% | 33.3% | 0.0% |
| answerable (all) | 75 | 77.3% | 16.0% | 2.7% | 4.0% |
| unanswerable | 15 | - | - | 6.7% (made up) | 93.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 85.3%
- Stated something wrong (incorrect on any question): 3 / 90 (3.3%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 48 / 54 answers
- Documents shown as sources (all retrieved): precision 0.29 / recall 0.98
- Documents cited by answer sentences: precision 0.86 / recall 0.95
- Answers rewritten by the support check: 3 / 75 answerable, 13 / 15 unanswerable
- End-to-end latency p50 / p95: 6.8 s / 11.8 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
