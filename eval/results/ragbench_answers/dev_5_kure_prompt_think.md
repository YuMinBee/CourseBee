# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:40 UTC

Split `dev`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=semantic, COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1, OLLAMA_THINK=true, COURSEBEE_SUPPORT_CHECK=off, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 100.0% | 0.0% | 0.0% | 0.0% |
| multi_hop | 7 | 85.7% | 0.0% | 14.3% | 0.0% |
| numeric | 10 | 100.0% | 0.0% | 0.0% | 0.0% |
| paraphrase | 15 | 86.7% | 0.0% | 0.0% | 13.3% |
| procedure | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| version_conflict | 3 | 100.0% | 0.0% | 0.0% | 0.0% |
| answerable (all) | 75 | 96.0% | 0.0% | 1.3% | 2.7% |
| unanswerable | 15 | - | - | 20.0% (made up) | 80.0% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 96.0%
- Stated something wrong (incorrect on any question): 4 / 90 (4.4%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 75 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 87.9% | 9.1% | 3.0% | 0.0% |
| multi_hop | 7 | 71.4% | 14.3% | 14.3% | 0.0% |
| numeric | 10 | 100.0% | 0.0% | 0.0% | 0.0% |
| paraphrase | 15 | 60.0% | 26.7% | 6.7% | 6.7% |
| procedure | 7 | 71.4% | 28.6% | 0.0% | 0.0% |
| version_conflict | 3 | 33.3% | 33.3% | 33.3% | 0.0% |
| answerable (all) | 75 | 78.7% | 14.7% | 5.3% | 1.3% |
| unanswerable | 15 | - | - | 26.7% (made up) | 73.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 86.0%
- Stated something wrong (incorrect on any question): 8 / 90 (8.9%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 50 / 54 answers
- Documents shown as sources (all retrieved): precision 0.29 / recall 0.98
- Documents cited by answer sentences: precision 0.94 / recall 0.95
- Answers rewritten by the support check: 0 / 75 answerable, 0 / 15 unanswerable
- End-to-end latency p50 / p95: 4.8 s / 9.0 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
