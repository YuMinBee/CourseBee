# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:40 UTC

Split `dev`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=semantic, COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1, OLLAMA_THINK=false, COURSEBEE_SUPPORT_CHECK=on, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 97.0% | 3.0% | 0.0% | 0.0% |
| multi_hop | 7 | 71.4% | 14.3% | 14.3% | 0.0% |
| numeric | 10 | 100.0% | 0.0% | 0.0% | 0.0% |
| paraphrase | 15 | 66.7% | 6.7% | 6.7% | 20.0% |
| procedure | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| version_conflict | 3 | 100.0% | 0.0% | 0.0% | 0.0% |
| answerable (all) | 75 | 89.3% | 4.0% | 2.7% | 4.0% |
| unanswerable | 15 | - | - | 13.3% (made up) | 86.7% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 91.3%
- Stated something wrong (incorrect on any question): 4 / 90 (4.4%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 79 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 84.8% | 15.2% | 0.0% | 0.0% |
| multi_hop | 7 | 71.4% | 14.3% | 14.3% | 0.0% |
| numeric | 10 | 90.0% | 10.0% | 0.0% | 0.0% |
| paraphrase | 15 | 66.7% | 0.0% | 13.3% | 20.0% |
| procedure | 7 | 85.7% | 14.3% | 0.0% | 0.0% |
| version_conflict | 3 | 33.3% | 66.7% | 0.0% | 0.0% |
| answerable (all) | 75 | 78.7% | 13.3% | 4.0% | 4.0% |
| unanswerable | 15 | - | - | 13.3% (made up) | 86.7% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 85.3%
- Stated something wrong (incorrect on any question): 5 / 90 (5.6%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 44 / 54 answers
- Documents shown as sources (all retrieved): precision 0.29 / recall 0.98
- Documents cited by answer sentences: precision 0.86 / recall 0.84
- Answers rewritten by the support check: 3 / 75 answerable, 13 / 15 unanswerable
- End-to-end latency p50 / p95: 3.0 s / 4.9 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
