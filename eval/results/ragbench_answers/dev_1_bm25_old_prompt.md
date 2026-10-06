# CourseBee RAG Benchmark — Answers

Generated: 2026-10-06 14:43:39 UTC

Split `dev`, retrieval mode `vector` (top_k=5), generator `qwen3:14b`, judge `qwen3:14b`.

Config: Kiwi BM25 with the v3 answer prompt (before the grounded prompt), OLLAMA_THINK=false, no support check (qwen judge re-run with the corrected rubric)

## Blind review (Claude)

Answers from every compared run were shuffled together and graded without run names.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 87.9% | 9.1% | 0.0% | 3.0% |
| multi_hop | 7 | 28.6% | 14.3% | 57.1% | 0.0% |
| numeric | 10 | 80.0% | 0.0% | 0.0% | 20.0% |
| paraphrase | 15 | 20.0% | 6.7% | 46.7% | 26.7% |
| procedure | 7 | 71.4% | 14.3% | 14.3% | 0.0% |
| version_conflict | 3 | 100.0% | 0.0% | 0.0% | 0.0% |
| answerable (all) | 75 | 66.7% | 8.0% | 16.0% | 9.3% |
| unanswerable | 15 | - | - | 53.3% (made up) | 46.7% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 70.7%
- Stated something wrong (incorrect on any question): 20 / 90 (22.2%)

## LLM judge (`qwen3:14b`)

Agrees with the blind review on 73 / 90 answers.

| Type | n | Correct | Partial | Incorrect | Abstained |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 33 | 90.9% | 6.1% | 3.0% | 0.0% |
| multi_hop | 7 | 28.6% | 42.9% | 28.6% | 0.0% |
| numeric | 10 | 80.0% | 0.0% | 10.0% | 10.0% |
| paraphrase | 15 | 20.0% | 6.7% | 60.0% | 13.3% |
| procedure | 7 | 57.1% | 28.6% | 14.3% | 0.0% |
| version_conflict | 3 | 33.3% | 33.3% | 33.3% | 0.0% |
| answerable (all) | 75 | 64.0% | 12.0% | 20.0% | 4.0% |
| unanswerable | 15 | - | - | 66.7% (made up) | 33.3% (correct) |

- Answer score (correct + 0.5 x partial) on answerable questions: 70.0%
- Stated something wrong (incorrect on any question): 25 / 90 (27.8%)

## Deterministic checks

- Empty answers (nothing retrieved): 0 / 75 answerable, 0 / 15 unanswerable
- Every reference number/unit present in the answer: 33 / 54 answers
- Documents shown as sources (all retrieved): precision 0.23 / recall 0.83
- Documents cited by answer sentences: precision 0.69 / recall 0.69
- Answers rewritten by the support check: 0 / 75 answerable, 0 / 15 unanswerable
- End-to-end latency p50 / p95: 1.4 s / 2.6 s

Verdicts come from LLMs; see the per-question JSON for their reasons.
