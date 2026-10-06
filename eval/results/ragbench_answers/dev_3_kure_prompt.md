# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:39 UTC

Split `dev`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: COURSEBEE_RETRIEVAL=semantic, COURSEBEE_EMBEDDING_MODEL=nlpai-lab/KURE-v1, OLLAMA_THINK=false, support check not yet implemented, COURSEBEE_TODAY=2026-10-06 (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 97.0% | 3.0% | 0.0% | 0.0% |
| multi_hop | 7 | 85.7% | 0.0% | 14.3% | 0.0% |
| numeric | 10 | 100.0% | 0.0% | 0.0% | 0.0% |
| paraphrase | 15 | 80.0% | 13.3% | 0.0% | 6.7% |
| procedure | 7 | 100.0% | 0.0% | 0.0% | 0.0% |
| version_conflict | 3 | 100.0% | 0.0% | 0.0% | 0.0% |
| answerable (all) | 75 | 93.3% | 4.0% | 1.3% | 1.3% |
| unanswerable | 15 | - | - | 40.0% (made up) | 60.0% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 95.3%
- Stated something wrong (incorrect on any question): 7 / 90 (7.8%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 80 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 90.9% | 9.1% | 0.0% | 0.0% |
| multi_hop | 7 | 71.4% | 14.3% | 14.3% | 0.0% |
| numeric | 10 | 90.0% | 10.0% | 0.0% | 0.0% |
| paraphrase | 15 | 66.7% | 20.0% | 6.7% | 6.7% |
| procedure | 7 | 85.7% | 14.3% | 0.0% | 0.0% |
| version_conflict | 3 | 33.3% | 66.7% | 0.0% | 0.0% |
| answerable (all) | 75 | 81.3% | 14.7% | 2.7% | 1.3% |
| unanswerable | 15 | - | - | 46.7% (made up) | 53.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 88.7%
- Stated something wrong (incorrect on any question): 9 / 90 (10.0%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 45 / 54 answers
- Documents shown as sources (all retrieved): precision 0.29 / recall 0.98
- Documents cited by answer sentences: precision 0.87 / recall 0.88
- Answers rewritten by the support check: 0 / 75 answerable, 0 / 15 unanswerable
- End-to-end latency p50 / p95: 1.2 s / 3.2 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
